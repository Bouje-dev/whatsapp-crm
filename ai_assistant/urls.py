from django.urls import path
from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("api/suggest/", views.ai_suggest_reply, name="ai_suggest_reply"),
    path("api/send-as-voice/", views.ai_send_reply_as_voice, name="ai_send_reply_as_voice"),
    path("api/copilot-chat/", views.copilot_chat, name="copilot_chat"),
    path("api/pending-escalations/", views.list_pending_escalations, name="list_pending_escalations"),
    path("api/escalations/status/", views.escalation_status, name="escalation_status"),
    path(
        "api/pending-escalations/resolve/",
        views.resolve_pending_escalation,
        name="resolve_pending_escalation",
    ),
    path(
        "knowledge-gap/<str:token>/",
        views.knowledge_gap_magic_link,
        name="knowledge_gap_magic",
    ),
    path("api/generate-product-aliases/", views.generate_product_aliases, name="generate_product_aliases"),
]
