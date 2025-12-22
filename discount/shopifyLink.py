import shopify
import logging
from django.conf import settings
from .models import CODProduct ,SimpleOrder , CustomUser , Activity ,ExternalTokenmodel ,Products ,TeamInvitation , Order , UserProductPermission
import time
from urllib.parse import quote
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from datetime import datetime
from django.utils.timezone import make_aware
from .models import Lead, Products, UserProductPermission

logger = logging.getLogger(__name__)

def initialize_shopify():
    try:
        # التحقق من توفر الإعدادات المطلوبة
        if not all([settings.SHOPIFY_STORE_URL, settings.SHOPIFY_API_VERSION, settings.SHOPIFY_ACCESS_TOKEN]):
            logger.critical("إعدادات Shopify غير مكتملة.")
            return False

        # تهيئة الجلسة
        session = shopify.Session(
            settings.SHOPIFY_STORE_URL,
            settings.SHOPIFY_API_VERSION,
            settings.SHOPIFY_ACCESS_TOKEN
        )
        shopify.ShopifyResource.activate_session(session)

        logger.info("تم تهيئة الاتصال بـ Shopify بنجاح.")
        return True
    except Exception as e:
        logger.critical(f"فشل تهيئة الاتصال: {str(e)}")
        return False
# 2. وظائف البحث المحسنة
def find_product_by_sku(sku):
    """بحث دقيق باستخدام SKU مع تشفير URL"""
    try:
        if not sku or not sku.strip():
            logger.warning("SKU فارغ أو غير صالح.")
            return None

        encoded_sku = quote(f'sku:"{sku.strip()}"')
        variants = shopify.Variant.find(query=encoded_sku)
        if variants:
            product_id = str(variants[0].product_id)
            logger.info(f"تم العثور على المنتج باستخدام SKU: {sku} → Product ID: {product_id}")
            return product_id
        else:
            logger.warning(f"لم يُعثر على منتج باستخدام SKU: {sku}")
            return None
    except Exception as e:
        logger.error(f"خطأ في البحث بالـ SKU: {sku} | {str(e)}")
        return None

def find_product_by_name(name):
    """بحث دقيق باستخدام الاسم مع تشفير URL"""
    try:
        if not name or not name.strip():
            logger.warning("اسم المنتج فارغ أو غير صالح.")
            return None

        encoded_name = quote(f'title:"{name.strip()}"')
        products = shopify.Product.find(query=encoded_name)
        if products:
            product_id = str(products[0].id)
            logger.info(f"تم العثور على المنتج باستخدام الاسم: {name} → Product ID: {product_id}")
            return product_id
        else:
            logger.warning(f"لم يُعثر على منتج باستخدام الاسم: {name}")
            return None
    except Exception as e:
        logger.error(f"خطأ في البحث بالاسم: {name} | {str(e)}")
        return None

# 3. الدالة الرئيسية مع التحسينات
from django.http import JsonResponse

def update_cod_ids_safely(request):
    # التحقق من تهيئة الاتصال
    if not initialize_shopify():
        return JsonResponse({"status": "error", "message": "فشل الاتصال بـ Shopify"}, status=500)

    # جلب المنتجات التي لا تحتوي على cod_id
    products = CODProduct.objects.filter(cod_id__isnull=True)
    results = {"total": products.count(), "success": 0, "failures": 0}

    for idx, product in enumerate(products):
        try:
            shopify_id = None

            # البحث باستخدام SKU إذا كان متاحًا
            if product.sku and product.sku.strip():
                shopify_id = find_product_by_sku(product.sku)

            # البحث باستخدام الاسم إذا لم يتم العثور على المنتج باستخدام SKU
            if not shopify_id and product.name and product.name.strip():
                shopify_id = find_product_by_name(product.name)

            if shopify_id:
                product.cod_id = shopify_id
                product.save(update_fields=['cod_id'])
                results["success"] += 1
                logger.info(f"تم تحديث المنتج: {product.name} → COD ID: {shopify_id}")
            else:
                results["failures"] += 1
                logger.warning(f"لم يُعثر على منتج: {product.name}")

            # إدارة Rate Limiting الذكية
            sleep_time = 2 if idx % 40 == 39 else 0.5
            time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"فشل في تحديث المنتج {product.id}: {str(e)}")
            results["failures"] += 1

    # إرجاع النتائج كاستجابة JSON
    return JsonResponse(results)

from discount.models import UserPermissionSetting








import shopify
from django.conf import settings
from .models import CODProduct
import time
from django.http import JsonResponse ,HttpResponse

shop_url = "cod-storet.myshopify.com"
api_version = "2023-10"
access_token = "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"

shopify.ShopifyResource.set_site(f"https://{shop_url}/admin/api/{api_version}")
shopify.ShopifyResource.headers = {"X-Shopify-Access-Token": access_token}

# 2. دالة مبسطة لإنشاء المنتج
def create_simple_product(product):
    try:
        # إنشاء المنتج الأساسي
        new_product = shopify.Product({
            'title': product.name,
            'body_html': product.name,
            'vendor': "متجرك",
            'product_type': "منتجات عامة",
            'variants': [{
                'price': str(product.original_price),
                'sku': product.sku or f"COD_{product.id}",
            }]
        })

        # إضافة الصورة إذا موجودة
        if product.productImage:
            image_url = f"{'test.com'}{product.productImage.url}"
            new_product.images = [{'src': image_url}]

        if new_product.save():
            product.updated = True
            product.save()
            return True
        return False

    except Exception as e:
        
        return False

# 3. الدالة الرئيسية
def sync_simple_products():
    products = CODProduct.objects.filter(stock__gt=0)

    for product in products:
        if create_simple_product(product):
            print(f"تم إنشاء المنتج: {product.name}")
        else:
            print(f"فشل إنشاء المنتج: {product.name}")

        time.sleep(1)  # تأخير بسيط بين الطلبات

    return {"status": "done", "count": products.count()}

# 4. استدعاء الدالة من View
def sync_products_view(request):
    result = sync_simple_products()
    return JsonResponse(result)












import requests
import json

shop_url = "cod-storet.myshopify.com"
api_version = "2023-10"  # استخدم أحدث إصدار من API
access_token = "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"  # استبدل هذا بالرمز الخاص بك

# رابط نقطة نهاية GraphQL
url = f"https://{shop_url}/admin/api/{api_version}/graphql.json"

def get_product_by_sku(sku, vid):
    if not sku:  # التحقق من أن SKU ليس فارغًا
        print('SKU is empty')
        return False

    product = CODProduct.objects.filter(sku=sku).first()
    
    if product:
        product.cod_id = vid
        product.save()


       
    else:
        print( f"Product with SKU {sku} not found.")
# الاستعلام GraphQL

def update_id(request):
    query = '''
    {
    products(first: 10) {
        nodes {
        id
        title
        vendor
        productType
        status
        variants(first: 10) {
            nodes {
            id
            title
            price
            sku
            }
        }
        }
        pageInfo {
        hasNextPage
        endCursor
        }
    }
    }
    '''

    # إعداد الطلب
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": access_token
    }

    # إرسال الطلب
    response = requests.post(
        url,
        headers=headers,
        json={"query": query},
        verify=False
    )

    # معالجة الاستجابة
    if response.status_code == 200:
        try:
            data = response.json()
            if not data or 'data' not in data or 'products' not in data['data']:
                print("Invalid response structure")
                products = []

            else:
                products = data["data"]["products"]["nodes"]
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            print("Response text:", response.text)
            products = []

        for product in products:
            print("Variants:")
            for variant in product['variants']['nodes']:
                variant_id = variant['id'].split('/')[-1]
                variant_sku = variant.get('sku')
                print(variant_sku)
                if variant_sku:
                    success = get_product_by_sku(variant_sku, variant_id)
                    print(f"  Variant ID: {variant_id} - Variant SKU: {variant_sku} - Update {'successful' if success else 'failed'}")
                else:
                    print(f"  Variant ID: {variant_id} has no SKU")

        # إرجاع رد ناجح
        return JsonResponse({"status": "success", "message": "Products processed successfully"}, status=200)
    else:
        # إرجاع رد في حالة الخطأ
        return JsonResponse({"status": "error", "message": f"Failed to fetch products. Status code: {response.status_code}"}, status=response.status_code)












from django.conf import settings
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils.translation import gettext as _
import requests

from .crypto import decrypt_token

# def get_simple_orders(request,sku):
#     """
#     جلب الطلبات المبسطة من COD API حسب SKU
#     """

#     s = ExternalTokenmodel.objects.filter(user=request.user).first()
#     if s :
#         y=s.access_token
#     else:
#         return False
#     decrypted = decrypt_token(y)

#     api_url = "https://api.cod.network/v1/seller/orders"
#     headers = {
#         'Authorization': f'Bearer {decrypted}',
#         'Content-Type': 'application/json'
#     }
#     params = {
#         'sku': sku,
#         'limit': 1000,
#         'status': 'all'
#     }

#     try:
#         response = requests.get(api_url, headers=headers, params=params)
#         response.raise_for_status()
#         data = response.json()

#         # تعديل هنا لملائمة هيكل البيانات الجديد
#         orders = data.get('data', [])

#         simplified_orders = []
#         for order in orders:
#             simplified = {
#                 'created_at': order.get('created_at'),  # استخدام الوقت الحالي إذا لم يكن موجودًا
#                 'customer_city' : order.get('customer_city'),
#                 'status' : order.get('status'),  # تغيير من status إلى status
#                 'order_id': order.get('id'),  # تغيير من orderId إلى id
#                 'tracking_number': order.get('tracking_number'),  # تغيير من trackingNumber إلى reference
#                 'sku': sku,  # نستخدم SKU الذي أدخله المستخدم
#                 'customer_name': order.get('customer_name', ''),
#                 'customer_phone': order.get('customer_phone', ''),
#                 'product_name': order.get('product_name', ''),  # قد تحتاج لتعديل هذا حسب API
#             }
#             simplified_orders.append(simplified)

#         return simplified_orders

#     except requests.exceptions.RequestException as e:
#         print(f"Error fetching orders: {str(e)}")
#         return []

# def table_update(request):
#     if request.user.is_authenticated:
#         # shopifyLink.update_id()
#         sku = 'HERBAL2B'
#         if not sku:
#             messages.error(request, _('الرجاء إدخال SKU صالح.'))
#             return redirect('tracking')

#         if sku:
#             saved_count = 0
#             new_orders = get_simple_orders(request,sku)

#             if new_orders:
#                 # طباعة البيانات المستلمة للتصحيح
#                 print(f"عدد الطلبيات المستلمة: {len(new_orders)}")
#                 print("عينة من البيانات:", new_orders[:1])

#                 # حفظ البيانات الجديدة

#                 for order_data in new_orders:
#                     try:
#                         obj, created = SimpleOrder.objects.update_or_create(
#                             order_id=order_data['order_id'],
#                             defaults={
#                                 'customer_city': order_data.get('customer_city', ''),  # إضافة المدينة إذا كانت موجودة
#                                 'created_at': order_data.get('created_at'),  # استخدام الوقت الحالي إذا لم يكن موجودًا
#                                 'status': order_data['status'],  # تغيير من status إلى status
#                                 'tracking_number': order_data['tracking_number'],
#                                 'sku': order_data['sku'],
#                                 'customer_name': order_data['customer_name'],
#                                 'customer_phone': order_data['customer_phone'],
#                                 'product_name': order_data['product_name'],
#                             }

#                         )
#                         print("Status from API:", order_data['status'])  # للتأكد من القيمة الواردة

#                         if created:
#                             saved_count += 1

#                     except Exception as e:
#                         print(f"Error saving order {order_data['order_id']}: {str(e)}")

#                 request.session['last_order_update'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
#             return JsonResponse({
#                     'seccess': True,
#                     'saved_count': saved_count
#                 })

#             # return redirect('tracking')  # تم التعديل هنا من 'simple_orders' إلى 'tracking'






from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
import requests
from .models import ExternalTokenmodel, SimpleOrder

def get_simple_orders(request, sku):
    """
    جلب الطلبات المبسطة من COD API حسب SKU أو جميع المنتجات المرتبطة بالمستخدم.
    """
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

    skus_to_fetch = []

    if sku == 'all':
        # products = Products.objects.filter(admin=user)
        # accespro = UserProductPermission.objects.get(user=user)
        permissions = UserProductPermission.objects.filter(user=request.user)
        products = [perm.product for perm in permissions]







        skus_to_fetch = [product.sku for product in products if product.sku]

        # return products

    else:
        skus_to_fetch = [sku]

    simplified_orders = []

    for sku_code in skus_to_fetch:
        api_url = "https://api.cod.network/v1/seller/orders"
        headers = {
            'Authorization': f'Bearer {decrypted_tok}',
            'Content-Type': 'application/json'
        }
        params = {
            'sku': sku_code,
            'limit': 1000,
            'status': 'all'
        }

        try:
            response = requests.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            orders = data.get('data', [])
            for order in orders:
                simplified_orders.append({
                    'created_at': order.get('created_at'),
                    'customer_city': order.get('customer_city'),
                    'status': order.get('status'),
                    'order_id': order.get('id'),
                    'tracking_number': order.get('tracking_number'),
                    'sku': sku_code,
                    'customer_name': order.get('customer_name', ''),
                    'customer_phone': order.get('customer_phone', ''),
                    'product_name': order.get('product_name', ''),
                    'price' : order.get('products', [])[0].get('price', '') ,
                    'currency' : order.get('currency', '') ,
                })

        except requests.exceptions.RequestException as e:
            print(f"Error fetching orders for SKU {sku_code}: {str(e)}")
            continue

    return simplified_orders
def table_update(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'المستخدم غير مسجل الدخول'})

    sku = request.GET.get('sku')
    if not sku:
        return JsonResponse({'success': False, 'error': 'SKU غير صالح'})



    # صلاحيات الوصول للمنتج
    user = request.user
    owner_ids = [user.id]
    if user.team_admin:
        owner_ids.append(user.team_admin.id)

    try:
        if sku == 'all':

            product = Products.objects.filter(admin_id__in=owner_ids).first()
        else:
            product = Products.objects.filter(sku=sku, admin_id__in=owner_ids).first()


    except Products.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'المنتج غير موجود أو ليس لديك صلاحية الوصول إليه'})

    new_orders = get_simple_orders(request, sku)
    saved_count = 0

    if new_orders:
        for order_data in new_orders:
            try:
                obj, created = SimpleOrder.objects.update_or_create(
                    order_id=order_data['order_id'],
                    defaults={
                        'customer_city': order_data.get('customer_city', ''),
                        'created_at': order_data.get('created_at'),
                        'status': order_data['status'],
                        'tracking_number': order_data['tracking_number'],
                        'sku': order_data['sku'],
                        'customer_name': order_data['customer_name'],
                        'customer_phone': order_data['customer_phone'],
                        'customer_country' : order_data.get('customer_country.name', ''),  # إضافة البلد إذا كان موجودًا
                        'product_name': order_data['product_name'],
                        'product': product ,  # هذا الربط بالمنتج
                        'price': order_data['price'] ,
                        'currency': order_data['currency'] ,  # إضافة العملة إذا كانت موجودة
                    }
                )
                if created:
                    saved_count += 1
            except Exception as e:
                print(f"Error saving order {order_data['order_id']}: {str(e)}")

        request.session['last_order_update'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')

    return JsonResponse({
        'success': True,
        'saved_count': saved_count
    })





def update_product(request):
    if request.method == 'POST':
        user = request.user
        if not user.is_team_admin:
            user = user.team_admin

        gettoken = ExternalTokenmodel.objects.filter(user=user).first()
        decrypted_tok = decrypt_token(gettoken.access_token)

        api_url = "https://api.cod.network/v1/seller/products"
        headers = {
            'Authorization': f'Bearer {decrypted_tok}',
            'Content-Type': 'application/json'
        }

        products = []
        page = 1
        while True:
            params = {
                'limit': 100,  # حسب ما يسمح به الـ API
                'page': page,
                'status': 'all'
            }
            try:
                response = requests.get(api_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                current_products = data.get('data', [])
                products.extend(current_products)

                pagination = data.get('meta', {}).get('pagination', {})
                if pagination.get('current_page') >= pagination.get('total_pages'):
                    break  # لا مزيد من الصفحات
                page += 1
            except requests.exceptions.RequestException as e:
                print(f"Error fetching products: {str(e)}")
                return JsonResponse({'success': False, 'message': 'فشل الاتصال بواجهة API'}, status=500)

        for product in products:
            quantity = 0
            if product.get('stocks') and isinstance(product['stocks'], list):
                quantity = product['stocks'][0].get('quantity', 0)
                project = product['stocks'][0].get('project', '')


            Products.objects.update_or_create(
                sku=product.get('sku'),
                defaults={
                    'admin': request.user,
                    'project': project,
                    'name': product.get('name'),
                    'stock': quantity
                })

        return JsonResponse({'success': True, 'message': 'تم التحديث بنجاح'})


from django.utils.timezone import now
from datetime import datetime

login_required(login_url='/auth/login/')
def tracking(request,leades = None):
    if not request.user.is_authenticated:
        return redirect('/auth/login/')
    request.session['last_product_update'] = timezone.now().isoformat()
    last_product_update = request.session.get('last_product_update')
   
    customer_phone = request.GET.get('tracking')
    # orders = SimpleOrder.objects.all()

    if customer_phone:
        orders = orders.filter(customer_phone__icontains=customer_phone)
    # productslist = Products.objects.filter(admin=request.user)
    # إذا كان المستخدم مدير فريق، جلب جميع المنتجات المرتبطة به مباشرة

    # productslist = Products.objects.filter(user_permissions__user=request.user)
    if request.user.is_authenticated:
        print('f👀' , request.user , request.user)
        if request.user.is_team_admin:
            productslist = Products.objects.filter(admin=request.user)
        else:
            productslist = Products.objects.filter(user_permissions__user=request.user)
    else:
        productslist = Products.objects.none()
    orders = SimpleOrder.objects.filter(product__in=productslist)

    # للمستخدم admin
    if request.user.is_team_admin:
        productslist = Products.objects.filter(admin=request.user)
        # الترقيم الصفحي
    paginator = Paginator(orders.order_by('-created_at'), 10)
    page = request.GET.get('page')
    orders_page = paginator.get_page(page)




   # إضافة بحث بسيط (اختياري)
    search_query = request.GET.get('search', '')
    country_query = request.GET.get('country','')
    project_query = request.GET.get('project','')


    products = ""
    if request.user.is_team_admin:
        products = CODProduct.objects.filter(user = request.user)
    else:
        get_user = CustomUser.objects.filter(id = request.user.id).first()
        get_user_admin = get_user.team_admin if get_user else None
        if get_user_admin:
      
            products = CODProduct.objects.filter(user = get_user_admin) | CODProduct.objects.filter(id__in = UserProductPermission.objects.filter(user = request.user).values_list('product_id', flat=True))

    if products :
        
        
        if not last_product_update:
            last_product_upd= products.last().last_updated
            last_product_update = datetime.fromisoformat(last_product_upd)
      
        if country_query:
            products = products.filter(country__icontains=country_query)
        if project_query:
            products = products.filter(project__icontains=project_query)

        if search_query:
            products = products.filter(
                Q(name__icontains=search_query) |
                Q(cod_id__icontains=search_query)
            )
        try:

            countries = set(products.values_list('country', flat=True))
            projects = set(products.values_list('project', flat=True))
        except Exception as e:
            # if something goes wrong, fallback to empty lists
            print(f"Error fetching values: {e}")
            products = []
            countries = []
            projects = []
    else: 
        products = []
        countries = []
        projects = []

    # افترض أن الحقل اسمه project
    # orderslist = Order.objects.all()
     

    today = now()
    current_year = today.year
    current_month = today.month

    # فرضاً orderslist هي جميع الطلبات المرتبطة بالمستخدم
    orderslist = Order.objects.filter(
        order_date__year=current_year,
        order_date__month=current_month,
        user=request.user
    ).order_by('-order_date')
    # جلب طلبات الشهر الماضي في السنة الحالية
    last_month = current_month - 1 if current_month > 1 else 12
    last_month_year = current_year if current_month > 1 else current_year - 1

    orderslastmonth = Order.objects.filter(
        order_date__year=last_month_year,
        order_date__month=last_month,
        user=request.user
    )
    # جلب جميع حسابات الفريق المرتبطة بالأدمين (الحسابات التابعة لهذا الأدمين)
    if request.user.is_team_admin:
        team_users = CustomUser.objects.filter(team_admin=request.user)
    else:
        team_users = CustomUser.objects.filter(team_admin=request.user.team_admin)

    # جلب الطلبات الخاصة بجميع أعضاء الفريق (بما فيهم الأدمين نفسه)
    # team_account_order = Order.objects.filter(user__in=team_users)
    # print('user' ,  team_users , 'orders' ,team_account_order )
    from django.db.models import Count

    # if request.user.is_team_admin:
    #     team_users = CustomUser.objects.filter(team_admin=request.user)
    # else:
    #     team_users = CustomUser.objects.filter(team_admin=request.user.team_admin)

    # كل مستخدم مع عدد الطلبات الخاصة به
    team_users_with_order_counts = team_users.annotate(order_count=Count('orders'))



    # team_account_order = [
    #     {
    #         'user': CustomUser.objects.get(id=item['user']),
    #         'order_count': item['order_count']
    #     }
    #     for item in team_account_order
    # ]
    # print('the team' , team_account_order)

    team_account_perm = UserProductPermission.objects.select_related("user")
    from discount.models import UserPermissionSetting
    user_permusstion = UserPermissionSetting.objects.filter(user=request.user).first()

    user = request.user

    # حصر المنتجات المسموح بها لهذا المستخدم
    if getattr(user, 'is_team_admin', False):
        allowed_product_ids = list(Products.objects.filter(admin=user).values_list('id', flat=True))
    else:
        allowed_product_ids = list(
            UserProductPermission.objects.filter(user=user).values_list('product_id', flat=True)
        )

    if not allowed_product_ids:
        # إظهار صفحة فارغة مع رسالة أو إرجاع قائمة صفرية
        leads = Lead.objects.none()
    else:
        leads = Lead.objects.filter(product_id__in=allowed_product_ids).select_related('product').order_by('-created_at')
        # leads.history = sorted(leads.history, key=lambda c: c['date'])


    today = now().date()
    first_day_this_month = today.replace(day=1)
    first_day_last_month = (first_day_this_month - timedelta(days=1)).replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)

    # جميع المستخدمين مع إحصائيات الطلبات
    stats = []
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = team_users

    BONUS_THRESHOLD = 10  # مثال: 10 طلبيات في اليوم

    for user in users:
        total_orders = user.orders.count()
        this_month_orders = user.orders.filter(order_date__gte=first_day_this_month).count()
        last_month_orders = user.orders.filter(order_date__gte=first_day_last_month,
                                               order_date__lte=last_day_last_month).count()
        today_orders = user.orders.filter(order_date__date=today).count()

        bonus = today_orders >= BONUS_THRESHOLD
        percent = 0
        if today_orders and BONUS_THRESHOLD:
            percent = int((today_orders * 100) / BONUS_THRESHOLD)
        user.progress_percent = min(percent, 100)  # ما يتجاوز 100



        stats.append({ "progress_percent": user.progress_percent,
            "user": user,
            "total_orders": total_orders ,
            "this_month": this_month_orders,
            "last_month": last_month_orders,
            "today_orders": today_orders,
            "bonus": bonus,
            "orders": user.orders.filter(
    created_at__year=current_year,
    created_at__month=today.month
)

        })



    lead_paginator = Paginator(leads.order_by('-created_at'), 10)
    page = request.GET.get('page')
    leads_page = lead_paginator.get_page(page)
    for lead in leads_page:
            try:
                if isinstance(lead.lead_inputs, str):
                    lead.lead_inputs_json = json.dumps(eval(lead.lead_inputs))
                else:
                    lead.lead_inputs_json = json.dumps(lead.lead_inputs)
            except Exception:
                lead.lead_inputs_json = "[]"





    from .models import WhatsAppChannel
    if request.user.is_team_admin or user.is_superuser:
        user_channels = WhatsAppChannel.objects.filter(owner=request.user).annotate(
        unread_count=Count('messages', filter=Q(messages__is_read=False, messages__is_from_me=False))
    )
    else:
        user_channels = WhatsAppChannel.objects.filter(assigned_agents=request.user).annotate(
        unread_count=Count('messages', filter=Q(messages__is_read=False, messages__is_from_me=False))
    )

    # print('-----------------user channnels  id ' , user_channels)
    
    # 2. تحديد القناة النشطة (Default Channel)
    # الخيار أ: نتحقق هل هناك قناة محفوظة في الجلسة (Session) من زيارة سابقة؟
    last_active_id = request.session.get('active_channel_id')
    
    active_channel = None
    if last_active_id:
        active_channel = user_channels.filter(id=last_active_id).first()
    
    # الخيار ب: إذا لم نجد، نأخذ أول قناة متاحة
    if not active_channel:
        active_channel = user_channels.first()

    unread_msg = []
    if active_channel:
        unread_msg = active_channel.messages.filter(is_read=False).count()
        
         


    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string('leads.html', {'leads_page': leads_page ,  'user_permusstion':user_permusstion,
            'order_users' : team_users_with_order_counts ,
            'orderslastmonth':orderslastmonth ,
            'productslists': products,
            'search_query': search_query,
            'countries': countries,
            'projects': projects,
            'orderslist': orderslist,
            'leads_list' : leads,


            'validate_token'  :ExternalTokenmodel.objects.filter(user=user, token_status=True).first(),

            # 'get_comment':get_comment,
            'orders': orders_page,
            'productslist' : productslist ,
            'products':orders ,
            'tracking_number': customer_phone or '',
            'last_update': last_product_update ,
            'team_accounts': team_account_perm,
                   # new for channels 
            'user_channels': user_channels,
            'initial_channel_id': active_channel.id if active_channel else 'null' ,
            'unread_msg': unread_msg ,
            'active_channel': active_channel
            
            }, request=request)

     
            return JsonResponse({'html': html})


# 1. تحديد القائد والأعضاء (كما هو)
    if getattr(user, 'is_team_admin', False):         
            leader = user
    else:        
            leader = getattr(user, 'team_admin', None)     

    if leader:           
            team_members = CustomUser.objects.filter(
                Q(team_admin=leader) | Q(id=leader.id)
            ).filter(is_active=True).distinct()
    else:     
            team_members = CustomUser.objects.filter(id=user.id)

    
    from discount.models import Contact
    
    # user.is_team_admin = True
    # if getattr(user, 'is_team_admin', False) or user.is_superuser:
    #     print('user_channels', )
    #     user_channels = WhatsAppChannel.objects.filter(owner=user).distinct()
        
    # else:
    #     user_channels = WhatsAppChannel.objects.filter(assigned_agents=user).distinct()

    pipeline_choices = Contact.PipelineStage.choices
    from discount.models import CannedResponse
    channel = active_channel.id if active_channel else None
    # quick_replay = CannedResponse.objects.filter(user = request.user , channel = channel).order_by("created_at")

    return render(request, 'tracking.html', {
        'validate_token'  :ExternalTokenmodel.objects.filter(user=request.user, token_status=True).first(),
         "stats": stats, "bonus_threshold": BONUS_THRESHOLD ,
            'user_permusstion':user_permusstion,
            'order_users' : team_users_with_order_counts ,
            'orderslastmonth':orderslastmonth ,
            'productslists': products,
            'search_query': search_query,
            'countries': countries,
            'projects': projects,  
            'orderslist': orderslist,
            'leads_list' : leads,
            # 'get_comment':get_comment,
            'orders': orders_page,
            'productslist' : productslist ,
            'products':orders ,
            'tracking_number': customer_phone or '',
            'last_update': last_product_update ,
            'team_accounts': team_account_perm,
            'leads_page':leads_page , 

            # new for channels 
            'user_channels': user_channels,
            'initial_channel_id': active_channel.id if active_channel else 'null' ,
            
            'unread_msg': unread_msg,
            'active_channel': active_channel ,
            'team_members': team_members , 
            'pipeline_choices': pipeline_choices
        })

from django.core.paginator import PageNotAnInteger, EmptyPage
from discount.activites import activity_log
def getSearch(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        search_term = request.POST.get('search_term', '')
        status_filter = request.POST.get('status', 'all')
        # company_filter = request.POST.get('company', 'all')
        product_filter = request.POST.get('product', 'all')
        print(product_filter)
        period_filter = request.POST.get('period', 'month')
        start_date_str = request.POST.get('start_date', '')
        end_date_str = request.POST.get('end_date', '')
        filtered_orders = SimpleOrder.objects.all()

        # فلترة الطلبات حسب المنتج (SKU) إذا تم تحديده
        if product_filter and product_filter != 'all':
            filtered_orders = filtered_orders.filter(sku=product_filter)

        # فلترة الطلبات حسب صلاحيات المستخدم
        if request.user.is_staff_member and not request.user.is_team_admin:
            productslist = Products.objects.filter(user_permissions__user=request.user)
            if product_filter and product_filter != 'all':
                filtered_products = productslist.filter(sku=product_filter)
                filtered_orders = filtered_orders.filter(product__in=filtered_products)
            else:
                filtered_orders = filtered_orders.filter(product__in=productslist)
        else:
            adminprolist = Products.objects.filter(admin=request.user)
            if product_filter and product_filter != 'all':
                products = adminprolist.filter(sku=product_filter)
                filtered_orders = filtered_orders.filter(sku=product_filter)

                # filtered_orders = filtered_orders.filter(product__in=products)
            else:
                filtered_orders = filtered_orders.filter(product__in=adminprolist)


        # تجميع الفلاتر الحقيقية فقط
        filters_used = {}
        if search_term:
            filters_used['البحث'] = search_term
        if status_filter != 'all':
            filters_used['الحالة'] = status_filter
        if product_filter != 'all':
            filters_used['المنتج'] = product_filter
        if period_filter != 'all':
            filters_used['الفترة'] = period_filter
        if start_date_str:
            filters_used['من'] = start_date_str
        if end_date_str:
            filters_used['إلى'] = end_date_str
        related_product =''
        if product_filter and product_filter != 'all':
            related_product = filtered_orders.first()



        # تسجيل الحدث إن وُجدت فلاتر أو عملية بحث
        if filters_used:
            activity_log(
                request,
                activity_type='product_filter',
                description='تمت فلترة الطلبات بواسطة عدة معايير',
                related_object=related_product if product_filter != 'all' else None
            )

        if period_filter == 'today':
            today = timezone.localdate() # الحصول على تاريخ اليوم في المنطقة الزمنية المحلية
            filtered_orders = filtered_orders.filter(created_at__date=today)
        elif period_filter == 'week':
            today = timezone.localdate()
            start_of_week = today - timedelta(days=today.weekday()) # Monday as start of week
            end_of_week = start_of_week + timedelta(days=6) # نهاية الأسبوع (الأحد)
            filtered_orders = filtered_orders.filter(created_at__date__range=[start_of_week, end_of_week])
        elif period_filter == 'month':
            today = timezone.localdate()
            start_of_month = today.replace(day=1)
            # حساب نهاية الشهر
            if today.month == 12:
                end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            filtered_orders = filtered_orders.filter(created_at__date__range=[start_of_month, end_of_month])
        elif period_filter == 'custom':
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    filtered_orders = filtered_orders.filter(created_at__date__gte=start_date)
                except ValueError:
                    pass # تجاهل التاريخ غير الصالح أو يمكنك إرسال رسالة خطأ
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    # إذا كان created_at هو DateTimeField، استخدم __lte=end_date لتضمين اليوم كاملاً
                    # إذا كان DateField، فـ __lte=end_date صحيح
                    filtered_orders = filtered_orders.filter(created_at__date__lte=end_date)
                except ValueError:
                    pass # تجاهل التاريخ غير الصالح
        # *****************************************

        # استلام رقم الصفحة من طلب AJAX، القيمة الافتراضية 1
        page_number = request.POST.get('page', 1)


        if search_term:
            filtered_orders = filtered_orders.filter(
                Q(tracking_number__icontains=search_term) |
                Q(customer_name__icontains=search_term) |
                Q(customer_phone__icontains=search_term) |
                Q(sku__icontains=search_term)
            )

        if status_filter:
            if status_filter != '':
                filtered_orders = filtered_orders.filter(status=status_filter)


        # if product_filter:
        #     if product_filter != '':
        #          productslist = Products.objects.filter(user_permissions__user=request.user)
        #          filtered_orders=filtered_orders.filter(product__in=productslist)

                #  filtered_orders = Products.objects.filter(sku=product_filter , admin = request.user)

        # ****** إضافة Pagination هنا ******
        items_per_page = 10 # عدد العناصر في كل صفحة، يمكنك تعديله
        paginator = Paginator(filtered_orders, items_per_page)

        try:
            orders_page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            orders_page_obj = paginator.page(1)
        except EmptyPage:
            orders_page_obj = paginator.page(paginator.num_pages)
        # ***********************************

        # عدد الطلبات الكلي بعد الفلترة (وليس فقط عدد الطلبات في الصفحة الحالية)
        total_filtered_count = filtered_orders.count()
        search_successful = total_filtered_count > 0

        # توليد HTML لصفوف الجدول للصفحة الحالية فقط
        html_rows = render_to_string(
            'partials/_search_results.html',
            {'orders': orders_page_obj}, # نمرر فقط عناصر الصفحة الحالية
            request=request
        )

        # توليد HTML لعناصر Pagination
        # سنحتاج إلى قالب جديد لهذه العناصر
        pagination_html = render_to_string(
            'partials/_pagination_controls.html',
            {'orders': orders_page_obj, 'paginator': paginator}, # نمرر orders_page_obj و paginator
            request=request
        )

        # إرجاع الاستجابة كـ JSON مع HTML لصفوف الجدول والـ pagination
        return JsonResponse({
            'success': search_successful,
            'html': html_rows,
            'count': total_filtered_count, # هذا هو العدد الإجمالي للنتائج المفلترة
            'pagination_html': pagination_html # HTML لعناصر Pagination
        })

    return JsonResponse({'error': 'Invalid request'}, status=400)






def filter_orders(request):
    try:
        search_term = request.GET.get('search_term', '').strip()
        status = request.GET.get('status', '').strip().lower()
        date_range = request.GET.get('date_range', '').strip()
        # product =

        query = Q()

        if search_term:
            query &= (
                Q(customer_phone__icontains=search_term) |
                Q(customer_name__icontains=search_term) |
                Q(tracking_number__icontains=search_term)
            )

        if status:
            query &= Q(status__iexact=status)

        now = timezone.now()
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query &= Q(created_at__gte=start_date)
        elif date_range == 'week':
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            query &= Q(created_at__gte=start_date)
        elif date_range == 'month':
            query &= Q(created_at__month=now.month, created_at__year=now.year)
        elif date_range == 'year':
            query &= Q(created_at__year=now.year)

        orders = SimpleOrder.objects.filter(query).order_by('-created_at')

        return JsonResponse({
            'html': render_to_string('partials/_initial_orders.html', {'orders': orders}),
            'count': orders.count(),
            'status': 'success'
        })

    except Exception as e:
        logger.error(f"Filter error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)