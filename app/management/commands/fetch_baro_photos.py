"""
Ankara Barosu websitesinden avukat fotoğraflarını indirir ve
media/baro_photos/ klasörüne kaydeder; BaroLawyer.photo_url alanını
/media/baro_photos/{sicil_no}.jpg olarak günceller.

Kullanım:
    python manage.py fetch_baro_photos --session-cookie "session=.eJw..."
    python manage.py fetch_baro_photos --session-cookie "session=.eJw..." --force
    python manage.py fetch_baro_photos --session-cookie "session=.eJw..." --limit 100
"""
import re
import time
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.models import BaroLawyer

BARO_DATA_URL = 'https://www.ankarabarosu.org.tr/data-source/'
BARO_BASE_URL = 'https://www.ankarabarosu.org.tr'
IMG_SRC_RE = re.compile(r"src=['\"]([^'\"]+\.jpg)['\"]", re.IGNORECASE)
SICIL_RE = re.compile(r"<h4[^>]*>\s*(\d+)\s*</h4>", re.IGNORECASE)


def _build_api_headers(session_cookie: str) -> dict:
    return {
        'cookie': session_cookie,
        'x-requested-with': 'XMLHttpRequest',
        'referer': 'https://www.ankarabarosu.org.tr/avukatlar/',
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/146.0.0.0 Safari/537.36'
        ),
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'tr,en;q=0.9',
    }


def _build_image_headers(session_cookie: str) -> dict:
    return {
        'cookie': session_cookie,
        'referer': 'https://www.ankarabarosu.org.tr/avukatlar/',
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/146.0.0.0 Safari/537.36'
        ),
        'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'accept-language': 'tr,en;q=0.9',
        'sec-fetch-dest': 'image',
        'sec-fetch-mode': 'no-cors',
        'sec-fetch-site': 'same-origin',
    }


def _fetch_page(session_cookie: str, start: int, length: int, requests) -> dict:
    params = {
        'draw': 1,
        'start': start,
        'length': length,
        'columns[0][data]': '0', 'columns[0][name]': '', 'columns[0][searchable]': 'true',
        'columns[0][orderable]': 'true', 'columns[0][search][value]': '', 'columns[0][search][regex]': 'false',
        'columns[1][data]': '1', 'columns[1][name]': '', 'columns[1][searchable]': 'true',
        'columns[1][orderable]': 'true', 'columns[1][search][value]': '', 'columns[1][search][regex]': 'false',
        'columns[2][data]': '2', 'columns[2][name]': '', 'columns[2][searchable]': 'true',
        'columns[2][orderable]': 'true', 'columns[2][search][value]': '', 'columns[2][search][regex]': 'false',
        'columns[3][data]': '3', 'columns[3][name]': '', 'columns[3][searchable]': 'true',
        'columns[3][orderable]': 'true', 'columns[3][search][value]': '', 'columns[3][search][regex]': 'false',
        'columns[4][data]': '4', 'columns[4][name]': '', 'columns[4][searchable]': 'true',
        'columns[4][orderable]': 'true', 'columns[4][search][value]': '', 'columns[4][search][regex]': 'false',
        'order[0][column]': '2', 'order[0][dir]': 'asc',
        'search[value]': '', 'search[regex]': 'false',
        'searched': '{"name":"","surname":"","sicil":""}',
    }
    resp = requests.get(
        BARO_DATA_URL,
        params=params,
        headers=_build_api_headers(session_cookie),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_photo_url(html: str) -> str:
    m = IMG_SRC_RE.search(html)
    if not m:
        return ''
    src = m.group(1)
    return src if src.startswith('http') else BARO_BASE_URL + src


def _parse_sicil(html: str) -> str:
    m = SICIL_RE.search(html)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"/avukat/(\d+)", html)
    return m2.group(1) if m2 else ''


def _download_photo(photo_url: str, sicil_no: str, session_cookie: str,
                    photos_dir: Path, requests) -> str:
    """Fotoğrafı indir, kaydet; başarılıysa local URL döndür yoksa ''."""
    local_path = photos_dir / f'{sicil_no}.jpg'
    try:
        resp = requests.get(
            photo_url,
            headers=_build_image_headers(session_cookie),
            timeout=30,
            stream=True,
        )
        if resp.status_code != 200:
            return ''
        content_type = resp.headers.get('content-type', '')
        if 'image' not in content_type and 'jpeg' not in content_type:
            return ''
        with open(local_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return f'/media/baro_photos/{sicil_no}.jpg'
    except Exception:
        return ''


class Command(BaseCommand):
    help = 'Baro websitesinden avukat fotoğraflarını indirir ve media/baro_photos/ klasörüne kaydeder'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-cookie',
            type=str,
            required=True,
            help='Baro session cookie (örn: "session=.eJw...")',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Her API isteğindeki kayıt sayısı (varsayılan: 500)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            default=False,
            help='Zaten fotoğrafı olan kayıtları da yeniden indir',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Maksimum indirilecek fotoğraf sayısı (0=sınırsız)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.1,
            help='API istekleri arası bekleme süresi saniye (varsayılan: 0.1)',
        )

    def handle(self, *args, **options):
        try:
            import requests as req
        except ImportError:
            raise CommandError("'requests' kütüphanesi gerekli: pip install requests")

        session_cookie = options['session_cookie'].strip()
        batch_size = options['batch_size']
        force = options['force']
        limit = options['limit']
        delay = options['delay']

        # Fotoğraf klasörünü oluştur
        photos_dir = Path(settings.MEDIA_ROOT) / 'baro_photos'
        photos_dir.mkdir(parents=True, exist_ok=True)
        self.stdout.write(f'Fotoğraflar kaydedilecek: {photos_dir}\n')

        # Baro API bağlantısını test et
        try:
            first_page = _fetch_page(session_cookie, 0, 1, req)
        except Exception as e:
            raise CommandError(
                f'Baro API\'ye erişilemedi: {e}\n'
                f'Session cookie geçerli mi? Cookie süresi dolmuş olabilir.'
            )

        total_remote = first_page.get('recordsTotal', 0)
        self.stdout.write(f'Baro\'da toplam {total_remote} kayıt var.\n')

        if total_remote == 0:
            self.stdout.write(self.style.WARNING('Hiç kayıt bulunamadı. Session cookie geçerli mi?'))
            return

        self.stdout.write(f'Fotoğraflar indiriliyor (batch_size={batch_size})...\n')

        start = 0
        total_downloaded = 0
        total_skipped = 0
        total_not_found = 0
        total_failed = 0

        while True:
            try:
                page_data = _fetch_page(session_cookie, start, batch_size, req)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Hata (start={start}): {e}'))
                break

            rows = page_data.get('data', [])
            if not rows:
                break

            for row in rows:
                if len(row) < 3:
                    continue

                photo_html = row[1]
                sicil_html = row[2]

                sicil_no = _parse_sicil(sicil_html)
                if not sicil_no:
                    continue

                photo_url = _parse_photo_url(photo_html)
                if not photo_url:
                    continue

                try:
                    bl = BaroLawyer.objects.get(sicil_no=sicil_no)
                except BaroLawyer.DoesNotExist:
                    total_not_found += 1
                    continue

                # Zaten local'de varsa atla
                local_path = photos_dir / f'{sicil_no}.jpg'
                if local_path.exists() and bl.photo_url and not force:
                    total_skipped += 1
                    continue

                # Fotoğrafı indir
                local_url = _download_photo(photo_url, sicil_no, session_cookie, photos_dir, req)
                if not local_url:
                    total_failed += 1
                    continue

                bl.photo_url = local_url
                bl.save(update_fields=['photo_url'])
                total_downloaded += 1

                if limit and total_downloaded >= limit:
                    break

                if delay:
                    time.sleep(delay)

            self.stdout.write(
                f'  {start + len(rows)}/{total_remote} işlendi '
                f'(indirildi: {total_downloaded}, atlandı: {total_skipped}, '
                f'hata: {total_failed})...',
                ending='\r',
            )
            self.stdout.flush()

            start += len(rows)

            if limit and total_downloaded >= limit:
                break

            if len(rows) < batch_size or start >= total_remote:
                break

        self.stdout.write('\n')
        self.stdout.write(self.style.SUCCESS(
            f'Tamamlandı! '
            f'İndirildi: {total_downloaded} | '
            f'Atlandı (zaten vardı): {total_skipped} | '
            f'İndirilemedi: {total_failed} | '
            f'DB\'de bulunamadı: {total_not_found}'
        ))
