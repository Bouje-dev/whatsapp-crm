"""
URL configuration for disound project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path ,include
from discount import views ,shopifyLink , user_dash , activites , tests
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404
from django.shortcuts import render

 
urlpatterns = [    
    # whatssap API cloud 
    path('discount/whatssapAPI/', include('discount.whatssapAPI.urls')),
 
    # tracking/get_tracking_company_data/
    path('admin/', admin.site.urls),

    path('discount/marketing/', include('discount.marketing.urls')),
    # ad spy links 
    path('discount/adspy/', include('discount.adspy.urls')),


     path('tracking/get_tracking_company_data/' , views.get_tracking_company_data , name='get_tracking_company_data'),

     path('tracking/filter_cod_products/' , views.filterinCode , name='filterinCode'),
    path('', views.home , name='home'),
    path('tracking/update-cod-products/', views.update_cod_products, name='update_cod_products'),
    path('api/products/<int:product_id>/', views.product_detail_api, name='product_detail_api'),
    path('page/', views.page, name='page'),
        path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('api/update-product/', views.update_product, name='update_product'),
    path('updateshopify/', shopifyLink.sync_products_view, name='updateshopify'),
    path('update_cod_ids_safely', shopifyLink.update_id, name='update_cod_ids_safely'),

    path('tracking/table_update/', shopifyLink.table_update, name='table_update'), #def for updating table 
    path('tracking/', shopifyLink.tracking, name='tracking'), #def for updating table 
    # path('search/', shopifyLink.getSearch, name='search'),

    path('tracking/orders/', shopifyLink.getSearch, name='orders_list'),
    path('tracking/filter/', shopifyLink.filter_orders, name='orders_filter'),
    # path('emploi/analytic/', user_dash.analytics_view, name='user_analityc'),
# user  
    path('auth/login/', user_dash.login_user, name='login'),
    path('auth/logout/', user_dash.logout, name='logout'),
    path('auth/singup/', user_dash.singup, name='singup'),
    path('auth/change_password/', user_dash.change_password, name='change_password'),
    # path('auth/forgot_password/', user_dash.forgot_password, name='forgot_password'),

    path('auth/edit_profile/', user_dash.edit_profile, name='update_profile'),
    path('auth/upgrade_plan/', user_dash.upgrade_plan, name='upgrade_plan'),

 
    path('tracking/user/access/token/', user_dash.link_token, name='access_token'),
    path('delete_token/<int:token_id>/', user_dash.delete_token, name='delete_token'),

    path('tracking/user/', user_dash.user, name='user'),


# stuff 
    path('tracking/user/invite_staff/', user_dash.invite_staff, name='invite_staff'),
    path('accept-invite/<str:token>/', user_dash.accept_invite , name='accept_invite'),
    path('tracking/unlink_user/<int:id>/', user_dash.unlink_user , name='unlink_user'),
    path('tracking/contact_support', user_dash.contact_support, name='contact_support'),
    path('tracking/user/setpassword/', user_dash.set_password, name='set_password') ,
   


#    update product from platform 
    path('tracking/update_product/', shopifyLink.update_product, name='update_product'),
 
    path('tracking/update_user_permissions/<int:user_id>/', user_dash.updatepermissions, name='upgrade_plan'),


    path('get-product-info/', user_dash.get_product_info, name='get_product_info'),
        path('submit-order/', user_dash.submit_order, name='submit_order'),
    path('tracking/update_order_limit/', user_dash.updatedealy, name='update_order_limit'),

     path("track-order", user_dash.track_injaz, name="track_order"),
     path("leadstracking/", user_dash.leadstracking, name="leadstracking"),
     path("tracking/save_activity_tracking/", activites.save_activity_tracking, name="save_activity_tracking"),

    # path('tracking/leadstracking/', user_dash.displayleads, name='displayleads'),  

    path("testing/" , tests.testing_Chanels , name="testing" ) ,
    path('send_msgtesting/', tests.send_msgtesting, name='send_msgtesting'),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if not settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


def custom_404(request, exception):
    return render(request, '404.html', status=404)

handler404 = custom_404
