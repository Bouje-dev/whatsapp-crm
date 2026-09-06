from django.urls import path

from discount.whatssapAPI import sandbox_views

urlpatterns = [
    path("", sandbox_views.sandbox_lab_page, name="sandbox_lab"),
    path("api/bootstrap/", sandbox_views.sandbox_bootstrap, name="sandbox_bootstrap"),
    path("api/messages/", sandbox_views.sandbox_messages, name="sandbox_messages"),
    path("api/state/", sandbox_views.sandbox_state, name="sandbox_state"),
    path("api/send/", sandbox_views.sandbox_send, name="sandbox_send"),
    path("api/reset/", sandbox_views.sandbox_reset, name="sandbox_reset"),
]
