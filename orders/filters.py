"""
Filter orders by status, date range, phone search, source (platform).
"""
import django_filters
from .models import Order

# Common platforms for filter dropdown (value sent to backend)
SOURCE_PLATFORM_CHOICES = [
    ("", "All sources"),
    ("facebook", "Facebook"),
    ("fb", "FB"),
    ("meta", "Meta"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("google", "Google"),
]


class OrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Order.STATUS_CHOICES)
    source = django_filters.ChoiceFilter(
        field_name="attribution_data__utm_source",
        lookup_expr="iexact",
        choices=SOURCE_PLATFORM_CHOICES,
    )
    phone = django_filters.CharFilter(lookup_expr="icontains")
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_before = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Order
        fields = ["status", "source", "phone", "date_after", "date_before"]
