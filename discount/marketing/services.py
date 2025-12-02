# your_app/services.py
"""
الخدمات التي تتعامل مع مزودي التتبع (COD proxy و شركات الشحن المباشرة).
ضع هنا فقط الأمور الضرورية:
- fetch_orders_from_cod: نموذج لاسترجاع الطلبات من الوسيط (COD proxy).
- fetch_tracking_status: نموذج لاسترجاع حالة تتبع بواسطة tracking_number من شركة الشحن المباشرة.
*/
"""
import os
import requests
import logging
from django.utils import timezone
from discount.models import ExternalOrder, CampaignVisit

logger = logging.getLogger(__name__)

COD_API_BASE = os.environ.get('COD_BASE_URL', 'https://api.cod.network')  # ضع في ENV القيمة الحقيقية
COD_API_KEY = os.environ.get('COD_API_KEY', '')
 
# مثال عام: استبدل المسارات والحقول حسب وثائق المزود لديك
def fetch_orders_from_cod(since=None, limit=100):
    
    """جلب قائمة الطلبات من وسيط COD. يعيد لائحة من dicts (كل dict هو payload لطلب).
    يُنصح ضبط since و pagination حسب واجهة الـ API الحقيقية.
    """
    headers = {'Authorization': f'Bearer {COD_API_KEY}', 'Accept': 'application/json'}
    params = {'limit': limit}
    if since:
        params['since'] = since.isoformat()
    try:
        resp = requests.get(f"{COD_API_BASE}/v1/orders", params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        # تفكيك حسب شكل الاستجابة الحقيقية — المثال يفترض key 'data'
        return payload.get('data', []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.exception("Error fetching COD orders: %s", e)
        return []


def fetch_tracking_status_from_carrier(tracking_number, carrier_api_url=None, api_key=None):
    """
    طلب حالة التتبع من شركة الشحن المباشرة باستخدام tracking_number.
    carrier_api_url: نقطة النهاية لطلب التتبع (تختلف حسب شركة الشحن).
    يُرجع dict على الأقل يحتوي على {'status': 'delivered'|'shipped'|... , 'raw': payload}
    **هنا قالب عام — عدله ليتناسب مع API الشحن التي تستخدمها.**
    """
    if not tracking_number:
        return {'status': 'unknown', 'raw': {}}
    try:
        # مثال: بعض شركات الشحن لديها endpoint GET /track/{tracking}
        if not carrier_api_url:
            # لا نعرف الشاحن لذلك نرجع unknown
            return {'status': 'unknown', 'raw': {}}
        resp = requests.get(f"{carrier_api_url.rstrip('/')}/track/{tracking_number}", timeout=20, headers={'Authorization': f"Bearer {api_key}"} if api_key else {})
        resp.raise_for_status()
        data = resp.json()
        # تحويل حالة الشركة لـ one of our states (مثال تقريبي)
        carrier_status = data.get('status') or data.get('delivery_status') or ''
        mapped = 'unknown'
        if 'deliv' in carrier_status.lower():
            mapped = 'delivered'
        elif 'ship' in carrier_status.lower() or 'out for delivery' in carrier_status.lower():
            mapped = 'shipped'
        elif 'created' in carrier_status.lower() or 'pending' in carrier_status.lower():
            mapped = 'created'
        return {'status': mapped, 'raw': data}
    except Exception as e:
        logger.exception("Error fetching tracking for %s : %s", tracking_number, e)
        return {'status': 'unknown', 'raw': {}}








import requests
from django.utils import timezone
from discount.models import ExternalOrder, CampaignVisit
from django.db import transaction
from django.utils.dateparse import parse_datetime

# معلومات API الخاصة بـ COD (يجب استبدالها بمعلوماتك الحقيقية)
COD_API_URL = "https://api.cod.network/v1/seller/leads"
COD_API_KEY =  "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczpcL1wvc2VsbGVyLmNvZC5uZXR3b3JrXC9jbGllbnRcL2dlbmVyYXRlLWFjY2Vzcy10b2tlbiIsImlhdCI6MTcxMzcxMDY3NSwiZXhwIjoxODcxMzkwNjc1LCJuYmYiOjE3MTM3MTA2NzUsImp0aSI6IjRNMUlabDRMWWRSNDFTdGEiLCJzdWIiOjM0OTgsInBydiI6IjIzYmQ1Yzg5NDlmNjAwYWRiMzllNzAxYzQwMDg3MmRiN2E1OTc2ZjcifQ.RtmBnjw8NxdAJeOU1oGiB15qY49mJXuBcbb8t3TnJcE"


# def searchwithphone(phone):
#     visit = CampaignVisit.objects.filter(raw_phone=phone).first()
#     if visit:
#         return visit.id
#     return None




def normalize_phone_number(raw_phone):
    """
    تطبيع رقم الهاتف ليكون بصيغة موحدة (مثال مبسط)
    """
    import re
    if not raw_phone:
        return None
    digits = re.sub(r'\D', '', raw_phone)
    if digits.startswith('0'):
        digits = '966' + digits[1:]
    elif not digits.startswith('966'):
        digits = '966' + digits
    return digits


def parse_datetime_or_now(date_str):
    """
    يحاول تحويل نص التاريخ إلى datetime، أو يعيد الوقت الحالي إذا فشل.
    """
    dt = parse_datetime(date_str) if date_str else None
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt











import logging
import re
import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from discount.models import ExternalOrder, CampaignVisit

logger = logging.getLogger(__name__)

# استحفظ مفاتيحك في settings.py: COD_API_KEY, COD_API_URL (مثلاً 'https://api.cod.network/v1/seller/leads')
COD_API_KEY = getattr(settings, "COD_API_KEY", None)
COD_API_URL = getattr(settings, "COD_API_URL", "https://api.cod.network/v1/seller/leads")


def normalize_phone_number(raw_phone) :
    """
    تطبيع مبسّط: إزالة غير الأرقام، وإضافة '966' إذا لم يبدأ برمز الدولة.
    عدّل هذه الدالة حسب قواعد أرقام بلدك.
    """
    if not raw_phone:
        return None
    digits = re.sub(r'\D', '', str(raw_phone))
    if not digits:
        return None
    if digits.startswith('0'):
        digits = '966' + digits[1:]
    elif not digits.startswith('966'):
        digits = '966' + digits
    return digits


def parse_datetime_or_now(date_str):
    dt = parse_datetime(date_str) if date_str else None
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@login_required
@require_POST
def fetch_and_update_order_cod(request):
    """
    View: يستدعي COD API (GET /seller/leads) ويعالج النتائج.
    - يقرأ هاتف كل lead، يطبّعه، يبحث عن CampaignVisit.phone_normalized فقط.
    - إن وُجدت زيارة -> create/update ExternalOrder وربطه بتلك الزيارة.
    - إن لم توجد زيارة -> يتخطى (لا ينشئ شيئًا).
    - يُرجع JSON مع إحصاءات المعالجة.
    """
    if not COD_API_KEY:
        return JsonResponse({"status": "error", "message": "COD API key not configured"}, status=500)

    # Optional: allow client to pass filters (e.g., phone) in POST json body
    try:
        payload = {}
        if request.body:
            import json
            payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}

    # We will query COD for leads. If the client provided 'phone' we can pass it to COD to filter.
    phone_filter = payload.get('phone')  # optional: you can pass phone to reduce data
    params = {
        'limit': payload.get('limit', 100),
        'status': payload.get('status', 'all')
    }
    if phone_filter:
        params['phone'] = phone_filter

    headers = {
        "Authorization": f"Bearer {COD_API_KEY}",
        "Accept": "application/json"
    }

    try:
        # COD expects GET for fetching leads
        resp = requests.get(COD_API_URL, headers=headers, params=params, timeout=30)
        text = resp.text
        status_code = resp.status_code
    except requests.RequestException as e:
        logger.exception("Failed to call COD API: %s", e)
        return JsonResponse({"status": "error", "message": f"Failed to call COD API: {str(e)}"}, status=502)

    # Parse response JSON (if any) to find items/leads
    try:
        data = resp.json()
    except Exception as e:
        logger.exception("Invalid JSON from COD: %s; raw=%s", e, text[:1000])
        return JsonResponse({"status": "error", "message": "Invalid JSON from COD", "raw": text[:2000]}, status=502)

    # If COD returned an error structure, surface it
    if status_code >= 400:
        logger.error("COD API error response: %s", data)
        return JsonResponse({"status": "error", "message": "COD API returned error", "details": data}, status=status_code)

    # Try to find list of leads in common keys
    candidate_lists = []
    if isinstance(data, dict):
        # Common shapes: { "data": [...], "status": "...", "meta": {...} }
        if 'data' in data and isinstance(data['data'], list):
            candidate_lists.append(data['data'])
        # Some APIs use 'leads' or 'items' or 'result'
        for k in ('leads', 'items', 'result', 'rows'):
            if k in data and isinstance(data[k], list):
                candidate_lists.append(data[k])
    elif isinstance(data, list):
        candidate_lists.append(data)

    # Flatten first non-empty candidate
    leads_list = []
    for lst in candidate_lists:
        if lst:
            leads_list = lst
            break

    # If still empty, try to find nested lists
    if not leads_list:
        # search for any nested list inside dict values
        for v in (data.values() if isinstance(data, dict) else []):
            if isinstance(v, list) and v:
                leads_list = v
                break

    # If still nothing, return no data
    if not leads_list:
        logger.info("COD returned no leads array; raw response keys: %s", list(data.keys()) if isinstance(data, dict) else 'non-dict')
        return JsonResponse({"status": "ok", "processed": 0, "created": 0, "updated": 0, "skipped_no_phone": 0, "skipped_no_visit": 0, "note": "no leads array in COD response", "raw": data})

    # process each lead
    created = 0
    updated = 0
    skipped_no_phone = 0
    skipped_no_visit = 0
    errors = []

    for item in leads_list:
        # item may be dict representing a lead/order. Be tolerant about field names.
        if not isinstance(item, dict):
            continue

        # Extract phone from common candidate keys
        raw_phone = None
        for key in ('phone', 'customer_phone', 'msisdn', 'phone_number', 'mobile'):
            if key in item and item.get(key):
                raw_phone = item.get(key)
                break
        # Some providers wrap lead inside 'lead' subobject
        if not raw_phone and isinstance(item.get('lead'), dict):
            for key in ('phone', 'customer_phone', 'msisdn', 'phone_number', 'mobile'):
                if item['lead'].get(key):
                    raw_phone = item['lead'].get(key)
                    break

        if not raw_phone:
            skipped_no_phone += 1
            logger.info("Lead skipped: no phone found in item: keys=%s", list(item.keys()))
            continue

        phone_normalized = normalize_phone_number(raw_phone)

        if not phone_normalized:
            skipped_no_phone += 1
            logger.info("Lead skipped: normalization failed for raw_phone=%s", raw_phone)
            continue

        # Find CampaignVisit by phone_normalized ONLY
        visit = CampaignVisit.objects.filter(phone_normalized=phone_normalized).first()
        if not visit:
            skipped_no_visit += 1
            logger.info("Lead skipped: no matching CampaignVisit for phone=%s", phone_normalized)
            continue

        # Determine external_order_id from common keys
        external_id = None
        for key in ('order_id', 'external_order_id', 'id', 'lead_id'):
            if key in item and item.get(key):
                external_id = str(item.get(key))
                break
        # Also check nested 'lead' object
        if not external_id and isinstance(item.get('lead'), dict):
            for key in ('order_id', 'external_order_id', 'id', 'lead_id'):
                if item['lead'].get(key):
                    external_id = str(item['lead'].get(key))
                    break

        # If no external id, skip creation to avoid ambiguous records (per your rule)
        if not external_id:
            logger.info("Lead skipped: no external id for phone=%s; item keys=%s", phone_normalized, list(item.keys()))
            skipped_no_phone += 1
            continue
        
        # Prepare fields
        customer_name = item.get('customer_name') or item.get('name') or (item.get('lead') or {}).get('customer_name') or ''
        status = item.get('status') or (item.get('lead') or {}).get('status') or 'unknown'
        tracking_number = item.get('tracking_number') or (item.get('lead') or {}).get('tracking_number') or ''
        created_at_str = item.get('created_at') or (item.get('lead') or {}).get('created_at')
        created_at = parse_datetime_or_now(created_at_str)

        # Create or update ExternalOrder for this external_id + platform 'cod'
        try:
            with transaction.atomic():
                order, was_created = ExternalOrder.objects.update_or_create(
                    external_order_id=external_id,
                    platform='cod',
                    defaults={
                        'raw_phone': raw_phone,
                        'phone_normalized': phone_normalized,
                        'customer_name': customer_name,
                        'status': status,
                        'tracking_number': tracking_number,
                        'created_at': created_at,
                        'fetched_at': timezone.now(),
                        'matched_visit': visit,
                        'meta': item
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
                 
        except Exception as e:
            logger.exception("Failed to create/update order for external_id=%s: %s", external_id, e)
            errors.append({"external_id": external_id, "error": str(e)})
            continue

    result = {
        "status": "ok",
        "processed": len(leads_list),
        "created": created,
        "updated": updated,
        "skipped_no_phone": skipped_no_phone,
        "skipped_no_visit": skipped_no_visit,
        "errors": errors
    }
     
    return JsonResponse(result)
 