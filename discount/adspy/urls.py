from django.contrib import admin
from django.urls import path ,include
from discount.adspy import views
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404
from django.shortcuts import render

 


from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdArchiveViewSet
from . import admin_views
router = DefaultRouter()
router.register(r'ads', AdArchiveViewSet, basename='ads')

urlpatterns = [
    path('adspy_dashboard' , views.adspy_dashboard , name="Adspy" )  ,
    path('api/', include(router.urls) ) ,
    path('api/saved-ads/' , views.collection_view , name="collection_view" )  ,
    path('api/save-ad/' , views.save_ad , name="save_ad" )  ,
    path('api/unsave-ad/' , views.unsave_ad , name="unsave_ad" )  ,
    path('api/fetch_ad/' , admin_views.fetch_ads_view , name="fetch_ads_view" )  ,
    
 
    path('admin/ads-dashboard/', admin_views.ads_dashboard_view, name='ads_dashboard'),
    path('api/admin/ads-list/', admin_views.api_ads_list, name='api_ads_list'),
    path('api/admin/stats/', admin_views.api_admin_stats, name='api_admin_stats'),
    path('api/admin/refresh-collection/', admin_views.api_refresh_collection, name='api_refresh_collection'),
    path('api/admin/delete-saved-ad/<int:saved_id>/', admin_views.api_delete_saved_ad, name='api_delete_saved_ad'),
]
