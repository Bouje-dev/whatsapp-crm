from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from discount.models import UserSavedAd
from django.http import JsonResponse


def adspy_dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, 'adspy/adspy_dashboard.html')


from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from discount.models import AdArchive
from .serializers import AdArchiveSerializer
from .filters import AdArchiveFilter
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 200

@method_decorator(cache_page(10), name='dispatch')  # cache list for 10 seconds as simple optimization
class AdArchiveViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AdArchive.objects.select_related('advertiser', 'country', 'creative').prefetch_related('ctas', 'tags').all()
    serializer_class = AdArchiveSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AdArchiveFilter
    ordering_fields = ['ad_delivery_start_time', 'spend', 'impressions']
    ordering = ['-ad_delivery_start_time']

    # example extra endpoint to return CTA list for UI
    @action(detail=False, methods=['get'])
    def ctas(self, request):
        from discount.models import CTA
        items = CTA.objects.order_by('name').values('name')
        return Response(list(items))





def collection_view(request: HttpRequest) -> HttpResponse:

    collection = UserSavedAd.objects.filter(user=request.user)
    collection_data = []
    for item in collection:
        for ad in AdArchive.objects.filter(ad_id=item.ad_id):
            collection_data.append({
            'advertiser': ad.advertiser.name if ad.advertiser else (ad.page_name or ''),
            'page_name': ad.page_name,
            'thumbnail': ad.creative.thumbnail_url if ad.creative and ad.creative.thumbnail_url else (f"/media/creatives/{ad.creative.image_hash}.jpg" if ad.creative and ad.creative.image_hash else None),
            'is_video': (ad.creative.is_video if ad.creative else False) or bool(ad.creative.video_url if ad.creative else None),
            'adsets_count': ad.adsets_count,
            'impressions': ad.impressions,
            'spend': ad.spend,
            'ctas': [cta.name for cta in ad.ctas.all()],
            'country': {'code': ad.country.code, 'name': ad.country.name} if ad.country else None,
            'published': ad.ad_delivery_start_time.strftime('%Y-%m-%d') if ad.ad_delivery_start_time else None,
            'platform': ad.platform,
            'status': ad.status,
            'ad_snapshot_url': ad.ad_snapshot_url,
            'primaryText': ad.creative.body if ad.creative else 'not text ',
            'id' : ad.ad_id ,

            #  collectis
            'ad_id': item.ad_id,
            'saved_at': item.saved_at,
            'note': item.note,
        })
     
    return JsonResponse({'collection': collection_data})
    


import json
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt  # فقط لو حابب تجرب بسرعة (لكن يفضل تخليه محمي بالـ CSRF لاحقًا)
def save_ad(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'success': False, 'status': 'invalid_json'})

        ad_id = data.get('ad_id')
        note = data.get('note', '')

        if ad_id:
            obj, created = UserSavedAd.objects.get_or_create(
                user=request.user, ad_id=ad_id,
                defaults={'note': note}
            )
            return JsonResponse({'success': True, 'status': 'saved', 'created': created})

    return JsonResponse({'success': False, 'status': 'error'})


def unsave_ad (request):
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'success': False, 'status': 'invalid_json'})

        ad_id = data.get('ad_id').strip()

        if ad_id:
            deleted, _ = UserSavedAd.objects.filter(user=request.user, ad_id=ad_id).delete()
            if deleted:
                return JsonResponse({'success': True, 'status': 'unsaved'})
            else:
                return JsonResponse({'success': False, 'status': 'not_found'})

    return JsonResponse({'success': False, 'status': 'error'})