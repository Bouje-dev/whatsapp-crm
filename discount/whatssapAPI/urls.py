
from django.urls import path
from . import views , flow , process_messages , templaite

from .flow import SaveFlowView 
urlpatterns = [
    path("webhook/", process_messages.whatsapp_webhook, name="whatsapp_webhook"),
    path("chat/", views.chat_view, name="chat_view"),
    path("whatsapp/", views.whatssap, name="whatsapp"),
    path("send/", views.send_message, name="send_message"),
    
    # API endpoints
    path("api/get_messages/", views.get_messages1, name="get_messages"),
    path("api/contactslist/", views.api_contactsList, name="api_contactslist"),
    path("api/last_message/", views.get_last_message, name="get_last_message"),
    
    path("api/contacts/", views.api_contacts2, name="api_contacts"),
    path("create_template/", views.create_template, name="create_template"),
    path("api/template/", views.api_templates, name="api_templates"),
    path("api_orders/", views.api_orders, name="api_orders"),
    path("api/templates/<int:pk>/", views.update_template, name="update_template"),

    path("api/templateShow/<int:pk>/", views.api_template, name="api_template"),
    path("sync_pending_templates" , templaite.sync_pending_templates , name="sync_pending_templates"),
    path("upload_media/", views.upload_media, name="upload_media"),

    # Flow Builder
    path('flow-builder/', flow.flow_builder_page, name='flow_builder_page'),
    
    # AutoReply CRUD
    path("api/autoreplies/", flow.api_list_autoreplies, name="api_list_autoreplies"),
    path("api/autoreplies/create/", flow.api_create_autoreply, name="api_create_autoreply"),
    path("api/autoreplies/<int:pk>/", flow.api_get_autoreply, name="api_get_autoreply"),
    path("api/autoreplies/<int:pk>/update/", flow.api_update_autoreply, name="api_update_autoreply"),
    path("api/autoreplies/<int:pk>/delete/", flow.api_delete_autoreply, name="api_delete_autoreply"),
    
    # Flow APIs
    path("api/flows/", flow.api_list_flows, name="api_list_flows"),
    path("api/flows/create/", SaveFlowView.as_view(), name="api_create_flow"),
    path("api/flows/<int:pk>/", flow.api_get_flow, name="api_get_flow"),
    path("api/flows/<int:pk>/update/", flow.api_update_flows, name="api_update_flow"),
    path("api/flows/<int:pk>/delete/", flow.api_delete_flow, name="api_delete_flow"),
    path("api/flows/<int:pk>/turnoff/", flow.api_off_flows, name="api_off_flow"),
    # Matching and Media
    path("api/match/", flow.api_match_message, name="api_match_message"),
    path("api/media/upload/", flow.api_upload_media_for_autoreply, name="api_upload_media_for_autoreply"),


    # privacy
    path("privacy/", views.privacy, name="privacy"),

    # save media   
    path("api/upload_media/" , views.upload_media_ , name="upload_media"),

    path("api/get_templates/" , templaite.get_whatsapp_templates , name="api_get_templates") ,



    path('api/channels/create/', views.create_channel_api, name='create_channel'),
   path('api/channels/connect_meta/', views.exchange_token_and_create_channel, name='connect_meta_channel'),


#    for dash 
path('api/dashboard/stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
path('api/dashboard/team/', views.api_team_stats, name='api_team_stats'),



]















 