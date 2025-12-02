import logging
from django.conf import settings
from .models import CODProduct ,SimpleOrder , CustomUser ,TeamInvitation , ExternalTokenmodel , Products , Activity ,UserProductPermission,Order
import time
from urllib.parse import quote
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from django.template.loader import render_to_string
from .forms import CustomUserCreationForm ,LoginForm ,ExternalTokenForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.contrib.auth.forms import SetPasswordForm , PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import redirect, render
from .activites import activity_log
from .Codnetwork import  fetch_leads_for_skus
from .crypto import encrypt_token
from django.core.mail import EmailMessage


# إعدادات تسجيل الدخول
def emploi (request):
    orders = 'welcom'
    # return JsonResponse({
    #         'html': render_to_string('partials/_user_analitycs.html', {'orders': orders}),
    #         'status': 'success'
    #     })


    return render ( request , 'partials/_user_analitycs.html', {'orders': orders})

from django.shortcuts import render
from django.db.models import Count, Q
from .models import SimpleOrder
from datetime import datetime, timedelta

# def analytics_view(request):
#     # فلترة حسب SKU إذا تم تحديده
#     sku = request.GET.get('sku', '')
#     period = request.GET.get('period', 'month')
    
#     # تحديد الفترة الزمنية
#     today = datetime.now().date()
#     if period == 'today':
#         start_date = today
#     elif period == 'week':
#         start_date = today - timedelta(days=7)
#     else:  # month
#         start_date = today - timedelta(days=330)
    
#     # استعلام أساسي
#     orders = SimpleOrder.objects.all()
#     if sku:
#         orders = orders.filter(sku=sku)
    
#     # استعلام للفترة الحالية
#     current_period_orders = orders.filter(created_at__gte=start_date)
    
#     # استعلام للفترة الماضية للمقارنة
#     if period == 'today':
#         previous_period_orders = orders.filter(created_at__date=today - timedelta(days=1))
#     elif period == 'week':
#         previous_period_orders = orders.filter(created_at__range=[today - timedelta(days=14), today - timedelta(days=7)])
#     else:  # month
#         previous_period_orders = orders.filter(created_at__range=[today - timedelta(days=60), today - timedelta(days=30)])
    
#     # حساب الإحصائيات الأساسية
#     total_orders = current_period_orders.count()
#     confirmed_orders = current_period_orders.filter().count()
#     shipped_orders = current_period_orders.filter(status='Pending').count()
#     delivered_orders = current_period_orders.filter(status='Delivered').count()
    
#     # حساب النسب المئوية للتغيير
#     prev_total = previous_period_orders.count()
#     orders_change_percentage = calculate_percentage_change(prev_total, total_orders)
    
#     prev_confirmed = previous_period_orders.filter(status='delivered').count()
#     confirmed_change_percentage = calculate_percentage_change(prev_confirmed, confirmed_orders)
    
#     prev_shipped = previous_period_orders.filter(status='shipped').count()
#     shipped_change_percentage = calculate_percentage_change(prev_shipped, shipped_orders)
    
#     prev_delivered = previous_period_orders.filter(status='delivered').count()
#     delivered_change_percentage = calculate_percentage_change(prev_delivered, delivered_orders)
    
#     # توزيع المدن
#     city_distribution = current_period_orders.exclude(customer_city__isnull=True)\
#         .values('customer_city')\
#         .annotate(count=Count('id'))\
#         .order_by('-count')[:10]
    
#     top_cities = list(city_distribution)
#     print(top_cities)
    
#     # معدل التوصيل (نسبة الطلبات الموصلة إلى المؤكدة)
#     delivery_rate = round((delivered_orders / confirmed_orders) * 100, 2) if confirmed_orders > 0 else 0
    
#     # متوسط وقت التوصيل (يمكنك إضافة هذا الحساب إذا كان لديك بيانات الوقت الفعلي للتوصيل)
#     avg_delivery_time = 3  # قيمة افتراضية - يجب استبدالها بحساب حقيقي
    
#     # قائمة SKUs الفريدة لقائمة التحديد
#     unique_skus = SimpleOrder.objects.order_by('sku').values_list('sku', flat=True).distinct()
    
#     context = {
#         'total_orders': total_orders,
#         'confirmed_orders': confirmed_orders,
#         'shipped_orders': shipped_orders,
#         'delivered_orders': delivered_orders,
#         'orders_change_percentage': orders_change_percentage,
#         'confirmed_change_percentage': confirmed_change_percentage,
#         'shipped_change_percentage': shipped_change_percentage,
#         'delivered_change_percentage': delivered_change_percentage,
#         'city_distribution': city_distribution,
#         'top_cities': top_cities,
#         'delivery_rate': delivery_rate,
#         'avg_delivery_time': avg_delivery_time,
#         'unique_skus': unique_skus,
#         'selected_sku': sku,
#         'has_password': request.user.has_usable_password(),

#     }
    
#     # return render(request, 'analytics.html', context)
#     return render ( request , 'partials/_user_analitycs.html', context)

 
def calculate_percentage_change(old_value, new_value):
    if old_value == 0:
        return 100 if new_value > 0 else 0
    return round(((new_value - old_value) / old_value) * 100, 2)




from django.contrib.auth import authenticate, login

def login_user(request):
    error = ""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()

        if not email or not password:
            error = "Please enter both email and password."
        else:
            user = authenticate(request, username=email, password=password)
            if user is not None:
                if not user.is_active:
                    error = "Your account is inactive. Please contact support."
                elif not getattr(user, 'is_verified', True):
                    error = "Your account is not verified. Please check your email for the activation link."
                else:
                    login(request, user)
                    return redirect('tracking')
            else:
                error = "Invalid email or password."
    return render(request, 'user/login.html', {'error': error})

login_required(login_url='/auth/login/')  
def  logout(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('home')  # إعادة التوجيه إلى الصفحة الرئيسية بعد تسجيل الخروج

 



# auth_services.py
from django.contrib.auth import authenticate, login
from django.core.mail import send_mail
from django.conf import settings
from .models import CustomUser
import random
import string

# email = EmailMessage(
#             subject=subject,
#             body=html_content,
#             from_email='bojamaabayad2001@gmail.com',
#             to=[invitation.email],
#         )
#         email.content_subtype = "html"
#         email.send(fail_silently=False)

import threading
from django.core.mail import EmailMessage
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.conf import settings

def _send_email_in_thread(email):
    """تنفيذ الإرسال في ثريد منفصل لعدم حظر السيرفر."""
    try:
        # نستخدم fail_silently=True لضمان عدم انهيار الثريد
        email.send(fail_silently=True) 
    except Exception as e:
        # يجب تسجيل الخطأ هنا لتتبعه في logs Railway
        print(f"❌ Threaded Email Error: {e}")
def resend_activation_email(request):
    user = request.user
    
    if not user.is_authenticated:
        return JsonResponse({'error': 'User not authenticated'}, status=401)

    # 1. توليد الكود
    code = user.generate_verification_code() 

    # 2. بناء الرابط الديناميكي (لحل مشكلة http://127.0.0.1)
    # نستخدم معلومات الطلب لإنشاء رابط حي (Live URL)
    current_host = request.get_host()
    protocol = 'https' if request.is_secure() else 'http'
    
    # تأكد أن المسار 'activate' معرف في urls.py
    activation_link = f'{protocol}://{current_host}/activate/{user.id}/' 

    # 3. بناء محتوى الإيميل
    subject = 'كود التحقق من حسابك'
    message_body = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f5; margin: 0; padding: 0; }}
            .email-container {{ max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e4e4e7; }}
            .header {{ background-color: #7c3aed; padding: 30px; text-align: center; }}
            .header h1 {{ color: #ffffff; margin: 0; font-size: 24px; letter-spacing: 1px; }}
            .content {{ padding: 40px 30px; color: #3f3f46; line-height: 1.6; text-align: center; }}
            .welcome-text {{ font-size: 18px; font-weight: 600; margin-bottom: 20px; color: #18181b; }}
            .code-box {{ background-color: #f3f0ff; color: #7c3aed; font-size: 32px; font-weight: bold; letter-spacing: 5px; padding: 15px; border-radius: 8px; margin: 30px 0; display: inline-block; border: 2px dashed #ddd6fe; }}
            .btn-activate {{ display: inline-block; background-color: #7c3aed; color: #ffffff; text-decoration: none; padding: 12px 30px; border-radius: 8px; font-weight: bold; margin-top: 20px; transition: background 0.3s; }}
            .btn-activate:hover {{ background-color: #6d28d9; }}
            .footer {{ background-color: #fafafa; padding: 20px; text-align: center; font-size: 12px; color: #a1a1aa; border-top: 1px solid #f4f4f5; }}
            .link-fallback {{ font-size: 12px; color: #a1a1aa; margin-top: 20px; word-break: break-all; }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="header">
                <h1>Waselytics</h1>
            </div>
            
            <div class="content">
                <div class="welcome-text">مرحباً {user.user_name or user.email} 👋</div>
                <p>شكراً لتسجيلك معنا! لإكمال إعداد حسابك والبدء في تتبع أرباحك، يرجى استخدام كود التحقق أدناه:</p>
                
                <div class="code-box">{code}</div>
                
                <p>أو يمكنك الضغط على الزر التالي لتفعيل الحساب مباشرة:</p>
                <a href="{activation_link}" class="btn-activate">تفعيل الحساب الآن</a>
                
                <div class="link-fallback">
                    إذا لم يعمل الزر، انسخ الرابط التالي:<br>
                    <a href="{activation_link}" style="color:#7c3aed;">{activation_link}</a>
                </div>
            </div>
            
            <div class="footer">
                &copy; 2025 Waselytics. جميع الحقوق محفوظة.<br>
                هذا إيميل آلي، الرجاء عدم الرد عليه.
            </div>
        </div>
    </body>
    </html>
    """
    
    email = EmailMessage(
            subject,
            body=message_body , 
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
    email.content_subtype = "html"

    
    print("⏳ Attempting to send email via Brevo...")
    email.send(fail_silently=False)  
    print("✅ Email Sent Successfully!")
    if not request.user.is_authenticated:
        login(request, user)
        print('tring to log in  user ')


    
 

        
    # 4. 🔥 الإرسال غير المتزامن (Fixes 500 Timeout)
    email_thread = threading.Thread(target=_send_email_in_thread, args=(email,))
    email_thread.start() 

    # 5. الرد الفوري للواجهة
    return JsonResponse({'success': True, 'message': 'تم إرسال رابط التفعيل لبريدك الإلكتروني. الرجاء التحقق من البريد.'})

def activate_account(request, user_id=None):
    code = request.POST.get('code' , None)
    user = request.user
    if code is not None :
        if user.email_verification_code == code: # نفترض وجود هذا الحقل
            user.is_active = True
            user.is_verified = True
            user.save()
            return JsonResponse({'success': True, 'message': 'Your account has been activated successfully'})
        else: return JsonResponse({'success': False, 'message': 'Invalid activation code'})
    else:
        # حالة النقر على الرابط المباشر
        user = get_object_or_404(CustomUser, pk=user_id) # نفترض CustomUser معرفة
        user.email_verified = True
        user.is_active = True
        user.save()
        return redirect('tracking')


def verify_code(request):
    code = request.POST.get('code' , None)
    user = request.user
    if code is not None :
        if user.email_verification_code == code:
            user.is_active = True
            user.is_verified = True
            user.save()

            return JsonResponse({'success': True, 'message': 'Your account has been activated successfully'})
            
        else: return JsonResponse({'success': False, 'message': 'Invalid activation code'})
  
def register_user(email, password, user_name):
    if CustomUser.objects.filter(email=email).exists():
        raise ValueError('البريد الإلكتروني مسجل مسبقاً')
    
    user = CustomUser.objects.create_user(
        username=email,
        email=email,
        password=password,
        user_name=user_name,
        
        
        # 🔥 التغيير هنا: نجعله نشطاً ليتمكن من الدخول
        is_active=True, 
        
        # ونعتمد على هذا الحقل لمنعه من دخول الداشبورد
        is_verified=True,
        
        is_team_admin=True

    )
    print('user'  ,user)
    
    # إنشاء ملف تعريف المستخدم
    # CustomUserCreationForm.objects.create(user=user)
    
    # إرسال كود التحقق
    # send_verification_email(user)
    
    return user

from django.contrib.auth import login
from django.contrib.auth import authenticate, login

def singup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user_name = form.cleaned_data['user_name']
            password = form.cleaned_data['password1']

            try:
                # 1. إنشاء المستخدم
                user = register_user(email=email, password=password, user_name=user_name)
                try :
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                except Exception as e:
                    print(f"❌ Login Error: {e}")
                    
                resend_activation_email(request)
              
                    
                return redirect('singup')
              
            except ValueError as e:
                print(f"❌ Registration Error: {e}")
               
                form.add_error('email', str(e))
                return render(request, 'user/singup.html', {'form': form})
        else:
            print(f"❌ Form is INVALID. Errors: {form.errors}")
            return render(request, 'user/singup.html', {'form': form})
    
    else:
        # GET Request

        print(f"🔎 Checking session: Is Authenticated? {request.user.is_authenticated}")
        
        if request.user.is_authenticated and not getattr(request.user, 'is_verified', False):
            return render(request, 'user/singup.html', {'form': CustomUserCreationForm()})
            
        form = CustomUserCreationForm()
    
    return render(request, 'user/singup.html', {'form': form})

 






login_required(login_url='/auth/login/')
def user(request):
    if not request.user.is_authenticated:
        return redirect("login")  # أو صفحة مناسبة
    if  request.user.is_superuser:
        request.user.is_team_admin = True
        request.user.save()

    tokenform =  ExternalTokenForm(request.POST or None)
    if request.method == 'POST':
        if tokenform.is_valid():
            platform = tokenform.cleaned_data['platform']
            access_token = tokenform.cleaned_data['access_token']
            extra_data = tokenform.cleaned_data.get('extra_data', {})
            user = request.user
            
    

 


            # هنا يمكنك معالجة التوكن الخارجي كما تريد
            # على سبيل المثال، حفظه في قاعدة البيانات أو استخدامه في طلبات API
            
            return JsonResponse({'status': 'success', 'message': 'Token processed successfully'})
    team_accounts = []
    # team_account_perm = 
    team_invitations = TeamInvitation.objects.filter(admin=request.user , is_used=False)
    team_account_perm = UserProductPermission.objects.select_related("user")
    
#     for user in team_account_perm:
#         # team_account_perm = user
#         team_account_perm.filter(user.is_active=True, user__team_admin=request.user)
#     # Replace this line:
# team_account_perm.filter(user.is_active=True, user__team_admin=request.user)

# With this corrected version:
#     team_account_perm = CustomUser.objects.filter(
#     is_active=True,
#     user__team_admin=request.user
# )

#     team_account_perm = UserProductPermission.objects.filter(
#     user__is_active=True,
#     user__team_admin=request.user
# ).select_related('user')  # Optimize database queries
#     team_accounts_simple = []
#     for perm in team_account_perm:
#             team_accounts_simple.append({
#         'username': perm.user.user_name or perm.user.email,
#         'email': perm.user.email
#     })
#     print(team_accounts_simple)


# Simplest approach - get unique users directly
    team_users = CustomUser.objects.filter(
    is_active=True,
    team_admin=request.user
).exclude(id=request.user.id)
    
    team_accounts_simple = []
    for user in team_users:
        team_accounts_simple.append({
        'username': user.user_name or user.email,
        'email': user.email ,
        'id' : user.id ,
        'product': Products.objects.filter(admin=user),
        'daily_order_limit':  UserProductPermission.objects.filter(user=user).first().daily_order_limit if UserProductPermission.objects.filter(user=user).exists() else 0
    })
    print(team_accounts_simple)
    team_members = CustomUser.objects.filter(team_admin=request.user).exclude(id=request.user.id)
    for invite in team_invitations:
        team_accounts.append({
        'id': invite.id,
        'email': invite.email,
        'user_name': invite.name or invite.email,
        'is_active': False,
        'source': 'invitation',
        'products': invite.products.all(),
        'get_platform_icon': 'fas fa-envelope'  # رمز افتراضي
        })
         

# الأعضاء المسجلين (نشطين)
    for user in team_members:
        team_accounts.append({
        'id': user.id,
        'email': user.email,
        'user_name': user.user_name or user.email,
        'is_active': True,
        'source': 'user',
        'get_platform_icon': 'fas fa-user-check'  # رمز افتراضي
    })



    Activ = Activity.objects.filter(user=request.user)
    stuff_users = CustomUser.objects.filter(
    is_team_admin=False,
    team_admin=request.user,
    # is_stuff=True
)
    
    activety= None
    for stuff in stuff_users:
        activety = Activity.objects.filter(user=stuff)
        if not activety:
            activety = None

        

    return render(request, 'user/user.html', {
        'tokenform': tokenform,
        'activities':activety,
        'Productslist': Products.objects.filter(admin=request.user),
        'tokens': ExternalTokenmodel.objects.filter(user=request.user),
        'is_verified': request.user.is_verified,
        'user': request.user,
        'has_password': request.user.has_usable_password(),
        'orders': SimpleOrder.objects.filter(customer_phone=request.user).order_by('-created_at'),
        'products': CODProduct.objects.all(),
        'team_invitations': team_accounts,
        'invitations': TeamInvitation.objects.filter(admin=request.user),
        'team_accounts': team_accounts_simple
    }) 








@login_required(login_url='/auth/login/')
def change_password(request):
    if request.method =='POST':
        
            old_password = request.POST.get('old_password', '').strip()
            new_password = request.POST.get('new_password1', '').strip()
            confirm_password = request.POST.get('new_password2', '').strip()
            print(old_password, new_password, confirm_password)
            if new_password != confirm_password:
                return JsonResponse({'success' : False , "message": 'passwords do not match'})
            if  request.user.check_password(old_password):
                request.user.set_password(new_password)
                request.user.save()
                return JsonResponse({'success' : True , "message": 'password changed successfully'})
            else:
                return JsonResponse({'success' : False , "message": 'old password is incorrect'})
        # else:
        #     return JsonResponse({'success' : False , "message": 'Failed to change password'})
    else:
        return JsonResponse({'success' : False , "message": 'Failed to change password'})

    
@login_required(login_url='/auth/login/')
def edit_profile(request):
    if request.method == 'POST':
        user = request.user
        user.user_name = request.POST.get('full_name', user.user_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        print(user.user_name , user.email , user.phone)
        try:
            user.save()
            return JsonResponse({'success': True, 'message': 'Profile updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Failed to update profile: {str(e)}'})

    
    
@login_required(login_url='/auth/login/')
def upgrade_plan(request):
    pass









# views.py
from .models import ExternalTokenmodel
from urllib.parse import urlencode
import requests
def verify_token(token):
    url = "https://api.cod.network/v1/seller/orders"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        # التحقق من حالة الاستجابة
        if response.status_code == 200:
            return True  # التوكن صحيح
        else:
            print("فشل التحقق، كود الاستجابة:", response.status_code)
            return False  # التوكن غير صحيح أو منتهي أو مرفوض

    except requests.exceptions.RequestException as e:
        print("خطأ في الاتصال:", str(e))
        return False

def verify_token_with_platform(token):
    return False


from django.http import JsonResponse
from .models import ExternalTokenmodel

login_required(login_url='/auth/login/')  
def link_token(request):
    if request.method == "POST":
        token = request.POST.get("access_token")
        name = request.POST.get("token_name")

        is_valid =verify_token(token)
        # تحقق من صحة التوكن (مثلاً عبر API خارجي)
        if not is_valid:
            return JsonResponse({
                "success": False,
                "message": "غير قادر على التحقق من صحة التوكن"
            }, status=400)

        # تحقق هل التوكن مرتبط مسبقًا
        if ExternalTokenmodel.objects.filter(user=request.user, platform="CodNetwork").exists():
            return JsonResponse({
                "success": False,
                "message": "Token موجود بالفعل"
            }, status=400)
        

        # شفر التوكن
        encrypted = encrypt_token(token)

        # خزنه
        ExternalTokenmodel.objects.create(
            user=request.user,
            platform = request.POST.get("platform" ,'Cod'),
            access_token=  encrypted,
            token_status= True ,
            token_name = request.POST.get("token_name", "unamed"),
            
        )
        

        return JsonResponse({
            "success": True,
            "message": "تم حفظ التوكن بنجاح"
        })


login_required(login_url='/auth/login/')  
def delete_token(request ,token_id):
        try:
            token = ExternalTokenmodel.objects.get(id=token_id, user=request.user)
            token.delete()
            return redirect('/tracking/user/?token_deleted')
            
        except ExternalTokenmodel.DoesNotExist:
            return JsonResponse({
                "success": False,
                "message": "التوكن غير موجود"
            }, status=404)
    








 
@login_required(login_url='/auth/login/')
def team_dashboard(request):
    if not request.user.is_authenticated or not request.user.is_team_admin:
        return redirect('login')

    team_members = CustomUser.objects.filter(team_admin=request.user)
    return render(request, 'team/dashboard.html', {
        'team_members': team_members
    })










from sib_api_v3_sdk import ApiClient, Configuration, TransactionalEmailsApi, SendSmtpEmail
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings
from django.urls import reverse

# def send_invitation_email(invitation):
#     """
#     ترسل دعوة عبر البريد الإلكتروني باستخدام Sendinblue API بناءً على كائن TeamInvitation.
#     """
#     invite_url = f"{settings.SITE_URL}{reverse('accept_invite', kwargs={'token': invitation.token})}"

#     subject = f"دعوة للانضمام إلى فريق {invitation.admin.user_name or invitation.admin.email}"
    
#     html_content = f"""
#     <html>
#         <body>
#             <p>مرحباً {invitation.name or invitation.email},</p>
#             <p>لقد دعاك <strong>{invitation.admin.user_name or invitation.admin.email}</strong> للانضمام إلى فريقه.</p>
#             <p>للانضمام، اضغط على الزر التالي:</p>
#             <p><a href="{invite_url}" style="background-color: #007bff; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px;">قبول الدعوة</a></p>
#             <p>إذا لم يعمل الزر، انسخ الرابط التالي وضعه في المتصفح:</p>
#             <p>{invite_url}</p>
#             <br>
#             <p>مع تحيات فريق الدعم</p>
#         </body>
#     </html>
#     """

#     # إعداد التهيئة مع مفتاح API
#     configuration = Configuration()
#     configuration.api_key['api-key'] = settings.SENDINBLUE_API_KEY

#     api_instance = TransactionalEmailsApi(ApiClient(configuration))

#     send_smtp_email = SendSmtpEmail(
#         to=[{"email": invitation.email, "name": invitation.name or ""}],
#         sender={"email": settings.DEFAULT_FROM_EMAIL, "name": "فريق الدعم"},
#         subject=subject,
#         html_content=html_content
#     )

#     try:
#         api_response = api_instance.send_transac_email(send_smtp_email)
#         print("Email sent successfully:", api_response)
#         return True
#     except ApiException as e:
#         return False
#         print("Exception when calling Sendinblue API:", e)





 

def send_invitation_email(invitation):
    invite_url = f"{settings.SITE_URL}{reverse('accept_invite', kwargs={'token': invitation.token})}"
    subject = f"دعوة للانضمام إلى فريق {invitation.admin.user_name or invitation.admin.email}"

    html_content = f"""
    <html>
        <body>
            <p>مرحباً {invitation.name or invitation.email},</p>
            <p>لقد دعاك <strong>{invitation.admin.user_name or invitation.admin.email}</strong> للانضمام إلى فريقه.</p>
            <p>للانضمام، اضغط على الزر التالي:</p>
            <p><a href="{invite_url}" style="background-color: #007bff; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px;">قبول الدعوة</a></p>
            <p>إذا لم يعمل الزر، انسخ الرابط التالي وضعه في المتصفح:</p>
            <p>{invite_url}</p>
            <br>
            <p>مع تحيات فريق الدعم</p>
        </body>
    </html>
    """

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email='bojamaabayad2001@gmail.com',
            to=[invitation.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        print("📧 تم إرسال الدعوة بنجاح")
        return True
    except Exception as e:
        print("❌ فشل في إرسال الدعوة:", e)
        return False




def invite_staff(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if not request.user.is_team_admin:
    #     return JsonResponse({'error': 'ليس لديك صلاحيات لدعوة أعضاء الفريق'}, status=403)
            return JsonResponse({
                "success": False,
                'message': 'ليس لديك صلاحيات لدعوة أعضاء الفريق'
                })


    if request.method == 'POST':
        email = request.POST.get('email')
        name = request.POST.get('name', '')
        role = request.POST.get('role', 'viewer')
        products = request.POST.getlist('products')
        if len(products) == 1 and ',' in products[0]:
            products = products[0].split(',')

        if not email:
            return JsonResponse({'error': 'البريد الإلكتروني مطلوب'}, status=400)

        if CustomUser.objects.filter(email=email).exists():
            return JsonResponse({
                'success' : False,
                'message': 'This email is already registered  with another account.'
                }, status=400)
        

        # معالجة المنتجات
        if 'all' in products:
            selected_products = Products.objects.filter(admin=request.user)
        else:
            # تأكد أن جميع الـ IDs صالحة وموجودة
            product_qs = Products.objects.filter(id__in=products, admin=request.user)

            if product_qs.count() != len(products):
                return JsonResponse({'error': 'بعض المنتجات غير موجودة أو لا تملك صلاحية الوصول إليها'}, status=400)
            
            selected_products = product_qs
            print(selected_products)


        # إنشاء الدعوة
        invitation = TeamInvitation.objects.create(
            email=email,
            admin=request.user,
            role=role,
            name=name,
        )
        invitation.products.set(selected_products)

        send_invitation_email(invitation)
        invitation.save()

        if not send_invitation_email(invitation):
            return JsonResponse({'error': 'فشل في إرسال البريد الإلكتروني'}, status=500)
        else:        
            return JsonResponse({'success': 'تم إرسال الدعوة بنجاح'}, status=200)
         

        # إرسال البريد (يمكن تفعيلها لاحقًا)
        # send_invitation_email(invitation)


    return render(request, 'team/invite_staff.html')
from django.contrib.auth import login
from django.http import JsonResponse

def accept_invite(request, token):
    error = ''
    invitation = get_object_or_404(TeamInvitation, token=token)
    if invitation.is_used:
        error  = 'هذه الدعوة قد تم استخدامها بالفعل'
    
    if request.user.is_authenticated:
        # إذا كان المستخدم مسجلاً الدخول بالفعل، يمكنه قبول الدعوة
        if invitation.email != request.user.email:
            return JsonResponse({'success': False,
                                  'message': 'لا يمكنك قبول هذه الدعوة، البريد الإلكتروني المسجل به غير متطابق'})
        # print('invit email' , invitation.email)

    if request.method == 'POST':
        user = CustomUser.objects.create_user(
            username=invitation.email,
            email=invitation.email,
            password=None,
            user_name=invitation.name,
            team_admin = invitation.admin,
            is_active=True,
            is_verified=True,  # تعيين الحالة إلى مفعل
            is_team_admin=False  # تعيين الحالة إلى غير أدمين فريق
        )
        user.set_unusable_password()
        user.save()
        # حدف الدعوة 
         
        login(request, user)
        for product in invitation.products.all():
                UserProductPermission.objects.get_or_create(
                    user=user,
                    product=product,
                    defaults={'role': invitation.role}
                )
        invitation.is_used = True
        invitation.save()
        return JsonResponse({'status': 'success'})
         

    return render(request, 'accept.html', {
        'inviter': invitation.admin,
        'email': invitation.email,
        'invetations': invitation,
        'error_message':error
    })

# def accept_invite(request, token):
#     invitation = get_object_or_404(TeamInvitation, token=token, is_used=False)
#     error = ''

#     if request.method == 'POST':
#         step = request.POST.get('step')

#         # المرحلة 1: إنشاء المستخدم من الدعوة
#         if step == 'accept':
#             full_name = request.POST.get('full_name', '').strip()

#             if CustomUser.objects.filter(email=invitation.email).exists():
#                 return JsonResponse({'status': 'error', 'message': 'البريد مستخدم مسبقًا'})

#             user = CustomUser.objects.create_user(
#                 username=invitation.email,
#                 email=invitation.email,
#                 user_name=full_name,
#                 password=None,
#                 team_admin=invitation.admin,
#                 stuff_momber=True,
#                 is_active=True,
#                 is_verified=True,
#                 is_team_admin=False
#             )
#             user.set_unusable_password()
#             user.save()

            # for product in invitation.products.all():
            #     UserProductPermission.objects.get_or_create(
            #         user=user,
            #         product=product,
            #         defaults={'role': invitation.role}
            #     )

#             login(request, user)
#             return JsonResponse({'status': 'success'})

#         # المرحلة 2: حفظ كلمة المرور
#         elif step == 'set_password':
#             if not request.user.is_authenticated:
#                 return JsonResponse({'status': 'error', 'message': 'لم يتم تسجيل الدخول'})

#             password = request.POST.get('password')
#             request.user.set_password(password)
#             request.user.save()
            

#             invitation.is_used = True
#             invitation.save()

#             return JsonResponse({'status': 'success'})

#     return render(request, 'accept.html', {
#         'inviter': invitation.admin,
#         'email': invitation.email,
#         'invetations': invitation,
#         'error_message': error
#     })


@login_required
def unlink_user(request, id):
    if not request.user.is_team_admin:
        return redirect('login')

    # message = 'unlinked'

    # 1. محاولة حذف دعوة TeamInvitation
    invitation = TeamInvitation.objects.filter(id=id, admin=request.user).first()
    if invitation:
        invitation.delete()
        return redirect(f'/tracking/user/?{"invitation_deleted"}')

    # 2. محاولة حذف مستخدم فعلي من الفريق
    member = CustomUser.objects.filter(id=id, team_admin=request.user).first()
    if member:
        member.delete()
        return redirect(f'/tracking/user/?{"user_deleted"}')

    # 3. لم يتم العثور على دعوة ولا عضو
    return JsonResponse({'error': 'المستخدم غير موجود أو ليس جزءًا من فريقك'}, status=404)

def contact_support(request):
    pass




from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
 
@login_required
@require_POST
def set_password(request):
    password1 = request.POST.get('password1')
    password2 = request.POST.get('password2')

    if not password1 or not password2:
        return JsonResponse({
            'status': 'error',
            'errors': ['يرجى إدخال كلمة المرور في كلا الحقلين']
        })

    if password1 != password2:
        return JsonResponse({
            'status': 'error',
            'errors': ['كلمتا المرور غير متطابقتين']
        })

    user = request.user
    user.set_password(password1)
    user.save()
    update_session_auth_hash(request, user)

    return JsonResponse({
        'status': 'success',
        'message': 'تم تعيين كلمة المرور بنجاح'
    })

    





@login_required(login_url='/auth/login/')
def updatepermissions(request, user_id):
    staff_member = get_object_or_404(CustomUser, id=user_id, team_admin=request.user)
    products = Products.objects.filter(admin=request.user)

    if request.method == 'POST':
        selected_products_ids = request.POST.getlist('products')
        role = request.POST.get('role', 'viewer')

        # حذف الصلاحيات القديمة
        UserProductPermission.objects.filter(user=staff_member).delete()

        # إضافة الصلاحيات الجديدة
        for pid in selected_products_ids:
            product = Products.objects.get(id=pid)
            UserProductPermission.objects.create(
                user=staff_member,
                product=product,
                role=role
            )

        return redirect('team_management')

    current_permissions = UserProductPermission.objects.filter(user=staff_member).values_list('product__id', flat=True)

    return render(request, 'update_permissions.html', {
        'staff_member': staff_member,
        'products': products,
        'current_permissions': current_permissions,
    })







 
def get_product_info(request):
    sku = request.GET.get("sku")
    try:
        product = CODProduct.objects.get(sku=sku)
        if product :
            return JsonResponse({
            "success": True,
            "name": product.name,
            "project": product.project,
        })
        else :
            return JsonResponse({
                "success": False,
                "message": "المنتج غير موجود"
            })
    except CODProduct.DoesNotExist:
        return JsonResponse({"success": False}, status=200)


import requests
import json
from .crypto import decrypt_token
from django.http import JsonResponse
from .models import Order, CODProduct
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta

def sendlead(request, cname, cphone, caddress, country_code, items):
    payload = {
        "phone": "",
        "name": cname,
        "country": country_code,
        "address": caddress,
        "items": items
    }
    user = request.user
    if not user.is_team_admin:
        user = user.team_admin

    token_obj = ExternalTokenmodel.objects.filter(user=user).first()
    if not token_obj:
        print("لم يتم العثور على رمز وصول للمستخدم.")
        return []

    try:
        decrypted_tok = decrypt_token(token_obj.access_token)
    except Exception as e:
        print(f"خطأ في فك تشفير التوكن: {str(e)}")
        return []

    headers = {
        "Authorization": f"Bearer {decrypted_tok}",
        "Content-Type": "application/json",
    }

    resp = requests.post(
        "https://api.cod.network/v1/seller/leads",
        data=json.dumps(payload),
        headers=headers
    )

    if resp.status_code == 201:
        print("✅ تم إرسال الطلب إلى COD Network بنجاح")
    else:
        print("❌ فشل في إرسال الطلب:", resp.status_code, resp.text)

    return resp

# @csrf_exempt
def submit_order(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "الطلب يجب أن يتم باستخدام POST"})

    # بيانات العميل
    name = request.POST.get("name")
    phone = request.POST.get("phone")
    address = request.POST.get("address")
    country_code = request.POST.get("country_code") or "SA"

    # المنتج المختار
    selected_product_sku = request.POST.get("selected_sku") 
    product_quantity = request.POST.get("product_quantity") or 1
    product_price = request.POST.get("product_price")
 
    # عناصر النموذج
    skus = request.POST.getlist("sku[]")
    is_gift_flags = request.POST.getlist("is_gift[]")
    print(f"selected_product_sku: {selected_product_sku}, product_quantity: {product_quantity}, product_price: {product_price}")
    
    if not selected_product_sku :
        return JsonResponse({"success": False, "message": "المنتج المختار غير موجود"} ,status=400)

    # استخراج SKU الهدية (إن وجدت)
    gift_sku = None
    for i in range(len(skus)):
        if is_gift_flags[i] == "true":
            gift_sku = skus[i]
            break

    items_payload = [{
        "sku": selected_product_sku,
        "quantity": int(product_quantity),
        "price": float(product_price)
    }]

    gift_obj = None
    if gift_sku:
        try:
            gift_obj = CODProduct.objects.get(sku=gift_sku)
            items_payload.append({
                "sku": gift_sku,
                "quantity": 1,
                "price": 0.0
            })
        except CODProduct.DoesNotExist:
            return JsonResponse({"success": False, "message": "الهدية غير موجودة في قاعدة البيانات"})

    # تحقق من الحد اليومي للطلبات إذا لم يكن المستخدم أدمين أو سوبر يوزر
    if request.user.is_team_admin or request.user.is_superuser:
        pass
    else:
        order_limit = UserProductPermission.objects.filter(user=request.user).first()
        today = now().date()
        user_orders_today = Order.objects.filter(user=request.user, order_date__date=today).count()
        user_limit = order_limit.daily_order_limit if order_limit else 0

        if user_limit and user_orders_today >= user_limit:
            return JsonResponse({
                "success": False,
                "message": f"لقد وصلت إلى الحد الأقصى لعدد الطلبات اليوم ({user_limit})"
            })
    
    resp = sendlead(request, name, phone, address, country_code, items_payload)
    # 2. التحقق من نجاح الإرسال قبل الحفظ
    if resp.status_code == 201:
        # إنشاء الطلب وربطه بالهدية إذا وجدت
        order = Order.objects.create(
            user=request.user,
            customer_name=name,
            customer_phone=phone,
            customer_city=address,
            product=selected_product_sku,
            product_quantity=product_quantity,
            product_price=product_price,
            gift_chosen=gift_obj
        )
        activity_log(
            request,
            activity_type='order_placed',
            description=f"طلب جديد لـ {name} ({phone}) للمنتج {selected_product_sku}" + (f" مع هدية {gift_sku}" if gift_sku else ""),
            related_object=None,
            ip_address=request.META.get('REMOTE_ADDR'),
            active_time=timezone.now()
        )
    else:
        try:
            error_data = resp.json()
            if "log" in error_data and isinstance(error_data["log"], list) and error_data["log"]:
                error_message = error_data["log"][0].get("message", error_data.get("message", "خطأ غير معروف"))
            else:
                error_message = error_data.get("message", "خطأ غير معروف")
        except ValueError:
            error_message = resp.text or "حدث خطأ غير متوقع أثناء إرسال الطلب"

        return JsonResponse({
            "success": False,
            "message": f"فشل إرسال الطلب: {error_message}"
        })

    return JsonResponse({"success": True, "message": "تم إرسال الطلب بنجاح"})

@login_required(login_url='/auth/login/')
def  updatedealy(request):
    if request.method == "POST":
        account_id = request.POST.get("account_id")
        new_limit = request.POST.get("order_limit")
        print(account_id)
        print(CustomUser.objects.filter(id=account_id))
        try:
            perm = UserProductPermission.objects.filter(user__id=account_id).first()
            print(perm)
            perm.daily_order_limit = int(new_limit)
            perm.save()
            return JsonResponse ({"success": True, "message": f" Updated successfully for {perm.user.user_name}"})
        except UserProductPermission.DoesNotExist:
            return JsonResponse({"success": False, "message": "لم يتم العثور على المستخدم"})












from django.views.decorators.csrf import csrf_exempt

from django.http import HttpResponse, JsonResponse
@csrf_exempt
def track_injaz(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    order_number = request.POST.get("order")
    if not order_number:
        return JsonResponse({"message": "Order number required"}, status=400)

    try:
        upstream = requests.post(
            "https://injaz-express.com/track_order.php",
            data={"order": order_number},
            timeout=15
        )
        upstream.raise_for_status()
    except requests.RequestException as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    print(order_number, upstream.status_code)
    print(upstream.text[:60000])  # نطبع أول 500 حرف فقط من الرد للتأكد


    return HttpResponse(upstream.text, content_type="text/html")









from django.http import JsonResponse
@login_required(login_url='/auth/login/')
@csrf_exempt
# def leadstracking(request):
#     # اقرأ قيمة sku من POST إن وُجِدت (ممكن تكون سلسلة مفصولة بفواصل)
#     sku_param = request.POST.get('productsku', '')

#     print("SKU parameter received:", sku_param)
    
#     if sku_param: 
#         # إذا أُرسل كسلسلة مثل "SKU1,SKU2" نحوّلها لقائمة
#         if isinstance(sku_param, str):
#             sku_list = [s.strip() for s in sku_param.split(',') if s.strip()]
#         else:
#             # سلامة إضافية: إذا وصلت كقيمة مفردة غير نصية
#             sku_list = [str(sku_param)]
#     else:
#         # لم يُمرّر sku في الطلب، نبحث عن SKUs التابعة للأدمين/المستخدم
#         # حالة المستخدم هو الأدمين نفسه
#         if getattr(request.user, 'is_team_admin', False):
#             sku_qs = Products.objects.filter(admin=request.user).values_list('sku', flat=True)
#             sku_list = list(sku_qs)
#         else:
#             # إذا للمستخدم رابط إلى team_admin (FK أو غيره) نستخدمه
#             team_admin = getattr(request.user, 'team_admin', None)
#             if team_admin:
#                 sku_qs = Products.objects.filter(admin=team_admin).values_list('sku', flat=True)
#                 sku_list = list(sku_qs)
#             else:
#                 # كحل أخير: نأخذ SKUs من جدول صلاحيات المستخدم UserProductPermission
#                 sku_qs = Products.objects.filter(
#                     id__in=UserProductPermission.objects.filter(user=request.user)
#                                                     .values_list('product_id', flat=True)
#                 ).values_list('sku', flat=True)
#                 sku_list = list(sku_qs)

#     # إذا لم نجد أي SKU نرجّع خطأ واضح
#     if not sku_list:
#         return JsonResponse({"status": "error", "message": "No SKUs found for this user"})


#     # استدعاء الدالة التي تجلب الـ leads مع تمرير قائمة الـ SKUs
#     req = fetch_leads_for_skus(request, sku_list=sku_list)
#     print("Fetching leads for SKUs:", sku_list)

#     if req is None:
#         print("Failed to fetch leads for SKUs:", sku_list)
#         return JsonResponse({"status": "error", "message": "Failed to fetch leads"})

#     print("Leads fetched successfully for SKUs:", sku_list)
#     return JsonResponse({"status": "success", "message": "Leads fetched successfully"})


 



def leadstracking(request):
    """
    View لالتقاط SKUs من POST أو من صلاحيات المستخدم، ثم استدعاء fetch_leads_for_skus.
    تعيد JsonResponse بنتيجة العملية وعدد الـ leads التي تم إدخالها/تحديثها.
    """

    sku_param = request.POST.get('productsku', '')

    print("SKU parameter received:", sku_param)

    if sku_param:
        if isinstance(sku_param, str):
            sku_list = [s.strip() for s in sku_param.split(',') if s.strip()]
        else:
            sku_list = [str(sku_param)]
    else:
        if getattr(request.user, 'is_team_admin', False):
            sku_qs = Products.objects.filter(admin=request.user).values_list('sku', flat=True)
            sku_list = list(sku_qs)
        else:
            team_admin = getattr(request.user, 'team_admin', None)
            if team_admin:
                sku_qs = Products.objects.filter(admin=team_admin).values_list('sku', flat=True)
                sku_list = list(sku_qs)
            else:
                sku_qs = Products.objects.filter(
                    id__in=UserProductPermission.objects.filter(user=request.user)
                                                    .values_list('product_id', flat=True)
                ).values_list('sku', flat=True)
                sku_list = list(sku_qs)

    if not sku_list:
        return JsonResponse({"status": "error", "message": "No SKUs found for this user"}, status=400)

    leads = fetch_leads_for_skus(request, sku_list=sku_list)
    print("Fetching leads for SKUs:", sku_list)

    if leads is None:
        print("Failed to fetch leads for SKUs:", sku_list)
        return JsonResponse({"status": "error", "message": "Failed to fetch leads"}, status=500)

    count = len(leads)
    print("Leads fetched successfully for SKUs:", sku_list, "count:", count)
    return JsonResponse({"status": "success", "message": "Leads fetched successfully", "leads_count": count})
