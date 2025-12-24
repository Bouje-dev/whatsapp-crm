import json
import re
import requests
from discount.user_dash import user
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from discount.models import WhatsAppChannel

@login_required
@require_POST
def update_channel_settings(request):
    """
    API لتحديث إعدادات القناة ومزامنة البروفايل مع واتساب
    """
    try:
        # 1. التحقق من البيانات الأساسية
        channel_id = request.POST.get('channel_id')
        if not channel_id:
            return JsonResponse({'status': 'error', 'message': 'Missing Channel ID'}, status=400)

        # 2. جلب القناة والتحقق من الملكية/الصلاحية
        try:
            channel = WhatsAppChannel.objects.get(id=channel_id)
        except WhatsAppChannel.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)

        # هل المستخدم هو المالك أو أدمن الفريق أو سوبر يوزر؟
        if not (request.user == channel.owner or request.user.is_team_admin or request.user.is_superuser):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized access'}, status=403)

        # ---------------------------------------------------------
        # 3. التحقق من التغييرات في البروفايل (قبل الحفظ)
        # ---------------------------------------------------------
        # نستخرج القيم الجديدة من الطلب
        new_desc = request.POST.get('business_description', '').strip()
        new_address = request.POST.get('business_address', '').strip()
        new_email = request.POST.get('business_email', '').strip()
        new_website = request.POST.get('business_website', '').strip()
        new_about = request.POST.get('business_about', '').strip(),

        channel_name = request.POST.get('channel_name', '').strip()
        print('reuqest, ', request.POST)
        
        # هل تغير شيء يستدعي الاتصال بـ Meta؟
        profile_changed = (
            channel.business_description != new_desc or
            channel.business_address != new_address or
            channel.business_email != new_email or
            channel.business_website != new_website or
            channel.business_about != new_about
        )

        # ---------------------------------------------------------
        # 4. تحديث البيانات محلياً (Database)
        # ---------------------------------------------------------
        # بيانات البروفايل
        channel.name = channel_name
        channel.business_description = new_desc
        channel.business_address = new_address
        channel.business_email = new_email
        channel.business_website = new_website
        channel.business_about = new_about 
        if 'profile_image' in request.FILES:
            channel.profile_image = request.FILES['profile_image']


        # بيانات الأتمتة (تحويل 'on' إلى True)
        channel.enable_welcome_msg = request.POST.get('enable_welcome_msg') == 'on'
        channel.welcome_msg_body = request.POST.get('welcome_msg_body', '')

        # بيانات النظام
        channel.enable_collision_detection = request.POST.get('enable_collision_detection') == 'on'
        # channel.show_blue_ticks = request.POST.get('show_blue_ticks') == 'on' # إذا كنت تستخدمها

        # حفظ في قاعدة البيانات
        channel.save()

        # ---------------------------------------------------------
        # 5. المزامنة مع Meta (فقط إذا تغير البروفايل)
        # ---------------------------------------------------------
        meta_sync_status = "skipped"
        meta_error = None

        if profile_changed:
            try:
                # استدعاء دالة المزامنة الخارجية
                sync_success, error_msg = sync_profile_with_meta(channel)
                
                if sync_success:
                    meta_sync_status = "success"
                else:
                    meta_sync_status = "failed"
                    meta_error = error_msg
                    
            except Exception as e:
                meta_sync_status = "failed"
                meta_error = str(e)
        
        # ---------------------------------------------------------
        # 6. الرد النهائي
        # ---------------------------------------------------------
        response_data = {
            'status': 'success',
            'message': 'Settings saved successfully',
            'meta_sync': {
                'status': meta_sync_status,
                'error': meta_error
            },
            # نرسل الإعدادات الجديدة ليتم تحديث واجهة الجافاسكريبت فوراً
            'config': {
                'enable_collision_detection': channel.enable_collision_detection,
                'enable_welcome_msg': channel.enable_welcome_msg
            }
        }

        # إذا فشلت المزامنة، نرسل تحذيراً ولكن لا نوقف العملية (status 200)
        # لأن الحفظ المحلي تم بنجاح
        if meta_sync_status == "failed":
            response_data['warning'] = f"Saved locally, but WhatsApp Sync failed: {meta_error}"

        return JsonResponse(response_data)

    except Exception as e:
        # التقاط أي خطأ غير متوقع في الكود
        print(f"❌ Critical Error saving settings: {e}")
        return JsonResponse({'status': 'error', 'message': f"Server Error: {str(e)}"}, status=500)


# ---------------------------------------------------
# Helper Function: Meta Sync
# ---------------------------------------------------
import requests
import mimetypes
import os

def sync_profile_with_meta(channel):
    """
    تحديث بيانات النشاط التجاري + صورة البروفايل على واتساب
    """
    if not channel.phone_number_id or not channel.access_token:
        return False, "Missing Phone Number ID or Access Token"

    base_url = "https://graph.facebook.com/v18.0"
    headers_auth = {"Authorization": f"Bearer {channel.access_token}"}

    # ==========================================
    # 1. تحديث البيانات النصية (Description, Address...)
    # ==========================================
    url_text = f"{base_url}/{channel.phone_number_id}/whatsapp_business_profile"
    
    payload_text = {
        "messaging_product": "whatsapp",
        "description": channel.business_description,
        "address": channel.business_address,
        "email": channel.business_email,
        "websites": [channel.business_website] if channel.business_website else [],
        # ملاحظة: "about" (الحالة) لها endpoint مختلف (whatsapp_business_profile/about)
    }

    try:
        # إرسال البيانات النصية
        resp_text = requests.post(url_text, headers=headers_auth, json=payload_text, timeout=10)
        
        if resp_text.status_code != 200:
            return False, f"Text Sync Failed: {resp_text.text}"

    except Exception as e:
        return False, f"Text Sync Error: {str(e)}"

    # ==========================================
    # 2. تحديث صورة البروفايل (Profile Picture)
    # ==========================================
    if channel.profile_image:
        url_photo = f"{base_url}/{channel.phone_number_id}/photo"
        
        try:
            # يجب فتح الملف كـ Binary (rb)
            # channel.profile_image.path يعطيك المسار الكامل للملف على السيرفر
            file_path = channel.profile_image.path
            
            if os.path.exists(file_path):
                # تحديد نوع الملف تلقائياً (jpeg/png)
                mime_type, _ = mimetypes.guess_type(file_path)
                
                with open(file_path, 'rb') as img_file:
                    files = {
                        'file': (os.path.basename(file_path), img_file, mime_type or 'image/jpeg')
                    }
                    
                    # ملاحظة هامة: لا نضع Content-Type يدوياً هنا، requests ستضعه تلقائياً كـ multipart/form-data
                    resp_photo = requests.post(url_photo, headers=headers_auth, files=files, timeout=20)
                    
                    if resp_photo.status_code != 200:
                        return False, f"Photo Sync Failed: {resp_photo.text}"
            else:
                return False, "Image file not found on server"

        except Exception as e:
            return False, f"Photo Sync Error: {str(e)}"

    return True, None














import random
from django.core.mail import send_mail
from django.core.cache import cache
from django.conf import settings

# 1. دالة إرسال رمز التحقق (OTP)
@login_required
@require_POST
def trigger_delete_otp(request):
    channel_id = request.POST.get('channel_id')
   
    
    try:
        channel = WhatsAppChannel.objects.get(id=channel_id)
        
        if request.user != channel.owner and not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        # توليد رمز عشوائي من 6 أرقام
        otp_code = str(random.randint(100000, 999999))
        
        # تخزين الرمز في الكاش لمدة 5 دقائق (300 ثانية)
        # المفتاح يربط القناة بالمستخدم لضمان الأمان
        cache_key = f"del_otp_{channel.id}_{request.user.id}"
        cache.set(cache_key, otp_code, timeout=300)

        # إرسال الإيميل
        send_mail(
            subject=f"Confirm Channel Deletion: {channel.phone_number}",
            message=f"Your confirmation code to DELETE channel {channel.phone_number} is: {otp_code}\nThis code expires in 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[request.user.email],
            fail_silently=False,
        )

        return JsonResponse({'status': 'success', 'message': 'OTP sent to your email'})

    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# 2. دالة تأكيد الحذف
@login_required
@require_POST
def confirm_delete_channel(request):
    channel_id = request.POST.get('channel_id')
    user_code = request.POST.get('otp_code')

    try:
        channel = WhatsAppChannel.objects.get(id=channel_id)
        
        # التحقق من الكاش
        cache_key = f"del_otp_{channel.id}_{request.user.id}"
        cached_code = cache.get(cache_key)

        if not cached_code:
            return JsonResponse({'status': 'error', 'message': 'Code expired or invalid. Please request a new one.'}, status=400)
        
        if str(cached_code) != str(user_code):
            return JsonResponse({'status': 'error', 'message': 'Incorrect code'}, status=400)

        # الحذف النهائي
        # channel.delete()
        
        # تنظيف الكاش
        cache.delete(cache_key)

        return JsonResponse({'status': 'success', 'message': 'Channel deleted successfully'}) # غير الرابط حسب مشروعك

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




@login_required
@require_POST
def get_channel_settings(request):
    channel_id = request.POST.get('channel_id')
    
    if not channel_id:
        return JsonResponse({'status': 'error', 'message': 'Channel ID is required'}, status=400)

    try:
        user = request.user
        
        # 1. التحقق من الصلاحية وجلب القناة
        if user.is_superuser or getattr(user, 'is_team_admin', False):
            # الأدمن يرى القنوات التي يملكها
            channel = WhatsAppChannel.objects.get(id=channel_id)
            # تحقق إضافي للأمان إن أردت: if channel.owner != user and not user.is_superuser: raise ...
        else:
            # الموظف العادي يرى القنوات المعين فيها (رغم أنه غالباً لن يدخل هنا)
            channel = WhatsAppChannel.objects.get(id=channel_id, assigned_agents=user)

        # 2. معالجة رابط الصورة
        # نتأكد أن هناك صورة، وإلا نرسل رابطاً افتراضياً أو نصاً فارغاً
        img_url = channel.profile_image.url if channel.profile_image else '/static/img/default-wa.png'

        # 3. تجهيز البيانات
        data = {
            'channel_name': channel.name,
            'phone_number': channel.phone_number,
            'status': channel.is_active,
            
            # بيانات البروفايل
            'b_descr': channel.business_description or '',
            'b_address': channel.business_address or '',
            'b_email': channel.business_email or '',
            'b_website': channel.business_website or '',
            'b_about': channel.business_about or '',
            
            # بيانات الأتمتة
            'b_welcom_enable': channel.enable_welcome_msg, # True/False
            'b_welcom_body': channel.welcome_msg_body or '',
            
            # رابط الصورة
            'b_img': img_url
        }
           
        return JsonResponse({'status': 'success', 'data': data})

    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Channel not found or access denied'}, status=404)
    except Exception as e:
        print(f"Error fetching settings: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)