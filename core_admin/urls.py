from django.urls import path

from .views import (
    AIChatLogsView,
    DashboardHomeView,
    MerchantSuspensionUpdateView,
    MerchantsSuspensionView,
    PendingVoiceCloneActionView,
    PendingVoiceClonesView,
)

app_name = "core_admin"

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="dashboard_home"),
    path("ai-chat-logs/", AIChatLogsView.as_view(), name="ai_chat_logs"),
    path("merchants-suspension/", MerchantsSuspensionView.as_view(), name="merchants_suspension"),
    path("merchants-suspension/update/", MerchantSuspensionUpdateView.as_view(), name="merchants_suspension_update"),
    path("pending-voice-clones/", PendingVoiceClonesView.as_view(), name="pending_voice_clones"),
    path("pending-voice-clones/action/", PendingVoiceCloneActionView.as_view(), name="pending_voice_clones_action"),
]

