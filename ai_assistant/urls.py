from django.urls import path
from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("api/suggest/", views.ai_suggest_reply, name="ai_suggest_reply"),
]
