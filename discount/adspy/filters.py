import django_filters
from discount.models import AdArchive, CTA
from django.db import models

class AdArchiveFilter(django_filters.FilterSet):
    platform = django_filters.CharFilter(field_name='platform', lookup_expr='iexact')
    status = django_filters.CharFilter(field_name='status', lookup_expr='iexact')
    is_video = django_filters.BooleanFilter(method='filter_is_video')
    cta = django_filters.CharFilter(method='filter_cta')  # can accept comma separated list
    country = django_filters.CharFilter(field_name='country__code', lookup_expr='iexact')
    date_from = django_filters.DateFilter(field_name='ad_delivery_start_time', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='ad_delivery_start_time', lookup_expr='lte')
    search = django_filters.CharFilter(method='filter_search')
    
    class Meta:
        model = AdArchive
        fields = []

    def filter_cta(self, queryset, name, value):
        vals = [v.strip() for v in value.split(',') if v.strip()]
        if not vals:
            return queryset
        return queryset.filter(ctas__name__in=vals).distinct()

    def filter_is_video(self, queryset, name, value):
        if value:
            return queryset.filter(creative__is_video=True)
        return queryset.filter(models.Q(creative__is_video=False) | models.Q(creative__is_video__isnull=True))

    def filter_search(self, queryset, name, value):
        v = value.strip()
        if not v:
            return queryset
        return queryset.filter(
            models.Q(page_name__icontains=v) |
            models.Q(advertiser__name__icontains=v) |
            models.Q(creative__body__icontains=v) |
            models.Q(ad_snapshot_url__icontains=v)
        )
