from ast import Assign
import logging
from multiprocessing import context
from django.conf import settings
from .models import CODProduct ,SimpleOrder , CustomUser ,TeamInvitation , ExternalTokenmodel , Products , Activity ,UserProductPermission,Order, Plan
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
from .activites import activity_log, log_activity
from .Codnetwork import  fetch_leads_for_skus
from .services.plan_limits import check_plan_limit
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
                    log_activity('login', f"User logged in ({email})", user=user, request=request, defer=False)
                    return redirect('tracking')
            else:
                log_activity('login_failed', f"Failed login attempt for {email}", request=request, defer=False)
                error = "Invalid email or password."
    return render(request, 'user/login.html', {'error': error})

login_required(login_url='/auth/login/')  
def  logout(request):
    from django.contrib.auth import logout
    log_activity('logout', 'User logged out', request=request, defer=False)
    logout(request)
    return redirect('home')

 



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
import os
import requests


 
 
def resend_activation_email(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'error': 'User not authenticated'}, status=401)

    # 1. تجهيز البيانات
    code = user.generate_verification_code()
    current_host = request.get_host()
    protocol = 'https' if request.is_secure() else 'http'
    activation_link = f'{protocol}://{current_host}/activate/{user.id}/'
    
     
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify your Waselytics Account</title>
        <style>
            /* Reset & Basics */
            body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }}
            
            /* Header */
            .header {{ background-color: #0f172a; padding: 30px; text-align: center; }}
            .logo {{ font-size: 24px; font-weight: bold; color: #ffffff; text-decoration: none; letter-spacing: 1px; }}
            .logo span {{ color: #7c3aed; }} /* Brand Purple */

            /* Content */
            .content {{ padding: 40px 30px; text-align: center; }}
            h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 16px; color: #111827; }}
            p {{ color: #4b5563; font-size: 16px; margin-bottom: 24px; }}
            
            /* The Code Box */
            .code-box {{ background-color: #f9fafb; border: 1px dashed #d1d5db; padding: 20px; border-radius: 12px; margin: 30px 0; display: inline-block; min-width: 200px; }}
            .otp-code {{ font-size: 32px; font-weight: 800; color: #7c3aed; letter-spacing: 6px; font-family: monospace; }}
            
            /* Button */
            .btn {{ display: inline-block; background-color: #7c3aed; color: #ffffff; font-weight: 600; padding: 14px 32px; border-radius: 8px; text-decoration: none; transition: background 0.3s ease; margin-top: 10px; }}
            .btn:hover {{ background-color: #6d28d9; }}
            
            /* Footer */
            .footer {{ background-color: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; }}
            .footer a {{ color: #7c3aed; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <a href="https://waselytics.com" class="logo">
                    Waselytics<span>.</span>
                </a>
            </div>

            <div class="content">
                <h1>Welcome to the Future of COD 🚀</h1>
                <p>
                    You are one step away from automating your order confirmation and unlocking real attribution data.
                    <br>Please verify your email address to access your dashboard.
                </p>

                <div class="code-box">
                    <div class="otp-code">{code}</div>
                </div>

                <p style="font-size: 14px; margin-top: 0;">Or click the button below:</p>
                
                <a href="{activation_link}" class="btn">Verify My Account</a>

                <p style="font-size: 13px; color: #9ca3af; margin-top: 30px;">
                    This code will expire in 10 minutes. If you didn't request this, you can safely ignore this email.
                </p>
            </div>

            <div class="footer">
                &copy; 2025 Waselytics Inc. All rights reserved.<br>
                <a href="https://waselytics.com">waselytics.com</a> | <a href="#">Support</a>
            </div>
        </div>
    </body>
    </html>
    """


    try:
       
        email = EmailMessage(
            subject="Your Verification Code - Waselytics", # عنوان الرسالة
            body=html_content,                             # المحتوى
            from_email=settings.DEFAULT_FROM_EMAIL,        # المرسل (noreply)
            to=[user.email],                               # المستقبل
        )

        # 3. تحديد النوع HTML
        email.content_subtype = "html"

        email.send(fail_silently=False)
        
        print(f"✅ OTP sent successfully via Hostinger to: {user.email}")
        return JsonResponse({'success': True, 'message': 'Code sent'})
    except Exception as e:
        print(f"❌ Failed to send OTP: {e}")
        return JsonResponse({'success': False, 'message': 'Failed to send'}, status=500)
        
     
def activate_account(request, user_id=None):
    code = request.POST.get('code' , None)
    user = request.user
    if code is not None :
        if user.email_verification_code == code: # نفترض وجود هذا الحقل
            user.is_active = True
            user.is_verified = True
            user.save()
            return JsonResponse({'success': True,  'message': 'Your account has been activated successfully' , 'is_active': user.is_verified})
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
        is_active=True,
        is_verified=False,
        is_team_admin=True,
    )
    log_activity('user_created', f"New account registered: {email} ({user_name})", user=user, defer=False)
    
    # إنشاء ملف تعريف المستخدم
    # CustomUserCreationForm.objects.create(user=user)
    
    # إرسال كود التحقق
    # send_verification_email(user)
    
    return user

from django.contrib.auth import login
from django.contrib.auth import authenticate, login

def singup(request):
    if request.user.is_authenticated and request.user.is_active and request.user.is_verified:
        return redirect('tracking')

    selected_plan = (request.GET.get("plan") or request.POST.get("selected_plan") or "").strip().lower()

    form = CustomUserCreationForm()
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user_name = form.cleaned_data['user_name']
            password = form.cleaned_data['password1']

            try:
                # 1. إنشاء المستخدم
                user = register_user(email=email, password=password, user_name=user_name)

                # Auto-assign plan from pricing page selection
                if selected_plan:
                    try:
                        plan_obj = Plan.objects.filter(name__iexact=selected_plan).first()
                        if plan_obj:
                            user.plan = plan_obj
                            user.save(update_fields=["plan"])
                    except Exception as e:
                        logging.getLogger(__name__).warning("singup plan assign: %s", e)

                try :
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                except Exception as e:
                    print(f"❌ Login Error: {e}")
                code = user.generate_verification_code()
                current_host = request.get_host()
                protocol = 'https' if request.is_secure() else 'http'
                activation_link = f'{protocol}://{current_host}/activate/{user.id}/'
                html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verify your Waselytics Account</title>
            <style>
                /* Reset & Basics */
                body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }}
                
                /* Header */
                .header {{ background-color: #0f172a; padding: 30px; text-align: center; }}
                .logo {{ font-size: 24px; font-weight: bold; color: #ffffff; text-decoration: none; letter-spacing: 1px; }}
                .logo span {{ color: #7c3aed; }} /* Brand Purple */

                /* Content */
                .content {{ padding: 40px 30px; text-align: center; }}
                h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 16px; color: #111827; }}
                p {{ color: #4b5563; font-size: 16px; margin-bottom: 24px; }}
                
                /* The Code Box */
                .code-box {{ background-color: #f9fafb; border: 1px dashed #d1d5db; padding: 20px; border-radius: 12px; margin: 30px 0; display: inline-block; min-width: 200px; }}
                .otp-code {{ font-size: 32px; font-weight: 800; color: #7c3aed; letter-spacing: 6px; font-family: monospace; }}
                
                /* Button */
                .btn {{ display: inline-block; background-color: #7c3aed; color: #ffffff; font-weight: 600; padding: 14px 32px; border-radius: 8px; text-decoration: none; transition: background 0.3s ease; margin-top: 10px; }}
                .btn:hover {{ background-color: #6d28d9; }}
                
                /* Footer */
                .footer {{ background-color: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; }}
                .footer a {{ color: #7c3aed; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <a href="https://waselytics.com" class="logo">
                        Waselytics<span>.</span>
                    </a>
                </div>

                <div class="content">
                    <h1>Welcome to the Future of COD 🚀</h1>
                    <p>
                        You are one step away from automating your order confirmation and unlocking real attribution data.
                        <br>Please verify your email address to access your dashboard.
                    </p>

                    <div class="code-box">
                        <div class="otp-code">{code}</div>
                    </div>

                    <p style="font-size: 14px; margin-top: 0;">Or click the button below:</p>
                    
                    <a href="{activation_link}" class="btn">Verify My Account</a>

                    <p style="font-size: 13px; color: #9ca3af; margin-top: 30px;">
                        This code will expire in 10 minutes. If you didn't request this, you can safely ignore this email.
                    </p>
                </div>

                <div class="footer">
                    &copy; 2025 Waselytics Inc. All rights reserved.<br>
                    <a href="https://waselytics.com">waselytics.com</a> | <a href="#">Support</a>
                </div>
            </div>
        </body>
        </html>
        """
                try:
                    email_msg = EmailMessage(
                        subject="Your Verification Code - Waselytics",
                        body=html_content,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[user.email],
                    )
                    email_msg.content_subtype = "html"
                    email_msg.send(fail_silently=False)
                except Exception as e:
                    print(f"❌ Failed to send OTP: {e}")
                
                # 🔥 التغيير هنا: لا توجهه لمكان آخر!
                # أعد عرض نفس الصفحة مع متغير يخبر المتصفح بإظهار الـ Popup
                print("✅ User created, showing OTP modal.")
                return render(request, 'user/singup.html', {'form': form, 'show_otp': True, 'selected_plan': selected_plan})

            except Exception as e:
                form.add_error(None, str(e))
    
    return render(request, 'user/singup.html', {'form': form, 'selected_plan': selected_plan})




from discount.models import WhatsAppChannel

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

    whatsapp_channels = WhatsAppChannel.objects.filter(owner=request.user)
  
  
    
 
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
 

    # Plans for subscription section (normalized to Starter / Pro / Elite)
    raw_plans = list(Plan.objects.all().order_by('price'))

    def _plan_tier_key(name):
        key = (name or "").strip().lower()
        if key in ("starter", "basic", "free"):
            return "starter"
        if key in ("pro", "premium"):
            return "pro"
        if key in ("elite",):
            return "elite"
        return "other"

    def _pick_representative(plans, preferred_names):
        if not plans:
            return None
        # Pick by preferred name order (not queryset order) so Starter does not
        # accidentally resolve to legacy Free when Basic exists.
        by_name = {(p.name or "").strip().lower(): p for p in plans}
        for name in preferred_names:
            if name in by_name:
                return by_name[name]
        return plans[0]

    buckets = {"starter": [], "pro": [], "elite": []}
    for p in raw_plans:
        tier = _plan_tier_key(p.name)
        if tier in buckets:
            buckets[tier].append(p)

    starter_plan = _pick_representative(buckets["starter"], ["starter", "basic", "free"])
    pro_plan = _pick_representative(buckets["pro"], ["pro", "premium"])
    elite_plan = _pick_representative(buckets["elite"], ["elite"])

    all_plans = [p for p in (starter_plan, pro_plan, elite_plan) if p is not None]

    user_plan = request.user.plan if (getattr(request.user, 'plan_id', None) and request.user.plan_id) else None
    current_plan = user_plan
    if not current_plan and starter_plan:
        current_plan = starter_plan
    if current_plan:
        current_tier = _plan_tier_key(current_plan.name)
        tier_selected = {"starter": starter_plan, "pro": pro_plan, "elite": elite_plan}.get(current_tier)
        if tier_selected:
            current_plan = tier_selected

    return render(request, 'user/user.html', {
        'tokenform': tokenform,
        'activities':activety,
        'whatsapp_channels':whatsapp_channels ,
        'Productslist': Products.objects.filter(admin=request.user),
        'tokens': ExternalTokenmodel.objects.filter(user=request.user),
        'is_verified': request.user.is_verified,
        'user': request.user,
        'has_password': request.user.has_usable_password(),
        'orders': SimpleOrder.objects.filter(customer_phone=request.user).order_by('-created_at'),
        'products': CODProduct.objects.all(),
        'team_invitations': team_accounts,
        'invitations': TeamInvitation.objects.filter(admin=request.user),
        'team_accounts': team_accounts_simple,
        'plans': all_plans,
        'current_plan': current_plan,
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
                log_activity('password_changed', 'Password changed successfully', request=request)
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
            log_activity('profile_updated', f"Profile updated: {user.user_name}, {user.email}", request=request)
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







 
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings
from django.urls import reverse
 
  
 
 


 

from django.urls import reverse
from django.core.mail import EmailMessage





from django.urls import reverse
# from django.core.mail import EmailMessage
from django.conf import settings
from django.core.mail import send_mail
def send_invitation_email(request, invitation):
    # 1. بناء الرابط الديناميكي
    relative_link = reverse('accept_invite', kwargs={'token': invitation.token})
    invite_url = request.build_absolute_uri(relative_link)

    # بيانات المرسل والمستقبل
    admin_name = invitation.admin.user_name or "The Team Admin"
    recipient_name = invitation.name or "There" # "Hi There" إذا لم يوجد اسم
    
    # عنوان الرسالة (Subject)
    subject = f"Invitation to join {admin_name}'s team on Waselytics"

    # تصميم القالب (HTML Template)
    # ملاحظة: نستخدم Inline CSS لأن برامج الإيميل لا تدعم External CSS جيداً
    # 
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>You've been invited to Waselytics</title>
        <style>
            /* Reset & Basics */
            body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
            .wrapper {{ width: 100%; table-layout: fixed; background-color: #f3f4f6; padding-bottom: 40px; }}
            
            /* Container */
            .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }}
            
            /* Header */
            .header {{ background-color: #0f172a; padding: 30px; text-align: center; border-bottom: 4px solid #7c3aed; }}
            .logo {{ font-size: 26px; font-weight: 800; color: #ffffff; text-decoration: none; letter-spacing: -0.5px; }}
            .logo span {{ color: #7c3aed; }} 

            /* Content Body */
            .content {{ padding: 40px 40px; }}
            
            /* Typography */
            h1 {{ margin-top: 0; color: #111827; font-size: 24px; font-weight: 700; line-height: 1.3; text-align: center; }}
            p {{ color: #4b5563; font-size: 16px; margin-bottom: 24px; }}
            
            /* User Badge */
            .inviter-badge {{ display: table; margin: 0 auto 24px auto; background-color: #f5f3ff; color: #7c3aed; padding: 8px 16px; border-radius: 50px; font-size: 14px; font-weight: 600; border: 1px solid #ddd6fe; }}
            
            /* CTA Button */
            .btn-container {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; background-color: #7c3aed; color: #ffffff !important; padding: 16px 36px; font-size: 16px; font-weight: 600; text-decoration: none; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(124, 58, 237, 0.3); transition: all 0.2s ease; }}
            .btn:hover {{ background-color: #6d28d9; transform: translateY(-1px); box-shadow: 0 6px 8px -1px rgba(124, 58, 237, 0.4); }}
            
            /* Link Box */
            .link-help {{ font-size: 13px; color: #9ca3af; text-align: center; margin-top: 30px; }}
            .link-box {{ background-color: #f9fafb; padding: 12px; border-radius: 6px; border: 1px solid #e5e7eb; word-break: break-all; font-size: 12px; color: #6b7280; text-align: center; margin-top: 8px; }}
            
            /* Footer */
            .footer {{ background-color: #f9fafb; padding: 24px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; }}
            .footer a {{ color: #6b7280; text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="wrapper">
            <div style="height: 40px;"></div>
            <div class="container">
                <div class="header">
                    <a href="https://waselytics.com" class="logo">
                        Waselytics<span>.</span>
                    </a>
                </div>

                <div class="content">
                    <div class="inviter-badge">
                        🚀 Invitation from {admin_name}
                    </div>

                    <h1>Unlock your workspace access</h1>
                    
                    <p>Hello <strong>{recipient_name}</strong>,</p>
                    
                    <p>
                        You have been selected to join the <strong>{admin_name}'s Team</strong> on Waselytics. 
                    </p>
                    <p>
                        Accept this invitation to start collaborating on order workflows, accessing real-time attribution data, and scaling your COD operations together.
                    </p>

                    <div class="btn-container">
                        <a href="{invite_url}" class="btn">Join the Team &rarr;</a>
                    </div>
                    
                    <p style="font-size: 14px; color: #6b7280; text-align: center;">
                        This invitation link is unique to you and will remain valid for 48 hours.
                    </p>

                    <div class="link-help">
                        Having trouble with the button? Copy this link:
                        <div class="link-box">
                            <a href="{invite_url}" style="color: #7c3aed; text-decoration: none;">{invite_url}</a>
                        </div>
                    </div>
                </div>

                <div class="footer">
                    <p>&copy; 2025 Waselytics Inc. All rights reserved.</p>
                    <p>
                        You received this email because you were invited to Waselytics. 
                        If this was a mistake, you can safely ignore this email.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    try:
        # لم نعد بحاجة لفحص مفتاح Brevo هنا
        
        # 1. إنشاء كائن الرسالة
        email = EmailMessage(
            subject=subject,
            body=html_content,
            # استبدل الإيميل الشخصي بإيميل الإعدادات (noreply)
            from_email=settings.DEFAULT_FROM_EMAIL, 
            to=[invitation.email],
        )

        # 2. تحديد أن محتوى الرسالة هو HTML وليس نصاً عادياً
        email.content_subtype = "html" 

        # 3. الإرسال (سيستخدم إعدادات SMTP Hostinger تلقائياً)
        email.send(fail_silently=False)

        print(f"📧 Invitation sent successfully via Hostinger SMTP to: {invitation.email}")
        return True

    except Exception as e:
        print("❌ Failed to send invitation:", e)
        return False


from django.contrib.auth import login
from django.http import JsonResponse



@check_plan_limit("max_team_members")
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
        channels_input = request.POST.get('channels', '')
        channels_list = channels_input.split(',') if channels_input else []
        if len(products) == 1 and ',' in products[0]:
            products = products[0].split(',')

        if not email:
            return JsonResponse({'error': 'البريد الإلكتروني مطلوب'}, status=400)

        if CustomUser.objects.filter(email=email).exists():
            return JsonResponse({
                'success' : False,
                'message': 'This email is already registered  with another account.'
                }, status=400)
        


        if 'all' in channels_list:
            # كل القنوات التي يملكها الأدمن
            selected_channels = WhatsAppChannel.objects.filter(owner=request.user)
        elif channels_list:
            # قنوات محددة (مع التحقق من الملكية)
            selected_channels = WhatsAppChannel.objects.filter(id__in=channels_list, owner=request.user)


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
            admin= request.user ,
            role=role,
            name=name,
        )
        invitation.products.set(selected_products)
        if channels_list:
            invitation.channels.set(selected_channels)  
        else:
            pass

        sent = send_invitation_email(request, invitation)
        invitation.save()

        if not sent:
            return JsonResponse({'error': 'فشل في إرسال البريد الإلكتروني'}, status=500)
        else:
            log_activity('invite_sent', f"Team invite sent to {email} (role: {role})", request=request, related_object=invitation)
            return JsonResponse({'success': 'تم إرسال الدعوة بنجاح'}, status=200)
         

        # إرسال البريد (يمكن تفعيلها لاحقًا)
        # send_invitation_email(invitation)


    # return render(request, 'team/invite_staff.html')
 
def accept_invite(request, token):
    error = ''
    invitation = get_object_or_404(TeamInvitation, token=token)
    
    if invitation.is_used:
        # إذا كانت مستخدمة، نوقف العملية فوراً
        return render(request, 'accept.html', {'error_message': 'This invitation has already been used.'})
    
    # إذا كان المستخدم مسجلاً، نتأكد أنه نفس صاحب الدعوة
    if request.user.is_authenticated:
        if invitation.email != request.user.email:
             return render(request, 'accept.html', {'error_message': 'You are logged in with a different email. Please logout first.'})

    if request.method == 'POST':
        # استقبال البيانات من الـ AJAX
        full_name = request.POST.get('full_name', invitation.name)
        password = request.POST.get('password') # 🔥 الجديد

        if not password:
             return JsonResponse({'status': 'error', 'message': 'Password is required'})

        try:
            # إنشاء المستخدم
            user = CustomUser.objects.create_user(
                username=invitation.email,
                email=invitation.email,
                password=password, # 🔥 نستخدم كلمة المرور الحقيقية هنا
                user_name=full_name,
                team_admin=invitation.admin,
                is_active=True,
                is_verified=True,
                is_team_admin=False
            )
            
            # منح الصلاحيات (كما هو في كودك الأصلي)
            for product in invitation.products.all():
                UserProductPermission.objects.get_or_create(
                    user=user,
                    product=product,
                    defaults={'role': invitation.role}
                )
            
            for channel in invitation.channels.all():
                channel.assigned_agents.add(user)

            # تحديث الدعوة
            invitation.is_used = True
            invitation.save()

            # تسجيل الدخول تلقائياً
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            log_activity('invite_accepted', f"Invite accepted by {invitation.email} (admin: {invitation.admin})", user=user, request=request, defer=False)
            return JsonResponse({'status': 'success'})

        except Exception as e:
            print(f"Error creating user: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)})

    # GET Request
    return render(request, 'accept.html', {
        'inviter': invitation.admin,
        'email': invitation.email,
        'invetations': invitation,
        'error_message': error
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
        log_activity('member_removed', f"Invitation deleted for {invitation.email}", request=request)
        invitation.delete()
        return redirect(f'/tracking/user/?{"invitation_deleted"}')

    # 2. محاولة حذف مستخدم فعلي من الفريق
    member = CustomUser.objects.filter(id=id, team_admin=request.user).first()
    if member:
        log_activity('member_removed', f"Team member removed: {member.user_name or member.email} (ID: {member.pk})", request=request)
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
        "phone": cphone,
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
@require_POST
def submit_order(request):
     
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "الطلب يجب أن يتم باستخدام POST"})

    # بيانات العميل
    name = request.POST.get("name")
    phone = request.POST.get("phone")
    address = request.POST.get("address")
    country_code = request.POST.get("country_code") or "SA"
    channel_id = request.POST.get("channel_id")
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
    
     
    if resp.status_code == 201:
        import uuid 
        try:
            product_instance = Products.objects.get(sku=selected_product_sku)
        except Products.DoesNotExist:
            return JsonResponse({"success": False, "message": "المنتج غير موجود في المخزون"}, status=400)

            
        order = SimpleOrder.objects.create(
                quantity = product_quantity,
                product=product_instance,   
                agent=request.user,
                channel=WhatsAppChannel.objects.get(id=channel_id),

                
                sku=selected_product_sku, 
                product_name=product_instance.name,  
                
                
                customer_name=name,
                customer_phone=phone,
                customer_city=address,  
                
                # السعر والعملة
                price=product_price,  
                
                # حقول النظام
                order_id=str(uuid.uuid4())[:8], 
                status='pending',
                created_at=timezone.now(),
               
                # الهدية
                gift_chosen=gift_obj,

                )
        # order = Order.objects.create(
        #     user=request.user,
        #     customer_name=name,
        #     customer_phone=phone,
        #     customer_city=address,
        #     product=selected_product_sku,
        #     product_quantity=product_quantity,
        #     product_price=product_price,
        #     gift_chosen=gift_obj ,
        #     channel= WhatsAppChannel.objects.get(id=channel_id) 
        # )
        log_activity(
            'simple_order_created',
            f"New order for {name} ({phone}), product: {selected_product_sku}" + (f", gift: {gift_sku}" if gift_sku else ""),
            request=request, related_object=order,
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
def updatedealy(request):
    if request.method == "POST":
        account_id = request.POST.get("account_id")
        new_limit = request.POST.get("order_limit")
        print(new_limit , account_id)
        print(CustomUser.objects.filter(id=account_id))
        try:
            perm = UserProductPermission.objects.filter(user__id=account_id).first()
            print(perm)
            perm.daily_order_limit = int(new_limit)
            perm.save()
            return JsonResponse ({"success": True, "message": f" Updated successfully for {perm.user.user_name}"})
        except UserProductPermission.DoesNotExist:
            return JsonResponse({"success": False, "message": "لم يتم العثور على المستخدم"})










import requests
from django.conf import settings
from bs4 import BeautifulSoup

def track_naqel_fast(waybill_no):
    # رابط الصفحة
    url = "https://www.naqelexpress.com/en/sa/tracking/"
    
    # محاكاة متصفح حقيقي (Header Spoofing)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.naqelexpress.com/en/sa/tracking/',
        'Origin': 'https://www.naqelexpress.com',
        'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
    }

    # نستخدم Session لحفظ الكوكيز تلقائياً بين الطلبات
    session = requests.Session()
    session.headers.update(headers)

    try:
        # ==========================================
        # الخطوة 1: الدخول للصفحة للحصول على التوكن
        # ==========================================
        print("1. Getting CSRF Token...")
        response_get = session.get(url, timeout=10)
        
        # استخراج التوكن من كود HTML
        soup = BeautifulSoup(response_get.content, 'html.parser')
        
        # البحث عن الحقل المخفي csrfmiddlewaretoken
        csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        
        if not csrf_input:
            return {"ok": False, "error": "Could not find CSRF token"}
            
        token = csrf_input['value']
       
        payload = {
            'csrfmiddlewaretoken': token,
            'waybills': waybill_no  # الاسم الذي وجدناه في الـ curl
        }

        response_post = session.post(url, data=payload, timeout=10)

        # ==========================================
        # الخطوة 3: استخراج النتيجة
        # ==========================================
        if response_post.status_code == 200:
            soup = BeautifulSoup(response_post.content, 'html.parser')
            
            # results_container = result_soup.find('div', class_='trborder') 
            data ={}
            import re
            # --- دالة مساعدة صغيرة لتنظيف النصوص ---
            def clean(text):
                return text.strip() if text else "N/A"

            shipment_label = soup.find('th', string=re.compile(r'SHIPMENT NO'))
            if shipment_label:
                # نأخذ العنصر التالي مباشرة (find_next_sibling)
                data['shipment_no'] = clean(shipment_label.find_next_sibling('td').text)

            # 2. استخراج الوجهة (DESTINATION)
            dest_label = soup.find('th', string=re.compile(r'DESTINATION'))
            if dest_label:
                data['destination'] = clean(dest_label.find_next_sibling('td').text)

            # 3. استخراج تاريخ التوصيل المتوقع (EXPECTED DELIVERY)
            date_label = soup.find('th', string=re.compile(r'EXPECTED DELIVERY'))
            if date_label:
                data['expected_date'] = clean(date_label.find_next_sibling('td').text)
            logs= []

            timeline_items = soup.find_all('p', class_=re.compile(r'text-white|text-light'))
    
            for item in timeline_items:
                text = item.get_text(strip=True)
                # فلترة النصوص غير المفيدة (مثل التواريخ فقط)
                if len(text) > 10 and not text.isdigit(): 
                    logs.append(text)
            data['timeline'] = logs

            # 4. استخراج الحالة الحالية (CURRENT STATUS) - لاحظ الاختلاف هنا!
            # في الـ HTML الخاص بهم، قيمة الحالة موجودة داخل <th> وليس <td>
            status_label = soup.find('th', string=re.compile(r'CURRENT STATUS'))
            if status_label:
                # نبحث عن الـ th التالي (لأن القيمة وضعت في th أيضاً حسب كودهم)
                status_value = status_label.find_next_sibling('th')
                
                if status_value:
                    data['raw_status'] = clean(status_value.text)
                else:
                    # احتياطاً لو غيروها لـ td
                    data['raw_status'] = clean(status_label.find_next_sibling('td').text)
            return data
        else:
            return {"ok": False, "error": f"Status Code: {response_post.status_code}"}

    except Exception as e:
        return {"ok": False, "error": str(e)}
def normalize_naqel_status(raw_text):
    text = raw_text.lower()
    
    if "delivered" in text:
        return 'delivered'
        
    elif "out for delivery" in text:
        return 'out_for_delivery'
        
    # الحالة التي سألت عنها وحالات مشابهة
    elif "returned to naqel facility" in text or "delivery failed" in text or "customer not available" in text:
        return 'exception' # ⚠️ حالة التدخل
        
    elif "shipment picked up" in text or "in transit" in text:
        return 'shipped'
        
    elif "shipment returned to origin" in text:
        return 'returned'
        
    else:
        return 'shipped' # افتراضياً نعتبرها مشحونة




 
    import requests

 

import hashlib
import requests
import json
import base64
from datetime import datetime

IMILE_RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA3dFPiKNZwt+HoBbPAG/t
7kZC2k3pBX2eCl5LeyeW8woNuEV5bA5kB9Y9KKTOQng62ERGPLwi84CdIB8s265
ljQUib//iO3jVrZesJueO5Xu+s80s3Z/89jgJleT1XawN1GubgkGXOoT1a7tvX8+
aItkGgR//48ELqJVVUL+yGsBtXxFjNmOEWxBJNQuwAf9yWcCIl1enD60GjZjPWrs
fw8QUqam7K5e45ealcPEYGenNePwuPpCq6twdD0YYYzKdRN0dZP1uTviFpNfph90
c9YgQ8kgDkRMcpjVv6KZ+bg5JZ4sK6LkV4vwOjPijisthHBvUXhu3fyhMgvoDO/j
5gwIDAQAB
-----END PUBLIC KEY-----"""


def _imile_rsa_sign(waybill_no):
    """Encrypt the waybill number with iMile's RSA public key for the sign header."""
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    key = RSA.import_key(IMILE_RSA_PUBLIC_KEY)
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(waybill_no.encode('utf-8'))
    return base64.b64encode(encrypted).decode('utf-8')


def track_imile_final(waybill_no):
    SECRET_SALT = "imileTrackQuery2024"

    raw_string = f"{waybill_no}{SECRET_SALT}"
    md5_code = hashlib.md5(raw_string.encode('utf-8')).hexdigest()

    url = f"https://www.imile.com/saastms/mobileWeb/track/query?waybillNo={waybill_no}&code={md5_code}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Accept': 'application/json',
        'lang': 'en_US',
        'sign': _imile_rsa_sign(waybill_no),
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()

            # التحقق من نجاح الطلب
            if data.get('status') == 'success' and data.get('resultObject'):
                result = data['resultObject']
                track_infos = result.get('trackInfos', [])
                
                # استخراج أحدث حالة (عادة تكون الأولى في القائمة)
                latest_event = track_infos[0] if track_infos else {}
                
                # الحالة الخام (نأخذ الـ content لأنه يحتوي التفاصيل الدقيقة مثل "Uncontactable")
                raw_status = latest_event.get('content', 'Unknown')
                status_time = latest_event.get('time', '')
                
                # تحليل السجل وحساب المحاولات الفاشلة
                stats = analyze_imile_history(track_infos)
                
                # توحيد الحالة للفرونت إند
                normalized_status = normalize_imile_status(raw_status)

                return {
                    "ok": True,
                    "tracking_company": "imile",
                    "order_number": result.get('waybillNo'),
                    "destination": result.get('country', 'KSA'), # أحياناً المدينة غير موجودة، الدولة تكفي
                    "expected_delivery": extract_expected_date(track_infos) or "Check App",
                    "order_status": normalized_status,      # (delivered, exception, shipped...)
                    "raw_status": raw_status,               # النص الأصلي من iMile
                    "failed_attempts": stats['attempts'],   # لبطاقة الذكاء
                    "last_update": status_time,
                    "history": stats['logs']                # السجل الكامل
                }
            else:
                 return {"ok": False, "error": "Shipment not found or Invalid Data"}
        else:
            return {"ok": False, "error": f"HTTP Error {response.status_code}"}

    except Exception as e:
        return {"ok": False, "error": str(e)}

# --- دوال المساعدة الذكية ---

def normalize_imile_status(content):
    text = str(content).lower()
    
    # حالات التسليم
    if "delivered" in text or "signed" in text: 
        return 'delivered'
    
    # حالات الخروج للتوصيل
    if "out for delivery" in text or "dispatching" in text: 
        return 'out_for_delivery'
    
    # حالات الاسترجاع
    if "returned" in text or "returning" in text: 
        return 'returned'
    
    # حالات الفشل والمشاكل (بناءً على الـ JSON الذي أرسلته)
    fail_keywords = [
        "fail", "uncontactable", "switch off", "doesn't want", 
        "refused", "cancel", "did not order", "change location",
        "noanswer", "customer not available"
    ]
    if any(keyword in text for keyword in fail_keywords):
        return 'exception'

    return 'shipped' # الافتراضي

def analyze_imile_history(track_infos):
    attempts = 0
    logs = []
    
    # الكلمات المفتاحية للفشل من واقع بياناتك
    fail_triggers = [
        "uncontactable", "noanswer", "doesn't want", 
        "refused", "delivery failed", "rescheduled"
    ]

    for item in track_infos: # القائمة أصلاً مرتبة من الأحدث للأقدم
        desc = item.get('content', '')
        time = item.get('time', '')
        logs.append(f"{time} - {desc}")
        
        # حساب المحاولات الفاشلة
        desc_lower = desc.lower()
        if any(trigger in desc_lower for trigger in fail_triggers):
            attempts += 1
            
    return {"attempts": attempts, "logs": logs}

def extract_expected_date(track_infos):
    # محاولة استخراج تاريخ مجدول من السجل مثل: "Shipment is scheduled to [2025-12-13]"
    for item in track_infos:
        content = item.get('content', '')
        if "scheduled to" in content.lower():
            # استخراج التاريخ البسيط
            import re
            match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', content)
            if match:
                return match.group(1)
    return None

# print(track_imile_final("6120825213610"))

# @csrf_exempt
def track_injaz(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    order_number = request.POST.get("order")
    if order_number.startswith("3"):
        resulta = track_naqel_fast(order_number)
        print(resulta['raw_status'])
        if resulta :
            get_status = normalize_naqel_status(resulta['raw_status'])
            context = {'order_status' : get_status,
                        'destination' : resulta['destination'],
                        'tracking_company' : "Naqel",
                        'order_number' : resulta.get('shipment_no', None),
                        'expected_delivery' : resulta['expected_date'],
                        'timeline' : resulta['timeline'],
                        # 'status' : resulta['status'],
                }

        if get_status :
            update = SimpleOrder.objects.filter(agent = request.user , tracking_number = order_number).update(status = get_status)
        return JsonResponse({"message": "Order status updated" , "data": context }, status=200)



    elif order_number.startswith("6"):
        resulta = track_imile_final(order_number)

        if not resulta or not resulta.get('ok'):
            error_msg = resulta.get('error', 'Unknown error') if resulta else 'No response from iMile'
            return JsonResponse({
                "error": error_msg,
                "detail": f"iMile returned no tracking data for {order_number}. "
                          "The shipment may not exist, may have been purged, "
                          "or iMile's tracking service is temporarily unavailable.",
                "tracking_number": order_number,
                "tracking_company": "imile",
            }, status=404)

        get_status = resulta.get('order_status')
        context = {
            'order_status': get_status,
            'destination': resulta.get('destination'),
            'tracking_company': "imile",
            'order_number': resulta.get('order_number', order_number),
            'expected_delivery': resulta.get('expected_delivery'),
            'timeline': resulta.get('history'),
            'failed_attempts': resulta.get('failed_attempts', 0),
            'last_update': resulta.get('last_update'),
            'raw_status': resulta.get('raw_status'),
        }

        if get_status:
            SimpleOrder.objects.filter(
                agent=request.user, tracking_number=order_number
            ).update(status=get_status)

        return JsonResponse({"message": "Order status updated", "data": context}, status=200)
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


def _accessible_whatsapp_channels_for_user(user):
    """Channels the user may configure (owner, team workspace, assigned agent, superuser)."""
    if getattr(user, "is_superuser", False):
        return WhatsAppChannel.objects.all().order_by("id")
    owner = getattr(user, "team_admin", None) or user
    owned = WhatsAppChannel.objects.filter(owner=owner)
    assigned = WhatsAppChannel.objects.filter(assigned_agents=user)
    return (owned | assigned).distinct().order_by("id")


@login_required(login_url="/auth/login/")
def voice_settings_dashboard(request):
    """
    Merchant Voice Gallery: pick AI agent voice with static MP3 previews (no ElevenLabs preview API).
    Catalog rows: Django Admin → Voice Gallery entries.
    """
    channels = _accessible_whatsapp_channels_for_user(request.user)
    channel_id = (request.GET.get("channel_id") or "").strip()
    channel = None
    if channel_id.isdigit():
        channel = channels.filter(id=int(channel_id)).first()
    if channel is None:
        channel = channels.first()
    return render(
        request,
        "dashboard/voice_settings.html",
        {
            "channels": channels,
            "channel": channel,
            "channel_id": channel.id if channel else None,
        },
    )
