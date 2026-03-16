"""
Kurul uyeliklerini committee_data.json dosyasindan yukler.
Railway deploy'da otomatik calistirilir.
"""
import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'CommitteeMembership tablosunu committee_data.json dosyasindan yukler'

    def handle(self, *args, **options):
        from app.models import CommitteeMembership, BaroLawyer

        count = CommitteeMembership.objects.count()
        if count > 0:
            self.stdout.write(f'CommitteeMembership tablosunda {count} kayit bulundu, siliniyor ve yeniden yukleniyor...')
            CommitteeMembership.objects.all().delete()

        from django.conf import settings
        json_path = os.path.join(str(settings.BASE_DIR), 'committee_data.json')

        if not os.path.exists(json_path):
            self.stdout.write(self.style.WARNING(f'committee_data.json bulunamadi: {json_path}'))
            return

        self.stdout.write(f'committee_data.json yukleniyor: {json_path}')

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.stdout.write(f'Toplam {len(data)} kayit bulundu.')

            # BaroLawyer lookup map
            baro_map = {bl.sicil_no: bl.pk for bl in BaroLawyer.objects.only('id', 'sicil_no')}

            records_to_create = []
            skipped = 0

            for item in data:
                gorev = item.get('gorev', '').strip()
                sicil_no = item.get('sicil_no', '').strip()
                ad_soyad = item.get('ad_soyad', '').strip()

                if not gorev or not sicil_no:
                    skipped += 1
                    continue

                baro_lawyer_id = baro_map.get(sicil_no)

                records_to_create.append(CommitteeMembership(
                    gorev=gorev,
                    sicil_no=sicil_no,
                    ad_soyad=ad_soyad,
                    baro_lawyer_id=baro_lawyer_id,
                ))

            with transaction.atomic():
                batch_size = 1000
                total = len(records_to_create)
                for i in range(0, total, batch_size):
                    batch = records_to_create[i:i + batch_size]
                    CommitteeMembership.objects.bulk_create(batch)
                    self.stdout.write(f'  {min(i + batch_size, total)}/{total} yuklendi...')

            self.stdout.write(self.style.SUCCESS(
                f'Tamamlandi: {len(records_to_create)} kayit yuklendi, {skipped} atlandi.'
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Hata: {e}'))
            raise
