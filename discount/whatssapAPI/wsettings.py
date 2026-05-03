import json
import logging
import os
import re
import requests
from discount.user_dash import user
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from discount.models import WhatsAppChannel, ChannelAgentRouting, VoiceCloneRequest
from discount.activites import log_activity
from django.views.decorators.http import require_http_methods

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
        new_about = request.POST.get('business_about', '').strip()

        channel_name = request.POST.get('channel_name', '').strip()

        # هل تغير شيء يستدعي الاتصال بـ Meta؟
        profile_changed = (
            (channel.business_description or '') != new_desc or
            (channel.business_address or '') != new_address or
            (channel.business_email or '') != new_email or
            (channel.business_website or '') != new_website or
            (channel.business_about or '') != new_about or
            ('profile_image' in request.FILES)
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

        # AI Voice & Sales Intelligence
        channel.ai_auto_reply = request.POST.get('ai_auto_reply') == 'on'
        channel.ai_voice_enabled = request.POST.get('ai_voice_enabled') == 'on'
        channel.voice_provider = request.POST.get('voice_provider', 'OPENAI').strip() or 'OPENAI'
        if channel.voice_provider not in ('OPENAI', 'ELEVENLABS'):
            channel.voice_provider = 'OPENAI'
        if hasattr(channel, 'ai_voice_provider'):
            channel.ai_voice_provider = channel.voice_provider
        channel.voice_gender = request.POST.get('voice_gender', 'FEMALE').strip() or 'FEMALE'
        if channel.voice_gender not in ('MALE', 'FEMALE'):
            channel.voice_gender = 'FEMALE'
        try:
            delay = int(request.POST.get('voice_delay_seconds', 20))
            channel.voice_delay_seconds = max(10, min(30, delay))
        except (TypeError, ValueError):
            channel.voice_delay_seconds = 20
        channel.ai_order_capture = request.POST.get('ai_order_capture') != 'off'  # default True
        if hasattr(channel, "ai_llm_engine"):
            _eng = (request.POST.get("ai_llm_engine") or "AUTO").strip().upper()
            if _eng in ("AUTO", "GPT_4O", "CLAUDE_3_5"):
                channel.ai_llm_engine = _eng
            else:
                channel.ai_llm_engine = "AUTO"
        if hasattr(channel, 'order_notify_method'):
            channel.order_notify_method = (request.POST.get('order_notify_method') or '').strip() or ''
            if channel.order_notify_method not in ('', 'EMAIL', 'WHATSAPP'):
                channel.order_notify_method = ''
        if hasattr(channel, 'order_notify_email'):
            channel.order_notify_email = (request.POST.get('order_notify_email') or '').strip() or None
        if hasattr(channel, 'order_notify_whatsapp_phone'):
            channel.order_notify_whatsapp_phone = (request.POST.get('order_notify_whatsapp_phone') or '').strip() or None
        # ElevenLabs API key is managed from environment only (ELEVENLABS_API_KEY).
        channel.voice_cloning_enabled = request.POST.get('voice_cloning_enabled') == 'on'
        if not _channel_is_premium(channel):
            channel.voice_cloning_enabled = False
        # Hard-guard: clear features if plan does not allow (prevents UI/API bypass)
        if not _store_can_feature(channel, 'auto_reply'):
            channel.ai_auto_reply = False
        if not _store_can_feature(channel, 'ai_voice'):
            channel.ai_voice_enabled = False
        # Voice Studio
        if hasattr(channel, 'voice_language'):
            channel.voice_language = request.POST.get('voice_language', 'AUTO').strip() or 'AUTO'
            if channel.voice_language not in ('AUTO', 'AR_MA', 'AR_SA', 'FR_FR', 'EN_US'):
                channel.voice_language = 'AUTO'
        if hasattr(channel, 'voice_stability'):
            try:
                channel.voice_stability = max(0.0, min(1.0, float(request.POST.get('voice_stability', 0.5))))
            except (TypeError, ValueError):
                channel.voice_stability = 0.5
        if hasattr(channel, 'voice_similarity'):
            try:
                channel.voice_similarity = max(0.0, min(1.0, float(request.POST.get('voice_similarity', 0.75))))
            except (TypeError, ValueError):
                channel.voice_similarity = 0.75
        # ai_voice_provider kept in sync with voice_provider above

        # حفظ في قاعدة البيانات
        channel.save()
        log_activity('wa_channel_updated', f"Channel settings updated: {channel.name}", request=request, related_object=channel)

        # ---------------------------------------------------------
        # 5. المزامنة مع Meta (فقط إذا تغير البروفايل)
        # ---------------------------------------------------------
        meta_sync_status = "skipped"
        meta_error = None

        if profile_changed:
            try:
                # استدعاء دالة المزامنة الخارجية
                profile_payload = {
                    "description": new_desc,
                    "address": new_address,
                    "email": new_email,
                    "website": new_website,
                    "about": new_about,
                }
                sync_success, error_msg = sync_profile_with_meta(channel, profile_payload=profile_payload)
                
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
                'enable_welcome_msg': channel.enable_welcome_msg,
                'ai_auto_reply': getattr(channel, 'ai_auto_reply', False),
                'ai_voice_enabled': getattr(channel, 'ai_voice_enabled', False),
                'voice_provider': getattr(channel, 'voice_provider', 'OPENAI'),
                'voice_gender': getattr(channel, 'voice_gender', 'FEMALE'),
                'voice_delay_seconds': getattr(channel, 'voice_delay_seconds', 20),
                'ai_order_capture': getattr(channel, 'ai_order_capture', True),
                'ai_llm_engine': getattr(channel, 'ai_llm_engine', 'AUTO') or 'AUTO',
                'voice_cloning_enabled': getattr(channel, 'voice_cloning_enabled', False),
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
import requests
import mimetypes
from django.conf import settings

def sync_profile_with_meta(channel, profile_payload=None):
    if not channel.phone_number_id or not channel.access_token:
        return False, "Missing Phone Number ID or Access Token"

    base_url = "https://graph.facebook.com/v18.0"
    user_headers = {"Authorization": f"Bearer {channel.access_token}"}
    
    # ✅ استخراج App Access Token (هذا هو المفتاح لحل المشكلة)
    # يتكون من APP_ID|APP_SECRET وهو يملك صلاحيات مطور التطبيق برمجياً
    app_access_token = f"{settings.META_APP_ID}|{settings.META_APP_SECRET}"

    # 1. تحديث البيانات النصية (باستخدام توكن العميل - سليم)
    url_text = f"{base_url}/{channel.phone_number_id}/whatsapp_business_profile"
    profile_payload = profile_payload or {}
    description = (profile_payload.get("description", channel.business_description) or "").strip()
    address = (profile_payload.get("address", channel.business_address) or "").strip()
    email = (profile_payload.get("email", channel.business_email) or "").strip()
    website = (profile_payload.get("website", channel.business_website) or "").strip()
    about = (profile_payload.get("about", channel.business_about) or "").strip()

    # IMPORTANT: Meta sync must contain ONLY General-card profile fields.
    payload_text = {
        "messaging_product": "whatsapp",
        "description": description,
        "address": address,
        "email": email,
        "websites": [website] if website else [],
    }
    if about:
        payload_text["about"] = about

    try:
        text_resp = requests.post(url_text, headers=user_headers, json=payload_text, timeout=10)
        if text_resp.status_code >= 400:
            return False, f"Text Sync Error: HTTP {text_resp.status_code} - {text_resp.text[:300]}"
    except Exception as e:
        return False, f"Text Sync Error: {str(e)}"

    # 2. تحديث صورة البروفايل (الطريقة المصححة)
    if channel.profile_image:
        try:
            img_file = channel.profile_image.open('rb')
            file_content = img_file.read()
            file_size = len(file_content)
            mime_type, _ = mimetypes.guess_type(channel.profile_image.name)
            mime_type = mime_type or 'image/jpeg'
            img_file.close()

            # أ) إنشاء جلسة رفع باستخدام App Access Token (لأن التطبيق هو المالك)
            session_url = f"{base_url}/{settings.META_APP_ID}/uploads"
            session_params = {
                "file_length": file_size,
                "file_type": mime_type,
                "access_token": app_access_token # ✅ التغيير هنا
            }
            
            session_resp = requests.post(session_url, params=session_params)
            if session_resp.status_code != 200:
                return False, f"Upload Session Failed: {session_resp.text}"
            
            upload_session_id = session_resp.json().get('id')

            # ب) رفع الصورة فعلياً باستخدام App Access Token
            upload_url = f"{base_url}/{upload_session_id}"
            headers_upload = {
                "Authorization": f"OAuth {app_access_token}", # ✅ التغيير هنا
                "file_offset": "0"
            }
            
            upload_resp = requests.post(upload_url, headers=headers_upload, data=file_content)
            if upload_resp.status_code != 200:
                return False, f"Binary Upload Failed: {upload_resp.text}"
            
            image_handle = upload_resp.json().get('h')

            # ج) الخطوة الأخيرة: ربط الـ Handle بالبروفايل (باستخدام توكن العميل)
            # يجب استخدام توكن العميل هنا لأننا نعدل على حسابه الخاص
            profile_pic_payload = {
                "messaging_product": "whatsapp",
                "profile_picture_handle": image_handle
            }
            
            final_resp = requests.post(url_text, headers=user_headers, json=profile_pic_payload)
            
            if final_resp.status_code != 200:
                return False, f"Final Update Failed: {final_resp.text}"

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

       
        channel_name = channel.name
        channel_phone = channel.phone_number
        channel.delete()
        
        # تنظيف الكاش
        cache.delete(cache_key)
        log_activity('wa_channel_deleted', f"Channel deleted: {channel_name} ({channel_phone})", request=request)
        return JsonResponse({'status': 'success', 'message': 'Channel deleted successfully'})

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



def fetch_meta_display_name(channel):
    """
    Fetch Meta display name (verified_name) from Cloud API.
    """
    if not channel or not channel.phone_number_id or not channel.access_token:
        return None
    url = f"https://graph.facebook.com/v18.0/{channel.phone_number_id}"
    params = {'fields': 'verified_name,display_phone_number'}
    headers = {"Authorization": f"Bearer {channel.access_token}"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code != 200:
            return None
        payload = response.json() or {}
        verified_name = (payload.get('verified_name') or '').strip()
        if verified_name:
            return verified_name
        display_phone = (payload.get('display_phone_number') or '').strip()
        return display_phone or None
    except Exception:
        return None


def fetch_meta_quality_rating(channel):
    """
    Fetch phone quality rating from Meta Cloud API.
    Typical values: GREEN, YELLOW, RED.
    """
    if not channel or not channel.phone_number_id or not channel.access_token:
        return None
    url = f"https://graph.facebook.com/v18.0/{channel.phone_number_id}"
    params = {'fields': 'quality_rating'}
    headers = {"Authorization": f"Bearer {channel.access_token}"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code != 200:
            return None
        payload = response.json() or {}
        quality = payload.get('quality_rating')
        if quality is None:
            return None
        quality_str = str(quality).strip().upper()
        return quality_str or None
    except Exception:
        return None


def fetch_meta_account_details(channel):
    """
    Fetch account details from Meta Cloud API for settings card.
    Returns normalized dict with safe fallbacks.
    """
    details = {
        'display_name': None,
        'connected_number': None,
        'waba_id': getattr(channel, 'business_account_id', None) if channel else None,
        'messaging_limit': None,
        'quality_rating': None,
        'account_status': None,
    }
    if not channel or not channel.phone_number_id or not channel.access_token:
        return details

    headers = {"Authorization": f"Bearer {channel.access_token}"}

    # Phone number node details
    try:
        phone_url = f"https://graph.facebook.com/v18.0/{channel.phone_number_id}"
        phone_params = {'fields': 'verified_name,display_phone_number,quality_rating,name_status,code_verification_status'}
        phone_res = requests.get(phone_url, headers=headers, params=phone_params, timeout=5)
        if phone_res.status_code == 200:
            payload = phone_res.json() or {}
            details['display_name'] = (payload.get('verified_name') or '').strip() or None
            details['connected_number'] = (payload.get('display_phone_number') or '').strip() or None
            qr = (payload.get('quality_rating') or '')
            details['quality_rating'] = str(qr).strip().upper() or None
            status = (payload.get('name_status') or payload.get('code_verification_status') or '')
            details['account_status'] = str(status).strip().upper() or None
    except Exception:
        pass

    # WABA node details (messaging tier and review status if available)
    if details['waba_id']:
        try:
            waba_url = f"https://graph.facebook.com/v18.0/{details['waba_id']}"
            waba_params = {'fields': 'messaging_limit_tier,account_review_status'}
            waba_res = requests.get(waba_url, headers=headers, params=waba_params, timeout=5)
            if waba_res.status_code == 200:
                waba_payload = waba_res.json() or {}
                limit_tier = (waba_payload.get('messaging_limit_tier') or '')
                details['messaging_limit'] = str(limit_tier).strip().upper() or None
                if not details['account_status']:
                    acc_status = (waba_payload.get('account_review_status') or '')
                    details['account_status'] = str(acc_status).strip().upper() or None
        except Exception:
            pass

    return details


def _channel_is_premium(channel):
    """True if store (channel owner) plan allows voice cloning. Uses Plan model."""
    return _store_can_feature(channel, 'voice_cloning')


def _store_can_feature(channel, feature_name):
    """True if channel owner's plan allows the feature."""
    if not channel or not getattr(channel, 'owner', None):
        return False
    store = channel.owner
    if hasattr(store, 'is_feature_allowed') and callable(store.is_feature_allowed):
        return store.is_feature_allowed(feature_name)
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
        latest_clone_req = VoiceCloneRequest.objects.filter(
            merchant=getattr(channel, "owner", None)
        ).order_by("-created_at").first()
        meta_account = fetch_meta_account_details(channel)
        meta_display_name = meta_account.get('display_name') or fetch_meta_display_name(channel)
        meta_quality_rating = meta_account.get('quality_rating') or fetch_meta_quality_rating(channel)
        data = {
            'channel_name': channel.name,
            'meta_display_name': meta_display_name,
            'meta_quality_rating': meta_quality_rating,
            'meta_connected_number': meta_account.get('connected_number'),
            'meta_waba_id': meta_account.get('waba_id'),
            'meta_messaging_limit': meta_account.get('messaging_limit'),
            'meta_account_status': meta_account.get('account_status'),
            'phone_number': channel.phone_number,
            'status': channel.is_active,
            
            'b_descr': channel.business_description or '',
            'b_address': channel.business_address or '',
            'b_email': channel.business_email or '',
            'b_website': channel.business_website or '',
            'b_about': channel.business_about or '', # تأكدنا من تحديثها
            
            'b_welcom_enable': channel.enable_welcome_msg,
            'b_welcom_body': channel.welcome_msg_body or '',
            'b_img': img_url,
            # AI Voice & Sales
            'ai_auto_reply': getattr(channel, 'ai_auto_reply', False),
            'ai_voice_enabled': getattr(channel, 'ai_voice_enabled', False),
            'voice_provider': getattr(channel, 'voice_provider', 'OPENAI'),
            'voice_gender': getattr(channel, 'voice_gender', 'FEMALE'),
            'voice_delay_seconds': getattr(channel, 'voice_delay_seconds', 20),
            'ai_order_capture': getattr(channel, 'ai_order_capture', True),
            'ai_llm_engine': getattr(channel, 'ai_llm_engine', 'AUTO') or 'AUTO',
            'order_notify_method': getattr(channel, 'order_notify_method', '') or '',
            'order_notify_email': getattr(channel, 'order_notify_email', '') or '',
            'order_notify_whatsapp_phone': getattr(channel, 'order_notify_whatsapp_phone', '') or '',
            'voice_cloning_enabled': getattr(channel, 'voice_cloning_enabled', False),
            'is_premium': _channel_is_premium(channel),
            # Plan-based feature flags for UI paywall (backend re-verifies on use)
            'plan_can_ai_voice': _store_can_feature(channel, 'ai_voice'),
            'plan_can_voice_cloning': _store_can_feature(channel, 'voice_cloning'),
            'plan_can_auto_reply': _store_can_feature(channel, 'auto_reply'),
            'plan_can_advanced_tones': _store_can_feature(channel, 'advanced_tones'),
            'voice_language': getattr(channel, 'voice_language', 'AUTO'),
            'voice_stability': getattr(channel, 'voice_stability', 0.5),
            'voice_similarity': getattr(channel, 'voice_similarity', 0.75),
            'cloned_voice_id': getattr(channel, 'cloned_voice_id', '') or '',
            'clone_request_status': getattr(latest_clone_req, "status", "") if latest_clone_req else "",
            'ai_voice_provider': getattr(channel, 'ai_voice_provider', 'OPENAI'),
            'elevenlabs_model_id': getattr(channel, 'elevenlabs_model_id', 'eleven_multilingual_v2'),
            'selected_voice_id': getattr(channel, 'selected_voice_id', '') or '',
            'voice_dialect': getattr(channel, 'voice_dialect', '') or '',
            'voice_preview_url': getattr(channel, 'voice_preview_url', '') or '',
            # Weighted Chat Routing (for settings UI): all assigned agents + defaults for missing config
            'routing': _routing_list_for_channel(channel),
            'ai_routing_percentage': getattr(channel, 'ai_routing_percentage', 0),
            'dynamic_offline_redistribution': getattr(channel, 'dynamic_offline_redistribution', False),
        }
           
        return JsonResponse({'status': 'success', 'data': data})

    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def _routing_list_for_channel(channel):
    """Return routing list for all assigned_agents with is_online; missing configs get 0% and is_accepting_chats True."""
    if not channel:
        return []
    config_by_agent = {
        c.agent_id: c
        for c in ChannelAgentRouting.objects.filter(channel=channel).select_related("agent")
    }
    out = []
    for agent in channel.assigned_agents.all():
        c = config_by_agent.get(agent.id)
        out.append({
            "agent_id": agent.id,
            "agent_name": getattr(agent, "username", None) or getattr(agent, "first_name", "") or str(agent.id),
            "routing_percentage": c.routing_percentage if c else 0,
            "is_accepting_chats": c.is_accepting_chats if c else True,
            "is_online": getattr(agent, "is_online", True),
        })
    return out


def _get_channel_for_user(request, channel_id):
    """Return channel if request.user has access (owner, team_admin, superuser, or assigned_agent), else None."""
    if not channel_id:
        return None
    try:
        channel = WhatsAppChannel.objects.get(id=channel_id)
    except WhatsAppChannel.DoesNotExist:
        return None
    user = request.user
    if user == channel.owner or user.is_superuser or getattr(user, 'is_team_admin', False):
        return channel
    if channel.assigned_agents.filter(pk=user.pk).exists():
        return channel
    return None


# ---------------------------------------------------------------------------
# Weighted Chat Routing: PUT /api/settings/routing
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["PUT", "POST"])
def update_routing_settings(request):
    """
    Update routing_percentage and is_accepting_chats for channel agents; optional ai_routing_percentage and dynamic_offline_redistribution.
    Body (JSON): { "channel_id": <id>, "routing": [ { "agent_id": <id>, "routing_percentage": 80, "is_accepting_chats": true }, ... ], "ai_routing_percentage": 0, "dynamic_offline_redistribution": false }
    When Full Autopilot is ON: human total + ai_routing_percentage must equal 100. When OFF: human total must equal 100 (AI share forced to 0).
    """
    try:
        if request.content_type and "application/json" in request.content_type:
            body = json.loads(request.body or "{}")
        else:
            body = getattr(request, "json", None) or {}
            if not body and request.POST:
                channel_id = request.POST.get("channel_id")
                routing_raw = request.POST.get("routing")
                if routing_raw:
                    try:
                        routing = json.loads(routing_raw)
                    except json.JSONDecodeError:
                        return JsonResponse({
                            "status": "error",
                            "message": "Invalid JSON in 'routing'.",
                        }, status=400)
                else:
                    routing = []
                body = {"channel_id": channel_id, "routing": routing}
        channel_id = body.get("channel_id")
        routing_list = body.get("routing")
        if channel_id is None:
            return JsonResponse({
                "status": "error",
                "message": "Missing channel_id.",
            }, status=400)
        if not isinstance(routing_list, list):
            return JsonResponse({
                "status": "error",
                "message": "Missing or invalid 'routing' array.",
            }, status=400)

        channel = _get_channel_for_user(request, channel_id)
        if not channel:
            return JsonResponse({"status": "error", "message": "Channel not found or access denied."}, status=404)

        allowed_agent_ids = set(channel.assigned_agents.values_list("id", flat=True))
        total = 0
        for item in routing_list:
            if not isinstance(item, dict):
                return JsonResponse({
                    "status": "error",
                    "message": "Each routing entry must be an object with agent_id, routing_percentage, is_accepting_chats.",
                }, status=400)
            agent_id = item.get("agent_id")
            pct = item.get("routing_percentage", 0)
            accepting = item.get("is_accepting_chats", True)
            if agent_id is None:
                return JsonResponse({"status": "error", "message": "Each entry must have agent_id (AI is configured via ai_routing_percentage)."}, status=400)
            if agent_id not in allowed_agent_ids:
                return JsonResponse({
                    "status": "error",
                    "message": f"Agent id {agent_id} is not assigned to this channel.",
                }, status=400)
            try:
                pct = int(pct)
            except (TypeError, ValueError):
                pct = 0
            pct = max(0, min(100, pct))
            total += pct
            item["_agent_id"] = agent_id
            item["_routing_percentage"] = pct
            item["_is_accepting_chats"] = bool(accepting)

        ai_auto_reply = getattr(channel, "ai_auto_reply", False)
        ai_pct = body.get("ai_routing_percentage")
        if ai_pct is not None:
            try:
                ai_pct = max(0, min(100, int(ai_pct)))
            except (TypeError, ValueError):
                ai_pct = getattr(channel, "ai_routing_percentage", 0)
        else:
            ai_pct = getattr(channel, "ai_routing_percentage", 0)
        if not ai_auto_reply:
            ai_pct = 0
        human_total = total
        if ai_auto_reply:
            if human_total + ai_pct != 100:
                return JsonResponse({
                    "status": "error",
                    "message": f"When Full Autopilot is ON, human total + AI percentage must equal 100 (human={human_total}, AI={ai_pct}).",
                }, status=400)
        else:
            if human_total != 100:
                return JsonResponse({
                    "status": "error",
                    "message": f"Sum of routing_percentage must equal exactly 100 (got {total}).",
                }, status=400)

        for item in routing_list:
            agent_id = item["_agent_id"]
            ChannelAgentRouting.objects.update_or_create(
                channel=channel,
                agent_id=agent_id,
                defaults={
                    "routing_percentage": item["_routing_percentage"],
                    "is_accepting_chats": item["_is_accepting_chats"],
                },
            )

        channel.ai_routing_percentage = ai_pct
        channel.dynamic_offline_redistribution = bool(body.get("dynamic_offline_redistribution", getattr(channel, "dynamic_offline_redistribution", False)))
        channel.save(update_fields=["ai_routing_percentage", "dynamic_offline_redistribution"])

        return JsonResponse({"status": "success", "message": "Routing updated."})
    except json.JSONDecodeError as e:
        return JsonResponse({"status": "error", "message": f"Invalid JSON: {e}"}, status=400)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("update_routing_settings: %s", e)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
@require_POST
def voice_preview(request):
    """POST channel_id, optional text. Returns MP3 file for preview. Temp file deleted after send."""
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    text = request.POST.get('text', '').strip() or None
    try:
        from discount.whatssapAPI.voice_engine import get_preview_audio
        path = get_preview_audio(channel, text=text)
        if not path or not os.path.exists(path):
            return JsonResponse({'status': 'error', 'message': 'Could not generate preview'}, status=502)
        with open(path, 'rb') as f:
            content = f.read()
        try:
            os.remove(path)
        except OSError:
            pass
        from django.http import HttpResponse
        r = HttpResponse(content, content_type='audio/mpeg')
        r['Content-Disposition'] = 'inline; filename="preview.mp3"'
        return r
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("voice_preview: %s", e)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_POST
def voice_clone(request):
    """
    Backward-compatible alias.
    Old UI calls /api/voice-clone/; now this endpoint creates a *pending* manual-review request.
    """
    return voice_request_clone(request)


@login_required
@require_POST
def voice_request_clone(request):
    """
    POST channel_id, file, consent_agreed.
    Store request in pending state only (manual review workflow); do NOT call ElevenLabs here.
    """
    channel_id = request.POST.get("channel_id")
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({"status": "error", "message": "Channel not found"}, status=404)
    if not _store_can_feature(channel, "voice_cloning"):
        return JsonResponse({"status": "error", "message": "Your current plan does not include voice cloning."}, status=403)

    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"status": "error", "message": "No audio file provided"}, status=400)

    consent_raw = (request.POST.get("consent_agreed") or "").strip().lower()
    consent_agreed = consent_raw in ("1", "true", "yes", "on")
    if not consent_agreed:
        return JsonResponse(
            {"status": "error", "message": "You must confirm legal ownership/authorization for this voice sample."},
            status=400,
        )

    # Lightweight server validation for file type and size (15 MB max)
    name = (getattr(uploaded, "name", "") or "").lower()
    allowed_ext = (".mp3", ".wav", ".m4a", ".ogg", ".webm")
    if not any(name.endswith(ext) for ext in allowed_ext):
        return JsonResponse({"status": "error", "message": "Unsupported audio format. Use mp3/wav/m4a/ogg/webm."}, status=400)
    size = getattr(uploaded, "size", 0) or 0
    if size > 15 * 1024 * 1024:
        return JsonResponse({"status": "error", "message": "Audio file is too large. Max size is 15MB."}, status=400)

    dialect_raw = (request.POST.get("dialect") or "").strip().upper()
    from discount.models import VOICE_DIALECT_CHOICES

    valid_dialects = {k for k, _ in VOICE_DIALECT_CHOICES}
    if dialect_raw not in valid_dialects:
        return JsonResponse(
            {"status": "error", "message": "Please select what dialect this voice is speaking."},
            status=400,
        )

    merchant = getattr(channel, "owner", None) or request.user
    req = VoiceCloneRequest.objects.create(
        merchant=merchant,
        audio_file=uploaded,
        consent_agreed=True,
        dialect=dialect_raw,
        status=VoiceCloneRequest.STATUS_PENDING,
    )
    return JsonResponse(
        {
            "status": "success",
            "request_id": req.id,
            "message": "Your voice is under review by our team for security purposes. It will be activated within 24 hours.",
        }
    )


# ---------------------------------------------------------------------------
# Voice Gallery (multilingual v2, native-friendly Arabic)
# ---------------------------------------------------------------------------

@login_required
def voice_gallery_page(request):
    """Render Voice Gallery; channel_id in GET or POST."""
    channel_id = request.GET.get('channel_id') or request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id) if channel_id else None
    return render(request, 'whatssap/voice_gallery.html', {
        'channel': channel,
        'channel_id': channel.id if channel else None,
    })


@login_required
@require_POST
def voice_gallery_list(request):
    """Return VoiceGalleryEntry rows + current selected_voice_id and voice_preview_url for channel."""
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    from discount.services.voice_catalog import serialize_voices_for_api

    form_prov = (request.POST.get("voice_provider") or "").strip().upper()
    if form_prov in ("OPENAI", "ELEVENLABS"):
        tts_provider = form_prov
    else:
        tts_provider = (
            getattr(channel, "ai_voice_provider", None)
            or getattr(channel, "voice_provider", None)
            or "OPENAI"
        )
        tts_provider = str(tts_provider).strip().upper() or "OPENAI"
    api_key = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    return JsonResponse({
        'status': 'success',
        'tts_provider': tts_provider,
        'voices': serialize_voices_for_api(request, provider=tts_provider),
        'selected_voice_id': getattr(channel, 'selected_voice_id', None) or '',
        'voice_dialect': getattr(channel, 'voice_dialect', None) or '',
        'voice_preview_url': getattr(channel, 'voice_preview_url', None) or '',
        'has_api_key': bool(api_key),
    })


@login_required
@require_POST
def voice_gallery_preview(request):
    """
    POST channel_id, voice_id. Returns local MP3 only — **never** calls ElevenLabs.

    Resolution order:
    1) `VoiceGalleryEntry.preview_audio_file` (uploaded in Admin)
    2) Static file from `preview_file` under static/audio/voice-previews/
    """
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    voice_id = (request.POST.get('voice_id') or '').strip()
    if not voice_id:
        return JsonResponse({'status': 'error', 'message': 'voice_id required'}, status=400)

    from django.contrib.staticfiles import finders
    from django.http import FileResponse
    from discount.models import VoiceGalleryEntry

    log = logging.getLogger(__name__)

    entry = VoiceGalleryEntry.objects.filter(elevenlabs_voice_id=voice_id, is_active=True).first()
    if not entry:
        return JsonResponse({'status': 'error', 'message': 'Voice not found in gallery'}, status=404)

    # 1) Uploaded MP3 (Admin → preview audio file)
    if getattr(entry, "preview_audio_file", None) and entry.preview_audio_file.name:
        try:
            fh = entry.preview_audio_file.open("rb")
            resp = FileResponse(fh, content_type="audio/mpeg", as_attachment=False)
            resp["Content-Disposition"] = 'inline; filename="voice_sample.mp3"'
            return resp
        except Exception as e:
            log.warning("voice_gallery_preview: could not open uploaded preview: %s", e)

    # 2) Static preview under staticfiles (audio/voice-previews/<preview_file>)
    static_name = (entry.preview_file or "").strip()
    if static_name:
        found = finders.find(f"audio/voice-previews/{static_name}")
        if found and os.path.isfile(found):
            try:
                fh = open(found, "rb")
                resp = FileResponse(fh, content_type="audio/mpeg", as_attachment=False)
                resp["Content-Disposition"] = 'inline; filename="voice_sample.mp3"'
                return resp
            except Exception as e:
                log.warning("voice_gallery_preview: could not open static preview: %s", e)

    return JsonResponse(
        {
            "status": "error",
            "message": (
                "No local preview audio for this voice. In Django Admin → Voice Gallery entries, "
                "upload an MP3 in “Preview audio file”, or set “Preview file” to a filename that exists "
                "under static/audio/voice-previews/."
            ),
        },
        status=400,
    )


@login_required
@require_POST
def voice_gallery_select(request):
    """POST channel_id, voice_id, optional voice_preview_url. Save selected voice to channel."""
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    voice_id = (request.POST.get('voice_id') or '').strip()
    if not voice_id:
        return JsonResponse({'status': 'error', 'message': 'voice_id required'}, status=400)
    voice_preview_url = (request.POST.get('voice_preview_url') or '').strip() or None
    if not hasattr(channel, 'selected_voice_id'):
        return JsonResponse({'status': 'error', 'message': 'Model not supported'}, status=400)

    from discount.models import VoiceGalleryEntry

    entry = VoiceGalleryEntry.objects.filter(elevenlabs_voice_id=voice_id, is_active=True).first()
    if not entry:
        return JsonResponse({'status': 'error', 'message': 'Voice not found in gallery'}, status=404)
    form_prov = (request.POST.get("voice_provider") or "").strip().upper()
    if form_prov in ("OPENAI", "ELEVENLABS"):
        tts_provider = form_prov
    else:
        tts_provider = (
            getattr(channel, "ai_voice_provider", None)
            or getattr(channel, "voice_provider", None)
            or "OPENAI"
        )
        tts_provider = str(tts_provider).strip().upper() or "OPENAI"
    row_provider = str(getattr(entry, "provider", "ELEVENLABS") or "ELEVENLABS").strip().upper()
    if row_provider != tts_provider:
        return JsonResponse(
            {
                'status': 'error',
                'message': f'This voice is for {row_provider}; switch Provider to match or pick another voice.',
            },
            status=400,
        )

    channel.selected_voice_id = voice_id
    if hasattr(channel, 'voice_preview_url'):
        channel.voice_preview_url = voice_preview_url or ''
    update_fields = ['selected_voice_id', 'voice_preview_url'] if hasattr(channel, 'voice_preview_url') else ['selected_voice_id']
    try:
        if hasattr(channel, "voice_dialect"):
            channel.voice_dialect = getattr(entry, "dialect", None) or channel.voice_dialect
            update_fields.append("voice_dialect")
    except Exception:
        pass
    channel.save(update_fields=update_fields)
    return JsonResponse({'status': 'success', 'selected_voice_id': voice_id})