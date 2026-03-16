"""
Baro verilerini JSON dosyasindan yukler.
Railway deploy'da otomatik calistirilir.
"""
import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'BaroLawyer tablosunu baro_data.json dosyasindan yukler'

    def handle(self, *args, **options):
        from app.models import BaroLawyer

        count = BaroLawyer.objects.count()
        if count > 0:
            self.stdout.write(f'BaroLawyer tablosunda {count} kayit bulundu, siliniyor ve yeniden yukleniyor...')
            BaroLawyer.objects.all().delete()

        from django.conf import settings
        json_path = os.path.join(str(settings.BASE_DIR), 'baro_data.json')

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
                # Hem eski format (fields: {...}) hem yeni format ({sicil_no: ...}) desteklenir
                if isinstance(item, dict) and 'fields' in item:
                    fields = item.get('fields', {})
                else:
                    fields = item

                sicil_no = fields.get('sicil_no', '')
                if not sicil_no:
                    skipped += 1
                    continue

                obj = BaroLawyer(
                    sicil_no=sicil_no,
                    ad=fields.get('ad', ''),
                    soyad=fields.get('soyad', ''),
                    tel=fields.get('tel', ''),
                    mail=fields.get('mail', ''),
                    adres=fields.get('adres', ''),
                    uye=fields.get('uye', ''),
                    cinsiyet=fields.get('cinsiyet', ''),
                    ilce=fields.get('ilce', ''),
                    dogum_yeri=fields.get('dogum_yeri', ''),
                    dogum_tarihi=fields.get('dogum_tarihi', ''),
                    mahalle_koy=fields.get('mahalle_koy', ''),
                    nufus_ilce=fields.get('nufus_ilce', ''),
                    nufus_il=fields.get('nufus_il', ''),
                )
                setattr(obj, 'mesleğe_baslama', fields.get('mesleğe_baslama', ''))
                records_to_create.append(obj)

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
