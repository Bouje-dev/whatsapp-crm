# yourapp/management/commands/populate_ads.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker
import random
from datetime import timedelta, datetime

from discount.models import (
    Advertiser, CTA, Country, Tag,
    AdCreative, AdArchive, MetricSnapshot
)

fake = Faker()


class Command(BaseCommand):
    help = "Populate DB with fake ads data for testing. Usage: python manage.py populate_ads --count 100 --start 2025-01-01 --end 2025-09-30"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=50, help='Number of ads to create')
        parser.add_argument('--start', type=str, default=None, help='Start date (YYYY-MM-DD) for published date range')
        parser.add_argument('--end', type=str, default=None, help='End date (YYYY-MM-DD) for published date range')

    @transaction.atomic
    def handle(self, *args, **options):
        count = options['count']
        start = options.get('start')
        end = options.get('end')

        if start:
            start_date = datetime.strptime(start, '%Y-%m-%d').date()
        else:
            start_date = (timezone.now() - timedelta(days=365)).date()

        if end:
            end_date = datetime.strptime(end, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()

        # 1) ensure master lists exist
        country_data = [
            ('US', 'United States'), ('EU', 'Europe'), ('MA', 'Morocco'),
            ('GB', 'United Kingdom'), ('CA', 'Canada'), ('AU', 'Australia')
        ]
        for code, name in country_data:
            Country.objects.get_or_create(code=code, defaults={'name': name})

        cta_names = [
            'Buy Now', 'Shop Now', 'Learn More', 'Message Page', 'Sign Up',
            'Get Offer', 'Download', 'Apply Now', 'Subscribe', 'WhatsApp Message',
            'Get Quote', 'Event RSVP', 'Donate Now', 'Play Game', 'Contact Us'
        ]
        for name in cta_names:
            CTA.objects.get_or_create(name=name)

        tag_names = ['summer','weekly','scale','promo','test']
        for t in tag_names:
            Tag.objects.get_or_create(name=t)

        platforms = ['facebook', 'instagram', 'tiktok']

        advertisers = []
        # create some advertisers
        for i in range(max(6, int(count/8))):
            page_id = fake.uuid4()[:12]
            name = fake.company()[:40]
            domain = fake.domain_name()
            page_name = fake.company_suffix()
            page_url = f'https://{domain}'
            # page_name
            adv, _ = Advertiser.objects.get_or_create(
                page_id=page_id,
                defaults={'name': name ,'page_name' : page_name, 'domain': domain, 'page_url': page_url}
            )
            advertisers.append(adv)

        # helper to random date between start_date and end_date
        def random_date():
            delta = (end_date - start_date).days
            if delta <= 0:
                return start_date
            d = start_date + timedelta(days=random.randint(0, delta))
            # set time portion too
            return datetime.combine(d, datetime.min.time()) + timedelta(hours=random.randint(0,23), minutes=random.randint(0,59))

        created_ads = []
        # create creatives and ads
        for i in range(count):
            creative_id = fake.uuid4()
            is_video = random.random() < 0.4  # 40% videos
            # use picsum to get deterministic placeholder images
            seed = creative_id[:8]
            thumbnail_url = f'https://picsum.photos/seed/{seed}/800/520'
            video_url = f'https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4' if is_video else None

            creative = AdCreative.objects.create(
                creative_id=creative_id,
                body=fake.sentence(nb_words=12),
                thumbnail_url=thumbnail_url,
                image_hash=f"{seed}",
                video_id=(fake.uuid4()[:10] if is_video else None),
                video_url=video_url,
                is_video=is_video,
                duration_seconds=(random.randint(10,120) if is_video else None)
            )

            advertiser = random.choice(advertisers)
            country = Country.objects.order_by('?').first()
            platform = random.choice(platforms)
            status = random.choice(['active', 'stopped'])
            adsets_count = random.randint(1, 150)
            impressions = random.randint(0, 500000)
            spend = round(random.uniform(0, 5000), 2)
            clicks = random.randint(0, max(1, impressions//100))
            published_dt = random_date()

            ad_id = fake.uuid4()[:12]
            ad_snapshot_url = f'https://{fake.domain_name()}/ad/{ad_id}'

            ad = AdArchive.objects.create(
                ad_id=ad_id,
                advertiser=advertiser,
                # page_name= advertiser.page_name or advertiser.name, 
                ad_snapshot_url=ad_snapshot_url,
                landing_url=f'https://{fake.domain_name()}/lp/{ad_id}',
                platform=platform,
                country=country,
                status=status,
                ad_delivery_start_time=published_dt,
                ad_delivery_stop_time=(published_dt + timedelta(days=random.randint(1,30))),
                adsets_count=adsets_count,
                impressions=impressions,
                spend=spend,
                clicks=clicks,
                ctr=(round((clicks / impressions * 100), 2) if impressions else None),
                cpc=(round(spend / clicks, 4) if clicks else None),
                conversions=random.randint(0, 200),
                cpa=(round(spend / random.randint(1, max(1, clicks)), 2) if spend else None),
                creative=creative,
                raw_json={'_mock': True, 'generated_at': str(timezone.now()), 'sample': True}
            )

            # assign CTAs and tags
            # pick 0-2 random CTAs
            ctas = list(CTA.objects.order_by('?')[:random.randint(0,2)])
            if ctas:
                ad.ctas.set(ctas)
            tags = list(Tag.objects.order_by('?')[:random.randint(0,2)])
            if tags:
                ad.tags.set(tags)

            # optional: create some daily snapshots for the last N days since publish
            days_to_snap = random.randint(0, 5)
            for s in range(days_to_snap):
                snap_date = (published_dt.date() + timedelta(days=s))
                MetricSnapshot.objects.get_or_create(
                    ad=ad,
                    snapshot_date=snap_date,
                    defaults={
                        'impressions': random.randint(0, impressions),
                        'spend': round(random.uniform(0, spend), 2),
                        'clicks': random.randint(0, clicks),
                        'conversions': random.randint(0, 10)
                    }
                )

            created_ads.append(ad)

            if (i+1) % 50 == 0:
                self.stdout.write(self.style.SUCCESS(f'Created {i+1} ads...'))

        self.stdout.write(self.style.SUCCESS(f'Done: created {len(created_ads)} ads.'))
#  generate_test_data.py