# your_app/views.py
"""
يوفر:
- endpoint لالتقاط الزيارة (capture_visit) - يستقبل raw_phone + utm's عبر POST.
- endpoint لبدء تحديث يدوي (manual_sync) - مؤمن بواسطة HEADER SECRET_TOKEN أو تسجيل دخول الموظف.
"""
from django.core.paginator import Paginator


import json
import os
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from discount.models import CampaignVisit, ExternalOrder ,ScriptFlow  , ExternalTokenmodel , CustomUser
from .utils import normalize_phone, find_best_visit_for_phone
from .services import fetch_orders_from_cod, fetch_tracking_status_from_carrier
from .services import fetch_and_update_order_cod
logger = logging.getLogger(__name__)
MANUAL_SYNC_SECRET = os.environ.get('MANUAL_SYNC_SECRET', 'set_this_secret')  # ضع SECRET في ENV


# @csrf_exempt
# def capture_visit(request):
#     """
#     يستقبل POST JSON:
#     {
#       "raw_phone": "...",
#       "utm_campaign": "...",
#       "utm_source": "...",
#       "utm_medium": "...",
#       "ad_id": "..."
#     }
#     يرجع {"ok": True} أو خطأ.
#     """
#     if request.method != 'POST':
#         return JsonResponse({'error': 'method_not_allowed'})
#     try:
#         data = json.loads(request.body.decode('utf-8'))
#         raw_phone = data.get('raw_phone', '')
#         utm_campaign = data.get('utm_campaign')
#         utm_source = data.get('utm_source')
#         if utm_source =="fb":
#             utm_source = "facebook"



#         if not raw_phone : 
#             raw_phone = None 
            
        
#         utm_medium = data.get('utm_medium') # placements
#         ad_id = data.get('ad_id')
#         site_source_name = data.get('site_source_name')
#         ad_name = data.get('ad_adset_name')
#         # http://127.0.0.1:8000/discount/marketing/testing/?utm_source=fb&utm_medium=Facebook_Desktop_Feed&utm_campaign=New+Sales+Campaign+-+Copy&campaign_id=120231644142440479&ad_id=120231809576050479&ad_name=crea1+ac+2&utm_id=120231644142440479&utm_content=120231809903610479&utm_term=120231644142430479&
#         phone_norm = ""
#         # phone_norm = normalize_phone(raw_phone)
#         if raw_phone:
#             phone_norm = normalize_phone(raw_phone)

#         visit = CampaignVisit.objects.create(
#             raw_phone=raw_phone,
#             phone_normalized=phone_norm,
#             utm_campaign=utm_campaign,
#             utm_source=utm_source,
#             utm_medium=utm_medium,
#             ad_id=ad_id,
#             ad_adset_name=ad_name,
#             site_source_name=site_source_name
#         )
#         # orders = ExternalOrder.objects.create(
#         #     platform =  utm_source or 'unknown',
#         #     raw_phone = raw_phone , 
#         #     phone_normalized = phone_norm
            
#         # )
         

#         return JsonResponse({'status': True, 'visit_id': str(visit.id)}, status=201)
#     except json.JSONDecodeError:
#         return JsonResponse({'error': 'invalid_json'})
#     except Exception as e:
#         logger.exception("capture_visit error")
#         return JsonResponse({'error': 'server_error'}, status=500)
 
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


@login_required
@require_POST
def create_flow(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'invalid_json'}, status=400)

    name = body.get('name', '')[:200]
    # cannel_id = body.get('cannel_id', '')

    allowed_domains = body.get('allowed_domains', '')  # e.g. "store.com,shop.store.com"
    config = body.get('config', {})

    # generate api_key (expose once)
    api_key = secrets.token_urlsafe(32)

    flow = ScriptFlow.objects.create(
        owner=request.user,
        name=name,
        api_key=api_key,
        allowed_domains=allowed_domains,
        config=config,
        active=True ,
        script=body.get('script')  # optionally save generated script

    )

    return JsonResponse({
        'status': True,
        'flow_id': str(flow.id),
        'api_key': api_key,
        'created_at': flow.created_at.isoformat()
    }, status=201)

def list_flows(request):
    qs = ScriptFlow.objects.filter(owner=request.user).order_by('-created_at')
    data = []
    for f in qs:
        data.append({
            'flow_id': str(f.id),
            'name': f.name,
            'allowed_domains': f.allowed_domains,
            'createdAt': f.created_at.isoformat(),
            'active': f.active,
            'script': f.script or '',
            'config': f.config or {}
        })
    return JsonResponse({'status': True, 'flows': data})

from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.views.decorators.http import require_http_methods

@login_required
@require_http_methods(['PATCH', 'DELETE'])
def flow_detail(request, flow_id):
    flow = get_object_or_404(ScriptFlow, id=flow_id, owner=request.user)

    if request.method == 'DELETE':
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

from urllib.parse import urlparse

@csrf_exempt
@require_POST
def capture_visit(request):
    if request.method == "OPTIONS":
        response = JsonResponse({"status": "ok"})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-FLOW-API-KEY"
        return response
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'invalid_json'}, status=400)
    region = request.GET.get("utm_region") or "SA"

    raw_phone = body.get('raw_phone', '') or ''
    utm_campaign = body.get('utm_campaign') or body.get('utm_campaign_id') or ''
    utm_source = body.get('utm_source') or ''
    utm_medium = body.get('utm_medium') or ''
    ad_id = body.get('ad_id') or ''
    site_source_name = body.get('site_source_name') or ''
    ad_adset_name = body.get('ad_adset_name') or body.get('ad_adset') or body.get('ad_name') or ''
    flow_id = body.get('flow_id')  # expected UUID string
    supplied_api_key = body.get('flow_api_key') or request.headers.get('X-FLOW-API-KEY')
    visits = body.get('visits')  or None # optional, default to 1 if not provided
    key = body.get('key') or None
    # visitorId = body.get('visitorId')
    visitorId = body.get('visitorId') or None
        
     
    # Verify flow if provided
    flow = None
    if not visitorId :
         return JsonResponse({'error': 'wrong_visitorId'}) 
    if not flow_id:
        return JsonResponse({'error': 'missing_flow_id'}, status=400)

    try:
        flow = ScriptFlow.objects.get(id=flow_id, active=True)
    except ScriptFlow.DoesNotExist:
        
        return JsonResponse({'error': 'invalid_flow'})

    # Two options: check api_key, or check origin domain against allowed_domains
    # Preferred: check api_key if provided
    if supplied_api_key:
        if supplied_api_key != flow.api_key:
            return JsonResponse({'error': 'invalid_api_key'}, status=403)
    else:
        # fallback: check Referer/Origin host is allowed
        origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
        host = ''
        try:
            host = urlparse(origin).hostname or ''
        except:
            host = ''
        allowed = flow.allowed_domains_list()
        
        if origin not in allowed:
            
            return JsonResponse({'error': 'origin_not_allowed'}, status=403)
        


    # Normalize phone
    phone_norm = normalize_phone(raw_phone, region ) if raw_phone else None


    existing = CampaignVisit.objects.filter(
    visit_id=visitorId,
    flow=flow,
    utm_campaign=utm_campaign,
    created_at__gte=timezone.now()-timedelta(seconds=30)
                ).first()

    if existing:
        return JsonResponse({
        'status': True,
        'visit_id': str(existing.id),
        'phone_normalized': phone_norm,
        'duplicate': True
    }, status=200)

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
}

# تحديث إذا موجود، أو إنشاء جديد
    visit, created = CampaignVisit.objects.update_or_create (
    visit_id=visitorId,  # المفتاح الأساسي لربط الزائر
    defaults=defaults_data
            )

    return JsonResponse({
        'status': True,
        'visit_id': str(visit.id),
        'phone_normalized': phone_norm
    }, status=201)


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
    context = {
        'has_password': request.user.has_usable_password(),
        'campaigns_metrics': campaigns_metrics,   # list of per-(utm,ad) dicts
        'totals': totals,
        'recent_orders': recent_orders,
        'recent_visits': recent_visits,
        'unmatched_orders_count': unmatched_orders_count,
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

from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

def analytics_view_data(request,platform="all", period_days=7):
    """
    Return simplified analytics payload:
      - KPIs
      - campaigns: list of campaigns each with adsets -> ads -> placements
    Uses CampaignVisit fields (utm_campaign, utm_source, ad_id, site_source_name, ad_adset_name)
    and ExternalOrder.matched_visit FK to join orders -> visits.
    """
    now = timezone.now()
    start_date = now - timedelta(days=period_days)

    # فلترة عامة
    orders_qs = ExternalOrder.objects.filter(matched_visit__user = request.user ,  created_at__gte=start_date)
    visits_qs = CampaignVisit.objects.filter(user= request.user,created_at__gte=start_date)

    if platform and platform != "all":
        orders_qs = orders_qs.filter(platform=platform)
        visits_qs = visits_qs.filter(utm_source=platform)

    # ---------- KPIs عامة ----------
    total_orders = orders_qs.count()
    confirmed_orders = orders_qs.filter(status="confirmed").count()
    shipped_orders = orders_qs.filter(status="shipped").count()
    delivered_orders = orders_qs.filter(status="delivered").count()
    cancelled_orders = orders_qs.filter(status="cancelled").count()
    total_visits = visits_qs.count()
    matched_visits = orders_qs.filter(matched_visit__isnull=False).count()

    kpis = {
        "total_orders": total_orders,
        "confirmed_orders": confirmed_orders,
        "shipped_orders": shipped_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "total_visits": total_visits,
        "matched_visits": matched_visits,
        # keep fraction (0..1) or percentage? We return fraction for consistent frontend formatting
        "confirmation_rate": (confirmed_orders / total_orders) if total_orders else 0.0
    }

    # ---------- visits per campaign (map) ----------
    visits_by_campaign = visits_qs.values('utm_campaign').annotate(visits=Count('id'))
    # build map: campaign_name -> visits count
    visits_map = { item['utm_campaign'] or '': item['visits'] for item in visits_by_campaign }

    # ---------- aggregate orders that are linked to visits ----------
    orders_linked = orders_qs.filter(matched_visit__isnull=False)

    # aggregate per campaign (orders + confirmed)
    orders_by_campaign = (
        orders_linked
        .values('matched_visit__utm_campaign', 'matched_visit__utm_source')
        .annotate(
            orders=Count('id'),
            confirmed=Count('id', filter=Q(status='confirmed'))
        )
    )

    campaigns = {}
    for row in orders_by_campaign:
        camp_name = row.get('matched_visit__utm_campaign') or 'Unknown'
        platform_label = row.get('matched_visit__utm_source') or ''
        if camp_name not in campaigns:
            campaigns[camp_name] = {
                "campaign_name": camp_name,
                "platform_label": platform_label,
                "orders": 0,
                "confirmed_orders": 0,
                "visits": visits_map.get(camp_name, 0),
                "adsets": {},                # will hold ad_id -> adset info
                "site_sources": set(),       # collect unique site_source_name values for the campaign
            }
        campaigns[camp_name]["orders"] += row.get('orders', 0)
        campaigns[camp_name]["confirmed_orders"] += row.get('confirmed', 0)

    # ---------- aggregate per ad (and collect ad_adset_name + site_source_name) ----------
    # include matched_visit__ad_adset_name and matched_visit__site_source_name in grouping
    ads_by_key = (
        orders_linked
        .values(
            'matched_visit__utm_campaign',
            'matched_visit__ad_id',
            'matched_visit__site_source_name',
            'matched_visit__ad_adset_name',
            'matched_visit__utm_medium'  # placements
        )
        .annotate(
            orders=Count('id'),
            confirmed=Count('id', filter=Q(status='confirmed'))
        )
    )

    for row in ads_by_key:
        camp_name = row.get('matched_visit__utm_campaign') or 'Unknown'
        ad_id = row.get('matched_visit__ad_id') or 'unknown_ad'
        placement = row.get('matched_visit__utm_medium') or None
        ad_adset_name = row.get('matched_visit__ad_adset_name') or ''  # the ad/adset name from CampaignVisit

        if camp_name not in campaigns:
            # campaign had no orders in previous step but found here -> initialize
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
                                # placement_name -> metrics
                "ad_adset_name": ad_adset_name  # attach the ad/adset name discovered
            }
        adsets[ad_id]["orders"] += row.get('orders', 0)
        adsets[ad_id]["confirmed_orders"] += row.get('confirmed', 0)

        # collect site_source at campaign level
        if placement:
            campaigns[camp_name]["site_sources"].add(placement)

        # placement aggregation per ad
        if placement:
            pls = adsets[ad_id]["placements"]
            if placement not in pls:
                pls[placement] = {"placement": placement, "site_source_name": placement, "orders": 0}
            pls[placement]["orders"] += row.get('orders', 0)

    # ---------- build final list for frontend ----------
    campaigns_list = []
    for camp_name, info in campaigns.items():
        adsets_list = []
        for ad_key, ad_info in info["adsets"].items():
            ad_visits = 0  # we don't have per-ad visits unless stored separately
            orders_n = ad_info["orders"]
            confirmed_n = ad_info["confirmed_orders"]
            conv_by_visits = (confirmed_n / ad_visits) if ad_visits else None
            conv_by_orders = (confirmed_n / orders_n) if orders_n else None

            placements = [v for v in ad_info["placements"].values()]
            adsets_list.append({
                "ad_id": ad_info["ad_id"],
                "orders": orders_n,
                "confirmed_orders": confirmed_n,
                "visits": ad_visits,
                "conversion_by_visits": round(conv_by_visits, 4) if conv_by_visits is not None else None,
                "conversion_by_orders": round(conv_by_orders, 4) if conv_by_orders is not None else None,
                "placements": placements,
                "ad_adset_name": ad_info.get("ad_adset_name", "")
            })

        camp_orders = info["orders"]
        camp_confirmed = info["confirmed_orders"]
        camp_visits = info["visits"] or 0
        conv_vis = (camp_confirmed / camp_visits) if camp_visits else None
        conv_ord = (camp_confirmed / camp_orders) if camp_orders else None

        campaigns_list.append({
            "campaign_name": info["campaign_name"],
            "platform_label": info["platform_label"],
            "campaign_id": "",   # you can fill from other sources if you store campaign ids
            "orders": camp_orders,
            "confirmed_orders": camp_confirmed,
            "visits": camp_visits,
            "conversion_by_visits": round(conv_vis, 4) if conv_vis is not None else None,
            "conversion_by_orders": round(conv_ord, 4) if conv_ord is not None else None,
            "adsets": adsets_list,
            # expose campaign-level site sources as list
            "site_sources": sorted(list(info["site_sources"]))
        })

    # include campaigns that had visits but no orders
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
                "site_sources": []
            })

    campaigns_list.sort(key=lambda x: x.get('orders', 0), reverse=True)

    payload = {
        "kpis": kpis,
        "campaigns": campaigns_list,
        # "orders": orders_qs.values(),  # أو أي تحويل تحتاجه
        "orders": list(orders_qs.values(
            'external_order_id', 'platform', 'status', 'customer_name',
            'phone_normalized', 'created_at', 'matched_visit__utm_campaign',
            'matched_visit__utm_source', 'matched_visit__utm_medium',
            'matched_visit__ad_id'
        )),
        "last_update": timezone.now().isoformat()
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
    qs = Products.objects.filter(admin = request.user).order_by('name')[:5000]  # limit if needed
    products = [{'id': str(p.id), 'name': p.name} for p in qs]
    return JsonResponse({'products': products})

# ========== get permissions for user (expanded) ==========
@login_required
@require_GET
def get_permissions_for_user(request):
    user_id = request.GET.get('user_id')
    if not user_id:
        return HttpResponseBadRequest(json.dumps({'error':'missing_user_id'}), content_type='application/json')

    # try:
    #     target_user = CustomUser.objects.get(pk=user_id)
    # except CustomUser.DoesNotExist:
    #     return HttpResponseBadRequest(json.dumps({'error':'invalid_user_id'}), content_type='application/json')
    target_user = CustomUser.objects.get(pk=user_id)
    # Authorization: staff or the user themself (tune to your needs)
    if not (request.user.is_staff or request.user == target_user):
        return HttpResponseForbidden(json.dumps({'error':'forbidden'}), content_type='application/json')

    perms_qs = UserProductPermission.objects.filter(user=target_user).select_related('product')
    perms = []
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

    return JsonResponse({'status':'ok', 'user_id': str(target_user.id), 'permissions': perms, 'global_permissions': global_permissions})

# ========== bulk update endpoint ==========
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

    if not user_id:
        return HttpResponseBadRequest(json.dumps({'error':'missing_user_id'}), content_type='application/json')

    try:
        target_user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return HttpResponseBadRequest(json.dumps({'error':'invalid_user_id'}), content_type='application/json')

    # apply updates in a transaction
    results = {'created':[], 'updated':[], 'deleted':[]}
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

 