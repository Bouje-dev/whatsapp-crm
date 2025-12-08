from django.urls import path
from . import views
from .recommendations import analytics_with_recommendations_view
from discount import user_dash
# from .views import test
urlpatterns = [      
    path('api/capture-visit/', views.capture_visit, name='capture_visit'),
    path('testing/',views.test, name='tset'),
    path('api/manual-sync/', views.manual_sync, name='manual_sync'),
    path('admin/manual-sync/', views.manual_sync_page, name='manual_sync_page'),  # صفحة داخلية للضغط
    path('analytics/', views.analytics_view, name='analytics'),
    path('api/dashboard-data/', views.dashboard_data_api, name='dashboard-data'),
    path('api/fetch-orders/', views.refresh, name='fetch_orders'),
    # path('api/fetch-tracking-status/', views.fetch_tracking_status_from_carrier, name='fetch_tracking_status'),
    # path('api/refresh-orders/', views.refresh, name='refresh_orders'),
   path('api/analytics-with-recommendations', analytics_with_recommendations_view, name='analytics-with-recommendations'),
    # path('api/recommendation/apply/', apply_recommendation, name='apply-recommendation'),
    # path('api/recommendation/ignore/', ignore_recommendation, name='ignore-recommendation'),
    path('api/products/list/', views.products_list, name='products-list'),
    path('api/channels/list/', views.channels_list, name='channels-list'),
    path('api/product-permissions/user/', views.get_permissions_for_user, name='get-permissions-for-user'),
    path('api/product-permissions/bulk_update/', views.bulk_update_permissions, name='bulk-update-permissions'),
    path("api/leads/filter/", views.filter_leads_api, name="filter_leads_api"),
    path('load-drop-product/', views.load_products, name='load_products') , 
    path('api/flows/create/', views.create_flow, name='create_flow') , 

     path('api/flows/', views.list_flows, name='list_flows'),
    path('api/flows/<uuid:flow_id>/', views.flow_detail, name='flow_detail'),



    path('resend_activation/', user_dash.resend_activation_email, name='resend_activation_email'),
    path('verify_code/', user_dash.verify_code, name='verify_code'),
    path('activate/<int:user_id>/', user_dash.activate_account, name='activate_account'),
]

# your_app/urls.py
 

 