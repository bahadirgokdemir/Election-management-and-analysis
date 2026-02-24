"""
Baro verilerini JSON dosyasindan yukler (sadece tablo bos ise).
Railway ilk deploy'da otomatik calistirilir.
"""
import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'BaroLawyer tablosu bos ise baro_data.json dosyasindan yukler'

    def handle(self, *args, **options):
        from app.models import BaroLawyer

        count = BaroLawyer.objects.count()
        if count > 0:
            self.stdout.write(f'BaroLawyer tablosunda zaten {count} kayit var, atlanıyor.')
            return

        json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), 'baro_data.json')

        if not os.path.exists(json_path):
            self.stdout.write(self.style.WARNING(f'baro_data.json bulunamadi: {json_path}'))
            return

        self.stdout.write(f'baro_data.json yukleniyor: {json_path}')

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.stdout.write(f'Toplam {len(data)} kayit bulundu.')

            records_to_create = []
            skipped = 0

            for item in data:
                fields = item.get('fields', {})
                sicil_no = fields.get('sicil_no', '')
                if not sicil_no:
                    skipped += 1
                    continue
                records_to_create.append(BaroLawyer(
                    sicil_no=sicil_no,
                    ad=fields.get('ad', ''),
                    soyad=fields.get('soyad', ''),
                    tel=fields.get('tel', ''),
                    mail=fields.get('mail', ''),
                    adres=fields.get('adres', ''),
                ))

            # Toplu ekleme - 1000'er batch
            with transaction.atomic():
                batch_size = 1000
                total = len(records_to_create)
                for i in range(0, total, batch_size):
                    batch = records_to_create[i:i + batch_size]
                    BaroLawyer.objects.bulk_create(batch, ignore_conflicts=True)
                    self.stdout.write(f'  {min(i + batch_size, total)}/{total} yuklendi...')

            self.stdout.write(self.style.SUCCESS(
                f'Tamamlandi: {len(records_to_create)} kayit yuklendi, {skipped} atlandi.'
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Hata: {e}'))
            raise
