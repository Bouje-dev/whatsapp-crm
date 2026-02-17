# your_app/views.py
"""
يوفر:
- endpoint لالتقاط الزيارة (capture_visit) - يستقبل raw_phone + utm's عبر POST.
- endpoint لبدء تحديث يدوي (manual_sync) - مؤمن بواسطة HEADER SECRET_TOKEN أو تسجيل دخول الموظف.
"""
from django.core.paginator import Paginator

from django.template import Context, Template
import json
import os
import logging
import re
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from discount.models import CampaignVisit, ExternalOrder ,ScriptFlow  , ExternalTokenmodel , CustomUser
from discount.activites import log_activity
from .utils import normalize_phone, find_best_visit_for_phone

def _get_default_channel_id(user):
    try:
        from discount.whatssapAPI.views import get_target_channel
        ch = get_target_channel(user, None)
        return ch.id if ch else None
    except Exception:
        return None
from .services import fetch_orders_from_cod, fetch_tracking_status_from_carrier
from .services import fetch_and_update_order_cod
logger = logging.getLogger(__name__)
from django.views.decorators.cache import cache_page
MANUAL_SYNC_SECRET = os.environ.get('MANUAL_SYNC_SECRET', 'set_this_secret')  # ضع SECRET في ENV



TRACKER_SCRIPT_TEMPLATE = """
(function() {
    // --- CONFIGURATION ---
    const CFG = {{safeCfg}}; 
    
   
    const STORAGE_KEYS = {
        VISITOR_ID: '__st_vid', ATTR_DATA: '__st_attr_data', SESSION_START: '__st_sess_start' 
    };

    // --- 1. HELPER: USER IDENTITY ---
    function getVisitorId() {
        let vid = localStorage.getItem(STORAGE_KEYS.VISITOR_ID);
        if (!vid) {
            vid = 'v_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now().toString(36);
            localStorage.setItem(STORAGE_KEYS.VISITOR_ID, vid);
            localStorage.setItem(STORAGE_KEYS.SESSION_START, new Date().toISOString());
        }
        return vid;
    }

    // --- 2. HELPER: ATTRIBUTION   ---
    function resolveAttribution() {
        const urlParams = new URLSearchParams(window.location.search);
        const currentData = {
            campaign_id: urlParams.get('campaign_id') || urlParams.get('utm_campaign'),
            adset_id: urlParams.get('adset_id'),
            ad_id: urlParams.get('ad_id') || urlParams.get('utm_content'),
            placement: urlParams.get('placement'),
            source: urlParams.get('utm_source') || urlParams.get('source'),
            medium: urlParams.get('utm_medium') || urlParams.get('placement'),
            click_id: urlParams.get('fbclid') || urlParams.get('ttclid') || urlParams.get('gclid') || null,
            ts: Date.now(),
            product_name: document.title 
        };
        Object.keys(currentData).forEach(key => currentData[key] === null && delete currentData[key]);

        if (Object.keys(currentData).length > 1) {
            localStorage.setItem(STORAGE_KEYS.ATTR_DATA, JSON.stringify(currentData));
            return currentData;
        } else {
            try { return JSON.parse(localStorage.getItem(STORAGE_KEYS.ATTR_DATA)) || {}; } catch (e) { return {}; }
        }
    }

    // --- 3. HELPER: SEND DATA ---
    function buildCapturePayload(extra) {
        const attr = resolveAttribution();
        return Object.assign({
            visitorId: getVisitorId(),
            flow_id: CFG.flow_id,
            // flow_api_key: CFG.flow_api_key, 
            url: window.location.href,
            referrer: document.referrer || '',
            utm_campaign: attr.campaign_id || attr.utm_campaign || '',
            utm_source: attr.source || '',
            utm_medium: attr.medium || attr.placement || '',
            ad_id: attr.ad_id || '',
            product_name: attr.product_name || '',
            device: /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop'
        }, extra || {});
    }

    function sendData(extraPayload) {
        // استخدم رابط API الخاص بك هنا
        const url = CFG.endpoint || "http://127.0.0.1:8000/discount/marketing/api/capture-visit/";
        if (!url) return;
        
        const fullPayload = buildCapturePayload(extraPayload);
        const blob = new Blob([JSON.stringify(fullPayload)], {type: 'application/json'});
        
        // استخدام sendBeacon لضمان الوصول حتى لو أغلقت الصفحة
        if (navigator.sendBeacon) {
            navigator.sendBeacon(url, blob);
        } else {
            fetch(url, {
                method: 'POST',
                body: blob,
                keepalive: true,
                headers: {'Content-Type': 'application/json'}
            }).catch(function() {});
        }
    }

    // --- 4. THE INTELLIGENT SCRAPER (الجديد) ---
    // هذه الدالة تبحث عن الحقول بناءً على اسمائها الشائعة
    function scrapeFormData(formElement) {
        const data = {};
        const inputs = formElement.querySelectorAll('input, select, textarea');
        
        // قاموس الأنماط (Regex Patterns) للتعرف على الحقول
        const patterns = {
            name: /name|nom|full|first|last|fname|lname|user/i,
            address: /addr|street|city|ville|state|region|zip|post|country|pays/i,
            phone: /phone|tel|mobile|whatsapp/i,
            product: /product|produit|item|variant|sku/i,
            quantity: /qty|quantity|quantite/i,
            price: /price|prix|total/i,
            notes: /note|message|comment/i
        };

        inputs.forEach(input => {
            const name = input.name || input.id || '';
            const val = input.value;
            
            // تجاهل الحقول المخفية الفارغة أو أزرار الإرسال
            if ((input.type === 'hidden' && !val) || input.type === 'submit') return;
            if (input.type === 'radio' && !input.checked) return;
            if (input.type === 'checkbox' && !input.checked) return;

            // التحقق من نوع الحقل
            for (const key in patterns) {
                if (patterns[key].test(name)) {
                    // إذا وجدنا تطابقاً، نخزن القيمة
                    // نقوم بدمج البيانات: data['customer_name'] = ...
                    if (!data[key]) data[key] = val; 
                    else data[key] += ' ' + val; // في حالة الاسم الأول + الاسم الثاني
                }
            }
            
            // نخزن كل البيانات الخام أيضاً للاحتياط
            if(name && val) data['raw_' + name] = val;
        });

        return data;
    }

    // --- 5. SUBMIT LISTENER ---
    // نراقب أي محاولة لإرسال فورم
    function initFormListener() {
        document.addEventListener('submit', function(e) {
        e.preventDefault();
            const form = e.target;
            // التحقق هل الفورم يحتوي على حقل هاتف؟ (للتأكد أنه فورم طلب وليس بحث)
            const hasPhone = form.querySelector('input[name*="phone"], input[type="tel"]');
            
            if (hasPhone) {
                const formData = scrapeFormData(form);
                sendData({
                    event: 'initiate_checkout', // أو purchase_attempt
                    form_data: formData
                });
            }
        }, {capture: true}); // capture: true لالتقاط الحدث قبل أن يوقفه المتجر
    }

    // --- 6. PAGE & PHONE TRACKING ---
    function trackPageView() {
        const startTime = Date.now();
        sendData({ event: 'page_view' });
        window.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'hidden') {
                sendData({ event: 'page_leave', time_spent: (Date.now() - startTime) / 1000 });
            }
        });
    }

    function initPhoneCapture() {
        var inputs = document.querySelectorAll('input[name*="phone"], input[type="tel"], input[name*="mobile"]');
        inputs.forEach(function(input) {
            input.addEventListener('blur', function(e) {
                var val = (e.target.value || '').replace(/[^0-9+]/g, '');
                if (val.length >= 8) {
                    var lastSent = sessionStorage.getItem('__st_last_phone');
                    if (lastSent !== val) {
                        sendData({ raw_phone: val, event: 'lead_capture' });
                        sessionStorage.setItem('__st_last_phone', val);
                    }
                }
            });
        });
    }

    // --- INIT ---
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            trackPageView();
            initPhoneCapture();
            initFormListener(); // تشغيل مراقب الفورم
        });
    } else {
        trackPageView();
        initPhoneCapture();
        initFormListener();
    }

})();
"""

@cache_page(60 * 15) 
def serve_tracker_js(request):
    from urllib.parse import urlparse
    # Support store_id (legacy), id, or token
    token = request.GET.get('store_id') or request.GET.get('id') or request.GET.get('token')
    if not token:
        return HttpResponse("// Missing token (use ?store_id= or ?id= or ?token=)", content_type="application/javascript", status=400)

    # 1. Look up flow by api_key, then id, then token (UUID)
    flow = None
    try:
        flow = ScriptFlow.objects.get(api_key=token, active=True, is_active=True)
    except ScriptFlow.DoesNotExist:
        try:
            flow = ScriptFlow.objects.get(id=token, active=True, is_active=True)
        except (ScriptFlow.DoesNotExist, ValueError, ValidationError):
            try:
                flow = ScriptFlow.objects.get(token=token, active=True, is_active=True)
            except (ScriptFlow.DoesNotExist, ValueError, ValidationError):
                return HttpResponse("// Invalid or inactive flow", content_type="application/javascript", status=404)

    # 2. Check owner account is active
    if flow.owner and not getattr(flow.owner, 'is_active', True):
        return HttpResponse("// Account inactive", content_type="application/javascript", status=403)

    # 3. Validate origin against allowed_domains (if set)
    allowed = flow.allowed_domains_list()
    if allowed:
        origin = request.META.get('HTTP_ORIGIN') or request.META.get('HTTP_REFERER') or ''
        try:
            host = (urlparse(origin).hostname or '').lower()
        except Exception:
            host = ''
        if not host or host not in allowed:
            return HttpResponse("// Origin not allowed", content_type="application/javascript", status=403)

    # 4. Build config and render script (same as serve_tracker_by_id)
    config = dict(flow.config or {})
    config['flow_id'] = str(flow.id)
    config['flow_api_key'] = flow.api_key
    config['captureEndpoint'] = request.build_absolute_uri('/discount/marketing/api/capture-visit/')
    rendered_js = _build_flow_script(config)

    response = HttpResponse(rendered_js, content_type="application/javascript")
    response['Access-Control-Allow-Origin'] = '*'
    return response


 
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .utils import normalize_phone
from django.contrib.auth import get_user_model

User = get_user_model()



# your_app/views.py
import json, secrets
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required


def _build_flow_script(config):
    """Build full inline tracker script from config (used when serving tracker.js by id)."""
    from django.template import Context, Template
    from django.utils.safestring import mark_safe
    cfg_str = json.dumps(config, ensure_ascii=False)
    cfg_str = cfg_str.replace('<', '\\u003c').replace('>', '\\u003e')
    # Mark safe so Django does not HTML-escape the JSON (would turn " into &quot; and break JS)
    tpl = Template(TRACKER_SCRIPT_TEMPLATE)
    return tpl.render(Context({'safeCfg': mark_safe(cfg_str)}))


def _build_loader_snippet(tracker_url, token):
    """Build the loader script snippet to embed on site. Example:
    <script>
    !function(w,d,t,u,k){...}(window,document,'script','TRACKER_URL','TOKEN');
    </script>
    Literal braces in the string must be doubled ({{ }}) so .format() does not treat them as placeholders.
    """
    loader = (
        "<script>\n"
        "!function(w,d,t,u,k){{\n"
        "  var f=d.getElementsByTagName(t)[0],j=d.createElement(t);\n"
        "  j.async=true; j.src=u+'?id='+k; f.parentNode.insertBefore(j,f);\n"
        "}}(window,document,'script','{tracker_url}','{token}');\n"
        "</script>"
    )
    return loader.format(tracker_url=tracker_url.rstrip('/'), token=token)


def serve_tracker_by_id(request):
    """Serve the full tracker JS for a flow. GET ?id=flow_id or ?id=api_key."""
    token = request.GET.get('id') or request.GET.get('token')
    if not token:
        return HttpResponse("// Missing id parameter", content_type="application/javascript", status=400)
    try:
        flow = ScriptFlow.objects.get(api_key=token, active=True)
    except ScriptFlow.DoesNotExist:
        try:
            flow = ScriptFlow.objects.get(id=token, active=True)
        except (ScriptFlow.DoesNotExist, ValueError, ValidationError):
            return HttpResponse("// Invalid or inactive flow", content_type="application/javascript", status=404)
    config = dict(flow.config or {})
    config['flow_id'] = str(flow.id)
    config['flow_api_key'] = flow.api_key
    config['captureEndpoint'] = request.build_absolute_uri('/discount/marketing/api/capture-visit/')
    script = _build_flow_script(config)
    response = HttpResponse(script, content_type="application/javascript")
    response['Access-Control-Allow-Origin'] = '*'
    return response


def _sanitize_flow_input(value, max_len=200, strip_html=True):
    """Sanitize string input: strip HTML/script, limit length. Returns str."""
    if value is None:
        return ''
    s = str(value).strip()
    if strip_html:
        import re
        s = re.sub(r'<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>', '', s, flags=re.I)
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'javascript:', '', s, flags=re.I)
        s = re.sub(r'on\w+\s*=', '', s, flags=re.I)
    s = s[:max_len]
    return s


@login_required
@require_POST
def create_flow(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'invalid_json'}, status=400)

    name = _sanitize_flow_input(body.get('name'), max_len=200)
    allowed_domains = _sanitize_flow_input(body.get('allowed_domains'), max_len=1000)
    allowed_domains_normalized = ','.join(d.strip() for d in allowed_domains.split(',') if d.strip())
    raw_config = body.get('config') or {}
    config = dict(raw_config) if isinstance(raw_config, dict) else {}
    config['description'] = _sanitize_flow_input(config.get('description'), max_len=2000)
    config['blockRepeat'] = bool(config.get('blockRepeat'))

    # Duplicate check: same owner, same name and normalized allowed_domains
    for existing in ScriptFlow.objects.filter(owner=request.user):
        existing_domains = ','.join(d.strip() for d in (existing.allowed_domains or '').split(',') if d.strip())
        if (existing.name or '').strip().lower() == (name or '').strip().lower() and existing_domains == allowed_domains_normalized:
            return JsonResponse({
                'error': 'A flow with this name and allowed domains already exists.',
                'flow_id': str(existing.id),
            }, status=409)

    api_key = secrets.token_urlsafe(32)

    flow = ScriptFlow.objects.create(
        owner=request.user,
        name=name,
        api_key=api_key,
        allowed_domains=allowed_domains,
        config=config,
        active=True,
        script=None,
    )

    # Generate loader snippet: embed script that loads tracker.js?id=api_key
    tracker_url = request.build_absolute_uri('/discount/marketing/tracker.js')
    generated_script = _build_loader_snippet(tracker_url, api_key)
    flow.script = generated_script
    flow.save(update_fields=['script'])

    log_activity('campaign_flow_created', f"Campaign flow '{name}' created (domains: {allowed_domains})", request=request, related_object=flow)
    return JsonResponse({
        'status': True,
        'flow_id': str(flow.id),
        'api_key': api_key,
        'created_at': flow.created_at.isoformat(),
        'script': generated_script,
    }, status=201)

def list_flows(request):
    from django.db.models import Count
    qs = ScriptFlow.objects.filter(owner=request.user).annotate(
        visits_count=Count('visits')
    ).order_by('-created_at')
    data = []
    for f in qs:
        data.append({
            'flow_id': str(f.id),
            'name': f.name,
            'allowed_domains': f.allowed_domains,
            'createdAt': f.created_at.isoformat(),
            'active': f.active,
            'script': f.script or '',
            'config': f.config or {},
            'visits_count': getattr(f, 'visits_count', 0),
        })
    return JsonResponse({'status': True, 'flows': data})

from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.views.decorators.http import require_http_methods

@login_required
@require_http_methods(['PATCH', 'DELETE'])
def flow_detail(request, flow_id):
    flow = get_object_or_404(ScriptFlow, id=flow_id, owner=request.user)

    if request.method == 'DELETE':
        log_activity('campaign_flow_deleted', f"Campaign flow '{flow.name}' deleted", request=request)
        flow.delete()
        return JsonResponse({'status': True})

    # PATCH: partial update
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'invalid_json'}, status=400)

    # allowed updates: name, active, script, config, allowed_domains
    if 'name' in body: flow.name = body['name'][:200]
    if 'active' in body: flow.active = bool(body['active'])
    if 'script' in body: flow.script = body['script']
    if 'config' in body: flow.config = body['config']
    if 'allowed_domains' in body: flow.allowed_domains = body['allowed_domains']
    flow.save()
    return JsonResponse({'status': True})
 


 # your_app/views.py (add or modify capture_visit)
from django.shortcuts import get_object_or_404
from urllib.parse import urlparse, parse_qs


def _product_name_from_url(url_string):
    """Parse product_name or product or p from URL query string."""
    if not url_string or not isinstance(url_string, str):
        return ''
    try:
        parsed = urlparse(url_string)
        qs = parse_qs(parsed.query)
        for key in ('product_name', 'product', 'p', 'utm_content'):
            val = qs.get(key) or []
            if val and str(val[0]).strip():
                return str(val[0]).strip()[:255]
    except Exception:
        pass
    return ''


def _get_form_data(body):
    """Return form_data dict from body. Handles form_data as object or JSON string."""
    if not isinstance(body, dict):
        return {}
    fd = body.get('form_data')
    if isinstance(fd, dict):
        return fd
    if isinstance(fd, str):
        try:
            return json.loads(fd)
        except Exception:
            return {}
    return {}


def _sanitize_text(value, max_length=None):
    """
    Sanitize user input before save: strip whitespace, remove HTML/script (XSS),
    enforce max length. Returns plain text safe for storage.
    """
    if value is None:
        return ''
    s = str(value).strip()
    if not s:
        return ''
    # Remove HTML tags
    s = re.sub(r'<[^>]*>', '', s)
    # Remove javascript: and data: URL schemes (XSS vectors)
    s = re.sub(r'(?i)javascript\s*:', '', s)
    s = re.sub(r'(?i)vbscript\s*:', '', s)
    s = re.sub(r'(?i)data\s*:\s*[^,\s]*', '', s)
    # Collapse multiple spaces
    s = re.sub(r'\s+', ' ', s).strip()
    if max_length is not None:
        s = s[:max_length]
    return s


def _sanitize_dict_strings(obj, max_str_len=5000):
    """Recursively sanitize string values in dict/list (e.g. client_data) to prevent XSS in stored JSON."""
    if isinstance(obj, dict):
        return {k: _sanitize_dict_strings(v, max_str_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_dict_strings(i, max_str_len) for i in obj]
    if isinstance(obj, str):
        return _sanitize_text(obj, max_length=max_str_len)
    return obj


def _save_customer_data_to_order(visit, flow, body, phone_normalized, utm_campaign, utm_source, ad_id):
    """
    When capture_visit receives data (phone, name, address, product_name, url, device, event, etc.),
    create or update an Order in the orders app and store full client/visit data.
    Payload may have top-level keys or nested body['form_data'] (dict or JSON string).
    """
    try:
        from orders.models import Order, Attribution, Store
    except ImportError:
        return
    body = body if isinstance(body, dict) else {}
    form_data = body.get('form_data') or body
    form_data = form_data if isinstance(form_data, dict) else {}
    utm_campaign = _sanitize_text(utm_campaign, 255)
    utm_source = _sanitize_text(utm_source, 255)
    ad_id = _sanitize_text(ad_id, 255)

    # Fixed keys: read from form_data then body, then sanitize (XSS + length)
    def _get(key, max_len=None):
        raw = form_data.get(key) or body.get(key)
        
        return _sanitize_text(raw, max_length=max_len)

    name = _get('name', 255) or _get('raw_name', 255) or _get('customer_name', 255) or form_data.get('name') or form_data.get('raw_name') or form_data.get('customer_name')
    address = _get('address', 2000) or _get('customer_address', 2000) or _get('address_line', 2000) or form_data.get('address') or form_data.get('customer_address') or form_data.get('address_line')
    if not address:
        parts = [
            _get('raw_address', 500),
            _get('raw_city', 200),
            _get('raw_country', 200),
            _get('raw_zip', 50),
        ]
        address = ' '.join(p for p in parts if p).strip()[:2000]
    product_name = _get('product_name', 255) or _get('product', 255)
    if not product_name:
        url_or_ref = _get('url', 2048) or _get('referrer', 2048)
        product_name = _product_name_from_url(url_or_ref) if url_or_ref else ''
    raw_phone = _get('raw_phone', 32) or _get('phone', 32)
    phone = (phone_normalized or raw_phone or '').strip()[:32]

    # Only create/update Order when we have at least a phone number. This prevents a second
    # request (e.g. visit beacon with no form data) from overwriting client info with placeholders.
    has_client_phone = bool(phone and phone != '—')
    if not has_client_phone:
        return

    owner = getattr(flow, 'owner', None)
    if not owner:
        return
    store, _ = Store.objects.get_or_create(owner=owner, defaults={'name': 'Default Store'})
    attribution, _ = Attribution.objects.get_or_create(
        campaign_visit=visit,
        defaults={'utm_campaign': utm_campaign, 'utm_source': utm_source, 'ad_id': ad_id or ''}
    )
    if not attribution.utm_campaign and utm_campaign:
        attribution.utm_campaign = utm_campaign
    if not attribution.utm_source and utm_source:
        attribution.utm_source = utm_source
    if not attribution.ad_id and ad_id:
        attribution.ad_id = ad_id or ''
    attribution.save()
    # Full payload for client_data — sanitize string values to prevent XSS in stored JSON
    client_data = _sanitize_dict_strings(dict(body)) if body else {}
    order_obj, created = Order.objects.update_or_create(
        attribution_data=attribution,
        defaults={
            'name': name or '—',
            'phone': phone,
            'address': address,
            'product_name': product_name or '—',
            'store': store,
            'client_data': client_data,
        }
    )
    if created:
        log_activity('order_created', f"Order created from landing: {phone}, product: {product_name}", related_object=order_obj)













def _cors_headers(response):
    """Add CORS headers so tracker.js on landing pages can call this API."""
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, X-FLOW-API-KEY'
    return response


@csrf_exempt
@require_http_methods(['POST', 'OPTIONS'])
def capture_visit(request):
    # CORS preflight: allow browser to send POST from tracker on other domains
    if request.method == 'OPTIONS':
        response = JsonResponse({'status': 'ok'})
        return _cors_headers(response)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        response = JsonResponse({'error': 'invalid_json'}, status=400)
        return _cors_headers(response)

    region = request.GET.get('utm_region') or 'SA'
    fd = _get_form_data(body)
    raw_phone = body.get('raw_phone') or fd.get('raw_phone') or fd.get('phone') or body.get('phone') or ''
    product_name = body.get('product_name') or fd.get('product_name') or ''
    utm_campaign = body.get('utm_campaign') or body.get('utm_campaign_id') or fd.get('utm_campaign') or ''
    utm_source = body.get('utm_source') or fd.get('utm_source') or ''
    utm_medium = body.get('utm_medium') or fd.get('utm_medium') or ''
    ad_id = body.get('ad_id') or fd.get('ad_id') or ''
    site_source_name = body.get('site_source_name') or fd.get('site_source_name') or ''
    ad_adset_name = body.get('ad_adset_name') or body.get('ad_adset') or body.get('ad_name') or fd.get('ad_adset_name') or ''
    flow_id = body.get('flow_id')
    supplied_api_key = body.get('flow_api_key') or request.META.get('HTTP_X_FLOW_API_KEY') or request.headers.get('X-FLOW-API-KEY')
    visitorId = body.get('visitorId') or body.get('visitor_id') or fd.get('visitorId') or fd.get('visitor_id')

    if not visitorId:
        response = JsonResponse({'error': 'missing_visitorId'}, status=400)
        return _cors_headers(response)
    if not flow_id:
        response = JsonResponse({'error': 'missing_flow_id'}, status=400)
        return _cors_headers(response)

    try:
        flow = ScriptFlow.objects.get(id=flow_id, active=True)
    except (ScriptFlow.DoesNotExist, ValueError, ValidationError):
        response = JsonResponse({'error': 'invalid_flow'}, status=404)
        return _cors_headers(response)

    # Verify request is from tracker: require api_key (sent by tracker.js) or origin in allowed_domains
    if supplied_api_key:
        if supplied_api_key != flow.api_key:
            response = JsonResponse({'error': 'invalid_api_key'}, status=403)
            return _cors_headers(response)
    else:
        origin = request.META.get('HTTP_ORIGIN') or request.META.get('HTTP_REFERER') or ''
        try:
            host = (urlparse(origin).hostname or '').lower()
            print("host", host)
        except Exception:
            host = ''
        allowed = flow.allowed_domains_list()
        if not allowed:
            response = JsonResponse({'error': 'origin_not_allowed'}, status=403)
            return _cors_headers(response)
        if not host or host not in allowed:
            response = JsonResponse({'error': 'origin_not_allowed'}, status=403)
            return _cors_headers(response)
        


    # Normalize phone
    phone_norm = normalize_phone(raw_phone, region ) if raw_phone else None


    existing = CampaignVisit.objects.filter(
    visit_id=visitorId,
    flow=flow,
    utm_campaign=utm_campaign,
    created_at__gte=timezone.now()-timedelta(seconds=30)
                ).first()

    if existing:
        if hasattr(existing, 'visit_meta'):
            existing.visit_meta = dict(body) if isinstance(body, dict) else {}
            existing.save(update_fields=['visit_meta'])
        _save_customer_data_to_order(existing, flow, body, phone_norm, utm_campaign, utm_source, ad_id)
        response = JsonResponse({
            'status': True,
            'visit_id': str(existing.id),
            'phone_normalized': phone_norm,
            'duplicate': True
        }, status=200)
        return _cors_headers(response)

    defaults_data = {
        'user': flow.owner if flow else None,
        'flow': flow,
        'raw_phone': raw_phone,
        'phone_normalized': phone_norm,
        'utm_campaign': utm_campaign,
        'utm_source': utm_source,
        'utm_medium': utm_medium,
        'ad_id': ad_id,
        'site_source_name': site_source_name,
        'ad_adset_name': ad_adset_name,
        'visit_meta': dict(body) if isinstance(body, dict) else {},
    }

    visit, created = CampaignVisit.objects.update_or_create(
        visit_id=visitorId,
        defaults=defaults_data
    )

    _save_customer_data_to_order(visit, flow, body, phone_norm, utm_campaign, utm_source, ad_id)

    response = JsonResponse({
        'status': True,
        'visit_id': str(visit.id),
        'phone_normalized': phone_norm,
    }, status=201)
    return _cors_headers(response)




@csrf_exempt
def manual_sync(request):
    """
    نقطة نهاية تبدا عملية جلب من COD ومطابقة.
    محمية بواسطة ترويسة بسيطة 'X-MANUAL-SYNC-TOKEN' يجب وضعها في ENV.
    ترجع عدد الطلبيات المعالجة.
    """
    # تحقق من توكن بسيط
    token = request.headers.get('X-MANUAL-SYNC-TOKEN') or request.GET.get('token')
    if token != MANUAL_SYNC_SECRET:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    try:
        # يمكنك تمرير منذ param لتقييد المزامنة
        since_param = request.GET.get('since')
        since = None
        if since_param:
            try:
                since = timezone.datetime.fromisoformat(since_param)
                since = timezone.make_aware(since, timezone.utc)
            except Exception:
                since = None

        cod_orders = fetch_orders_from_cod(since=since, limit=200)
        processed = 0
        for od in cod_orders:
            try:
                ext_id = od.get('id') or od.get('order_id') or od.get('external_id')
                raw_phone = od.get('recipient_phone') or od.get('phone') or od.get('customer_phone') or ''
                phone_norm = normalize_phone(raw_phone) or ''
                created_at_raw = od.get('created_at') or od.get('createdAt')
                created_at = timezone.now()
                try:
                    if created_at_raw:
                        created_at = timezone.datetime.fromisoformat(created_at_raw.replace('Z','+00:00'))
                        created_at = timezone.make_aware(created_at, timezone.utc)
                except Exception:
                    created_at = timezone.now()

                # حفظ / تحديث ExternalOrder
                obj, created = ExternalOrder.objects.update_or_create(
                    external_order_id=str(ext_id),
                    defaults={
                        'platform': 'cod',
                        'order_ref': od.get('order_ref') or od.get('reference'),
                        'raw_phone': raw_phone,
                        'phone_normalized': phone_norm,
                        'customer_name': od.get('recipient_name') or od.get('customer_name') or '',
                        'status': od.get('status') or 'unknown',
                        'created_at': created_at,
                        'meta': od
                    }
                )

                # مطالبة بشركات الشحن المباشرة إن وُجد رقم تتبع داخل od (مثال الحقل)
                tracking_num = od.get('tracking_number') or od.get('tracking') or (obj.meta.get('tracking') if obj.meta else None)
                if tracking_num:
                    # نحفظ رقم التتبع ثم نطلب حالة التتبع من الشركة (مبسط)
                    obj.tracking_number = tracking_num
                    track_info = fetch_tracking_status_from_carrier(tracking_num)
                    obj.status = track_info.get('status', obj.status)
                    # حفظ بيانات خام
                    obj.meta['carrier_tracking_raw'] = track_info.get('raw')
                    obj.save()
                else:
                    obj.save()

                # المطابقة على أساس الهاتف + أقرب وقت
                visits_qs = CampaignVisit.objects.filter(user = request.user ,phone_normalized=obj.phone_normalized)
                matched = find_best_visit_for_phone(obj.phone_normalized, obj.created_at, visits_qs)
                if matched:
                    obj.matched_visit = matched
                    obj.save()
                processed += 1
            except Exception:
                logger.exception("error processing order payload: %s", od)
                continue

        return JsonResponse({'ok': True, 'processed': processed})
    except Exception:
        logger.exception("manual_sync error")
        return JsonResponse({'error': 'server_error'}, status=500)


# صفحة بسيطة تُظهر زر التحديث (يمكن وضعها في admin أو صفحة داخلية)
@staff_member_required
def manual_sync_page(request):
    """
    صفحة بسيطة (HTML) تعرض زر لبدء المزامنة اليدوية.
    الزر ينادي endpoint /api/manual-sync/?token=...
    """
    secret = os.environ.get('MANUAL_SYNC_SECRET', '')
    return render(request, 'your_app/manual_sync_button.html', {'manual_token': secret})








def test(request):
    """
    صفحة اختبارية لعرض بعض المعلومات أو تنفيذ وظائف تجريبية.
    """

    return render(request, 'partials/test.html', {})






# put data in analyctic template

# your_app/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q

@login_required
def analytics_view(request):
    """
    View that prepares aggregated analytics for campaigns (based on CampaignVisit) and orders
    (based on ExternalOrder.matched_visit). Returns context containing:
    - campaigns_metrics: list of dicts, each with visits/orders/confirmation/delivery/conversion rates
    - totals: aggregated totals across all campaigns
    - recent_orders: last N ExternalOrder objects for detail display
    - recent_visits: last N CampaignVisit objects for detail display
    - unmatched_orders_count: number of ExternalOrder without matched_visit (need sync)
    """

    # ---------- 1) Aggregate visits grouped by (utm_campaign, ad_id) ----------
    # We group by utm_campaign and ad_id because you requested metrics per campaign/adset.
    visits_qs = CampaignVisit.objects.filter(user = request.user)

    visits_agg = (
        visits_qs
        .values('utm_campaign', 'ad_id', 'utm_source')   # group keys
        .annotate(visits=Count('id'))
        .order_by('-visits')
    )

    # ---------- 2) Aggregate orders (those already matched to visits) ----------
    # We count total orders + confirmed + delivered grouped by the matched visit keys.
    orders_qs = ExternalOrder.objects.filter(matched_visit__user = request.user).order_by('-matched_visit__created_at')

    orders_agg_qs = (
        orders_qs
        .values('matched_visit__utm_campaign', 'matched_visit__ad_id')
        .annotate(
            orders=Count('id'),
            confirmed=Count('id', filter=Q(status='confirmed')),
            delivered=Count('id', filter=Q(status='delivered'))
        )
    )

    # Convert orders aggregation into a lookup dict for quick merging:
    # key = (utm_campaign, ad_id)
    orders_map = {}
    for o in orders_agg_qs:
        key = (o.get('matched_visit__utm_campaign') or '', o.get('matched_visit__ad_id') or '')
        orders_map[key] = {
            'orders': o['orders'],
            'confirmed': o['confirmed'],
            'delivered': o['delivered']
        }

    # ---------- 3) Build merged campaigns metrics list ----------
    campaigns_metrics = []
    seen_keys = set()

    total_visits = 0
    total_orders = 0
    total_confirmed = 0
    total_delivered = 0

    for v in visits_agg:
        utm = v.get('utm_campaign') or ''   # could be empty
        ad_id = v.get('ad_id') or ''
        utm_source = v.get('utm_source') or ''
        visits = v.get('visits', 0)

        key = (utm, ad_id)
        seen_keys.add(key)

        o = orders_map.get(key, {'orders': 0, 'confirmed': 0, 'delivered': 0})
        orders = o['orders']
        confirmed = o['confirmed']
        delivered = o['delivered']

        # rates (guard against division by zero)
        conversion_rate = (orders / visits) if visits else None
        confirmation_rate = (confirmed / orders) if orders else None
        delivery_rate = (delivered / orders) if orders else None

        campaigns_metrics.append({
            'utm_campaign': utm,
            'ad_id': ad_id,
            'utm_source': utm_source,
            'visits': visits,
            'orders': orders,
            'confirmed': confirmed,
            'delivered': delivered,
            'conversion_rate': conversion_rate,    # float or None
            'confirmation_rate': confirmation_rate,
            'delivery_rate': delivery_rate,
        })

        total_visits += visits
        total_orders += orders
        total_confirmed += confirmed
        total_delivered += delivered

    # ---------- 4) Include campaigns that appear in orders_map but had no visits (edge case) ----------
    # (so we don't lose any campaign that had orders but visits record missing)
    for key, vals in orders_map.items():
        if key in seen_keys:
            continue
        utm, ad_id = key
        orders = vals['orders']
        confirmed = vals['confirmed']
        delivered = vals['delivered']

        conversion_rate = None   # no visits recorded
        confirmation_rate = (confirmed / orders) if orders else None
        delivery_rate = (delivered / orders) if orders else None

        campaigns_metrics.append({
            'utm_campaign': utm,
            'ad_id': ad_id,
            'utm_source': None,
            'visits': 0,
            'orders': orders,
            'confirmed': confirmed,
            'delivered': delivered,
            'conversion_rate': conversion_rate,
            'confirmation_rate': confirmation_rate,
            'delivery_rate': delivery_rate,
        })

        total_orders += orders
        total_confirmed += confirmed
        total_delivered += delivered
        # visits remain unchanged

    # ---------- 5) Totals + overall rates ----------
    overall_conversion_rate = (total_orders / total_visits) if total_visits else None
    overall_confirmation_rate = (total_confirmed / total_orders) if total_orders else None
    overall_delivery_rate = (total_delivered / total_orders) if total_orders else None

    totals = {
        'visits': total_visits,
        'orders': total_orders,
        'confirmed': total_confirmed,
        'delivered': total_delivered,
        'conversion_rate': overall_conversion_rate,
        'confirmation_rate': overall_confirmation_rate,
        'delivery_rate': overall_delivery_rate,
    }

    # ---------- 6) Recent samples for detailed panels (non-aggregated tables) ----------
    RECENT_LIMIT = 100
    recent_orders = ExternalOrder.objects.filter(matched_visit__user= request.user).select_related('matched_visit').order_by('-created_at')[:RECENT_LIMIT]
    recent_visits = CampaignVisit.objects.filter(user = request.user).order_by('-created_at')[:RECENT_LIMIT]

    # Count orders that are not matched (suggest running manual sync)
    unmatched_orders_count = ExternalOrder.objects.filter(matched_visit__user= request.user ,matched_visit__isnull=True).count()

    # ---------- 7) Prepare context and render ----------
    from django.contrib.auth import get_user_model
    from orders.filters import SOURCE_PLATFORM_CHOICES
    from orders.models import Order

    User = get_user_model()
    context = {
        'has_password': request.user.has_usable_password(),
        'campaigns_metrics': campaigns_metrics,   # list of per-(utm,ad) dicts
        'totals': totals,
        'recent_orders': recent_orders,
        'recent_visits': recent_visits,
        'unmatched_orders_count': unmatched_orders_count,
        # For embedded orders tab (order_list_embed.html)
        'agents': User.objects.filter(is_active=True).order_by('username'),
        'status_choices': Order.STATUS_CHOICES,
        'source_choices': SOURCE_PLATFORM_CHOICES,
        'default_channel_id': _get_default_channel_id(request.user),
    }

    return render(request, 'partials/_user_analitycs.html', context)






# views.py أو services.py
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
# from discount.models import ExternalOrder, CampaignVisit


# def analytics_view_data(platform="all", period_days=7):
#     now = timezone.now()
#     start_date = now - timedelta(days=period_days)

#     # فلترة الطلبات حسب المدة
#     orders_qs = ExternalOrder.objects.filter(created_at__gte=start_date)
#     if platform != "all":
#         orders_qs = orders_qs.filter(platform=platform)

#     # فلترة الزيارات حسب المدة
#     visits_qs = CampaignVisit.objects.filter(created_at__gte=start_date)
#     if platform != "all":
#         visits_qs = visits_qs.filter(utm_source=platform)

#     # ====== KPIs ======
#     kpis = {
#         # "total_orders": orders_qs.filter(status="confirmed").count(),
#         "total_orders": orders_qs.count(),
#         "confirmed_orders": orders_qs.filter(status="confirmed").count(),
#         "shipped_orders": orders_qs.filter(status="shipped").count(),
#         "delivered_orders": orders_qs.filter(status="delivered").count(),
#         "cancelled_orders": orders_qs.filter(status="cancelled").count(),
#         "total_visits": visits_qs.count(),
#         "matched_visits": orders_qs.filter(matched_visit__isnull=False).count(),
#         "confirmation_rate": round(
#             (orders_qs.filter(status="confirmed").count() / orders_qs.count()) * 100, 2
#         ) if orders_qs.count() else 0,
#     }


#     # ====== بيانات الطلبات ======
#     orders_data = list(
#         orders_qs.values(
#             "external_order_id",
#             "platform",
#             "status",
#             "customer_name",
#             "phone_normalized",
#             "created_at",
#             "matched_visit__utm_campaign",
#             "matched_visit__utm_source",
#             "matched_visit__utm_medium",
#             "matched_visit__ad_id",
#         )
#     )

#     # ====== بيانات الزيارات ======
#     visits_data = list(
#         visits_qs.values(
#             "phone_normalized",
#             "utm_campaign",
#             "utm_source",
#             "utm_medium",
#             "ad_id",
#             "created_at",
#         )
#     )

#     # ====== النتيجة ======
#     payload = {
#         "kpis": kpis,
#         "orders": orders_data,
#         "visits": visits_data,
#     }
#     return payload



from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.http import JsonResponse

# Platform dropdown value -> possible utm_source values in DB (case-insensitive match)
PLATFORM_UTM_SOURCE_ALIASES = {
    "facebook": ["facebook", "fb", "meta", "instagram", "meta / facebook"],
    "google": ["google", "google ads", "googleads"],
    "tiktok": ["tiktok", "tiktok ads", "tiktok_ads"],
    "snapchat": ["snapchat", "snap"],
}


def _platform_filter_values(platform_clean):
    """Return Q filter for CampaignVisit.utm_source (visits_qs)."""
    aliases = PLATFORM_UTM_SOURCE_ALIASES.get(platform_clean, [platform_clean])
    q = Q(utm_source__iexact=aliases[0])
    for a in aliases[1:]:
        q = q | Q(utm_source__iexact=a)
    return q


def _platform_filter_orders(platform_clean):
    """Return Q filter for orders.Order via attribution_data.utm_source."""
    aliases = PLATFORM_UTM_SOURCE_ALIASES.get(platform_clean, [platform_clean])
    q = Q(attribution_data__utm_source__iexact=aliases[0])
    for a in aliases[1:]:
        q = q | Q(attribution_data__utm_source__iexact=a)
    return q


def analytics_view_data(request, platform="all", period_days=7):
    """
    Return analytics payload using the orders.Order model (CRM orders).
    
    Data flow:
      orders.Order -> Order.attribution_data (Attribution)
                   -> Attribution.campaign_visit (CampaignVisit)
    
    Payload shape (unchanged for frontend compatibility):
      { kpis: {...}, campaigns: [...], orders: [...], last_update: "..." }
    """
    from orders.models import Order

    now = timezone.now()
    start_date = now - timedelta(days=period_days)

    # ── Base querysets ──────────────────────────────────────────────
    # Orders scoped to current user's stores
    orders_qs = Order.objects.for_user(request.user).filter(created_at__gte=start_date)
    # Visits scoped to current user
    visits_qs = CampaignVisit.objects.filter(user=request.user, created_at__gte=start_date)

    if platform and platform != "all":
        platform_clean = (platform or "").strip().lower()
        visits_qs = visits_qs.filter(_platform_filter_values(platform_clean))
        orders_qs = orders_qs.filter(_platform_filter_orders(platform_clean))

    # ── KPIs ────────────────────────────────────────────────────────
    total_orders = orders_qs.count()
    confirmed_orders = orders_qs.filter(status="CONFIRMED").count()
    shipped_orders = orders_qs.filter(status="SHIPPED").count()
    delivered_orders = orders_qs.filter(status="DELIVERED").count()
    cancelled_orders = orders_qs.filter(status="CANCELED").count()
    total_visits = visits_qs.count()
    matched_visits = orders_qs.filter(attribution_data__isnull=False).count()

    conversion_rate = (total_orders / total_visits) if total_visits else 0.0
    confirmation_rate = (confirmed_orders / total_orders) if total_orders else 0.0
    delivery_rate = (delivered_orders / confirmed_orders) if confirmed_orders else 0.0

    kpis = {
        "total_orders": total_orders,
        "orders": total_orders,
        "confirmed_orders": confirmed_orders,
        "shipped_orders": shipped_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "total_visits": total_visits,
        "visits": total_visits,
        "matched_visits": matched_visits,
        "conversion_rate": conversion_rate,
        "confirmation_rate": confirmation_rate,
        "delivery_rate": delivery_rate,
        "spend": 0.0,
    }

    # ── Visits per source (for KPI dropup: source -> visitors -> orders) ──
    visits_by_source = visits_qs.values('utm_source').annotate(visits=Count('id'))
    orders_by_source = (
        orders_qs
        .filter(attribution_data__isnull=False)
        .values('attribution_data__utm_source')
        .annotate(orders=Count('id'))
    )
    orders_source_map = {
        (row['attribution_data__utm_source'] or 'Direct'): row['orders']
        for row in orders_by_source
    }
    source_breakdown = []
    for row in visits_by_source:
        src = row['utm_source'] or 'Direct'
        v = row['visits']
        o = orders_source_map.get(src, 0)
        source_breakdown.append({"source": src, "visitors": v, "orders": o})
    source_breakdown.sort(key=lambda x: x['visitors'], reverse=True)

    kpis["source_breakdown"] = source_breakdown

    # ── Visits per campaign (map) ───────────────────────────────────
    visits_by_campaign = visits_qs.values('utm_campaign').annotate(visits=Count('id'))
    visits_map = {item['utm_campaign'] or '': item['visits'] for item in visits_by_campaign}

    # ── Visits per (campaign, ad_id) for ad-level rollup ────────────
    visits_by_campaign_ad = visits_qs.values('utm_campaign', 'ad_id').annotate(visits=Count('id'))
    visits_ad_map = {
        (item['utm_campaign'] or '', item['ad_id'] or ''): item['visits']
        for item in visits_by_campaign_ad
    }

    # ── Orders with attribution (linked to campaigns) ───────────────
    # Path: Order -> attribution_data (Attribution) -> campaign_visit (CampaignVisit)
    orders_linked = orders_qs.filter(attribution_data__isnull=False)

    # Aggregate per campaign (orders + confirmed)
    orders_by_campaign = (
        orders_linked
        .values('attribution_data__utm_campaign', 'attribution_data__utm_source')
        .annotate(
            orders=Count('id'),
            confirmed=Count('id', filter=Q(status='CONFIRMED')),
        )
    )

    campaigns = {}
    for row in orders_by_campaign:
        camp_name = row.get('attribution_data__utm_campaign') or 'Unknown'
        platform_label = row.get('attribution_data__utm_source') or ''
        if camp_name not in campaigns:
            campaigns[camp_name] = {
                "campaign_name": camp_name,
                "platform_label": platform_label,
                "orders": 0,
                "confirmed_orders": 0,
                "visits": visits_map.get(camp_name, 0),
                "adsets": {},
                "site_sources": set(),
            }
        campaigns[camp_name]["orders"] += row.get('orders', 0)
        campaigns[camp_name]["confirmed_orders"] += row.get('confirmed', 0)

    # ── Aggregate per ad (ad_id, adset name, placements) ────────────
    # ad_id is on Attribution; adset_name, utm_medium are on CampaignVisit
    ads_by_key = (
        orders_linked
        .values(
            'attribution_data__utm_campaign',
            'attribution_data__ad_id',
            'attribution_data__campaign_visit__site_source_name',
            'attribution_data__campaign_visit__ad_adset_name',
            'attribution_data__campaign_visit__utm_medium',
        )
        .annotate(
            orders=Count('id'),
            confirmed=Count('id', filter=Q(status='CONFIRMED')),
        )
    )

    for row in ads_by_key:
        camp_name = row.get('attribution_data__utm_campaign') or 'Unknown'
        ad_id = row.get('attribution_data__ad_id') or 'unknown_ad'
        placement = row.get('attribution_data__campaign_visit__utm_medium') or None
        ad_adset_name = row.get('attribution_data__campaign_visit__ad_adset_name') or ''

        if camp_name not in campaigns:
            campaigns[camp_name] = {
                "campaign_name": camp_name,
                "platform_label": '',
                "orders": 0,
                "confirmed_orders": 0,
                "visits": visits_map.get(camp_name, 0),
                "adsets": {},
                "site_sources": set(),
            }

        adsets = campaigns[camp_name]["adsets"]
        if ad_id not in adsets:
            adsets[ad_id] = {
                "ad_id": ad_id,
                "orders": 0,
                "confirmed_orders": 0,
                "placements": {},
                "ad_adset_name": ad_adset_name,
            }
        adsets[ad_id]["orders"] += row.get('orders', 0)
        adsets[ad_id]["confirmed_orders"] += row.get('confirmed', 0)

        if placement:
            campaigns[camp_name]["site_sources"].add(placement)
            pls = adsets[ad_id]["placements"]
            if placement not in pls:
                pls[placement] = {"placement": placement, "site_source_name": placement, "orders": 0}
            pls[placement]["orders"] += row.get('orders', 0)

    # ── Build final campaigns list for frontend ─────────────────────
    campaigns_list = []
    for camp_name, info in campaigns.items():
        adsets_list = []
        for ad_key, ad_info in info["adsets"].items():
            ad_visits = visits_ad_map.get((camp_name, ad_key), 0)
            orders_n = ad_info["orders"]
            confirmed_n = ad_info["confirmed_orders"]
            # Conversion = orders / visits (what % of visits became orders)
            conv_by_visits = (orders_n / ad_visits) if ad_visits else None
            conv_by_orders = (confirmed_n / orders_n) if orders_n else None

            adsets_list.append({
                "ad_id": ad_info["ad_id"],
                "orders": orders_n,
                "confirmed_orders": confirmed_n,
                "visits": ad_visits,
                "conversion_by_visits": round(conv_by_visits, 4) if conv_by_visits is not None else None,
                "conversion_by_orders": round(conv_by_orders, 4) if conv_by_orders is not None else None,
                "placements": list(ad_info["placements"].values()),
                "ad_adset_name": ad_info.get("ad_adset_name", ""),
            })

        camp_orders = info["orders"]
        camp_confirmed = info["confirmed_orders"]
        camp_visits = info["visits"] or 0
        # Conversion = orders / visits (what % of visits became orders)
        conv_vis = (camp_orders / camp_visits) if camp_visits else None
        # Confirmation = confirmed / orders (what % of orders got confirmed)
        conv_ord = (camp_confirmed / camp_orders) if camp_orders else None

        campaigns_list.append({
            "campaign_name": info["campaign_name"],
            "platform_label": info["platform_label"],
            "campaign_id": "",
            "orders": camp_orders,
            "confirmed_orders": camp_confirmed,
            "visits": camp_visits,
            "conversion_by_visits": round(conv_vis, 4) if conv_vis is not None else None,
            "conversion_by_orders": round(conv_ord, 4) if conv_ord is not None else None,
            "adsets": adsets_list,
            "site_sources": sorted(list(info["site_sources"])),
        })

    # Include campaigns that had visits but no orders
    for camp_name, vcount in visits_map.items():
        if camp_name not in campaigns:
            campaigns_list.append({
                "campaign_name": camp_name,
                "platform_label": '',
                "campaign_id": '',
                "orders": 0,
                "confirmed_orders": 0,
                "visits": vcount,
                "conversion_by_visits": None,
                "conversion_by_orders": None,
                "adsets": [],
                "site_sources": [],
            })

    campaigns_list.sort(key=lambda x: x.get('orders', 0), reverse=True)

    # ── Orders list for time-series chart ───────────────────────────
    # Frontend reads: created_at, status (for chart grouping)
    # Keep same field names the JS expects
    orders_data = list(
        orders_qs
        .select_related('attribution_data', 'attribution_data__campaign_visit')
        .values(
            'id',
            'status',
            'name',
            'phone',
            'created_at',
            'attribution_data__utm_campaign',
            'attribution_data__utm_source',
            'attribution_data__ad_id',
            'attribution_data__campaign_visit__utm_medium',
        )
    )
    # Normalize status to lowercase for frontend compatibility
    # (JS checks status==='confirmed' in lowercase)
    for o in orders_data:
        if o.get('status'):
            o['status'] = o['status'].lower()

    payload = {
        "kpis": kpis,
        "campaigns": campaigns_list,
        "orders": orders_data,
        "last_update": timezone.now().isoformat(),
    }
    return payload



def dashboard_data_api(request):
    platform = request.GET.get('platform', 'all')
    period = int(request.GET.get('period', 7))
    payload = analytics_view_data(request,platform=platform, period_days=period)


    return JsonResponse(payload, safe=True)








@csrf_exempt
def refresh(request): 
    fetchorder = fetch_and_update_order_cod(request)
    if fetchorder:
        print("Orders updated successfully")
        return JsonResponse({'status': 'success', 'message': 'Orders updated successfully'})
    else:
        print("Order not update")
        return JsonResponse({'status': 'error', 'message': 'Failed to update orders'}, status=500)





# views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from discount.models import Products, UserProductPermission, UserPermissionSetting, CustomUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

# ========== products list (simple) ==========
@login_required
@require_GET
def products_list(request):
    # Return minimal product info used in the modal
    qs = Products.objects.filter(admin = request.user).order_by('name')[:5000]   
    products = [{'id': str(p.id), 'name': p.name} for p in qs]
    return JsonResponse({'products': products})

# ========== get permissions for user (expanded) ==========
@login_required
@require_GET
def get_permissions_for_user(request):
    user_id = request.GET.get('user_id')
    if not user_id:
        return HttpResponseBadRequest(json.dumps({'error':'missing_user_id'}), content_type='application/json')
    target_user = CustomUser.objects.get(pk=user_id)
    # Authorization: staff or the user themself (tune to your needs)
    if not (request.user.is_staff or request.user == target_user):
        return HttpResponseForbidden(json.dumps({'error':'forbidden'}), content_type='application/json')

    perms_qs = UserProductPermission.objects.filter(user=target_user).select_related('product')
    perms = []
    assigned_channels_qs = target_user.channels.filter(owner=request.user)
    
    assigned_channels_data = [{
        'id': str(c.id),
        'name': c.name,
        'phone': c.phone_number
    } for c in assigned_channels_qs]


    for p in perms_qs:
        perms.append({
            'target_user':target_user.username,
            'product_id': str(p.product.id),
            'product_name': p.product.name,
            'role': p.role,
            'daily_order_limit': p.daily_order_limit
        })

    # load global settings
    try:
        ups = target_user.permission_setting
        global_permissions = {
            'can_create_orders': bool(ups.can_create_orders),
            'can_view_analytics': bool(ups.can_view_analytics),
            'extra': ups.extra or {}
        }
    except UserPermissionSetting.DoesNotExist:
        global_permissions = {'can_create_orders': False, 'can_view_analytics': False, 'extra': {}}

    return JsonResponse({'status':'ok', 'user_id': str(target_user.id), 'permissions': perms, 'global_permissions': global_permissions , 'channel_permissions': assigned_channels_data,})


# 1. دالة جديدة لجلب كل القنوات المتاحة (Available)
def channels_list(request):
    if not request.user.is_staff: # أو is_team_admin حسب نظامك
         return JsonResponse({'channels': []})
         
    # جلب القنوات التي يملكها الأدمن الحالي
    qs = WhatsAppChannel.objects.filter(owner=request.user).order_by('name')
    
    # نرسل الاسم والرقم ليكون العرض واضحاً
    channels = [{
        'id': str(c.id), 
        'name': c.name, 
        'phone': c.phone_number
    } for c in qs]
    
    return JsonResponse({'channels': channels})

 

# ========== bulk update endpoint ==========
from discount.models import WhatsAppChannel
@login_required
@require_POST
def bulk_update_permissions(request):
    # Only staff allowed in this example to change other user's perms - adjust as needed
    if not request.user.is_staff:
        return HttpResponseForbidden(json.dumps({'error':'forbidden'}), content_type='application/json')

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest(json.dumps({'error':'invalid_json'}), content_type='application/json')

    user_id = body.get('user_id')
    assignments = body.get('assignments', [])  # list of {product_id, role, daily_order_limit}
    removals = body.get('removals', [])        # list of product_ids to remove
    global_permissions = body.get('global_permissions', {})
    channel_ids_assigned = body.get('channel_assignments', []) # [1, 2, ...]
    channel_removals = body.get('channel_removals', [])        # [3, ...]


    if not user_id:
        return HttpResponseBadRequest(json.dumps({'error':'missing_user_id'}), content_type='application/json')

    try:
        target_user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return HttpResponseBadRequest(json.dumps({'error':'invalid_user_id'}), content_type='application/json')

    # apply updates in a transaction
    # results = {'created':[], 'updated':[], 'deleted':[]}
    results = {
        'created': [], 
        'updated': [], 
        'deleted': [],
        'channels_added': [],   # 🔥 ضروري جداً لتفادي KeyError
        'channels_removed': []  # 🔥 ضروري جداً لتفادي KeyError
    }
    with transaction.atomic():
        # handle removals
        if removals:
            qs = UserProductPermission.objects.filter(user=target_user, product_id__in=removals)
            deleted_count = qs.count()
            qs.delete()
            results['deleted'] = removals

        # handle assignments create/update
        for a in assignments:
            pid = a.get('product_id')
            role = a.get('role') or 'viewer'
            try:
                limit = int(a.get('daily_order_limit') or 0)
            except Exception:
                limit = 0
            # validate product exists
            try:
                prod = Products.objects.get(pk=pid)
            except Products.DoesNotExist:
                continue
            perm_obj, created = UserProductPermission.objects.update_or_create(
                user=target_user,
                product=prod,
                defaults={'role': role, 'daily_order_limit': limit}
            )
            if created:
                results['created'].append(str(prod.id))
            else:
                results['updated'].append(str(prod.id))

        # أ) حذف القنوات المطلوبة (Removals)
        if channel_removals:
            # نتحقق أن القنوات تابعة للأدمن الحالي للحماية
            channels_to_remove = WhatsAppChannel.objects.filter(
                id__in=channel_removals, 
                owner=request.user
            )
            for ch in channels_to_remove:
                ch.assigned_agents.remove(target_user) # إزالة العلاقة
                results['channels_removed'].append(ch.id)

        # ب) إضافة/تأكيد القنوات الجديدة (Assignments)
        if channel_ids_assigned:
            # نتحقق أن القنوات تابعة للأدمن
            channels_to_add = WhatsAppChannel.objects.filter(
                id__in=channel_ids_assigned, 
                owner=request.user
            )
            for ch in channels_to_add:
                # add ذكية، إذا كان موجوداً لن تكرره
                ch.assigned_agents.add(target_user)
                results['channels_added'].append(ch.id)

        # handle global permissions (create or update UserPermissionSetting)
        if global_permissions is not None:
            ups, created_ups = UserPermissionSetting.objects.get_or_create(user=target_user)
            ups.can_create_orders = bool(global_permissions.get('can_create_orders', ups.can_create_orders))
            ups.can_view_analytics = bool(global_permissions.get('can_view_analytics', ups.can_view_analytics))
            # keep or merge extra
            extra = ups.extra or {}
            extra.update(global_permissions.get('extra', {}))
            ups.extra = extra
            ups.save()

    return JsonResponse({'status':'ok', 'result': results})




# # views.py
# from django.http import JsonResponse
# from django.utils.dateparse import parse_date
# from django.utils import timezone
# from datetime import timedelta 
# from discount.models import ExternalOrder , Lead
# from discount.shopifyLink import tracking
# def filter_leads_api(request):
#     status = request.GET.get("status")
#     period = request.GET.get("period")
#     start_date = request.GET.get("start_date")
#     end_date = request.GET.get("end_date")
#     product_sku = request.GET.get("product_sku")
#     country = request.GET.get("country")
#     live_search_leads = request.GET.get("live_search_leads", None)
#     if live_search_leads:
#         live_search_leads = live_search_leads.lower()



    
#     user = request.user


#     # حصر المنتجات المسموح بها لهذا المستخدم
#     if getattr(user, 'is_team_admin', False):
#         allowed_product_ids = list(Products.objects.filter(admin=user).values_list('id', flat=True))
#     else:
#         allowed_product_ids = list(
#             UserProductPermission.objects.filter(user=user).values_list('product_id', flat=True)
#         )
#     products ,  countries , projects , orderslist , orders_page , productslist , products , last_product_update, team_account_perm, user_permusstion, team_users_with_order_counts, orderslastmonth, leads = tracking(request,leades = True)
#     print('req.products' , countries ,projects , orderslist , orders_page )

#     if not allowed_product_ids:
#         # إظهار صفحة فارغة مع رسالة أو إرجاع قائمة صفرية
#         qs = Lead.objects.none()
#     else:
#         qs = Lead.objects.filter(product_id__in=allowed_product_ids).select_related('product').order_by('-created_at')
#         # leads.history = sorted(leads.history, key=lambda c: c['date'])
        

#     if live_search_leads:
#         # فلترة حسب البحث المباشر
#         qs = qs.filter(Q(phone__icontains=live_search_leads) | Q(name__icontains=live_search_leads) |
#                        Q(email__icontains=live_search_leads) | Q(product__name__icontains=live_search_leads))


#     # 🔹 فلترة حسب status
#     if status:
#         # هنا map للـ status كما عندك في الخيارات
#         status_map = {
#             "Pending": "confirmed",
#             "Delivered": "cancelled",
#             "Return": "wrong",
#         }
#         mapped_status = status_map.get(status, status)
#         qs = qs.filter(status__iexact=mapped_status)

#     # 🔹 فلترة حسب الفترة الزمنية
#     now = timezone.now()
#     if period == "today":
#         qs = qs.filter(created_at__date=now.date())
#     elif period == "week":
#         qs = qs.filter(created_at__gte=now - timedelta(days=7))
#     elif period == "month":
#         qs = qs.filter(created_at__gte=now - timedelta(days=30))
#     elif period == "custom" and start_date and end_date:
#         start = parse_date(start_date)
#         end = parse_date(end_date)
#         if start and end:
#             qs = qs.filter(created_at__date__range=[start, end])

#     # 🔹 فلترة حسب المنتج
#     if product_sku:
#         qs = qs.filter(matched_visit__utm_campaign=product_sku)  # أو حسب sku إذا عندك relation بمنتجاتك

#     # 🔹 فلترة حسب الدولة
#     if country:
#         qs = qs.filter(meta__country__iexact=country)  # لو عندك الدولة محفوظة في meta

#     # 🔹 تجهيز الرد
#     from django.template.loader import render_to_string
#     from discount.models import UserPermissionSetting
#     user_permusstion = UserPermissionSetting.objects.filter(user=request.user).first()
#     lead_paginator = Paginator(qs.order_by('-created_at'), 10)
#     page = request.GET.get('page')
#     leads_page = lead_paginator.get_page(page)

#     html = render_to_string('leads.html', {'leads_page': leads_page ,  'user_permusstion':user_permusstion,
                                           
#                                            'order_users' : team_users_with_order_counts ,
#         'orderslastmonth':orderslastmonth ,
#         'productslists': products,
#         # 'search_query': search_query,
#         'countries': countries,
#         'projects': projects,
#         'orderslist': orderslist,
#         'leads_list' : leads,
#         # 'get_comment':get_comment,
#         'orders': orders_page,
#         'productslist' : productslist ,

#         'last_update': last_product_update ,
#         'team_accounts': team_account_perm
#         })


#     return JsonResponse({"html": html})










from django.shortcuts import render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.utils import timezone
from datetime import timedelta

from discount.models import Lead, Products

# def filter_leads_api(request):
#     status = request.GET.get("status")
#     period = request.GET.get("period")
#     start_date = request.GET.get("start_date")
#     end_date = request.GET.get("end_date")
#     product_sku = request.GET.get("product_sku")
#     country = request.GET.get("country")  # لو تريد استخدامه لاحقاً
#     search_query = request.GET.get("search")

#     qs = Lead.objects.select_related("product").all()

#     # 🔹 فلترة حسب الحالة (status)
#     if status:
#         qs = qs.filter(status__iexact=status)

#     # 🔹 فلترة حسب الفترة الزمنية
#     now = timezone.now()
#     if period == "today":
#         qs = qs.filter(created_at__date=now.date())
#     elif period == "week":
#         qs = qs.filter(created_at__gte=now - timedelta(days=7))
#     elif period == "month":
#         qs = qs.filter(created_at__gte=now - timedelta(days=30))
#     elif period == "custom" and start_date and end_date:
#         start = parse_date(start_date)
#         end = parse_date(end_date)
#         if start and end:
#             qs = qs.filter(created_at__date__range=[start, end])

#     # 🔹 فلترة حسب المنتج (SKU)
#     if product_sku:
#         qs = qs.filter(product__sku=product_sku)

#     # 🔹 البحث (search by name or phone)
#     if search_query:
#         qs = qs.filter(name__icontains=search_query) | qs.filter(phone__icontains=search_query)

#     # 🔹 Pagination (صفحات)
#     paginator = Paginator(qs,15)  # 20 lead لكل صفحة
#     page_number = request.GET.get("page")
#     leads_page = paginator.get_page(page_number)

#     # (هنا حسب نظامك) مثلاً: استرجاع صلاحيات المستخدم
#     user_permusstion = {"can_create_orders": True, "can_view_analytics": False}

#     html = render_to_string("leads.html", {
#         "leads_page": leads_page,
#         "user_permusstion": user_permusstion,
#     }, request=request)

#     return JsonResponse({"html": html})




from datetime import timedelta
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db.models import Q

# Constants
DEFAULT_PAGE_SIZE = 10
VALID_PERIODS = {"today", "week", "month", "custom"}
VALID_STATUSES = {"cancelled", "cancelled price", "wrong" , "expired"}  # Example; adjust based on your model


def filter_leads_api(request):
    status = request.GET.get("status")
    period = request.GET.get("period")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    product_sku = request.GET.get("product_sku")
    search_query = request.GET.get("search")
    qs = ""
    this_user = UserPermissionSetting.objects.filter(user = request.user).first()
    if this_user :
        qs = Lead.objects.select_related("product").filter(product__in = Products.objects.filter(admin = request.user) | Products.objects.filter(id__in = UserProductPermission.objects.filter(user = request.user).values_list('product_id', flat=True)))
    else:
        qs = Lead.objects.select_related("product").filter(product__admin=request.user)


    # 🔹 Filter by status
    if status and status.lower() in VALID_STATUSES:
        qs = qs.filter(status__iexact=status)
        print(f"Filtering by status: {qs}")

    # 🔹 Filter by period
    now = timezone.now()
    if period in VALID_PERIODS:
        if period == "today":
            qs = qs.filter(created_at__date=now.date())
        elif period == "week":
            qs = qs.filter(created_at__gte=now - timedelta(days=7))
        elif period == "month":
            qs = qs.filter(created_at__gte=now - timedelta(days=30))
        elif period == "custom" and start_date and end_date:
            try:
                start = parse_date(start_date)
                end = parse_date(end_date)
                if start and end:
                    qs = qs.filter(created_at__date__range=[start, end])
            except Exception:
                pass  # Silently ignore invalid dates or log as needed

    # 🔹 Filter by product SKU
    if product_sku:
        qs = qs.filter(product__sku=product_sku)

    # 🔹 Search by name or phone
    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query) | Q(phone__icontains=search_query)
        )


        from discount.models import Message
        unread_phones = list(Message.objects.filter(
        is_read=False, 
        is_from_me=False ,
    ).values_list('sender', flat=True).distinct())
        print(leads_page)
        


    # 🔹 Pagination
    paginator = Paginator(qs, DEFAULT_PAGE_SIZE)
    page_number = request.GET.get("page")
    leads_page = paginator.get_page(page_number)
    try:
            # لو كان lead.lead_inputs مخزن كنص بايثون → نحوله JSON
        if isinstance(leads_page.lead_inputs, str):
                leads_page.lead_inputs_json = json.dumps(eval(leads_page.lead_inputs))
        else:
                leads_page.lead_inputs_json = json.dumps(leads_page.lead_inputs)
    except Exception:
            leads_page.lead_inputs_json = "[]"

    # 🔹 User permissions (mocked for now)
    user_permission = {
        "can_create_orders": True,
        "can_view_analytics": False,
    }
    validate_token = ExternalTokenmodel.objects.filter(user = request.user).first()

    html = render_to_string(
        "leads.html",
        {"validate_token":validate_token , 
         'unread_phones':unread_phones ,
            "leads_page": leads_page,
            "user_permusstion": user_permission,  # Keeping key as is to preserve template compatibility
        },
        request=request,
    )

    return JsonResponse({"html": html})













# load COD drop product  
def load_products(request):
    from discount.models import CODProduct
    if request.user.is_team_admin:
        products = CODProduct.objects.filter(user = request.user)
    else:
        get_user = CustomUser.objects.filter(id = request.user.id).first()
        get_user_admin = get_user.team_admin if get_user else None
        if get_user_admin:
      
            products = CODProduct.objects.filter(user = get_user_admin) | CODProduct.objects.filter(id__in = UserProductPermission.objects.filter(user = request.user).values_list('product_id', flat=True))

        # products = CODProduct.objects.filter(user = request.user) | CODProduct.objects.filter(id__in = UserProductPermission.objects.filter(user = request.user).values_list('product_id', flat=True))
    
    
    

 
    return render(request, 'partials/_product_views.html', {'productslists': products })

 