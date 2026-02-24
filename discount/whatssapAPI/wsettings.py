import json
import os
import re
import requests
from discount.user_dash import user
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from discount.models import WhatsAppChannel
from discount.activites import log_activity

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
        if hasattr(channel, 'order_notify_method'):
            channel.order_notify_method = (request.POST.get('order_notify_method') or '').strip() or ''
            if channel.order_notify_method not in ('', 'EMAIL', 'WHATSAPP'):
                channel.order_notify_method = ''
        if hasattr(channel, 'order_notify_email'):
            channel.order_notify_email = (request.POST.get('order_notify_email') or '').strip() or None
        if hasattr(channel, 'order_notify_whatsapp_phone'):
            channel.order_notify_whatsapp_phone = (request.POST.get('order_notify_whatsapp_phone') or '').strip() or None
        # Only update API key when user provided a non-empty value (never wipe with empty on save)
        _new_key = (request.POST.get('elevenlabs_api_key') or '').strip()
        if _new_key:
            channel.elevenlabs_api_key = _new_key
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
                'enable_welcome_msg': channel.enable_welcome_msg,
                'ai_auto_reply': getattr(channel, 'ai_auto_reply', False),
                'ai_voice_enabled': getattr(channel, 'ai_voice_enabled', False),
                'voice_provider': getattr(channel, 'voice_provider', 'OPENAI'),
                'voice_gender': getattr(channel, 'voice_gender', 'FEMALE'),
                'voice_delay_seconds': getattr(channel, 'voice_delay_seconds', 20),
                'ai_order_capture': getattr(channel, 'ai_order_capture', True),
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

def sync_profile_with_meta(channel):
    if not channel.phone_number_id or not channel.access_token:
        return False, "Missing Phone Number ID or Access Token"

    base_url = "https://graph.facebook.com/v18.0"
    user_headers = {"Authorization": f"Bearer {channel.access_token}"}
    
    # ✅ استخراج App Access Token (هذا هو المفتاح لحل المشكلة)
    # يتكون من APP_ID|APP_SECRET وهو يملك صلاحيات مطور التطبيق برمجياً
    app_access_token = f"{settings.META_APP_ID}|{settings.META_APP_SECRET}"

    # 1. تحديث البيانات النصية (باستخدام توكن العميل - سليم)
    url_text = f"{base_url}/{channel.phone_number_id}/whatsapp_business_profile"
    payload_text = {
        "messaging_product": "whatsapp",
        "description": channel.business_description,
        "address": channel.business_address,
        "email": channel.business_email,
        "websites": [channel.business_website] if channel.business_website else [],
    }

    try:
        requests.post(url_text, headers=user_headers, json=payload_text, timeout=10)
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
            'b_img': img_url,
            # AI Voice & Sales
            'ai_auto_reply': getattr(channel, 'ai_auto_reply', False),
            'ai_voice_enabled': getattr(channel, 'ai_voice_enabled', False),
            'voice_provider': getattr(channel, 'voice_provider', 'OPENAI'),
            'voice_gender': getattr(channel, 'voice_gender', 'FEMALE'),
            'voice_delay_seconds': getattr(channel, 'voice_delay_seconds', 20),
            'ai_order_capture': getattr(channel, 'ai_order_capture', True),
            'order_notify_method': getattr(channel, 'order_notify_method', '') or '',
            'order_notify_email': getattr(channel, 'order_notify_email', '') or '',
            'order_notify_whatsapp_phone': getattr(channel, 'order_notify_whatsapp_phone', '') or '',
            'elevenlabs_api_key': getattr(channel, 'elevenlabs_api_key', '') or '',
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
            'ai_voice_provider': getattr(channel, 'ai_voice_provider', 'OPENAI'),
            'elevenlabs_model_id': getattr(channel, 'elevenlabs_model_id', 'eleven_multilingual_v2'),
            'selected_voice_id': getattr(channel, 'selected_voice_id', '') or '',
            'voice_preview_url': getattr(channel, 'voice_preview_url', '') or '',
        }
           
        return JsonResponse({'status': 'success', 'data': data})

    except WhatsAppChannel.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
    """POST channel_id, file (audio sample). Clone voice via ElevenLabs, save to channel, and create a VoicePersona for My Voices with a unique name."""
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    if not request.FILES.get('file'):
        return JsonResponse({'status': 'error', 'message': 'No audio file provided'}, status=400)
    try:
        from discount.whatssapAPI.voice_engine import clone_voice
        from discount.models import VoicePersona
        from django.core.cache import cache
        voice_id, err = clone_voice(channel, request.FILES['file'])
        if err:
            return JsonResponse({'status': 'error', 'message': err}, status=400)
        user = getattr(channel, 'owner', None) or request.user
        # Create a VoicePersona so it appears in Flow Builder "My Voices" with a unique name
        existing_names = set(
            VoicePersona.objects.filter(owner=user, is_system=False).values_list('name', flat=True)
        )
        num = 1
        while f"My Voice {num}" in existing_names:
            num += 1
        name = f"My Voice {num}"
        VoicePersona.objects.create(
            name=name,
            description="Cloned voice",
            voice_id=voice_id,
            is_system=False,
            owner=user,
            behavioral_instructions="",
            language_code="AR_MA",
            tier=VoicePersona.TIER_STANDARD,
        )
        cache.delete(f"personas_my_{user.id}")
        return JsonResponse({'status': 'success', 'voice_id': voice_id})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("voice_clone: %s", e)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
    """Return VOICE_GALLERY + current selected_voice_id and voice_preview_url for channel."""
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    from discount.whatssapAPI.voice_engine import VOICE_GALLERY
    api_key = (getattr(channel, 'elevenlabs_api_key', None) or '').strip() or os.environ.get('ELEVENLABS_API_KEY', '').strip()
    return JsonResponse({
        'status': 'success',
        'voices': VOICE_GALLERY,
        'selected_voice_id': getattr(channel, 'selected_voice_id', None) or '',
        'voice_preview_url': getattr(channel, 'voice_preview_url', None) or '',
        'has_api_key': bool(api_key),
    })


@login_required
@require_POST
def voice_gallery_preview(request):
    """POST channel_id, voice_id, optional text. Returns MP3 for that voice (multilingual_v2). Temp file deleted after send."""
    channel_id = request.POST.get('channel_id')
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)
    voice_id = (request.POST.get('voice_id') or '').strip()
    if not voice_id:
        return JsonResponse({'status': 'error', 'message': 'voice_id required'}, status=400)
    text = (request.POST.get('text') or 'مرحباً، أنا مساعدك الذكي.').strip()[:500]
    try:
        from discount.whatssapAPI.voice_engine import generate_voice_sample
        api_key = (getattr(channel, 'elevenlabs_api_key', None) or '').strip() or os.environ.get('ELEVENLABS_API_KEY', '').strip()
        if not api_key:
            return JsonResponse({
                'status': 'error',
                'message': 'ElevenLabs API key not set. Save your API key in Channel Settings → Voice Identity → ElevenLabs API Key, then try again.',
            }, status=400)
        path, err = generate_voice_sample(voice_id, text, api_key=api_key)
        if err:
            return JsonResponse({'status': 'error', 'message': err}, status=400)
        if not path or not os.path.exists(path):
            return JsonResponse({'status': 'error', 'message': 'Could not generate sample'}, status=502)
        with open(path, 'rb') as f:
            content = f.read()
        try:
            os.remove(path)
        except OSError:
            pass
        from django.http import HttpResponse
        r = HttpResponse(content, content_type='audio/mpeg')
        r['Content-Disposition'] = 'inline; filename="voice_sample.mp3"'
        return r
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("voice_gallery_preview: %s", e)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
    channel.selected_voice_id = voice_id
    if hasattr(channel, 'voice_preview_url'):
        channel.voice_preview_url = voice_preview_url or ''
    channel.save(update_fields=['selected_voice_id', 'voice_preview_url'] if hasattr(channel, 'voice_preview_url') else ['selected_voice_id'])
    return JsonResponse({'status': 'success', 'selected_voice_id': voice_id})