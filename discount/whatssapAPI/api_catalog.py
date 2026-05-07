"""
REST-style catalog for WhatsApp product cards (whatssap.html product panel).
"""
import json
import re
import uuid

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from discount.models import WhatsAppCatalogProduct

from .views import get_target_channel

PRODUCT_CATEGORY_LABELS = {
    "beauty": "Beauty",
    "electronics": "Electronics",
    "fragrances": "Fragrances",
    "general": "General",
}


def _parse_offer(raw):
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_url_list(raw):
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _is_video_url(u):
    if not u or not isinstance(u, str):
        return False
    return bool(re.search(r"\.(mp4|webm|ogg)(\?|$)", u.strip(), re.I))


def _save_uploaded_media(request):
    """Return (image_urls, video_urls) from request.FILES['images']."""
    imgs, vids = [], []
    for f in request.FILES.getlist("images"):
        ext = (f.name or "").rsplit(".", 1)[-1].lower() if "." in (f.name or "") else "bin"
        key = f"wa_catalog/{uuid.uuid4().hex}.{ext}"
        path = default_storage.save(key, f)
        url = default_storage.url(path)
        if _is_video_url(url) or (f.content_type and f.content_type.startswith("video/")):
            vids.append(url)
        else:
            imgs.append(url)
    return imgs, vids


def _serialize_list_item(p):
    imgs = p.images or []
    thumb = imgs[0] if imgs else None
    return {
        "id": p.id,
        "name": p.name,
        "price": p.price or "",
        "currency": (p.currency or "MAD").strip() or "MAD",
        "images": [thumb] if thumb else [],
    }


def _serialize_detail(p):
    imgs = list(p.images or [])
    vids = list(p.videos or [])
    return {
        "id": p.id,
        "name": p.name,
        "price": p.price or "",
        "backup_price": p.backup_price or "",
        "coupon_code": p.coupon_code or "",
        "currency": (p.currency or "MAD").strip() or "MAD",
        "description": p.description or "",
        "delivery_options": p.delivery_options or "",
        "category": (p.category or "general").strip().lower() or "general",
        "how_to_use": p.how_to_use or "",
        "checkout_mode": p.checkout_mode or "standard_cod",
        "offer": json.dumps(p.offer) if p.offer else "",
        "images": imgs,
        "videos": vids,
    }


@login_required(login_url="/auth/login/")
@require_GET
def api_products_list(request):
    channel = get_target_channel(request.user, request.GET.get("channel_id"))
    if not channel:
        return JsonResponse({"products": []})
    qs = WhatsAppCatalogProduct.objects.filter(channel=channel).order_by("-updated_at")
    return JsonResponse({"products": [_serialize_list_item(p) for p in qs]})


@login_required(login_url="/auth/login/")
@require_GET
def api_products_detail(request, pk):
    channel = get_target_channel(request.user, request.GET.get("channel_id"))
    if not channel:
        return JsonResponse({"error": "Channel not found"}, status=404)
    p = WhatsAppCatalogProduct.objects.filter(id=pk, channel=channel).first()
    if not p:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse(_serialize_detail(p))


@login_required(login_url="/auth/login/")
@require_POST
def api_products_create(request):
    channel = get_target_channel(request.user, request.POST.get("channel_id"))
    if not channel or not channel.has_user_permission(request.user):
        return JsonResponse({"success": False, "error": "Invalid channel"}, status=403)

    name = (request.POST.get("name") or "").strip()
    price = (request.POST.get("price") or "").strip()
    description = (request.POST.get("description") or "").strip()
    if not name or not price or not description:
        return JsonResponse({"success": False, "error": "Missing required fields", "errors": ["Name, price, and description are required."]}, status=400)

    up_imgs, up_vids = _save_uploaded_media(request)
    json_imgs = [u for u in _parse_url_list(request.POST.get("image_urls")) if not _is_video_url(u)]
    json_vids = [u for u in _parse_url_list(request.POST.get("image_urls")) if _is_video_url(u)]

    p = WhatsAppCatalogProduct.objects.create(
        channel=channel,
        name=name,
        price=price,
        backup_price=(request.POST.get("backup_price") or "").strip(),
        coupon_code=(request.POST.get("coupon_code") or "").strip(),
        currency=(request.POST.get("currency") or "MAD").strip() or "MAD",
        description=description,
        delivery_options=(request.POST.get("delivery_options") or "").strip(),
        category=(request.POST.get("category") or "general").strip().lower() or "general",
        how_to_use=(request.POST.get("how_to_use") or "").strip(),
        checkout_mode=(request.POST.get("checkout_mode") or "standard_cod").strip() or "standard_cod",
        offer=_parse_offer(request.POST.get("offer")),
        images=json_imgs + up_imgs,
        videos=json_vids + up_vids,
    )
    return JsonResponse({"success": True, "product_id": p.id})


@login_required(login_url="/auth/login/")
@require_POST
def api_products_update(request, pk):
    channel = get_target_channel(request.user, request.POST.get("channel_id"))
    if not channel or not channel.has_user_permission(request.user):
        return JsonResponse({"success": False, "error": "Invalid channel"}, status=403)
    p = WhatsAppCatalogProduct.objects.filter(id=pk, channel=channel).first()
    if not p:
        return JsonResponse({"success": False, "error": "Not found"}, status=404)

    name = (request.POST.get("name") or "").strip()
    price = (request.POST.get("price") or "").strip()
    description = (request.POST.get("description") or "").strip()
    if not name or not price or not description:
        return JsonResponse({"success": False, "error": "Missing required fields", "errors": ["Name, price, and description are required."]}, status=400)

    up_imgs, up_vids = _save_uploaded_media(request)
    parsed = _parse_url_list(request.POST.get("image_urls"))
    json_imgs = [u for u in parsed if not _is_video_url(u)]
    json_vids = [u for u in parsed if _is_video_url(u)]

    p.name = name
    p.price = price
    p.backup_price = (request.POST.get("backup_price") or "").strip()
    p.coupon_code = (request.POST.get("coupon_code") or "").strip()
    p.currency = (request.POST.get("currency") or "MAD").strip() or "MAD"
    p.description = description
    p.delivery_options = (request.POST.get("delivery_options") or "").strip()
    p.category = (request.POST.get("category") or "general").strip().lower() or "general"
    p.how_to_use = (request.POST.get("how_to_use") or "").strip()
    p.checkout_mode = (request.POST.get("checkout_mode") or "standard_cod").strip() or "standard_cod"
    p.offer = _parse_offer(request.POST.get("offer"))
    if up_imgs or up_vids:
        p.images = json_imgs + up_imgs
        p.videos = json_vids + up_vids
    else:
        p.images = json_imgs
        p.videos = json_vids
    p.save()
    return JsonResponse({"success": True, "product_id": p.id})


@login_required(login_url="/auth/login/")
@require_POST
def api_products_classify(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}
    title = (body.get("title") or "").strip()
    desc = (body.get("description") or "").lower()
    text = f"{title} {desc}".lower()
    category, label = "general", PRODUCT_CATEGORY_LABELS["general"]
    if any(k in text for k in ("cream", "serum", "skin", "بشرة", "كريم", "عناية")):
        category, label = "beauty", PRODUCT_CATEGORY_LABELS["beauty"]
    elif any(k in text for k in ("phone", "laptop", "usb", "شاحن", "هاتف", "سماعة")):
        category, label = "electronics", PRODUCT_CATEGORY_LABELS["electronics"]
    elif any(k in text for k in ("perfume", "عطر", "fragrance", "oud")):
        category, label = "fragrances", PRODUCT_CATEGORY_LABELS["fragrances"]
    return JsonResponse({"category": category, "label": label})


@login_required(login_url="/auth/login/")
@require_POST
def api_products_extract_from_link(request):
    """Placeholder: full scraping/LLM extraction can be wired later."""
    url = (request.POST.get("url") or "").strip()
    if not url:
        return JsonResponse({"success": False, "error": "URL required"}, status=400)
    return JsonResponse(
        {
            "success": False,
            "error": "Automatic import from links is not enabled on this server yet. Use “Create manually”.",
        }
    )
