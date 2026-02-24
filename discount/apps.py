from django.apps import AppConfig


class DiscountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'discount'

    def ready(self):
        # هذه الخطوة مهمة للتكامل مع لوحة الإدارة
        from django.contrib.auth.models import User
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        # تحديث العلاقة في LogEntry
        ContentType.objects.clear_cache()
        User = self.get_model('CustomUser')
        LogEntry.user.field.remote_field.model = User

        # Connect signals (post_save SimpleOrder -> sync to Google Sheets)
        import discount.signals  # noqa: F401