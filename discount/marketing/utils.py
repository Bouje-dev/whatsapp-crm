# your_app/utils.py
"""
دوال مساعدة: تنظيف أرقام الهاتف، مطابقة أقرب زيارة، و helpers صغيرة.
"""

import phonenumbers
from phonenumbers import NumberParseException
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

# الافتراضي: سنعالج 4 دول تعمل بها: KW, SA, AE, QA
DEFAULT_REGIONS = ['KW','SA','AE','QA']

# your_app/utils.py
import phonenumbers

def normalize_phone(raw_phone, default_region='SA'):
    """
    Try to parse and return E.164 normalized phone (e.g. +9665xxxxxxxx).
    Returns None if can't parse.
    default_region: ISO country code to try (e.g. 'SA' for Saudi).
    """
    if not raw_phone:
        return None
    s = str(raw_phone).strip()
    # remove common noise
    if s == '':
        return None
    try:
        # try parse as international first
        num = phonenumbers.parse(s, None)
    except Exception:
        try:
            # fallback to default region
            num = phonenumbers.parse(s, default_region)
        except Exception:
            return None
    if not phonenumbers.is_possible_number(num):
        return None
    if not phonenumbers.is_valid_number(num):
        # still return E164 for possible number? safer to return None
        # return None
        pass
    try:
        return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164).replace('+', '')
        # we remove + to store without plus or store with + if you prefer:
        # return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None

def find_best_visit_for_phone(phone_norm, order_created_at, visit_qs):
    """
    اختيار أفضل CampaignVisit مطابق بواسطة:
    - نفس phone_normalized
    - البحث في نافذة زمنية حول وقت الطلب (افتراضي 48 ساعة قبل - 24 ساعة بعد)
    - إرجاع أول/أقرب إدخال أو None
    """
    # هذه الدالة تفترض أن visit_qs تم فلترته بالرقم مسبقًا
    window_start = order_created_at - timezone.timedelta(hours=48)
    window_end = order_created_at + timezone.timedelta(hours=24)
    visits = visit_qs.filter(created_at__range=(window_start, window_end)).order_by('created_at')
    if visits.exists():
        return visits.first()
    return None
