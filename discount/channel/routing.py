# routing.py
from django.urls import re_path
from .consumers import ChatConsumer ,WebhookConsumer

websocket_urlpatterns = [
    re_path(r'chat/stream/$', WebhookConsumer.as_asgi()),
]