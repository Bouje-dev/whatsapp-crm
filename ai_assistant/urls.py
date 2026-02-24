from django.urls import path
from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("api/suggest/", views.ai_suggest_reply, name="ai_suggest_reply"),
    path("api/send-as-voice/", views.ai_send_reply_as_voice, name="ai_send_reply_as_voice"),
]
