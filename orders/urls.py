from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("", views.OrderListView.as_view(), name="order_list"),
    path("partial/table/", views.order_table_partial, name="order_table_partial"),
    path("export/", views.order_export, name="order_export"),
    path("import/", views.order_import, name="order_import"),
    path("update-status/<int:pk>/", views.order_update_status, name="order_update_status"),
    path("update-agent/<int:pk>/", views.order_update_agent, name="order_update_agent"),
    path("bulk-assign/", views.order_bulk_assign, name="order_bulk_assign"),
]
