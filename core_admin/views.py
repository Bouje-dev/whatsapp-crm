import json
import os
from collections import deque
from datetime import timedelta
from decimal import Decimal

import requests
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import F, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from ai_assistant.models import AIUsageLog
from discount.models import (
    ChatSession,
    CustomUser,
    Message,
    Products,
    VoiceCloneRequest,
    WhatsAppChannel,
    VoicePersona,
    VOICE_DIALECT_DEFAULT,
)


superuser_required = user_passes_test(lambda u: bool(getattr(u, "is_superuser", False)))


@method_decorator([login_required, superuser_required], name="dispatch")
class DashboardHomeView(TemplateView):
    template_name = "core_admin/dashboard_home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        now = timezone.now()
        today = now.date()
        # Last 7 days including today
        week_start = now - timedelta(days=6)

        token_expr = F("prompt_tokens") + F("completion_tokens")

        merchants_active = CustomUser.objects.filter(stripe_subscription_status="active").count()
        merchants_trialing = CustomUser.objects.filter(stripe_subscription_status="trialing").count()

        tokens_today = (
            AIUsageLog.objects.filter(created_at__date=today)
            .aggregate(total=Sum(token_expr))
            .get("total")
            or 0
        )

        daily_qs = (
            AIUsageLog.objects.filter(created_at__gte=week_start)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(tokens=Sum(token_expr))
            .order_by("day")
        )
        tokens_by_day = {row["day"]: row["tokens"] or 0 for row in daily_qs}

        labels = []
        data = []
        for i in range(7):
            d = (today - timedelta(days=(6 - i)))
            labels.append(d.strftime("%Y-%m-%d"))
            data.append(int(tokens_by_day.get(d, 0) or 0))

        tokens_week = AIUsageLog.objects.filter(created_at__gte=week_start).aggregate(
            total=Sum(token_expr)
        ).get("total") or 0

        wallet_sum = (
            CustomUser.objects.aggregate(total=Sum("wallet_balance")).get("total") or Decimal("0")
        )
        pending_voice_clones = VoiceCloneRequest.objects.filter(status=VoiceCloneRequest.STATUS_PENDING).count()

        ctx.update(
            {
                "merchants_active": merchants_active,
                "merchants_trialing": merchants_trialing,
                "tokens_today": int(tokens_today),
                "tokens_week": int(tokens_week),
                "wallet_sum": wallet_sum,
                "chart_labels_json": json.dumps(labels),
                "chart_data_json": json.dumps(data),
                "week_start": week_start.date().isoformat(),
                "today": today.isoformat(),
                "pending_voice_clones": pending_voice_clones,
            }
        )
        return ctx


@method_decorator([login_required, superuser_required], name="dispatch")
class AIChatLogsView(TemplateView):
    template_name = "core_admin/ai_chat_logs.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        request = self.request
        try:
            limit_sessions = int(request.GET.get("limit", 30))
        except Exception:
            limit_sessions = 30
        limit_sessions = min(max(limit_sessions, 1), 100)

        try:
            messages_per_session = int(request.GET.get("messages_per_session", 12))
        except Exception:
            messages_per_session = 12
        messages_per_session = min(max(messages_per_session, 3), 50)

        cutoff = timezone.now() - timedelta(days=7)

        sessions = list(
            ChatSession.objects.select_related("channel", "active_node", "channel__owner")
            .filter(last_interaction__gte=cutoff)
            .order_by("-last_interaction")[:limit_sessions]
        )

        session_keys = {(s.channel_id, s.customer_phone) for s in sessions}
        channel_ids = [s.channel_id for s in sessions if s.channel_id]
        phones = [s.customer_phone for s in sessions if s.customer_phone]

        key_to_messages = {key: deque(maxlen=messages_per_session) for key in session_keys}

        messages_qs = (
            Message.objects.filter(
                channel_id__in=channel_ids,
                sender__in=phones,
                is_internal=False,
                timestamp__gte=cutoff,
            )
            .order_by("timestamp")
        )

        for msg in messages_qs:
            key = (msg.channel_id, msg.sender)
            bucket = key_to_messages.get(key)
            if bucket is None:
                continue
            bucket.append(msg)

        # Resolve product ids from active_node.ai_model_config (best-effort)
        product_ids = set()
        for s in sessions:
            try:
                ai_cfg = getattr(s.active_node, "ai_model_config", None) or {}
                if isinstance(ai_cfg, dict) and ai_cfg.get("product_id") is not None:
                    product_ids.add(int(ai_cfg.get("product_id")))
            except Exception:
                continue

        products_map = {}
        if product_ids:
            for p in Products.objects.filter(id__in=product_ids):
                products_map[p.id] = p

        session_cards = []
        for s in sessions:
            merchant = getattr(s.channel, "owner", None) if s.channel_id else None
            merchant_label = None
            if merchant:
                merchant_label = (
                    getattr(merchant, "user_name", None)
                    or getattr(merchant, "username", None)
                    or merchant.email
                )

            ai_cfg = getattr(s.active_node, "ai_model_config", None) or {}
            product_id = None
            if isinstance(ai_cfg, dict):
                try:
                    pid = ai_cfg.get("product_id")
                    product_id = int(pid) if pid is not None else None
                except Exception:
                    product_id = None
            product = products_map.get(product_id)

            msgs = list(key_to_messages.get((s.channel_id, s.customer_phone), []))
            rendered_msgs = []
            for m in msgs:
                role = "AI" if getattr(m, "is_from_me", False) else "User"
                body = (m.body or "").strip()
                captions = (m.captions or "").strip() if getattr(m, "captions", None) else ""
                text = body or captions
                if not text and m.media_type:
                    text = f"[{m.media_type}]"
                rendered_msgs.append(
                    {
                        "role": role,
                        "text": text[:8000],
                        "media_type": m.media_type,
                        "timestamp": m.timestamp,
                        "msg_type": m.type,
                    }
                )

            session_cards.append(
                {
                    "session_id": s.id,
                    "merchant_label": merchant_label,
                    "channel_name": getattr(s.channel, "name", "") if s.channel_id else "",
                    "customer_phone": s.customer_phone,
                    "product_name": getattr(product, "name", None) if product else None,
                    "product_price": getattr(product, "price", None) if product else None,
                    "active_node_type": getattr(s.active_node, "node_type", None) if s.active_node else None,
                    "active_node_id": getattr(s.active_node, "id", None) if s.active_node else None,
                    "ai_enabled": s.ai_enabled,
                    "last_interaction": s.last_interaction,
                    "messages": rendered_msgs,
                }
            )

        ctx.update(
            {
                "sessions": session_cards,
                "limit_sessions": limit_sessions,
                "messages_per_session": messages_per_session,
                "cutoff": cutoff.isoformat(),
            }
        )
        return ctx


@method_decorator([login_required, superuser_required], name="dispatch")
class MerchantsSuspensionView(TemplateView):
    template_name = "core_admin/merchant_suspension.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        merchants = (
            CustomUser.objects.filter(is_bot=False)
            .order_by("-date_joined")
            .only("id", "email", "user_name", "stripe_subscription_status", "is_suspended", "suspension_reason")
        )
        ctx.update({"merchants": merchants})
        return ctx


@method_decorator([login_required, superuser_required], name="dispatch")
class MerchantSuspensionUpdateView(TemplateView):
    template_name = "core_admin/merchant_suspension.html"

    def post(self, request, *args, **kwargs):
        merchant_id = (request.POST.get("merchant_id") or "").strip()
        is_suspended = (request.POST.get("is_suspended") or "") == "on"
        reason = (request.POST.get("suspension_reason") or "").strip()

        if merchant_id:
            merchant = CustomUser.objects.filter(pk=merchant_id).first()
            if merchant:
                merchant.is_suspended = is_suspended
                merchant.suspension_reason = reason if is_suspended else None
                merchant.save(update_fields=["is_suspended", "suspension_reason"])

        return redirect("/founder-hq/merchants-suspension/")


@method_decorator([login_required, superuser_required], name="dispatch")
class PendingVoiceClonesView(TemplateView):
    template_name = "core_admin/pending_voice_clones.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pending = (
            VoiceCloneRequest.objects.select_related("merchant")
            .filter(status=VoiceCloneRequest.STATUS_PENDING)
            .order_by("created_at")
        )
        reviewed = (
            VoiceCloneRequest.objects.select_related("merchant")
            .exclude(status=VoiceCloneRequest.STATUS_PENDING)
            .order_by("-created_at")[:30]
        )
        ctx.update({"pending_requests": pending, "recent_requests": reviewed})
        return ctx


@method_decorator([login_required, superuser_required], name="dispatch")
class PendingVoiceCloneActionView(TemplateView):
    template_name = "core_admin/pending_voice_clones.html"

    def post(self, request, *args, **kwargs):
        req_id = (request.POST.get("request_id") or "").strip()
        action = (request.POST.get("action") or "").strip().lower()
        if not req_id or action not in ("approve", "reject"):
            return redirect("/founder-hq/pending-voice-clones/")

        clone_req = VoiceCloneRequest.objects.select_related("merchant").filter(pk=req_id).first()
        if not clone_req or clone_req.status != VoiceCloneRequest.STATUS_PENDING:
            return redirect("/founder-hq/pending-voice-clones/")

        if action == "reject":
            clone_req.status = VoiceCloneRequest.STATUS_REJECTED
            clone_req.save(update_fields=["status"])
            return redirect("/founder-hq/pending-voice-clones/")

        # Approve: only here we call ElevenLabs API.
        merchant = clone_req.merchant
        channel = WhatsAppChannel.objects.filter(owner=merchant).order_by("id").first()
        api_key = (getattr(channel, "elevenlabs_api_key", None) or "").strip() if channel else ""
        if not api_key:
            api_key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
        if not api_key:
            clone_req.status = VoiceCloneRequest.STATUS_REJECTED
            clone_req.save(update_fields=["status"])
            return redirect("/founder-hq/pending-voice-clones/")

        try:
            clone_req.audio_file.open("rb")
            file_bytes = clone_req.audio_file.read()
            filename = os.path.basename(getattr(clone_req.audio_file, "name", "") or "sample.mp3")
        finally:
            try:
                clone_req.audio_file.close()
            except Exception:
                pass

        voice_name = f"{(merchant.user_name or merchant.username or 'Merchant').strip()} Custom Voice"
        headers = {"xi-api-key": api_key}
        data = {"name": voice_name[:100]}
        files = {"files": (filename, file_bytes, "audio/mpeg")}
        try:
            r = requests.post("https://api.elevenlabs.io/v1/voices/add", headers=headers, data=data, files=files, timeout=90)
            r.raise_for_status()
            out = r.json() if r.content else {}
            voice_id = (out.get("voice_id") or "").strip()
            if not voice_id:
                raise ValueError("ElevenLabs returned no voice_id")
        except Exception:
            clone_req.status = VoiceCloneRequest.STATUS_REJECTED
            clone_req.save(update_fields=["status"])
            return redirect("/founder-hq/pending-voice-clones/")

        # Save voice for merchant channels (profile-level effect in this app)
        owned_channels = WhatsAppChannel.objects.filter(owner=merchant)
        dkey = getattr(clone_req, "dialect", None) or VOICE_DIALECT_DEFAULT
        for ch in owned_channels:
            updates = []
            if hasattr(ch, "selected_voice_id"):
                ch.selected_voice_id = voice_id
                updates.append("selected_voice_id")
            if hasattr(ch, "cloned_voice_id"):
                ch.cloned_voice_id = voice_id
                updates.append("cloned_voice_id")
            if hasattr(ch, "voice_dialect"):
                ch.voice_dialect = dkey
                updates.append("voice_dialect")
            if updates:
                ch.save(update_fields=updates)

        # Create a persona entry so it appears in "My Voices".
        existing_names = set(
            VoicePersona.objects.filter(owner=merchant, is_system=False).values_list("name", flat=True)
        )
        idx = 1
        while f"My Voice {idx}" in existing_names:
            idx += 1
        VoicePersona.objects.create(
            name=f"My Voice {idx}",
            description="Approved custom clone",
            voice_id=voice_id,
            provider=VoicePersona.PROVIDER_ELEVENLABS,
            is_system=False,
            owner=merchant,
            behavioral_instructions="",
            language_code="AR_MA",
            dialect=dkey,
            tier=VoicePersona.TIER_STANDARD,
        )

        clone_req.status = VoiceCloneRequest.STATUS_APPROVED
        clone_req.save(update_fields=["status"])
        return redirect("/founder-hq/pending-voice-clones/")
