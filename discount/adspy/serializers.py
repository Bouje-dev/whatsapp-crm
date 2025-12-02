from rest_framework import serializers
from discount.models import AdArchive

class AdArchiveSerializer(serializers.ModelSerializer):
    advertiser = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    is_video = serializers.SerializerMethodField()
    ctas = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    published = serializers.DateTimeField(source='ad_delivery_start_time', format='%Y-%m-%d', allow_null=True)
    # ad_snapshot_url = serializers.CharField(source='ad_snapshot_url')

    class Meta:
        model = AdArchive
        fields = [
            'ad_id',
            'advertiser',
            'page_name',
            'thumbnail',
            'is_video',
            'adsets_count',
            'impressions',
            'spend',
            'ctas',
            'country',
            'published',
            'platform',
            'status',
            'ad_snapshot_url',
        ]

    def get_advertiser(self, obj):
        if obj.advertiser:
            return {'page_id': obj.advertiser.page_id, 'name': obj.advertiser.name}
        return {'page_id': None, 'name': obj.page_name or ''}

    def get_thumbnail(self, obj):
        if obj.creative and getattr(obj.creative, 'thumbnail_url', None):
            return obj.creative.thumbnail_url
        # fallback: build from image_hash if you store path pattern
        if obj.creative and getattr(obj.creative, 'image_hash', None):
            return f"/media/creatives/{obj.creative.image_hash}.jpg"
        return None

    def get_is_video(self, obj):
        if obj.creative:
            return getattr(obj.creative, 'is_video', False) or bool(getattr(obj.creative, 'video_url', None))
        return False

    def get_ctas(self, obj):
        return [cta.name for cta in obj.ctas.all()]
    
    def get_country(self, obj):
        if obj.country:
            return {'code': obj.country.code, 'name': obj.country.name}
        return None
