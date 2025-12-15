from django.shortcuts import redirect
from django.urls import reverse

class AccountActivationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. قائمة الصفحات المسموح بزيارتها حتى لو الحساب غير مفعل
        # (مثل صفحة تسجيل الخروج، وصفحة إعادة إرسال الكود، وصفحة التفعيل نفسها)
        # يجب أن تضع هنا روابط الـ URLs الخاصة بك بدقة
        exempt_urls = [
            '/auth/logout/',
            '/auth/verify-email/',   # الصفحة التي يضع فيها الكود
            '/auth/resend-code/',    # رابط إعادة الإرسال
            '/admin/',               # لوحة الأدمن (اختياري)
            '/static/',  
            '/auth/login/',
            'discount/whatssapAPI/auth/singup/' ,
            '/discount/marketing/verify_code/',
            '/discount/marketing/resend_activation/',
            '/discount/marketing/activate/<int:user_id>/' ,
            '/auth/singup/'
                 
        ]
              
        path = request.path
        if '/activate/' in path:
            return self.get_response(request)


        # 2. التحقق من المستخدم
        if request.user.is_authenticated:
            # افترضت هنا أن لديك حقلاً اسمه is_email_verified
            # إذا كنت تستخدم حقلاً آخر، غير الاسم هنا
            if not request.user.is_verified: 
                
                # تأكد أن المستخدم ليس في صفحة مسموحة أصلاً (لتجنب الدوران اللانهائي)
                current_path = request.path
                if not any(current_path.startswith(url) for url in exempt_urls):
                    # توجيه إجباري لصفحة التفعيل
                    return redirect('/auth/singup/') 

        response = self.get_response(request)
        return response