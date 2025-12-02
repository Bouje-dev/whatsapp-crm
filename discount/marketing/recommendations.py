# your_app/analytics/recommendations_granular.py
import uuid
import math
from typing import List, Dict, Any, Optional

# إعداد قابل للتعديل
CFG = {
    "MIN_VISITS_PLATFORM": 50,
    "MIN_VISITS_PLACEMENT": 20,
    "MIN_CONFIRMED_ORDERS": 5,
    "PLATFORM_DELTA_CONV": 0.20,   # 20% أفضل من المتوسط
    "PLATFORM_DELTA_DELIVERY": 0.05,
    "PLACEMENT_ADVANTAGE_DELTA": 0.15,
    "INCREASE_BUDGET_BASE_PCT": 15,
    "TEST_PCT": 10,
    "RETURN_RATE_MAX": 0.12
}


def safe_div(a, b, default=None):
    try:
        if b is None or b == 0:
            return default
        return float(a) / float(b)
    except Exception:
        return default


def aggregate_platforms(campaigns: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Agg campaigns => platform summary (and collect placements)"""
    platforms = {}
    # placements_by_platform: {platform: {placement: {visits, confirmed, delivered, orders}}}
    placements_by_platform = {}

    for c in campaigns or []:
        platform = (c.get("platform") or c.get("platform_label") or "unknown").lower()
        cam_visits = int(c.get("visits") or 0)
        cam_orders = int(c.get("orders") or 0)
        cam_confirmed = int(c.get("confirmed_orders") or 0)
        cam_delivered = int(c.get("delivered_orders") or 0)
        cam_spend = float(c.get("spend") or 0.0)
        cam_revenue = float(c.get("revenue") or 0.0)
        platforms.setdefault(platform, {"visits":0,"orders":0,"confirmed":0,"delivered":0,"spend":0.0,"revenue":0.0,"campaigns":[]})
        p = platforms[platform]
        p["visits"] += cam_visits
        p["orders"] += cam_orders
        p["confirmed"] += cam_confirmed
        p["delivered"] += cam_delivered
        p["spend"] += cam_spend
        p["revenue"] += cam_revenue
        p["campaigns"].append(c)

        # gather placements from campaign.adsets -> ad -> placements OR campaign.site_sources list
        # support both shapes
        # 1) if campaign has 'site_sources' list (your earlier payload used site_sources)
        if c.get("site_sources") and isinstance(c["site_sources"], list):
            for pl in c["site_sources"]:
                placements_by_platform.setdefault(platform, {}).setdefault(pl, {"visits":0,"confirmed":0,"delivered":0,"orders":0})
                placements_by_platform[platform][pl]["visits"] += cam_visits  # coarse assign
                placements_by_platform[platform][pl]["confirmed"] += cam_confirmed
                placements_by_platform[platform][pl]["delivered"] += cam_delivered
                placements_by_platform[platform][pl]["orders"] += cam_orders

        # 2) if campaign has adsets with placements breakdown
        if c.get("adsets") and isinstance(c["adsets"], list):
            for adset in c["adsets"]:
                # adset may have adset['placements'] list of {placement, orders, visits}
                pls = adset.get("placements") or []
                # visits/adset level fallback
                for pl in pls:
                    pname = pl.get("placement") or pl.get("site_source_name") or "unknown_placement"
                    placements_by_platform.setdefault(platform, {}).setdefault(pname, {"visits":0,"confirmed":0,"delivered":0,"orders":0})
                    placements_by_platform[platform][pname]["visits"] += int(pl.get("visits") or 0)
                    placements_by_platform[platform][pname]["confirmed"] += int(pl.get("confirmed_orders") or pl.get("confirmed") or 0)
                    placements_by_platform[platform][pname]["delivered"] += int(pl.get("delivered_orders") or pl.get("delivered") or 0)
                    placements_by_platform[platform][pname]["orders"] += int(pl.get("orders") or 0)

    # compute derived rates
    for pk, s in platforms.items():
        s["conversion_rate"] = safe_div(s["confirmed"], s["visits"], 0.0) or 0.0
        s["delivery_rate"] = safe_div(s["delivered"], s["confirmed"], 0.0) or 0.0
        s["avg_cpa"] = safe_div(s["spend"], s["confirmed"], None)
        s["avg_aov"] = safe_div(s["revenue"], s["confirmed"], None)

    return platforms, placements_by_platform


def generate_recommendations_granular(campaigns: List[Dict[str, Any]], cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    cfg = cfg or CFG
    recs = []
    if not campaigns:
        return recs

    platforms, placements_by_platform = aggregate_platforms(campaigns)

    # compute platform averages
    platform_keys = list(platforms.keys())
    platform_conv_rates = [platforms[k]["conversion_rate"] for k in platform_keys if platforms[k]["visits"]>0]
    avg_platform_conv = (sum(platform_conv_rates) / len(platform_conv_rates)) if platform_conv_rates else 0.0

    # 1) Compare platforms: find outperformers and underperformers
    for pk, stats in platforms.items():
        visits = stats.get("visits",0)
        if visits < cfg["MIN_VISITS_PLATFORM"]:
            continue
        conv = stats.get("conversion_rate",0.0)
        delivery = stats.get("delivery_rate",0.0)
        delta_conv = safe_div(conv - avg_platform_conv, avg_platform_conv, 0.0) if avg_platform_conv>0 else None

        # platform outperforming (conv & delivery)
        if delta_conv is not None and delta_conv >= cfg["PLATFORM_DELTA_CONV"] and delivery >= cfg["PLATFORM_DELTA_DELIVERY"]:
            # suggest shifting budget here; compute suggested pct proportional to delta and volume
            suggested_pct = min(50, int(cfg["INCREASE_BUDGET_BASE_PCT"] * (1 + (delta_conv*2)) * (1 + stats.get("orders",0)/100.0)))
            recs.append({
                "id": str(uuid.uuid4()),
                "type": "platform_outperforming",
                "platform": pk,
                "score": round((conv*100.0 + delivery*50.0 + stats.get("orders",0)/10.0),2),
                "confidence": min(0.98, 0.4 + min(0.6, math.log10(max(1,visits))/2.0)),
                "reason": f"Platform '{pk}' conv {conv:.2%} (delta {delta_conv:.1%} vs avg {avg_platform_conv:.2%}), delivery {delivery:.2%}.",
                "suggested_action": {"action":"increase_budget","by_percent": suggested_pct},
                "explanation": {"platform_stats": stats, "avg_platform_conv": avg_platform_conv, "delta_conv": delta_conv}
            })

    # 2) Platform-to-platform reallocation suggestions:
    # find best platform and worst platform where difference is substantial
    sorted_platforms = sorted(platforms.items(), key=lambda x: x[1].get("conversion_rate",0), reverse=True)
    if len(sorted_platforms) >= 2:
        best_k, best_stats = sorted_platforms[0]
        worst_k, worst_stats = sorted_platforms[-1]
        # check if shifting likely beneficial
        if best_stats["visits"] >= cfg["MIN_VISITS_PLATFORM"] and worst_stats["visits"] >= cfg["MIN_VISITS_PLATFORM"]:
            # require meaningful gap
            gap = safe_div(best_stats["conversion_rate"] - worst_stats["conversion_rate"], worst_stats["conversion_rate"] or 1e-9, None)
            if gap is not None and gap > cfg["PLATFORM_DELTA_CONV"]:
                recs.append({
                    "id": str(uuid.uuid4()),
                    "type": "reallocate_from_to",
                    "from_platform": worst_k,
                    "to_platform": best_k,
                    "score": round((best_stats["conversion_rate"]-worst_stats["conversion_rate"])*1000,2),
                    "confidence": 0.6,
                    "reason": f"Consider moving some budget from '{worst_k}' (conv {worst_stats['conversion_rate']:.2%}) to '{best_k}' (conv {best_stats['conversion_rate']:.2%}) — gap {gap:.1%}.",
                    "suggested_action": {"action":"reallocate_test", "from": worst_k, "to": best_k, "test_pct": cfg["TEST_PCT"]},
                    "explanation": {"best_platform": best_stats, "worst_platform": worst_stats, "gap": gap}
                })

    # 3) Placement-level recommendations (within each platform)
    for pk, placements in (placements_by_platform or {}).items():
        if not placements:
            continue
        # compute platform avg conv to compare per placement
        p_stats = platforms.get(pk, {})
        p_conv = p_stats.get("conversion_rate", 0.0)
        for pname, plstats in placements.items():
            pl_visits = plstats.get("visits",0)
            if pl_visits < cfg["MIN_VISITS_PLACEMENT"]:
                continue
            pl_conv = safe_div(plstats.get("confirmed",0), plstats.get("visits",1), 0.0)
            delta = safe_div(pl_conv - p_conv, p_conv, 0.0) if p_conv>0 else None
            if delta is not None and delta >= cfg["PLACEMENT_ADVANTAGE_DELTA"]:
                recs.append({
                    "id": str(uuid.uuid4()),
                    "type": "placement_prefer",
                    "platform": pk,
                    "placement": pname,
                    "score": round((pl_conv*100.0 + plstats.get("confirmed",0)/10.0),2),
                    "confidence": min(0.95, 0.3 + math.log10(max(1,pl_visits))/2.0),
                    "reason": f"Placement '{pname}' on '{pk}' has higher conv {pl_conv:.2%} vs platform avg {p_conv:.2%} (delta {delta:.1%}).",
                    "suggested_action": {"action":"prioritize_placement","by_percent": min(30, int(10 + delta*100))},
                    "explanation": {"placement_stats": plstats, "platform_avg_conv": p_conv, "delta": delta}
                })

    # 4) Campaign-level deeper recommendations (targeted)
    for c in campaigns:
        cam_name = c.get("campaign_name") or c.get("name") or "unknown"
        visits = int(c.get("visits") or 0)
        confirmed = int(c.get("confirmed_orders") or 0)
        delivered = int(c.get("delivered_orders") or 0)
        conv = safe_div(confirmed, visits, 0.0)
        delivery_rate = safe_div(delivered, confirmed, 0.0)
        # if confirmed good but delivered low -> shipping investigate (keep this)
        if confirmed >= cfg["MIN_CONFIRMED_ORDERS"] and delivery_rate < 0.40:
            recs.append({
                "id": str(uuid.uuid4()),
                "type": "investigate_shipping",
                "campaign": cam_name,
                "score": round(50 + confirmed/10.0,2),
                "confidence": 0.6,
                "reason": f"Campaign '{cam_name}' confirmed {confirmed} but delivery rate low {delivery_rate:.2%}.",
                "suggested_action": {"action":"check_shipping","notes":"verify courier/fulfillment/addresses"},
                "explanation": {"campaign_raw": c, "metrics": {"visits":visits,"confirmed":confirmed,"delivered":delivered,"conv":conv,"delivery_rate":delivery_rate}}
            })
        # if campaign conv significantly above platform average -> suggest expand within platform
        plat = (c.get("platform") or c.get("platform_label") or "unknown").lower()
        plat_conv = platforms.get(plat, {}).get("conversion_rate", 0.0)
        if plat_conv and conv > plat_conv * (1.0 + cfg["PLATFORM_DELTA_CONV"]) and visits >= cfg["MIN_VISITS_PLATFORM"]:
            recs.append({
                "id": str(uuid.uuid4()),
                "type": "scale_campaign_on_platform",
                "campaign": cam_name,
                "platform": plat,
                "score": round((conv*100.0 + delivered/10.0),2),
                "confidence": 0.55,
                "reason": f"Campaign '{cam_name}' conversion {conv:.2%} > platform '{plat}' avg {plat_conv:.2%}. Consider scaling.",
                "suggested_action": {"action":"scale_campaign","by_percent":min(40, int((conv/plat_conv - 1)*100))},
                "explanation": {"campaign_metrics": {"visits":visits,"confirmed":confirmed,"conv":conv}, "platform_avg": plat_conv}
            })

    # sort recs
    recs.sort(key=lambda r: r.get("score",0), reverse=True)
    return recs


# your_app/analytics/views.py
import logging
from django.http import JsonResponse, HttpRequest
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)

# استبدل المسار إلى مكان وجود دالتك الفعلية
 
# دالتك الحالية التي تجمع payload (analytics_view_data)
# غيّر الاستيراد لو كانت في مكان آخر
from .views import analytics_view_data

def analytics_with_recommendations_view(request: HttpRequest):
    """
    API endpoint: يجلب بيانات analytics ثم يبني platforms_summary, placements_by_platform,
    ويولد توصيات granular باستخدام generate_recommendations_granular.
    يدعم ?platform=all&period=7 و ?debug=1 ليعيد معلومات تصحيحية.
    """
    platform = request.GET.get("platform", "all")
    try:
        period = int(request.GET.get("period", 7))
    except Exception:
        period = 7
    debug = request.GET.get("debug") in ("1", "true", "True")

    # 1) اجلب payload من دالتك الأساسية
    try:
        payload = analytics_view_data(request,platform=platform, period_days=period) or {}
    except Exception as e:
        logger.exception("analytics_view_data raised exception")
        return JsonResponse({"error": "analytics_view_data failed", "details": str(e)}, status=500)

    # 2) استخرج campaigns بصيغة قائمة (fallbacks إذا كان الاسم مختلف)
    campaigns = payload.get("campaigns")
    if campaigns is None:
        # محاولة استخدام أسماء بديلة قد تكون استُخدمت في تنفيذك السابق
        campaigns = payload.get("campaigns_list") or payload.get("orders") or payload.get("orders_data") or []

    # coerce to list if queryset-like
    try:
        if hasattr(campaigns, "values") and not isinstance(campaigns, list):
            campaigns = list(campaigns)
        elif not isinstance(campaigns, list):
            campaigns = list(campaigns) if hasattr(campaigns, "__iter__") else [campaigns]
    except Exception:
        logger.exception("Failed to coerce campaigns to list; using fallback empty list")
        campaigns = list(campaigns) if isinstance(campaigns, (list, tuple)) else []

    # 3) Generate platform/placement summaries
    try:
        platforms_summary, placements_by_platform = aggregate_platforms(campaigns)
    except Exception as e:
        logger.exception("aggregate_platforms failed")
        platforms_summary = {}
        placements_by_platform = {}

    # 4) Generate recommendations (granular)
    try:
        recommendations = generate_recommendations_granular(campaigns)
        if recommendations is None:
            recommendations = []
    except Exception as e:
        logger.exception("generate_recommendations_granular failed")
        # في وضع debug نعيد تفاصيل الخطأ
        if debug:
            return JsonResponse({
                "error": "generate_recommendations_granular failed",
                "details": str(e),
                "payload_sample": {
                    "campaigns_sample": campaigns[:5] if isinstance(campaigns, (list,tuple)) else str(type(campaigns))
                }
            }, status=500, encoder=DjangoJSONEncoder)
        recommendations = []

    # 5) تحضير النتيجة النهائية
    result = {
        "kpis": payload.get("kpis", {}),
        "campaigns": campaigns,
        "platforms_summary": platforms_summary,
        "placements_by_platform": placements_by_platform,
        "recommendations": recommendations,
        "last_update": payload.get("last_update", timezone.now().isoformat()),
        "meta": {
            "campaigns_count": len(campaigns) if isinstance(campaigns, (list,tuple)) else None,
            "recommendations_count": len(recommendations)
        }
    }

    if debug:
        result["debug_payload"] = payload

    # Use DjangoJSONEncoder to handle datetimes/Decimals
    return JsonResponse(result, encoder=DjangoJSONEncoder, safe=True)
