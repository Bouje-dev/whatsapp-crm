import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from discount.models import AdArchive, AdCreative
from django.utils.dateparse import parse_datetime

class Command(BaseCommand):
    help = "Fetch Ads from Meta Ad Library for a given country and store in DB"

    def add_arguments(self, parser):
        parser.add_argument('--country', type=str, required=True, help='Country code (ISO, e.g. US, MA)')
        parser.add_argument('--limit', type=int, default=50, help='Max number of ads to fetch (default 50)')

    def handle(self, *args, **options):
        country = options['country']
        limit = options['limit']
        token = getattr(settings, 'FACEBOOK_ACCESS_TOKEN', None)
        api_version = getattr(settings, 'FACEBOOK_API_VERSION', 'v16.0')
        if not token:
            self.stderr.write("Please set FACEBOOK_ACCESS_TOKEN in settings.")
            return

        base = f"https://graph.facebook.com/{api_version}/ads_archive"
        params = {
            'access_token': token,
            'ad_reached_countries': f'["{country}"]',  # مهم: يطلب غالبًا مصفوفة
            'fields': 'id,ad_snapshot_url,page_id,page_name,ad_delivery_start_time,ad_delivery_stop_time,ad_creative,spend,impressions',
            'limit': 25,  # حجم صفحة الاسترجاع من API؛ سنكرر حتى نصل للحَد
        }

        fetched = 0
        next_url = None
        backoff = 1

        while fetched < limit:
            try:
                if next_url:
                    resp = requests.get(next_url, timeout=30)
                else:
                    resp = requests.get(base, params=params, timeout=30)
                data = resp.json()
                if resp.status_code != 200:
                    self.stderr.write(f"Error from API: {data}")
                    # إذا كان خطأ مؤقت: تأخير وتكرار
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue
                backoff = 1

                ads = data.get('data', [])
                if not ads:
                    self.stdout.write("No more ads returned.")
                    break

                for ad in ads:
                    if fetched >= limit:
                        break
                    ad_id = ad.get('id')
                    # تجنب الازدواجية
                    if AdArchive.objects.filter(ad_id=ad_id).exists():
                        self.stdout.write(f"Ad {ad_id} exists. Skipping.")
                        fetched += 1
                        continue

                    creative_block = ad.get('ad_creative') or {}
                    creative_id = creative_block.get('id') or creative_block.get('creative_id') or None
                    creative_obj = None
                    if creative_id:
                        creative_obj, created = AdCreative.objects.get_or_create(
                            creative_id=creative_id,
                            defaults={'body': creative_block.get('body')}
                        )
                        # محاولة الحصول على video_id إذا كان غير مخزن
                        if not creative_obj.video_id:
                            # محاولة استدعاء endpoint للـ creative للحصول على video_id
                            try:
                                token_for_call = token
                                creative_url = f"https://graph.facebook.com/{api_version}/{creative_id}"
                                cr_params = {'access_token': token_for_call, 'fields': 'video_id,body,image_hash'}
                                cr_resp = requests.get(creative_url, params=cr_params, timeout=20)
                                cr_json = cr_resp.json()
                                vid = cr_json.get('video_id')
                                if vid:
                                    creative_obj.video_id = vid
                                    # محاولة لاسترجاع رابط الفيديو المصدر
                                    try:
                                        video_url_resp = requests.get(
                                            f"https://graph.facebook.com/{api_version}/{vid}",
                                            params={'access_token': token_for_call, 'fields': 'source'},
                                            timeout=20
                                        ).json()
                                        video_source = video_url_resp.get('source')
                                        if video_source:
                                            creative_obj.video_url = video_source
                                    except Exception as e:
                                        self.stdout.write(f"Could not fetch video source for {vid}: {e}")
                                creative_obj.save()
                            except Exception as e:
                                self.stdout.write(f"Creative details fetch failed for {creative_id}: {e}")

                    # حفظ AdArchive
                    ad_record = AdArchive.objects.create(
                        ad_id=ad_id,
                        page_id=ad.get('page_id'),
                        page_name=ad.get('page_name'),
                        ad_snapshot_url=ad.get('ad_snapshot_url'),
                        ad_delivery_start_time=parse_datetime(ad.get('ad_delivery_start_time')) if ad.get('ad_delivery_start_time') else None,
                        ad_delivery_stop_time=parse_datetime(ad.get('ad_delivery_stop_time')) if ad.get('ad_delivery_stop_time') else None,
                        creative=creative_obj,
                        raw_json=ad
                    )
                    self.stdout.write(f"Saved ad {ad_record.ad_id}")
                    fetched += 1

                # متابعة الصفحة التالية
                paging = data.get('paging', {})
                next_url = paging.get('next')
                if not next_url:
                    break
            except Exception as e:
                self.stderr.write(f"Exception during fetch loop: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

        self.stdout.write(f"Finished. Total fetched: {fetched}")
