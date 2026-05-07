from django.http import JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string

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


class PlanRequiredMiddleware:
    """
    Enforce plan activation:
    - For HTML pages: inject a non-dismissible paywall modal.
    - For API/AJAX requests: block with 403 JSON.
    """

    PREFIX_EXEMPT_PATHS = (
        "/auth/",
        "/admin/",
        "/static/",
        "/media/",
        "/discount/marketing/",
        "/discount/whatssapAPI/api/billing/",
        "/discount/whatssapAPI/api/dev/",
    )
    EXACT_EXEMPT_PATHS = (
        "/",
        "/privacy-policy/",
        "/terms/",
        "/data-deletion/",
        "/contact/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _resolve_billing_owner(user):
        # Team members inherit billing status from their team admin account.
        return getattr(user, "team_admin", None) or user

    def _is_exempt_path(self, path):
        if path in self.EXACT_EXEMPT_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in self.PREFIX_EXEMPT_PATHS)

    @staticmethod
    def _is_api_or_ajax(request):
        path = request.path or ""
        if "/api/" in path:
            return True
        return request.headers.get("X-Requested-With") == "XMLHttpRequest"

    @staticmethod
    def _render_modal(request):
        from discount.models import Plan

        defaults = {
            "starter": {"display_name": "Starter", "monthly_price": 19},
            "pro": {"display_name": "Pro", "monthly_price": 41},
            "elite": {"display_name": "Elite", "monthly_price": 99},
        }
        plan_feature_defaults = {
            "starter": [
                "AI Sales Agent",
                "AI Order Tracking",
                "Google Sheets Sync",
            ],
            "pro": [
                "Everything in Starter",
                "Smart Flow Builder",
                "Quick Replies & Templates",
            ],
            "elite": [
                "Everything in Pro",
                "Team Monitoring",
                "Profit Tracker (Beta)",
            ],
        }
        plans_by_slug = {}
        for plan in Plan.objects.all():
            slug = (plan.name or "").strip().lower()
            if slug in defaults:
                monthly = int(plan.price) if plan.price is not None else defaults[slug]["monthly_price"]
                yearly = max(1, round(monthly * 0.8))
                plans_by_slug[slug] = {
                    "slug": slug,
                    "display_name": defaults[slug]["display_name"],
                    "monthly_price": monthly,
                    "yearly_price": yearly,
                    "channels_text": (
                        "Unlimited WhatsApp channels"
                        if plan.max_channels is None
                        else f"{plan.max_channels} WhatsApp channel" + ("" if plan.max_channels == 1 else "s")
                    ),
                    "team_text": (
                        "Unlimited team members"
                        if plan.max_team_members is None
                        else f"{plan.max_team_members} team member" + ("" if plan.max_team_members == 1 else "s")
                    ),
                    "orders_text": (
                        "Unlimited orders / month"
                        if plan.max_monthly_orders is None
                        else f"{plan.max_monthly_orders} orders / month"
                    ),
                    "features": plan_feature_defaults[slug],
                }

        paywall_plans = []
        for slug in ("starter", "pro", "elite"):
            if slug in plans_by_slug:
                paywall_plans.append(plans_by_slug[slug])
                continue
            monthly = defaults[slug]["monthly_price"]
            paywall_plans.append(
                {
                    "slug": slug,
                    "display_name": defaults[slug]["display_name"],
                    "monthly_price": monthly,
                    "yearly_price": max(1, round(monthly * 0.8)),
                    "channels_text": "Limits by selected plan",
                    "team_text": "Limits by selected plan",
                    "orders_text": "Limits by selected plan",
                    "features": plan_feature_defaults[slug],
                }
            )

        return render_to_string(
            "partials/_paywall_modal.html",
            {"paywall_plans": paywall_plans},
            request=request,
        )

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        if user.is_superuser or user.is_staff or getattr(user, "is_bot", False):
            return self.get_response(request)

        if self._is_exempt_path(request.path):
            return self.get_response(request)

        if not getattr(user, "is_verified", False):
            return self.get_response(request)

        owner = self._resolve_billing_owner(user)
        # Fallback: if webhook delivery is delayed/missed, activate on Stripe success redirect.
        if (
            not getattr(owner, "plan_id", None)
            and request.GET.get("success") == "true"
            and request.GET.get("session_id")
        ):
            from discount.services.stripe_billing import assign_plan_from_success_session

            assign_plan_from_success_session(
                session_id=request.GET.get("session_id"),
                expected_user_id=owner.pk,
            )
            owner.refresh_from_db(fields=["plan"])

        if getattr(owner, "plan_id", None):
            return self.get_response(request)

        if self._is_api_or_ajax(request):
            return JsonResponse(
                {
                    "error": "no_active_plan",
                    "message": "Please activate a plan to continue.",
                },
                status=403,
            )

        response = self.get_response(request)
        content_type = (response.get("Content-Type") or "").lower()
        if "text/html" not in content_type:
            return response
        if getattr(response, "streaming", False):
            return response

        try:
            body = response.content.decode(getattr(response, "charset", "utf-8"))
        except Exception:
            return response

        if "id=\"plan-paywall-overlay\"" in body:
            return response

        modal_html = self._render_modal(request)
        if "</body>" in body:
            before, after = body.rsplit("</body>", 1)
            body = f"{before}{modal_html}</body>{after}"
        else:
            body = body + modal_html
        response.content = body.encode(getattr(response, "charset", "utf-8"))
        if response.has_header("Content-Length"):
            del response["Content-Length"]
        return response


class SuspensionRequiredMiddleware:
    """
    Risk management kill-switch:
    If a merchant (or team member) is suspended, block access to the app UI.
    - HTML requests: redirect to /account-suspended/
    - API/AJAX: return 403 JSON
    """

    PREFIX_EXEMPT_PATHS = (
        "/auth/",
        "/admin/",
        "/static/",
        "/media/",
        "/discount/marketing/",
        "/discount/whatssapAPI/api/billing/",
        "/discount/whatssapAPI/api/dev/",
        "/founder-hq/",
    )
    EXACT_EXEMPT_PATHS = (
        "/",
        "/privacy-policy/",
        "/terms/",
        "/data-deletion/",
        "/contact/",
        "/account-suspended/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _resolve_suspension_owner(user):
        # Team members inherit suspension from their team admin account.
        return getattr(user, "team_admin", None) or user

    def _is_exempt_path(self, path: str) -> bool:
        if not path:
            return False
        if path in self.EXACT_EXEMPT_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in self.PREFIX_EXEMPT_PATHS)

    @staticmethod
    def _is_api_or_ajax(request) -> bool:
        req_path = request.path or ""
        if "/api/" in req_path:
            return True
        return request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        # Founder / platform staff always allowed.
        if user.is_superuser or user.is_staff or getattr(user, "is_bot", False):
            return self.get_response(request)

        if self._is_exempt_path(request.path):
            return self.get_response(request)

        owner = self._resolve_suspension_owner(user)
        if not getattr(owner, "is_suspended", False):
            return self.get_response(request)

        reason = getattr(owner, "suspension_reason", None) or ""

        if self._is_api_or_ajax(request):
            return JsonResponse(
                {"error": "account_suspended", "message": reason or "This account is suspended."},
                status=403,
            )
        return redirect("/account-suspended/")