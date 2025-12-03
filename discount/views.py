
# Create your views here.
# views.py
from discount.crypto import decrypt_token
from .utils import download_and_save_local_image

from django.shortcuts import render, redirect
from django.contrib import messages
import requests
from .models import CODProduct, ExternalTokenmodel, Order ,SimpleOrder , Products , UserProductPermission
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse ,HttpResponse
from django.db.models import Count
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

# views.py
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
import json


from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404



import shopify
import time

# تهيئة API

# التهيئة بالطريقة التي تعمل عندك

# مثال للاستخدام:



#def updateShopify(request):
#    pass







def order_track(request, sku):
    product = get_object_or_404(CODProduct, sku=sku)
    set_order = Order.objects.create(
        gift_chosen= product,
        customer_name = 'null',
        product = product.name ,
    )
    return HttpResponse(f"تم إنشاء الطلب بنجاح! المنتج المختار: {product.name}")

@csrf_exempt
def free_gifts_api(request, country=None):
    if not country:
        return JsonResponse({'status': 'denied', 'message': 'No country provided', 'products': []})

    products = CODProduct.objects.filter(stock__gt=0, country=country)
    data = []

    for product in products:
        data.append({
            'sku': product.sku,
            'name': product.name,
            'image': product.productImage.url if product.productImage else '/static/default-product.png',
            'stock': product.stock,
            'original_price': product.original_price,
        })

    return JsonResponse({'status': 'approved' , 'products': data})





@csrf_exempt
def update_product(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        name = request.POST.get('name')
        image = request.FILES.get('image')

        if not product_id:
            return JsonResponse({"success": False, "error": "رقم المنتج مطلوب"}, status=400)
        if name:
            product = CODProduct.objects.get(id=product_id)
            # CODProduct.objects.filter(id=product_id).update(name=name ,updated = True)
            product.name=name
            product.updated = True
            product.save()
           



        # تحديث الصورة
        if image:
            product = CODProduct.objects.get(id=product_id)
            product.productImage.save(f"{product_id}_image.jpg", ContentFile(image.read()), save=True)
            product.updated = True
            product.save()
            # path = default_storage.save(f"products/{product_id}_image.jpg", image)
            # CODProduct.objects.filter(id=product_id).update(image_url=path , updated = True)

            # print(f"Image saved at: {path}")
            # يمكنك هنا تحديث قاعدة البيانات بالمسار الجديد

        return JsonResponse({
            "success": True,
            "message": "تم تحديث المنتج"
        })

    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)





from django.db.models import Count, Sum, Avg, F, Q
from django.db.models.functions import TruncDay
from django.utils import timezone
from datetime import timedelta

def analytics_dashboard(request):
    # تحديد الفترة الزمنية
    time_range = request.GET.get('range', 'month')
    date_threshold = calculate_date_threshold(time_range)
    
    # الإحصائيات الأساسية
    orders = Order.objects.filter(created_at__gte=date_threshold)
    total_orders = orders.count()
    orders_with_gift = orders.exclude(gift_chosen=None).count()
    confirmed_orders = orders.filter(confirmed=True).count()
    
    # إحصائيات إضافية
    average_order_value = orders.aggregate(aov=Avg('total_amount'))['aov'] or 0
    product_views = ProductView.objects.filter(view_date__gte=date_threshold).count()
    conversions = orders.count()
    conversion_rate = (conversions / product_views * 100) if product_views > 0 else 0
    returning_customers = User.objects.filter(orders__created_at__gte=date_threshold).annotate(order_count=Count('orders')).filter(order_count__gt=1).count()
    
    # توزيع الهدايا
    gift_distribution = orders.exclude(gift_chosen=None).values('gift_chosen__name').annotate(
        count=Count('gift_chosen'),
        total_revenue=Sum('total_amount')
    ).order_by('-count')[:10]
    
    # توزيع الفئات
    category_distribution = GiftCategory.objects.annotate(
        total_orders=Count('gifts__order'),
        total_revenue=Sum('gifts__order__total_amount')
    ).values('name', 'total_orders', 'total_revenue')
    
    # اتجاهات المبيعات
    sales_trend = orders.annotate(
        day=TruncDay('created_at')
    ).values('day').annotate(
        total_sales=Sum('total_amount')
    ).order_by('day')
    
    # أداء الدول
    country_performance = orders.values('country').annotate(
        total_orders=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-total_revenue')[:10]
    
    # الطلبات الحديثة
    recent_orders = orders.select_related('gift_chosen').order_by('-created_at')[:10]
    
    # عناصر قليلة المخزون
    low_stock_items = Product.objects.filter(
        stock__lte=F('low_stock_threshold')
    ).order_by('stock')[:10]
    
    # حساب النسب المئوية
    gift_percentage = (orders_with_gift / total_orders * 100) if total_orders > 0 else 0
    confirmation_rate = (confirmed_orders / total_orders * 100) if total_orders > 0 else 0
    retention_rate = (returning_customers / User.objects.count() * 100) if User.objects.count() > 0 else 0
    
    context = {
        # الإحصائيات الأساسية
        'total_orders': total_orders,
        'orders_with_gift': orders_with_gift,
        'confirmed_orders': confirmed_orders,
        'average_order_value': round(average_order_value, 2),
        'product_views': product_views,
        'conversions': conversions,
        'conversion_rate': round(conversion_rate, 1),
        'returning_customers': returning_customers,
        'retention_rate': round(retention_rate, 1),
        
        # بيانات الرسوم البيانية
        'gift_labels': [item['gift_chosen__name'] for item in gift_distribution],
        'gift_data': [item['count'] for item in gift_distribution],
        'category_labels': [item['name'] for item in category_distribution],
        'category_data': [item['total_orders'] for item in category_distribution],
        'sales_labels': [item['day'].strftime("%Y-%m-%d") for item in sales_trend],
        'sales_data': [float(item['total_sales'] or 0) for item in sales_trend],
        'country_labels': [item['country'] for item in country_performance],
        'country_data': [float(item['total_revenue'] or 0) for item in country_performance],
        
        # الجداول
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
        
        # النسب المئوية
        'gift_percentage': round(gift_percentage, 1),
        'confirmation_rate': round(confirmation_rate, 1),
    }
    
    return render(request, 'analytics/dashboard.html', context)

def calculate_date_threshold(time_range):
    today = timezone.now()
    if time_range == 'today':
        return today - timedelta(hours=24)
    elif time_range == 'week':
        return today - timedelta(days=7)
    elif time_range == 'month':
        return today - timedelta(days=30)
    elif time_range == 'quarter':
        return today - timedelta(days=90)
    elif time_range == 'year':
        return today - timedelta(days=365)
    else:
        return today - timedelta(days=30)
    




    








def page(request):
    products = CODProduct.objects.filter(stock__gt=0)

    return render (request ,'lp.html',{'products': products})


def product_detail_api(request, product_id):
    product = CODProduct.objects.get(id=product_id)
    data = {
        'id': product.id,
        'name': product.name,
        'cod_id': product.cod_id,
        'original_price': product.original_price,
        'product_cost': product.product_cost,
        'stock': product.stock,
        'productImage': product.productImage,
        'sku': product.sku
    }
    return JsonResponse(data)  # يُرجع JSON تلقائياً


 
def home(request):
 
    
    if request.user.is_authenticated:
            products = CODProduct.objects.filter(stock__gt=0)
            # إضافة بحث بسيط (اختياري)
            search_query = request.GET.get('search', '')
            country_query = request.GET.get('country', '')
            project_query = request.GET.get('project', '')
            if country_query:
                products = products.filter(country__icontains=country_query)
            if project_query:
                products = products.filter(project__icontains=project_query)

            if search_query:
                products = products.filter(
                    Q(name__icontains=search_query) |
                    Q(cod_id__icontains=search_query)
                )
            countries = set(products.values_list('country', flat=True))
            
            # نفس الشيء مع المشاريع إن أردت
            projects = set(products.values_list('project', flat=True))  # افترض أن الحقل اسمه project

            return render(request, 'home.html', {
                'products': products,
                'search_query': search_query,
                'countries': countries,
                'projects': projects,
            })
    else:
        return render(request, 'home.html',)


# @transaction.atomic
# def update_cod_products(request):
#     try:
#         headers = {"Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczpcL1wvc2VsbGVyLmNvZC5uZXR3b3JrXC9jbGllbnRcL2dlbmVyYXRlLWFjY2Vzcy10b2tlbiIsImlhdCI6MTcxMzcxMDY3NSwiZXhwIjoxODcxMzkwNjc1LCJuYmYiOjE3MTM3MTA2NzUsImp0aSI6IjRNMUlabDRMWWRSNDFTdGEiLCJzdWIiOjM0OTgsInBydiI6IjIzYmQ1Yzg5NDlmNjAwYWRiMzllNzAxYzQwMDg3MmRiN2E1OTc2ZjcifQ.RtmBnjw8NxdAJeOU1oGiB15qY49mJXuBcbb8t3TnJcE"}
#         response = requests.get("https://api.cod.network/v1/seller/drop-products", headers=headers)

#         if response.status_code == 200:
#             data = response.json()
#             saved_count = 0

#             for product_data in data.get('data', []):
#                 try:
#                     # استخراج السعر من up_sell_and_backup_prices (أول سعر في القائمة)
#                     price_data = product_data.get('up_sell_and_backup_prices', [{}])[0]
#                     price = float(price_data.get('price', 0))
#                     updatpro = CODProduct.objects.filter(cod_id=str(product_data['id']))
#                     if updatpro.updated == True :
#                         CODProduct.objects.update_or_create(
#                         cod_id=str(product_data['id']),
#                         defaults={
#                             # 'name': product_data.get('name', ''),
#                             'original_price': price,
#                             'sku': product_data.get('sku'),
#                             'product_cost':product_data.get('product_cost' ,0),
#                             'stock': int(product_data.get('quantity', 0)),
#                             # 'image_url': product_data.get('media', {}).get('default_image', '')
#                         }
#                     )
#                     saved_count += 1
#                     product = CODProduct.objects.update_or_create(
#                         cod_id=str(product_data['id']),
#                         defaults={
#                             'name': product_data.get('name', ''),
#                             'original_price': price,
#                             'sku': product_data.get('sku'),
#                             'product_cost':product_data.get('product_cost' ,0),
#                             'stock': int(product_data.get('quantity', 0)),
#                             'image_url': product_data.get('media', {}).get('default_image', '')

#                         }
#                     )
#                             # إذا لم يتم تنزيل الصورة سابقاً أو كانت غير موجودة → نبدأ التنزيل
#                     if not product.productImage:
#                             success = download_and_save_local_image(product, product_data['image_url'])
#                     if success:
#                             product.save()

#                 except Exception as e:
#                     print(f"Failed to save product {product_data.get('id')}: {str(e)}")
#                     continue

#             messages.success(request, f'تم تحديث {saved_count} منتج بنجاح!')
#             return redirect('cod_products_list')  # تأكد من وجود هذا المسار في urls.py

#         else:
#             messages.error(request, 'فشل في جلب البيانات من COD API')
#             return redirect('home')

#     except Exception as e:
#         messages.error(request, f'حدث خطأ غير متوقع: {str(e)}')
#         return redirect('home')



        # headers = {"Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczpcL1wvc2VsbGVyLmNvZC5uZXR3b3JrXC9jbGllbnRcL2dlbmVyYXRlLWFjY2Vzcy10b2tlbiIsImlhdCI6MTcxMzcxMDY3NSwiZXhwIjoxODcxMzkwNjc1LCJuYmYiOjE3MTM3MTA2NzUsImp0aSI6IjRNMUlabDRMWWRSNDFTdGEiLCJzdWIiOjM0OTgsInBydiI6IjIzYmQ1Yzg5NDlmNjAwYWRiMzllNzAxYzQwMDg3MmRiN2E1OTc2ZjcifQ.RtmBnjw8NxdAJeOU1oGiB15qY49mJXuBcbb8t3TnJcE"}
        # response = requests.get("https://api.cod.network/v1/seller/drop-products", headers=headers , params=params)

@transaction.atomic

def update_cod_products(request):
    token_obj = ExternalTokenmodel.objects.filter(user=request.user).first()
    if token_obj is None or not token_obj.token_status:
           return JsonResponse({
    'message': 'you need an access token',
     'status' : False })

    
    try:
        token_obj = ExternalTokenmodel.objects.filter(user=request.user).first()
        decrypted_tok = decrypt_token(token_obj.access_token)
        headers = {"Authorization": f"Bearer {decrypted_tok} "}
 
        
        # الخطوة 1: جلب جميع الصفحات
        all_products = []
        page = 1
        while True:
            params = {
                "page": page,
                "per_page": 100  # الحد الأقصى المسموح به
            }
            
            response = requests.get(
                "https://api.cod.network/v1/seller/drop-products",
                headers=headers,
                params=params
            )
            
            if response.status_code != 200:
                print(f"Failed to fetch page {page}: {response.status_code}")
                break
                
            data = response.json()
            current_products = data.get('data', [])
            all_products.extend(current_products)
            
            # التحقق إذا كانت هذه آخر صفحة
            pagination = data.get('meta', {}).get('pagination', {})
            if page >= pagination.get('total_pages', 1):
                break
                
            page += 1
            time.sleep(1)  # تأخير لمدة ثانية لتجنب الضغط على السيرفر

        # الخطوة 2: معالجة جميع المنتجات
        saved_count = 0
        existing_ids = set(CODProduct.objects.values_list('cod_id', flat=True))
        
        for product_data in all_products:
            try:
                price_data = product_data.get('up_sell_and_backup_prices', [{}])[0]
                price = float(price_data.get('price', 0))
                
                is_new = str(product_data['id']) not in existing_ids
                
                product = CODProduct.objects.update_or_create(
                    cod_id=str(product_data['id']),
                    defaults={
                        'user' : request.user ,
                        'country': product_data.get('country'),
                        'original_price': price,
                        'project': product_data.get('project'),
                        'sku': product_data.get('sku'),
                        'product_cost': product_data.get('product_cost', 0),
                        'stock': int(product_data.get('quantity', 0)),
                        'image_url': product_data.get('media', {}).get('default_image', ''),
                        'updated': not is_new  # تحديث الحالة إذا كان منتجاً موجوداً
                    }
                )[0]
                 
                # فقط للمنتجات الجديدة أو التي لم يتم تحديثها من قبل
                if is_new or not product.updated:
                    product.name = product_data.get('name', product.name)
                    image_url = product_data.get('media', {}).get('default_image', '')
                    
                    if image_url and (is_new or not product.productImage):
                        product.image_url = image_url
                        success = download_and_save_local_image(product, image_url)
                        if success:
                            product.save()
                
                product.save()
                saved_count += 1
                
            except Exception as e:
                print(f"فشل في معالجة المنتج {product_data.get('id')}: {str(e)}")
                continue

        # return JsonResponse({
        #     'success': True,
        #     'message': 'تمت التحديث بنجاح',
        #     'saved_count': saved_count
        # })
        codProduct = CODProduct.objects.filter(stock__gt=0)
        last_update = codProduct.last().last_updated
        return JsonResponse({
    'last_update': last_update.strftime('%Y-%m-%d %H:%M:%S'), 
    'message': 'تم التحديث بنجاح!',
    'updated_html': render_to_string('partials/_product_views.html', {'productslists': codProduct})
})

        # return redirect(f'/tracking/user/?product_updates={saved_count}')

    except Exception as e:
        messages.error(request, f'حدث خطأ غير متوقع: {str(e)}')
        return redirect('home')
    








def filterinCode(request):
        products = CODProduct.objects.filter(stock__gt=0)
        # إضافة بحث بسيط (اختياري)
        search_query = request.POST.get('search', '')
        country_query = request.POST.get('country', '')
        project_query = request.POST.get('project', '')
        if country_query:
            products = products.filter(country__icontains=country_query)
        if project_query:
            
            products = products.filter(project__icontains=project_query)

        if search_query:
            products = products.filter(
                Q(name__icontains=search_query) |
                Q(cod_id__icontains=search_query)
            )
        countries = set(products.values_list('country', flat=True))
        
        projects = set(products.values_list('project', flat=True))  # افترض أن الحقل اسمه project

         

        return JsonResponse({
    'message': 'تم الفلترة بنجاح!',
    'updated_html': render_to_string('partials/_product_views.html', {'productslists': products ,     'countries': countries,
        'projects': projects,})
})







 


import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

@csrf_exempt
def get_tracking_company_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            data = {}

        period = data.get('period', '7')
        product = data.get('product', 'all')
        country = data.get('country', 'all')
        # إن أرسلت start_date/end_date بالـ snake_case فاستعملهما هنا
        start_date_in = data.get('start_date') or data.get('startDate')
        end_date_in = data.get('end_date') or data.get('endDate')

        

        # ===== تحديد المنتجات المسموح بها للمستخدم =====
        admin_products = None
        if getattr(request.user, 'is_team_admin', False):
            
            # Products هو نموذج المنتجات عندك - يرجع queryset من Products
            admin_products = Products.objects.filter(admin=request.user)
            if not admin_products.exists():
                return JsonResponse({'error': 'No products found for this admin'})
            # نحولها لقائمة IDs لسهولة المقارنات لاحقاً
            allowed_product_ids = list(admin_products.values_list('id', flat=True))
        else:
            
            user_products = UserProductPermission.objects.filter(user=request.user)
            getproducst_id = user_products.values_list('product_id', flat=True)
            product_ids = list(getproducst_id)  # مثال: [24, 25, 26]
            admin_products = product_ids
            allowed_product_ids = product_ids
            

            if not admin_products:
                return JsonResponse({'error': 'No products found for this staff member'})

        # ===== بناء استعلام الطلبات مع تصفية حسب المنتجات المسموح بها =====
        # استخدمنا product_id__in مع قائمة الأيدي
        trackingdata = SimpleOrder.objects.filter(product_id__in=allowed_product_ids)

        # ===== إذا اختار المستخدم منتج محدد =====
        if product != 'all':
            # محصول: product قد يأتي كـ id (رقم كسلسلة) أو كـ sku
            selected_product_id = None
            try:
                # حاول تحويله إلى رقم
                pid = int(product)
                selected_product_id = pid
            except (ValueError, TypeError):
                # لم يكن رقماً، حاول البحث بالـ SKU
                prod = Products.objects.filter(sku=product).first()
                if prod:
                    selected_product_id = prod.id

            # لو وجدنا معرف المنتج المختار، تأكد أنه من ضمن المسموح ثم صفّ
            if selected_product_id is not None and selected_product_id in allowed_product_ids:
                trackingdata = trackingdata.filter(product_id=selected_product_id)
            else:
                # أو إرجاع نتيجة فارغة إذا المنتج غير موجود أو غير مصرح للمستخدم
                return JsonResponse({'orders': []})
             

        # ===== فلتر الدولة =====
        if country != 'all':
            trackingdata = trackingdata.filter(customer_country=country)
            

        # ===== فلتر الفترة الزمنية =====
        now = timezone.now()
        if period != 'custom' and isinstance(period, str) and period.isdigit():
            days = int(period)
            date_threshold = now - timedelta(days=days)
            trackingdata = trackingdata.filter(created_at__gte=date_threshold)
        elif period == 'custom':
            if start_date_in and end_date_in: 
                # 0693098387
                try:
                    sd = datetime.strptime(start_date_in, '%Y-%m-%d').date()
                    ed = datetime.strptime(end_date_in, '%Y-%m-%d').date()
                    trackingdata = trackingdata.filter(created_at__date__gte=sd, created_at__date__lte=ed)
                except ValueError:
                    return JsonResponse({'error': 'Invalid date format'}, status=400)
            else:
                # إذا اختار custom ولم يرسل تواريخ، نعيد خطأ أو نكمل بدون فلتر — هنا نعيد خطأ
                return JsonResponse({'error': 'start_date and end_date required for custom period'}, status=400)

        # ===== تجهيز الإخراج =====
        tracking_list = list(trackingdata.values('tracking_number', 'status').distinct())
        return JsonResponse({'orders': tracking_list})

    else:
        
        return JsonResponse({'error': 'Invalid request method'}, status=405)
 










# footer lins 
def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def terms(request):
    return render(request, 'terms.html')    

def data_deletion(request):
    return render(request, 'data_deletion.html')

def contact(request):
    return render(request, 'contact.html')

