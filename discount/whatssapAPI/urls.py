
from discount.whatssapAPI import wsettings
from django.urls import path
from . import views , flow , process_messages , templaite , whaDash

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
    path("api_orders/<int:order_id>/sync/", views.api_order_sync_google_sheets, name="api_order_sync_google_sheets"),
    path("api_products/", views.api_products_list, name="api_products_list"),
    path("api_products/create/", views.api_products_create, name="api_products_create"),
    path("api_products/extract_from_link/", views.api_products_extract_from_link, name="api_products_extract_from_link"),
    path("api_products/<int:product_id>/", views.api_products_detail, name="api_products_detail"),
    path("api_products/<int:product_id>/update/", views.api_products_update, name="api_products_update"),
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
    path("api/flows/scrape-product-url/", flow.api_scrape_product_url, name="api_scrape_product_url"),
    path("api/flows/node-media-upload/", flow.api_upload_flow_node_media, name="api_upload_flow_node_media"),
    path("api/preview-voice/", flow.api_preview_voice, name="api_preview_voice"),
    path("api/personas/", flow.api_list_personas, name="api_list_personas"),
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
# AI Analytics Dashboard
path('analytics/', views.ai_analytics_dashboard_page, name='ai_analytics_dashboard'),
path('api/ai-analytics/', views.api_ai_analytics, name='api_ai_analytics'),
path('api/ai-analytics/export-csv/', views.api_ai_analytics_export_csv, name='api_ai_analytics_export_csv'),

path('api/assign-agent/', views.assign_agent_to_contact, name='assign_agent_to_contact'),

path('api/update-crm/', views.update_contact_crm, name='update_contact_crm'),

path('api/analytics/lifecycle/' , whaDash.api_lifecycle_stats , name='api_lifecycle_stats'),
path('api/agent-stats/', whaDash.api_agent_stats, name='api_agent_stats'),
path('api/create-canned-response/' , whaDash.create_canned_response , name='api_create_canned_response'),
path('api/get-canned-responses/', whaDash.get_canned_responses , name='api_get_canned_responses'),

path('api/confirm-delete-channel/' , wsettings.confirm_delete_channel , name='confirm_delete_channel'),
path('api/trigger-delete-otp/' , wsettings.trigger_delete_otp , name='trigger_delete_otp'),
path('api/update-channel-settings/' , wsettings.update_channel_settings , name='update_channel_settings'),

path('api/get-channel-settings/' , wsettings.get_channel_settings , name='get_channel_settings'),

    # Voice Studio
    path('api/voice-preview/', wsettings.voice_preview, name='voice_preview'),
    path('api/voice-clone/', wsettings.voice_clone, name='voice_clone'),
    # Voice Gallery (multilingual v2, native-friendly)
    path('voice-gallery/', wsettings.voice_gallery_page, name='voice_gallery_page'),
    path('api/voice-gallery/list/', wsettings.voice_gallery_list, name='voice_gallery_list'),
    path('api/voice-gallery/preview/', wsettings.voice_gallery_preview, name='voice_gallery_preview'),
    path('api/voice-gallery/select/', wsettings.voice_gallery_select, name='voice_gallery_select'),
    # HITL: Chat session AI status and re-enable
    path('api/chat-session/status/', process_messages.api_chat_session_status, name='api_chat_session_status'),
    path('api/chat-session/re-enable-ai/', process_messages.api_chat_session_reenable_ai, name='api_chat_session_reenable_ai'),
    path('api/chat-session/toggle-ai/', process_messages.api_chat_session_toggle_ai, name='api_chat_session_toggle_ai'),
    # Google Sheets: global config + test connection + service email
    path('api/google-sheets/config/', flow.api_google_sheets_config, name='api_google_sheets_config'),
    path('api/google-sheets/test-connection/', flow.api_google_sheets_test_connection, name='api_google_sheets_test_connection'),
    path('api/google-sheets/service-email/', flow.api_google_sheets_service_email, name='api_google_sheets_service_email'),
]















 