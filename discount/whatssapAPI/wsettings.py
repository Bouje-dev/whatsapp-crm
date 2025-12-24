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
                    print("Meta sync failed:", error_msg)
                    
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
    if not channel.phone_number_id or not channel.access_token:
        return False, "Missing Phone Number ID or Access Token"

    base_url = "https://graph.facebook.com/v18.0"
    headers_auth = {"Authorization": f"Bearer {channel.access_token}"}

    # =========================================================
    # 1. تحديث البيانات النصية (الوصف، العنوان، البريد...) - هذا الجزء سليم
    # =========================================================
    url_text = f"{base_url}/{channel.phone_number_id}/whatsapp_business_profile"
    payload_text = {
        "messaging_product": "whatsapp",
        "description": channel.business_description,
        "address": channel.business_address,
        "email": channel.business_email,
        "websites": [channel.business_website] if channel.business_website else [],
    }

    try:
        resp_text = requests.post(url_text, headers=headers_auth, json=payload_text, timeout=10)
        if resp_text.status_code != 200:
            return False, f"Text Sync Failed: {resp_text.text}"
    except Exception as e:
        return False, f"Text Sync Error: {str(e)}"

    # =========================================================
    # 2. تحديث صورة البروفايل (الطريقة الصحيحة والمعقدة للـ Cloud API)
    # =========================================================
    if channel.profile_image:
        try:
            # أ) فتح الصورة وقراءة بياناتها وحجمها
            img_file = channel.profile_image.open('rb')
            file_content = img_file.read()
            file_size = len(file_content)
            mime_type, _ = mimetypes.guess_type(channel.profile_image.name)
            mime_type = mime_type or 'image/jpeg'
            img_file.close()

            # ب) جلب App ID (ضروري لإنشاء جلسة الرفع)
            debug_token_url = f"{base_url}/debug_token?input_token={channel.access_token}"
            app_id_resp = requests.get(debug_token_url, headers=headers_auth)
            if app_id_resp.status_code != 200:
                return False, "Failed to fetch App ID from Meta"
            
            app_id = app_id_resp.json().get('data', {}).get('app_id')
            if not app_id:
                return False, "App ID not found in token"

            # ج) إنشاء جلسة رفع (Create Upload Session)
            # نقطة النهاية: /<APP_ID>/uploads
            session_url = f"{base_url}/{app_id}/uploads"
            session_params = {
                "file_length": file_size,
                "file_type": mime_type,
                "access_token": channel.access_token 
            }
            
            session_resp = requests.post(session_url, params=session_params)
            if session_resp.status_code != 200:
                return False, f"Failed to create upload session: {session_resp.text}"
            
            upload_session_id = session_resp.json().get('id')

            # د) رفع الصورة فعلياً إلى الجلسة للحصول على الـ Handle
            # نقطة النهاية: https://graph.facebook.com/v18.0/<UPLOAD_SESSION_ID>
            upload_url = f"{base_url}/{upload_session_id}"
            headers_upload = {
                "Authorization": f"OAuth {channel.access_token}",
                "file_offset": "0"
            }
            
            # نرفع البيانات الثنائية (Binary) مباشرة
            upload_resp = requests.post(upload_url, headers=headers_upload, data=file_content)
            
            if upload_resp.status_code != 200:
                return False, f"Binary Upload Failed: {upload_resp.text}"
            
            # الرد يحتوي على 'h' وهو الـ Handle المطلوب
            image_handle = upload_resp.json().get('h')

            # هـ) الخطوة الأخيرة: ربط الـ Handle بالبروفايل
            profile_pic_url = f"{base_url}/{channel.phone_number_id}/whatsapp_business_profile"
            profile_pic_payload = {
                "messaging_product": "whatsapp",
                "profile_picture_handle": image_handle
            }
            
            final_resp = requests.post(profile_pic_url, headers=headers_auth, json=profile_pic_payload)
            
            if final_resp.status_code != 200:
                return False, f"Final Profile Picture Update Failed: {final_resp.text}"

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





import requests
from django.core.files.base import ContentFile

def fetch_and_update_meta_profile(channel):
    """
    جلب بيانات البروفايل من Meta وتحديث القناة محلياً
    """
    if not channel.phone_number_id or not channel.access_token:
        return # لا يمكن العمل بدون توكن

    url = f"https://graph.facebook.com/v18.0/{channel.phone_number_id}/whatsapp_business_profile"
    params = {
        'fields': 'about,address,description,email,profile_picture_url,websites,vertical'
    }
    headers = {"Authorization": f"Bearer {channel.access_token}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json().get('data', [])
            if not data: return
            
            profile = data[0]
            
            # تحديث البيانات المحلية
            channel.business_description = profile.get('description', '')
            channel.business_address = profile.get('address', '')
            channel.business_email = profile.get('email', '')
            channel.business_about = profile.get('about', '') # ملاحظة: about أحيانا تحتاج endpoint منفصل لكن غالباً تأتي هنا
            
            websites = profile.get('websites', [])
            if websites:
                channel.business_website = websites[0] # نأخذ أول رابط
            
            # تحديث الصورة (اختياري لأنه قد يستهلك وقتاً في التحميل)
            # meta_pic_url = profile.get('profile_picture_url')
            # if meta_pic_url:
            #     # هنا يمكنك كتابة كود لتحميل الصورة وحفظها إذا أردت
            #     pass

            channel.save()
            return True
            
    except Exception as e:
        print(f"Error syncing from Meta: {e}")
        return False



@login_required
@require_POST
def get_channel_settings(request):
    channel_id = request.POST.get('channel_id')
    
    if not channel_id:
        return JsonResponse({'status': 'error', 'message': 'Channel ID is required'}, status=400)

    try:
        user = request.user
        
        # 1. جلب القناة
        if user.is_superuser or getattr(user, 'is_team_admin', False):
            channel = WhatsAppChannel.objects.get(id=channel_id)
        else:
            channel = WhatsAppChannel.objects.get(id=channel_id, assigned_agents=user)

        # ============================================================
        # 🔥 الجديد: محاولة المزامنة مع Meta قبل عرض البيانات 🔥
        # ============================================================
        # نقوم بذلك فقط إذا كان هناك توكن صالح، ولا نوقف الكود لو فشل (try/except داخلي)
        if channel.access_token:
            fetch_and_update_meta_profile(channel)
            # نعيد تحميل الكائن من الداتابيز لضمان أننا نملك أحدث القيم المحفوظة
            channel.refresh_from_db()

        # 2. معالجة رابط الصورة
        img_url = channel.profile_image.url if channel.profile_image else '/static/img/default-wa.png'

        # 3. تجهيز البيانات (الآن هي محدثة من ميتا)
        data = {
            'channel_name': channel.name,
            'phone_number': channel.phone_number,
            'status': channel.is_active,
            
            'b_descr': channel.business_description or '',
            'b_address': channel.business_address or '',
            'b_email': channel.business_email or '',
            'b_website': channel.business_website or '',
            'b_about': channel.business_about or '', # تأكدنا من تحديثها
            
            'b_welcom_enable': channel.enable_welcome_msg,
            'b_welcom_body': channel.welcome_msg_body or '',
            
            'b_img': img_url
        }
           
        return JsonResponse({'status': 'success', 'data': data})

    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)