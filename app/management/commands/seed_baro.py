"""
Baro verilerini JSON dosyasindan yukler.
Railway deploy'da otomatik calistirilir.

ÖNEMLI: Mevcut kayıtları SİLMEZ — günceller veya yeni ekler.
Bu sayede BaroLawyerTag (kara/beyaz liste), photo_url ve diğer sonradan
eklenen alanlar deploy sırasında korunur.
"""
import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'BaroLawyer tablosunu baro_data.json dosyasindan yukler (mevcut veri korunur)'

    def handle(self, *args, **options):
        from app.models import BaroLawyer

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

            # Mevcut kayıtları sicil_no → pk eşlemesiyle yükle
            existing = {
                bl.sicil_no: bl
                for bl in BaroLawyer.objects.only(
                    'id', 'sicil_no', 'ad', 'soyad', 'tel', 'mail', 'adres',
                    'uye', 'cinsiyet', 'ilce', 'dogum_yeri', 'dogum_tarihi',
                    'mahalle_koy', 'nufus_ilce', 'nufus_il', 'mesleğe_baslama',
                )
            }
            self.stdout.write(f'Veritabaninda {len(existing)} mevcut kayit var.')

            UPDATE_FIELDS = [
                'ad', 'soyad', 'tel', 'mail', 'adres', 'uye', 'cinsiyet',
                'ilce', 'dogum_yeri', 'dogum_tarihi', 'mahalle_koy',
                'nufus_ilce', 'nufus_il', 'mesleğe_baslama',
            ]
            # photo_url kasıtlı olarak güncelleme listesinde YOK
            # (deploy sırasında korunması için)

            to_create = []
            to_update = []
            skipped = 0

            for item in data:
                if isinstance(item, dict) and 'fields' in item:
                    fields = item.get('fields', {})
                else:
                    fields = item

                sicil_no = fields.get('sicil_no', '')
                if not sicil_no:
                    skipped += 1
                    continue

                if sicil_no in existing:
                    bl = existing[sicil_no]
                    bl.ad = fields.get('ad', '')
                    bl.soyad = fields.get('soyad', '')
                    bl.tel = fields.get('tel', '')
                    bl.mail = fields.get('mail', '')
                    bl.adres = fields.get('adres', '')
                    bl.uye = fields.get('uye', '')
                    bl.cinsiyet = fields.get('cinsiyet', '')
                    bl.ilce = fields.get('ilce', '')
                    bl.dogum_yeri = fields.get('dogum_yeri', '')
                    bl.dogum_tarihi = fields.get('dogum_tarihi', '')
                    bl.mahalle_koy = fields.get('mahalle_koy', '')
                    bl.nufus_ilce = fields.get('nufus_ilce', '')
                    bl.nufus_il = fields.get('nufus_il', '')
                    setattr(bl, 'mesleğe_baslama', fields.get('mesleğe_baslama', ''))
                    to_update.append(bl)
                else:
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
                    to_create.append(obj)

            with transaction.atomic():
                batch_size = 500

                # Güncelle
                if to_update:
                    for i in range(0, len(to_update), batch_size):
                        batch = to_update[i:i + batch_size]
                        BaroLawyer.objects.bulk_update(batch, UPDATE_FIELDS, batch_size=batch_size)
                        self.stdout.write(
                            f'  Guncellendi: {min(i + batch_size, len(to_update))}/{len(to_update)}...',
                            ending='\r'
                        )
                    self.stdout.write('')

                # Yeni ekle
                if to_create:
                    for i in range(0, len(to_create), batch_size):
                        batch = to_create[i:i + batch_size]
                        BaroLawyer.objects.bulk_create(batch, ignore_conflicts=True)
                        self.stdout.write(
                            f'  Eklendi: {min(i + batch_size, len(to_create))}/{len(to_create)}...',
                            ending='\r'
                        )
                    self.stdout.write('')

            self.stdout.write(self.style.SUCCESS(
                f'Tamamlandi: {len(to_update)} guncellendi, '
                f'{len(to_create)} yeni eklendi, {skipped} atlandi. '
                f'Etiketler ve fotolar korundu.'
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Hata: {e}'))
            raise
