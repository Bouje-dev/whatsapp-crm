from django.contrib import admin
from discount.models import CODProduct ,Order , SimpleOrder ,Products , TeamInvitation ,UserProductPermission , Lead , ScriptFlow
# Register your models here.
from discount.models import ExternalOrder ,  CampaignVisit  , AdArchive , AdCreative , UserSavedAd , CTA ,Advertiser , Message
class CODdrop(admin.ModelAdmin):
    list_display= ['name']
admin.site.register(CODProduct, CODdrop)

# class CODorder(admin.ModelAdmin):
#     list_display= ['name']
# admin.site.register(Order, CODorder)



class SimpleOrders(admin.ModelAdmin):
    list_display= ['customer_phone' , 'product_name']
    search_fields = ['customer_phone' , 'product_name']
admin.site.register(SimpleOrder, SimpleOrders)




# discount/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser ,ExternalTokenmodel

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_verified', 'is_staff' ,'is_team_admin')
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('phone', 'is_verified')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)


class ExternalTokenmo(admin.ModelAdmin):
    list_display = ['platform', 'created_at']
admin.site.register(ExternalTokenmodel, ExternalTokenmo)


class product(admin.ModelAdmin):
    list_display = ['name']

admin.site.register(Products, product)


class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = ( 'name' , 'email' , 'admin' , )

admin.site.register(TeamInvitation, TeamInvitationAdmin)




class UserProductPermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'role']
admin.site.register(UserProductPermission, UserProductPermissionAdmin)



class OrderAdmin(admin.ModelAdmin):
    list_display = ['customer_name','customer_phone', 'product', 'created_at']
    search_fields = ['customer_phone', 'product']
admin.site.register(Order, OrderAdmin)




class CampaignVisitAdmin(admin.ModelAdmin):
    list_display = ['flow','phone_normalized', 'created_at', 'utm_campaign']
    search_fields = ['phone_normalized', 'utm_campaign']

admin.site.register(CampaignVisit, CampaignVisitAdmin)


class ExternalOrders(admin.ModelAdmin):
    list_display = ['platform','phone_normalized', 'created_at', 'status']
    search_fields = ['phone_normalized', 'product']
    
admin.site.register(ExternalOrder, ExternalOrders)



class leads(admin.ModelAdmin):
    list_display = ['phone' ,'status', 'created_at']

admin.site.register(Lead, leads)


class ScriptFlowAdmin(admin.ModelAdmin):
    list_display = ['name', 'active', 'created_at']
    search_fields = ['name']

admin.site.register(ScriptFlow, ScriptFlowAdmin)


# class AdCreativeInline(admin.StackedInline):
#     model = AdCreative
#     extra = 0
#     readonly_fields = ('thumbnail_url', 'image_hash', 'is_video', 'video_url', 'body')
    
# admin.site.register(AdCreative , AdCreativeInline)



class AdArchiveAdmin(admin.ModelAdmin):
    list_display = ('ad_id', 'page_name', 'advertiser', 'platform', 'status', 'ad_delivery_start_time')
    search_fields = ('ad_id', 'page_name', 'advertiser__name')
    list_filter = ('platform', 'status', 'country__code')
    # readonly_fields = ('ad_id', 'page_name', 'advertiser', 'platform', 'status', 'ad_delivery_start_time', 'ad_snapshot_url', 'creative')
    # inlines = [AdCreativeInline]
    ordering = ('-ad_delivery_start_time',)
admin.site.register(AdArchive, AdArchiveAdmin)

class AdCreativeAdmin(admin.ModelAdmin):
    list_display = ('thumbnail_url', 'is_video', 'video_url')
    search_fields = ('ad__ad_id', 'ad__page_name', 'ad__advertiser__name')
    list_filter = ('is_video',)
admin.site.register(AdCreative, AdCreativeAdmin)


class AdvertiserAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
admin.site.register(Advertiser, AdvertiserAdmin)


# https://video.fcmn1-2.fna.fbcdn.net/o1/v/t2/f2/m366/AQNC-qzn7DntDBCJzwZTnchw49CBAaOzv3qGSmyrLWPZkQk940zrG5mVRxfQMJ37lVGZ4pcXG6vJQEK_gJ0PPRL-YARRZ2ByysvY6SDyDm1-xQ.mp4?_nc_cat=103&_nc_oc=AdmTsE913o2gt1-S-QC-SFtGSFSHgotybqaoMAGpUZXqRnng7V1XyDHA2Rcl9OUNj7s&_nc_sid=5e9851&_nc_ht=video.fcmn1-2.fna.fbcdn.net&_nc_ohc=VbCcw_8ukD0Q7kNvwEeQ9-V&efg=eyJ2ZW5jb2RlX3RhZyI6Inhwdl9wcm9ncmVzc2l2ZS5WSV9VU0VDQVNFX1BST0RVQ1RfVFlQRS4uQzMuNzIwLmRhc2hfaDI2NC1iYXNpYy1nZW4yXzcyMHAiLCJ4cHZfYXNzZXRfaWQiOjEyMDc5NDM0NjM4MDM2MjksInZpX3VzZWNhc2VfaWQiOjEwMTIyLCJkdXJhdGlvbl9zIjo5MCwidXJsZ2VuX3NvdXJjZSI6Ind3dyJ9&ccb=17-1&vs=5276c2f3874e5046&_nc_vs=HBksFQIYRWZiX2VwaGVtZXJhbC8wNjQyQkM2NTMwQzA1MkM0RDBERjI0QkQwOTBDRDJBNl9tdF8xX3ZpZGVvX2Rhc2hpbml0Lm1wNBUAAsgBEgAVAhg6cGFzc3Rocm91Z2hfZXZlcnN0b3JlL0dCV0dteHVlZFRnOTJzNEJBTl93M1dsTzJLOEZidjRHQUFBRhUCAsgBEgAoABgAGwKIB3VzZV9vaWwBMRJwcm9ncmVzc2l2ZV9yZWNpcGUBMRUAACba64yRyKelBBUCKAJDMywXQFaIgxJul40YGWRhc2hfaDI2NC1iYXNpYy1nZW4yXzcyMHARAHUAZZSeAQA&_nc_gid=YUFW08BRPsgjvnW2i38zVg&_nc_zt=28&oh=00_Afb5nXLBgC6-d8q7ESCr1MHdy2obPgeBWNzB8XM4MEyRXw&oe=68DA00C1


class  MessageT(admin.ModelAdmin):
    list_display = ('sender', 'body', 'timestamp', 'is_from_me')
    search_fields = ('sender', 'body')
    list_filter = ('is_from_me', 'timestamp')

admin.site.register(Message, MessageT)





# Flows and every thing  
from .models import  AutoReply , Flow , Node ,   Message ,Contact , Template

class AutoReplyAdmin(admin.ModelAdmin):
    list_display = ( 'trigger', 'created_at', 'updated_at')
    
    ordering = ('-created_at',)
admin.site.register(AutoReply, AutoReplyAdmin)


class FlowAdmin(admin.ModelAdmin):
    list_display = ( 'name', 'created_at', 'updated_at')

    ordering = ('-created_at',)

admin.site.register(Flow, FlowAdmin)



class Nodes(admin.ModelAdmin):
    list_display = ('node_type','flow')

admin.site.register(Node , Nodes)


 

class Contacts(admin.ModelAdmin):
    list_display =('name' , 'phone')

admin.site.register(Contact , Contacts)



class Templaites(admin.ModelAdmin):
    list_display = ('name' , 'status')
admin.site.register(Template , Templaites)

# testing 
from .models import groupchat , GroupMessages
admin.site.register(groupchat)
admin.site.register(GroupMessages)




from .models import WhatsAppChannel
class ChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'phone_number_id', 'business_account_id', 'access_token', 'is_active', 'created_at')
    search_fields = ('name', 'phone_number', 'phone_number_id', 'business_account_id')
    list_filter = ('is_active', 'created_at')
admin.site.register(WhatsAppChannel, ChannelAdmin)


# from .models import ChannelPermission
# class ChannelPermissionAdmin(admin.ModelAdmin):
#     list_display = ('channel', 'user', 'permission')
#     search_fields = ('channel', 'user')
#     list_filter = ('user',)
# admin.site.register(ChannelPermission, ChannelPermissionAdmin)


# from .models import ChannelUser
# class ChannelUserAdmin(admin.ModelAdmin):
#     list_display = ('channel', 'user', 'permission')
#     search_fields = ('channel', 'user', 'permission')
#     list_filter = ('permission',)
# admin.site.register(ChannelUser, ChannelUserAdmin)


# from .models import ChannelMessage
# class ChannelMessageAdmin(admin.ModelAdmin):
#     list_display = ('channel', 'user', 'message')
#     search_fields = ('channel', 'user', 'message')
#     list_filter = ('message',)
# admin.site.register(ChannelMessage, ChannelMessageAdmin) 