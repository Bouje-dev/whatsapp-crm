import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime
from .models import Lead , ExternalTokenmodel,Products
from .crypto import decrypt_token
    
 
import requests
from django.utils.dateparse import parse_datetime
from django.utils import timezone

# def fetch_leads_for_skus(request, sku_list):
#     user = request.user
#     # إذا المستخدم ليس team admin نستخدم team_admin (إن وُجد)
#     if not getattr(user, 'is_team_admin', False):
#         user = getattr(user, 'team_admin', user)

#     token_obj = ExternalTokenmodel.objects.filter(user=user).first()
#     if not token_obj:
#         print("لم يتم العثور على رمز وصول للمستخدم.")
#         return []

#     decrtoken = decrypt_token(token_obj.access_token)

#     API_URL = "https://api.cod.network/v1/seller/leads"
#     HEADERS = {"Authorization": f"Bearer {decrtoken}"}

#     # تأكد من أن sku_list قائمة
#     if isinstance(sku_list, str):
#         sku_list = [s.strip() for s in sku_list.split(',') if s.strip()]
#     else:
#         try:
#             sku_list = list(sku_list)
#         except Exception:
#             sku_list = [str(sku_list)]

#     leads_objs = []
#     page = 1
#     per_page = 10
#     # limit = 20

#     while True:
#         # بناء params بحيث يتكرر key "sku" لكل قيمة (requests يدعم list of tuples)
#         params = [("sku", sku) for sku in sku_list]
#         params += [("limit", per_page), ("page", page)]

#         try:
#             resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=30)
#         except Exception as e:
#             print("Request error:", e)
#             break

#         if resp.status_code != 200:
#             print("API returned status", resp.status_code, resp.text)
#             break

#         page_data = resp.json().get("data", [])
#         if not page_data:
#             break

#         for lead in page_data:
#             # محاولة إيجاد الـ product بواسطة sku داخل الـ lead أو داخل items
#             product_obj = None
#             sku_candidate = lead.get('sku') or lead.get('product_sku')
#             if not sku_candidate:
#                 items = lead.get('items')
#                 if isinstance(items, dict):
#                     sku_candidate = items.get('sku') or items.get('product_sku')
#                 elif isinstance(items, list) and len(items) > 0 and isinstance(items[0], dict):
#                     sku_candidate = items[0].get('sku') or items[0].get('product_sku')

#             if sku_candidate:
#                 product_obj = Products.objects.filter(sku=str(sku_candidate)).first()

#             # تحويل created_at إلى aware datetime إن أمكن
#             created_at_val = None
#             raw_dt = lead.get('created_at')
#             if raw_dt:
#                 parsed = parse_datetime(raw_dt)
#                 if parsed:
#                     if timezone.is_naive(parsed):
#                         parsed = timezone.make_aware(parsed, timezone=timezone.utc)
#                     created_at_val = parsed

#             defaults = {
#                 # "message" : lead.get['[{"id": 25682404, "status": "cancelled", "comment": "تم الغاء الطلبيه العميل لم يعد يريد المنتج", "created_at": 1699266115}, {"id": 25670926, "status": "no reply", "comment": "NO REPLY", "created_at": 1699262608}, {"id": 25555532, "status": "call later scheduled", "comment": "call later Call at:2023-11-06 10:22", "created_at": 1699176187}]']
#                 "phone": lead.get("phone"),
#                 "status": lead.get("status"),
#                 "lead_inputs": lead.get("lead_inputs", {}) or {},
#                 "history": lead.get("history", []) or [],
#                 "items": lead.get("items", {}) or {},
#                 "product": product_obj,
#                 "calls": lead.get("calls", []) or [],
#             }
#             if created_at_val:
#                 defaults["created_at"] = created_at_val

#             obj, created = Lead.objects.update_or_create(
#                 id=lead["id"],
#                 defaults=defaults,
#             )
#             leads_objs.append(obj)

#         page += 1

#     return leads_objs


import requests
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse

# استورد النماذج والوظائف المساعدة المطلوبة من مشروعك
from discount.models import ExternalTokenmodel, Products, Lead, UserProductPermission
from discount.crypto import decrypt_token  # عدّل المسار حسب مشروعك


def fetch_leads_for_skus(request, sku_list):
    """
    تجلب الـ leads من الـ API الخارجي لقائمة SKUs الموجودة في sku_list.
    تتحقق من وجود رمز الوصول للمستخدم أو للـ team admin، وتمنع تكرار معالجة نفس الـ lead
    عبر حفظ معرفات الـ leads التي تمت معالجتها في مجموعة.
    تعيد قائمة كائنات Lead (المخزنة/المحدّثة).
    """

    user = request.user
    # إذا المستخدم ليس team admin نستخدم team_admin (إن وُجد)
    if not getattr(user, 'is_team_admin', False):
        user = getattr(user, 'team_admin', user)

    token_obj = ExternalTokenmodel.objects.filter(user=user).first()
    if not token_obj or not getattr(token_obj, 'access_token', None):
        print("لم يتم العثور على رمز وصول للمستخدم.")
        return []

    try:
        decrtoken = decrypt_token(token_obj.access_token)
    except Exception as e:
        print("خطأ أثناء فك تشفير التوكن:", e)
        return []

    API_URL = "https://api.cod.network/v1/seller/leads"
    HEADERS = {"Authorization": f"Bearer {decrtoken}"}

    # تأكد من أن sku_list قائمة
    if isinstance(sku_list, str):
        sku_list = [s.strip() for s in sku_list.split(',') if s.strip()]
    else:
        try:
            sku_list = list(sku_list)
        except Exception:
            sku_list = [str(sku_list)]

    if not sku_list:
        return []

    leads_objs = []
    seen_lead_ids = set()  # لمنع تكرار إدخال نفس الـ lead أكثر من مرة

    page = 1
    per_page = 50  # زيّد العدد لكل صفحة لتحسين الأداء إن سمح الـ API

    while True:
        # بناء params بحيث يتكرر key "sku" لكل قيمة (requests يدعم list of tuples)
        params = [("sku", sku) for sku in sku_list]
        params += [("limit", per_page), ("page", page)]

        try:
            resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=30)
        except requests.RequestException as e:
            print("Request error:", e)
            break

        if resp.status_code != 200:
            print("API returned status", resp.status_code, resp.text)
            break
  

        try:
            resp_json = resp.json()
        except ValueError as e:
            print("Invalid JSON response:", e)
            break

        page_data = resp_json.get("data", [])
        if not page_data:
            break

        for lead in page_data:
            try:
                lead_id = lead.get("id")
            except Exception:
                lead_id = None

            if not lead_id:
                # إذا لم يوجد معرف صريح نتجنّب إدخالها لأننا لا نستطيع تحديثها لاحقًا بثبات
                print("Lead without id, skipping:", lead)
                continue

            if lead_id in seen_lead_ids:
                # تمّت معالجته سابقًا من هذه الاستدعاء
                continue

            seen_lead_ids.add(lead_id)

            # محاولة إيجاد الـ product بواسطة sku داخل الـ lead أو داخل items
            product_obj = None
            sku_candidate = lead.get('sku') or lead.get('product_sku')
            if not sku_candidate:
                items = lead.get('items')
                if isinstance(items, dict):
                    sku_candidate = items.get('sku') or items.get('product_sku')
                elif isinstance(items, list) and len(items) > 0 and isinstance(items[0], dict):
                    sku_candidate = items[0].get('sku') or items[0].get('product_sku')

            if sku_candidate:
                try:
                    # استخدم مقارنة غير حساسة لحالة الأحرف إن رغبت
                    product_obj = Products.objects.filter(sku=str(sku_candidate)).first()
                except Exception as e:
                    print("DB error while querying product by SKU:", e)
                    product_obj = None

            # تحويل created_at إلى aware datetime إن أمكن
            created_at_val = None
            raw_dt = lead.get('created_at')
            if raw_dt:
                # API قد يعيد timestamp integer أو سلسلة ISO
                parsed = None
                try:
                    if isinstance(raw_dt, (int, float)):
                        parsed = timezone.datetime.fromtimestamp(int(raw_dt), tz=timezone.utc)
                    else:
                        parsed = parse_datetime(str(raw_dt))
                        if parsed and timezone.is_naive(parsed):
                            parsed = timezone.make_aware(parsed, timezone=timezone.utc)
                except Exception:
                    parsed = None

                if parsed:
                    created_at_val = parsed

            defaults = {
                "phone": lead.get("phone"),
                "status": lead.get("status"),
                "lead_inputs": lead.get("lead_inputs", {}) or {},
                "history": lead.get("history", []) or [],
                "items": lead.get("items", {}) or {},
                "product": product_obj,
                "calls": lead.get("calls", []) or [],
            }
            if created_at_val:
                defaults["created_at"] = created_at_val

            try:
                obj, created = Lead.objects.update_or_create(
                    id=lead_id,
                    defaults=defaults,
                )
                leads_objs.append(obj)
            except Exception as e:
                print(f"DB error while update_or_create lead {lead_id}:", e)
                # لا نكسر الحلقة بسبب خطأ في سجل واحد
                continue

        page += 1

    # نعيد قائمة الكائنات المحفوظة (قد تكون فارغة)
    return leads_objs

 