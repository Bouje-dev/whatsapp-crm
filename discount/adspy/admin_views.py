# admin_views.py
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.db.models import Count
import json
from discount.models import UserSavedAd, AdArchive ,AdCreative
from django.contrib.auth import get_user_model
User = get_user_model()
# from discount.models import AdArchive, UserSavedAd
@staff_member_required
def ads_dashboard_view(request: HttpRequest):
    """
    يعرض صفحة الواجهة — القالب يحوي JS الذي يتصل بالـ APIs الأخرى.
    """
    users = User.objects.all()
    ads = AdArchive.objects.all()
    
   

    return render(request, 'admin/ads_dashboard.html', {'users': users ,'ads' : ads})


@staff_member_required
def api_admin_stats(request: HttpRequest):
    """
    يعيد إحصاءات سريعة:عدد الإعلانات المحفوظة، عدد المستخدمين النشطين (مثال)، آخر حفظ.
    """
    total_saved_ads = UserSavedAd.objects.count()
    # عرّف "active users" كما يناسبك. كمثال نعتبر المستخدمين الذين لديهم حفظ خلال آخر 30 يومًا.
    from django.utils import timezone
    from datetime import timedelta
    since = timezone.now() - timedelta(days=30)
    active_users = User.objects.filter(usersavedad__saved_at__gte=since).distinct().count()

    last_saved = UserSavedAd.objects.order_by('-saved_at').values('saved_at').first()
    last_saved_at = last_saved['saved_at'].isoformat() if last_saved and last_saved['saved_at'] else None

    return JsonResponse({
        'total_saved_ads': total_saved_ads,
        'active_users_30d': active_users,
        'last_saved_at': last_saved_at,
    })


@staff_member_required
def api_ads_list(request: HttpRequest):
    """
    Returns paginated list of saved ads joining fields from AdArchive (based on collection_view logic).
    Accepts query params:
      - page (default 1)
      - page_size (default 20)
      - q (search across page_name / advertiser)
      - status / platform (filters)
    """
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    platform = request.GET.get('platform', '').strip()

    # جلب العناصر المحفوظة
    saved_qs = UserSavedAd.objects.select_related('user').all().order_by('-saved_at')

    # يمكن تحسين الأداء بالـ prefetch/select_related للعلاقات
    # تطبيق فلترة بحث على الحقول المطلوبة (page_name, advertiser)
    if q:
        saved_qs = saved_qs.filter(ad_id__in=AdArchive.objects.filter(
            page_name__icontains=q
        ).values_list('ad_id', flat=True))

    # بناء قائمة النتائج كما في collection_view
    results = []
    ad_ids = [s.ad_id for s in saved_qs]
    # جلب Ads دفعة واحدة للمساعدة في الأداء
    ads_map = {a.ad_id: a for a in AdArchive.objects.filter(ad_id__in=ad_ids).select_related('advertiser', 'creative', 'country')}

    for saved in saved_qs:
        ad = ads_map.get(saved.ad_id)
        if not ad:
            continue
        results.append({
            'saved_id': saved.id,
            'advertiser': ad.advertiser.name if getattr(ad, 'advertiser', None) else (ad.page_name or ''),
            'page_name': ad.page_name,
            'thumbnail': (ad.creative.thumbnail_url if getattr(ad, 'creative', None) and getattr(ad.creative, 'thumbnail_url', None)
                          else (f"/media/creatives/{ad.creative.image_hash}.jpg" if getattr(ad, 'creative', None) and getattr(ad.creative, 'image_hash', None) else None)),
            'is_video': bool((getattr(ad, 'creative', None) and getattr(ad.creative, 'is_video', False)) or getattr(ad, 'creative', None) and getattr(ad.creative, 'video_url', None)),
            'adsets_count': ad.adsets_count,
            'impressions': ad.impressions,
            'spend': ad.spend,
            'ctas': [cta.name for cta in ad.ctas.all()],
            'country': {'code': ad.country.code, 'name': ad.country.name} if getattr(ad, 'country', None) else None,
            'published': ad.ad_delivery_start_time.strftime('%Y-%m-%d') if getattr(ad, 'ad_delivery_start_time', None) else None,
            'platform': ad.platform,
            'status': ad.status,
            'ad_snapshot_url': ad.ad_snapshot_url,
            # collection info
            'ad_id': saved.ad_id,
            'saved_at': saved.saved_at.isoformat() if saved.saved_at else None,
            'note': saved.note or '',
        })

    # pagination on results list (since we built it in Python)
    paginator = Paginator(results, page_size)
    page_obj = paginator.get_page(page)

    return JsonResponse({
        'count': paginator.count,
        'num_pages': paginator.num_pages,
        'page': page_obj.number,
        'results': list(page_obj.object_list),
    })


@staff_member_required
@require_http_methods(['POST'])
def api_refresh_collection(request: HttpRequest):
    """
    مثال لدالة تُعيد جلب أو تحديث الـ collection من مصدر خارجي.
    في مشروعك يجب تضع هنا المنطق الفعلي للتحديث (مثلاً تفريغ كاش أو تشغيل مهمة خلفية).
    """
    # مثال بسيط: نعيد إحصاءات بعد "تحديث" وهمي
    # لو عندك وظيفة حقيقية لاستيراد/تحديث الموارد استدعها هنا.
    return JsonResponse({'ok': True, 'message': 'Refresh triggered (implement actual refresh logic).'})

@staff_member_required
@require_http_methods(['DELETE'])
def api_delete_saved_ad(request: HttpRequest, saved_id: int):
    """
    حذف عنصر محفوظ من مجموعه (by saved_id).
    """
    obj = get_object_or_404(UserSavedAd, id=saved_id)
    obj.delete()
    return JsonResponse({'ok': True})



















 
import json
import logging
import time
import requests
import traceback
from decimal import Decimal, InvalidOperation
from typing import Iterable, Dict, Any, Optional, Tuple, List

from django.conf import settings
from django.db import transaction, IntegrityError, DataError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from discount.models import AdArchive, AdCreative, Advertiser, Country, CTA, Tag

logger = logging.getLogger(__name__)

FB_API_VERSION = getattr(settings, "FB_API_VERSION", "v23.0")
FB_GRAPH_BASE = "https://graph.facebook.com"
FB_PAGE_SIZE = getattr(settings, "FB_PAGE_SIZE", 50)

# مجموعة رموز facebook المدعومة (مقتطف، ويمكن توسيعها كما تحتاج)
FB_ALLOWED = {
    "ALL","BR","IN","GB","US","CA","AR","AU","AT","BE","CL","CN","CO","HR","DK","DO","EG",
    "FI","FR","DE","GR","HK","ID","IE","IL","IT","JP","JO","KW","LB","MY","MX","NL","NZ",
    "NG","NO","PK","PA","PE","PH","PL","RU","SA","RS","SG","ZA","KR","ES","SE","CH","TW",
    "TH","TR","AE","VE","PT","LU","BG","CZ","SI","IS","SK","LT","TT","BD","LK","KE","HU",
    "MA","CY","JM","EC","RO","BO","GT","CR","QA","SV","HN","NI","PY","UY","PR","BA","PS",
    "TN","BH","VN","GH","MU","UA","MT","BS","MV","OM","MK","LV","EE","IQ","DZ","AL","NP",
    "MO","ME","SN","GE","BN","UG","GP","BB","AZ","TZ","LY","MQ","CM","BW","ET","KZ","NA",
    "MG","NC","MD","FJ","BY","JE","GU","YE","ZM","IM","HT","KH","AW","PF","AF","BM","GY",
    "AM","MW","AG","RW","GG","GM","FO","LC","KY","BJ","AD","GD","VI","BZ","VC","MN","MZ",
    "ML","AO","GF","UZ","DJ","BF","MC","TG","GL","GA","GI","CD","KG","PG","BT","KN","SZ",
    "LS","LA","LI","MP","SR","SC","VG","TC","DM","MR","AX","SM","SL","NE","CG","AI","YT",
    "CV","GN","TM","BI","TJ","VU","SB","ER","WS","AS","FK","GQ","TO","KM","PW","FM","CF",
    "SO","MH","VA","TD","KI","ST","TV","NR","RE","LR","ZW","CI","MM","AN","AQ","BQ","BV",
    "IO","CX","CC","CK","CW","TF","GW","HM","XK","MS","NU","NF","PN","BL","SH","MF","PM",
    "SX","GS","SS","SJ","TL","TK","UM","WF","EH"
}


def _parse_dt_make_aware(dt_str: Optional[str]):
    if not dt_str:
        return None
    dt = parse_datetime(dt_str)
    if dt is None:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(dt_str)
        except Exception:
            return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_default_timezone())
    return dt


def _safe_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _normalize_countries_param(countries: Optional[Iterable[str]]):
    """
    يحوّل input إلى شكل مناسب لباراميتر ad_reached_countries:
    - إن كانت "ALL" تعيد "ALL"
    - إن كانت قائمة تعيد JSON dumped list مع رموز مُنقّحة ومقبولة
    - إن لم يوجد شيء تعيد None
    """
    if not countries:
        return None
    if isinstance(countries, str):
        countries_list = [countries.strip().upper()]
    else:
        countries_list = [str(c).strip().upper() for c in list(countries) if c]
    countries_list = [c for c in countries_list if c]
    if not countries_list:
        return None
    if len(countries_list) == 1 and countries_list[0] == "ALL":
        return "ALL"
    filtered = [c for c in countries_list if c in FB_ALLOWED]
    return json.dumps(filtered) if filtered else None


def fetch_ads_from_ad_library(
    access_token: str,
    search_terms: Optional[str] = None,
    countries: Optional[Iterable[str]] = None,
    ad_type: Optional[str] = None,
    limit_per_page: int = FB_PAGE_SIZE,
    max_pages: Optional[int] = None,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    debug: bool = False
) -> Iterable[Dict[str, Any]]:
    """
    Generator: يمرّر إعلانات واحدةً تلو الأخرى.
    """
    api = FB_API_VERSION
    url = f"{FB_GRAPH_BASE}/{api}/ads_archive"

    base_fields = [
        "ad_library_id",
        "id",
        "page_id",
        "page_name",
        "ad_snapshot_url",
        "ad_creation_time",
        "ad_delivery_start_time",
        "ad_delivery_stop_time",
        "ad_creative_bodies",
        "publisher_platforms",
        "ad_active_status",
        "ad_reached_countries",
        "demographic_distribution",
        "impressions",
        "spend",
        "bylines",
        # يمكنك توسيع الحقول عند الحاجة
    ]

    params = {
        "access_token": access_token,
        "limit": limit_per_page,
        "fields": ",".join(base_fields)
    }

    if search_terms:
        params["search_terms"] = search_terms
    countries_param = _normalize_countries_param(countries)
    if countries_param:
        params["ad_reached_countries"] = countries_param
    if ad_type:
        params["ad_type"] = ad_type

    session = requests.Session()
    session.headers.update({
        "User-Agent": "AdSpy/1.0",
        "Accept": "application/json"
    })

    pages_fetched = 0
    next_url = None
    last_payload = None

    while True:
        attempt = 0
        while True:
            attempt += 1
            try:
                if debug:
                    logger.info("FB request attempt %d url=%s params=%s", attempt, next_url or url, None if next_url else params)
                resp = session.get(next_url or url, params=params if not next_url else None, timeout=30)
                status = resp.status_code

                if status == 200:
                    break

                # handle rate limiting and server errors with backoff
                if status in (429, 503):
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else (backoff_factor * (2 ** (attempt - 1)))
                    logger.warning("FB returned %s. waiting %s seconds. body=%s", status, wait, resp.text)
                    time.sleep(wait)
                    if attempt >= max_retries:
                        raise RuntimeError(f"Max retries reached for status {status}. last resp: {resp.text}")
                    continue

                if 500 <= status < 600:
                    wait = backoff_factor * (2 ** (attempt - 1))
                    logger.warning("FB server error %s. retrying in %s sec. body=%s", status, wait, resp.text)
                    time.sleep(wait)
                    if attempt >= max_retries:
                        raise RuntimeError(f"Facebook API server error {status}. body: {resp.text}")
                    continue

                # 4xx errors: return helpful message
                try:
                    body = resp.json()
                    
                except Exception:
                    body = resp.text
                raise RuntimeError(f"Facebook API error {status}: {body}")

            except requests.RequestException as e:
                wait = backoff_factor * (2 ** (attempt - 1))
                logger.exception("Network error when calling Facebook API. attempt %s. will wait %s", attempt, wait)
                time.sleep(wait)
                if attempt >= max_retries:
                    raise RuntimeError(f"Network error calling Facebook API. last error: {e}")

        # success: parse payload
        try:
            payload = resp.json()
        except ValueError:
            logger.error("Non-JSON response from Facebook: %s", resp.text)
            raise RuntimeError(f"Non-JSON response from Facebook: {resp.text}")

        last_payload = payload
        data = payload.get("data", [])
        
        if debug:
            logger.info("Fetched page items=%d paging=%s", len(data), payload.get("paging"))

        for item in data:
            yield item

        pages_fetched += 1
        if max_pages and pages_fetched >= max_pages:
            break

        paging = payload.get("paging", {})
        next_url = paging.get("next")
        if not next_url:
            break














# save vetched ad 
# ضع هذا في ملف facebook_adlib.py أو مكان الدوال لديك
import json
import logging
import traceback
import re
import requests
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, Tuple, List

from django.conf import settings
from django.db import transaction, IntegrityError, DataError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from discount.models import AdArchive, AdCreative, Advertiser, Country, CTA, Tag

logger = logging.getLogger(__name__)

FB_API_VERSION = getattr(settings, "FB_API_VERSION", "v23.0")
FB_GRAPH_BASE = getattr(settings, "FB_GRAPH_BASE", "https://graph.facebook.com")


# ----------------- مساعدات لتحويل التواريخ/الأرقام -----------------
def _parse_dt_make_aware(dt_str: Optional[str]):
    if not dt_str:
        return None
    dt = parse_datetime(dt_str)
    if dt is None:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(dt_str)
        except Exception:
            return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_default_timezone())
    return dt

_impression_re = re.compile(r'[\d,]+')
_money_re = re.compile(r'[-+]?[0-9]*[.,]?[0-9]+')

def _parse_int_from_string(s):
    if s is None:
        return None
    try:
        if isinstance(s, (int, float)):
            return int(s)
        s = str(s).strip()
        m = _impression_re.search(s)
        if m:
            val = m.group(0).replace(',', '')
            return int(val)
        # fallback: any digits
        m2 = re.search(r'\d+', s.replace(',', ''))
        if m2:
            return int(m2.group(0))
        return None
    except Exception:
        return None

def _parse_decimal_from_string(s):
    if s is None:
        return None
    try:
        if isinstance(s, (int, float, Decimal)):
            return Decimal(str(s))
        s = str(s).strip()
        # remove thousands separators then find number
        s_clean = s.replace(',', '')
        m = _money_re.search(s_clean)
        if not m:
            return None
        return Decimal(m.group(0))
    except (InvalidOperation, ValueError, TypeError):
        return None

def _extract_metric(value, prefer='avg'):
    if value is None:
        return None
    # dict => range
    if isinstance(value, dict):
        min_keys = ('min', 'lower_bound', 'lower')
        max_keys = ('max', 'upper_bound', 'upper')
        min_val = None
        max_val = None
        for k in min_keys:
            if k in value and value[k] is not None:
                min_val = value[k]
                break
        for k in max_keys:
            if k in value and value[k] is not None:
                max_val = value[k]
                break
        min_n = _parse_decimal_from_string(min_val) if min_val is not None else None
        max_n = _parse_decimal_from_string(max_val) if max_val is not None else None
        if min_n is not None and max_n is not None:
            if prefer == 'min':
                return min_n
            if prefer == 'max':
                return max_n
            try:
                return (min_n + max_n) / 2
            except Exception:
                return min_n
        if min_n is not None:
            return min_n
        if max_n is not None:
            return max_n
        return None
    # list/tuple
    if isinstance(value, (list, tuple)):
        for v in value:
            res = _extract_metric(v, prefer=prefer)
            if res is not None:
                return res
        return None
    # numeric/text
    int_candidate = _parse_int_from_string(value)
    if int_candidate is not None:
        return int_candidate
    dec_candidate = _parse_decimal_from_string(value)
    if dec_candidate is not None:
        return dec_candidate
    return None


# ----------------- محاولة جلب creatives مفصلة من Marketing API -----------------
def _fetch_creatives_for_ad(ad_identifier: str, access_token: Optional[str] = None):
    """
    يحاول استدعاء /{ad_id}/adcreatives لإحضار thumbnail_url, video_id, body, object_story_spec إن أمكن.
    يعيد قائمة creatives (كل عنصر dict) أو [] عند الفشل.
    يحتاج access_token صالح (server token أفضل).
    """
    if not access_token:
        return []
    url = f"{FB_GRAPH_BASE}/{FB_API_VERSION}/{ad_identifier}/adcreatives"
    params = {
        "access_token": access_token,
        "fields": "id,body,thumbnail_url,object_story_spec,video_id"
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            logger.debug("Failed to fetch creatives for %s: %s", ad_identifier, resp.text)
            return []
        payload = resp.json()
        return payload.get("data", []) or []
    except Exception as e:
        logger.exception("Exception fetching creatives for %s: %s", ad_identifier, e)
        return []


def _fetch_video_source(video_id: str, access_token: Optional[str] = None) -> Optional[str]:
    if not access_token or not video_id:
        return None
    url = f"{FB_GRAPH_BASE}/{FB_API_VERSION}/{video_id}"
    params = {"access_token": access_token, "fields": "source,length"}
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            logger.debug("Failed to fetch video %s: %s", video_id, resp.text)
            return None
        payload = resp.json()
        return payload.get("source")
    except Exception:
        return None


# ----------------- الدالة الرئيسية المحسّنة للحفظ -----------------
@transaction.atomic
def save_ad_and_creatives_safe(ad_json: Dict[str, Any], access_token: Optional[str] = None) -> Tuple[Optional[AdArchive], Optional[Dict[str, Any]]]:
    """
    يحاول حفظ AdCreative و AdArchive.
    يعيد (ad_obj, None) عند النجاح أو (None, {"error":..., "traceback":...}) عند الفشل.
    """
    try:
        ad_id = ad_json.get("ad_library_id") or ad_json.get("id")
        if not ad_id:
            return None, {"error": "missing ad id", "payload_summary": str(ad_json)[:200]}

        # page info
        page_name = ad_json.get("page_name") or ad_json.get("byline") or "Unknown"
        page_id = ad_json.get("page_id")  # انت لديك حقل page_id فريد في Advertiser

        # Advertiser: ربط/إنشاء باستخدام page_id إن توفر، وإلا باسم الصفحة
        advertiser = None
        try:
            if page_id:
                advertiser, created = Advertiser.objects.get_or_create(page_id=str(page_id), defaults={"name": page_name})
            else:
                advertiser, created = Advertiser.objects.get_or_create(name=page_name, defaults={})
        except Exception as ex:
            logger.exception("Advertiser creation error page_id=%s page_name=%s: %s", page_id, page_name, ex)
            advertiser = None

        # country
        country_obj = None
        try:
            reached = ad_json.get("ad_reached_countries") or ad_json.get("countries") or []
            if isinstance(reached, str):
                reached = [reached]
            if isinstance(reached, (list, tuple)) and len(reached) > 0:
                first_iso = str(reached[0]).strip().upper()
                if first_iso:
                    country_obj = Country.objects.filter(code__iexact=first_iso).first()
        except Exception:
            country_obj = None

        # CTAs and tags
        ctas = []
        tags = []
        try:
            raw_ctas = ad_json.get("call_to_action") or ad_json.get("ctas") or []
            if raw_ctas and isinstance(raw_ctas, (list, tuple)):
                for c in raw_ctas:
                    name = str(c).strip()
                    if name:
                        obj, _ = CTA.objects.get_or_create(name=name)
                        ctas.append(obj)
            raw_tags = ad_json.get("tags") or ad_json.get("bylines") or []
            if raw_tags and isinstance(raw_tags, (list, tuple)):
                for t in raw_tags:
                    name = str(t).strip()
                    if name:
                        obj, _ = Tag.objects.get_or_create(name=name)
                        tags.append(obj)
        except Exception:
            logger.exception("Error processing CTAs/Tags for ad %s", ad_id)

        # Body text
        bodies = ad_json.get("ad_creative_bodies") or []
        if isinstance(bodies, str):
            body_text = bodies
        elif isinstance(bodies, (list, tuple)):
            body_text = "\n".join(str(x) for x in bodies if x)
        else:
            body_text = str(bodies) if bodies else None

        # محاولة جلب creatives مفصلة من Marketing API (إن كان access_token متاح)
        thumbnail_url = ad_json.get("ad_snapshot_url") or None
        video_id = None
        video_url = None
        is_video = False

        try:
            creatives = _fetch_creatives_for_ad(ad_id, access_token)
            if creatives:
                first_creative = creatives[0]
                # أخذ body إن لم يكن متوفرًا
                if not body_text:
                    body_text = first_creative.get("body") or body_text
                # thumbnail
                thumb = first_creative.get("thumbnail_url") or None
                if thumb:
                    thumbnail_url = thumb
                # video id
                vid = first_creative.get("video_id")
                if vid:
                    video_id = vid
                    is_video = True
                    # حاول جلب source الفيديو
                    source = _fetch_video_source(video_id, access_token)
                    if source:
                        video_url = source
        except Exception:
            logger.exception("Error fetching creatives for ad %s", ad_id)

        creative_id = f"creative_{ad_id}"
        # حفظ أو تحديث AdCreative
        creative_obj, created = AdCreative.objects.update_or_create(
            creative_id=creative_id,
            defaults={
                "body": body_text,
                "thumbnail_url": thumbnail_url,
                "video_id": video_id,
                "video_url": video_url,
                "is_video": bool(is_video),
            }
        )

        # تواريخ
        ad_delivery_start = _parse_dt_make_aware(ad_json.get("ad_delivery_start_time"))
        ad_delivery_stop = _parse_dt_make_aware(ad_json.get("ad_delivery_stop_time"))

        # استخراج impressions و spend بمتانة
        raw_impr = ad_json.get("impressions") or ad_json.get("estimated_impressions") or None
        impr_val = _extract_metric(raw_impr, prefer='avg')
        if isinstance(impr_val, Decimal):
            try:
                impressions_final = int(impr_val.to_integral_value(rounding='ROUND_HALF_UP'))
            except Exception:
                impressions_final = int(impr_val)
        elif isinstance(impr_val, (int,)):
            impressions_final = int(impr_val)
        else:
            impressions_final = None

        raw_spend = ad_json.get("spend") or ad_json.get("estimated_spend") or None
        spend_val = _extract_metric(raw_spend, prefer='avg')
        if isinstance(spend_val, Decimal):
            try:
                spend_final = spend_val.quantize(Decimal("0.01"))
            except Exception:
                spend_final = Decimal(str(spend_val)).quantize(Decimal("0.01"))
        elif isinstance(spend_val, (int, float)):
            spend_final = Decimal(str(spend_val)).quantize(Decimal("0.01"))
        else:
            spend_final = None

        # حالة الإعلان
        status = ad_json.get("ad_active_status") or ("ACTIVE" if (not ad_delivery_stop or ad_delivery_stop > timezone.now()) else "INACTIVE")

        # حفظ AdArchive باستخدام ad_id كحقل فريد لمنع التكرار
        ad_obj, created = AdArchive.objects.update_or_create(
            ad_id=ad_id,
            defaults={
                "advertiser": advertiser,
                "page_name": page_name,
                "ad_snapshot_url": ad_json.get("ad_snapshot_url") or thumbnail_url,
                "landing_url": ad_json.get("landing_url") or ad_json.get("call_to_action_link") or None,
                "platform": ",".join(ad_json.get("publisher_platforms") or []) if ad_json.get("publisher_platforms") else None,
                "country": country_obj,
                "status": status,
                "ad_delivery_start_time": ad_delivery_start,
                "ad_delivery_stop_time": ad_delivery_stop,
                "raw_json": ad_json,
                "creative": creative_obj,
                "impressions": impressions_final,
                "spend": spend_final,
            }
        )

        # ربط CTAs و Tags
        if ctas:
            try:
                ad_obj.ctas.set(ctas)
            except Exception:
                logger.exception("Failed to set ctas for ad %s", ad_id)
        if tags:
            try:
                ad_obj.tags.set(tags)
            except Exception:
                logger.exception("Failed to set tags for ad %s", ad_id)

        ad_obj.save()
        return ad_obj, None

    except (IntegrityError, DataError) as db_err:
        tb = traceback.format_exc()
        logger.exception("DB error saving ad %s: %s", ad_json.get("ad_library_id") or ad_json.get("id"), db_err)
        transaction.set_rollback(True)
        return None, {"error": str(db_err), "traceback": tb}
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception("Unexpected error saving ad %s: %s", ad_json.get("ad_library_id") or ad_json.get("id"), e)
        transaction.set_rollback(True)
        return None, {"error": str(e), "traceback": tb}



 
def fetch_and_store_ads(access_token: str, search_terms: Optional[str] = None, countries: Optional[Iterable[str]] = None, ad_type: Optional[str] = None, max_pages: Optional[int] = 2, debug: bool = False):
    fetched = 0
    saved_ids: List[str] = []
    errors: List[Dict[str, Any]] = []
    for ad_json in fetch_ads_from_ad_library(access_token, search_terms, countries, ad_type, max_pages=max_pages, debug=debug):
        fetched += 1
        ad_obj, err = save_ad_and_creatives_safe(ad_json, access_token)
        if ad_obj:
            saved_ids.append(ad_obj.ad_id)
        else:
            errors.append({
                "ad": ad_json.get("ad_library_id") or ad_json.get("id"),
                "error": err.get("error") if err else "unknown",
                "traceback": err.get("traceback")[:2000] if err and err.get("traceback") else None
            })
    return {"fetched": fetched, "saved_count": len(saved_ids), "ids": saved_ids, "errors": errors}






 
  
# @csrf_exempt
# @require_POST
# def fetch_ads_view(request):
#     """
#     endpoint يستدعى عبر زر في الواجهة. يتوقع POST مع حقول:
#     access_token (إن لم يكن مخزنًا في env) ، search_terms ، country (ككود ISO)
#     """
#     # access_token = "EAAUwb6OhLh8BPhPziyZACMcfd87yZB3ZAblDnBSgcRgpHf6fdqzZCWt5HrG6OIQn4DibE8ey1ySZBHZClWeX3wE4X5PcWNxOfTMoPgZACiQHur9dRcZCcwwaXTOi4H7vEO95ipl4jRLKBt4dZCVi2JtSxz2COvSzmw9R7VvSH7ko4jorSNc9wTrXky4b64ZABgv7Q4nzKhCSR1WZCI2Tpk1Dw0OF2dMzJd4g0W8N5ZCC6u5eMxZCKPlCbkhcynwZDZD"
#     access_token = getattr(settings, 'FACEBOOK_ACCESS_TOKEN', None)
#     if not access_token:
#         return HttpResponseBadRequest("missing access token")

#     try:
#         payload = json.loads(request.body.decode('utf-8'))
#     except Exception:
#         return HttpResponseBadRequest("Invalid JSON body")

#     search_terms = (payload.get('search_terms') or "").strip()
#     country = (payload.get('country') or "").strip().upper()
#     # max_pages = int(payload.get('max_pages') or MAX_PAGES_DEFAULT)
#     print('country' , country)

#     result = fetch_and_store_ads(access_token, search_terms=search_terms, countries=country, max_pages=2)
#     return JsonResponse(result)


 

import json
import os
import time
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.core.cache import cache
from django.conf import settings

# from .facebook_adlib import fetch_and_store_ads

FB_ACCESS_TOKEN = "EAAUwb6OhLh8BPDzxFkbCAxJKf7YYUWaSJgZBw6vMp8E1cS9OFC3j9b50aDWGYXKwy4ElHbrqnlWZBLGdGQVUbD6W5p89niVIRZArklJoq0BprZAzWQMeqgyYsAinSzU7IsRHbrRT6RlLZCwNAaxKhY2m6E2aZA2Th3EZCENWC77FpF5OiTJtcLIZBdy5XmXoPdsN8J1nfL6TOOZBMSW9tZBgZDZD"
RATE_LIMIT_SECONDS = getattr(settings, "ADLIB_RATE_LIMIT_SECONDS", 30)
LOCK_TTL = getattr(settings, "ADLIB_LOCK_TTL", 120)

def _get_user_key(request):
    if request.user.is_authenticated:
        return f"adlib_user_lock_{request.user.id}"
    ip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return f"adlib_ip_lock_{ip}"

@csrf_protect
@require_POST
@never_cache
def fetch_ads_view(request):
    access_token = FB_ACCESS_TOKEN
    if not access_token:
        return HttpResponseForbidden("Server access token not configured")

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON body")

    search_terms = (payload.get('search_terms') or "").strip() or None
    country = (payload.get('country') or "").strip().upper() or None
    max_pages = int(payload.get('max_pages') or getattr(settings, "ADLIB_MAX_PAGES", 2))

    countries = [country] if country else None

    # rate limit / lock
    user_key = _get_user_key(request)
    last_ts = cache.get(user_key + "_ts")
    now_ts = time.time()
    if last_ts and (now_ts - float(last_ts) < RATE_LIMIT_SECONDS):
        return JsonResponse({"detail": "Rate limited. Try again later."}, status=429)

    lock_key = user_key + "_lock"
    got_lock = cache.add(lock_key, "1", timeout=LOCK_TTL)
    if not got_lock:
        return JsonResponse({"detail": "Another fetch is in progress. Try again later."}, status=429)
    cache.set(user_key + "_ts", now_ts, timeout=RATE_LIMIT_SECONDS)

    try:
        result = fetch_and_store_ads(access_token=access_token, search_terms=search_terms, countries=countries, ad_type=None, max_pages=max_pages, debug=False)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        cache.delete(lock_key)
