"""
Baro_Merkezler_vs.xlsx dosyasından kurul üyeliklerini database'e yükleyen management command
Kullanım: python manage.py load_committee_data
"""
import pandas as pd
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from app.models import CommitteeMembership, BaroLawyer


class Command(BaseCommand):
    help = 'Baro_Merkezler_vs.xlsx dosyasından kurul üyeliklerini database\'e yükler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Excel dosya yolu (varsayılan: proje dizinindeki Baro_Merkezler_vs.xlsx)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Mevcut verileri temizle ve yeniden yükle',
        )

    def handle(self, *args, **options):
        file_path = options.get('file')
        clear = options.get('clear', False)

        if file_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            file_path = base_dir / 'Baro_Merkezler_vs.xlsx'

        file_path = Path(file_path)
        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f'Dosya bulunamadı: {file_path}'))
            raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")

        self.stdout.write(f'Kurul üyelikleri yükleniyor: {file_path}')

        try:
            df = pd.read_excel(file_path)
            self.stdout.write(f'Excel dosyasından {len(df)} satır okundu.')
            self.stdout.write(f'Sütunlar: {df.columns.tolist()}')

            if clear:
                deleted_count = CommitteeMembership.objects.count()
                CommitteeMembership.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'{deleted_count} mevcut kayıt silindi.'))

            # BaroLawyer lookup map
            baro_map = {bl.sicil_no: bl for bl in BaroLawyer.objects.all()}

            created = 0
            errors = 0

            with transaction.atomic():
                memberships = []
                for idx, row in df.iterrows():
                    try:
                        gorev_raw = row.iloc[0]
                        sicil_raw = row.iloc[1]
                        ad_soyad_raw = row.iloc[2]

                        if pd.isna(gorev_raw) or pd.isna(sicil_raw):
                            continue

                        gorev = str(gorev_raw).strip()
                        if isinstance(sicil_raw, (int, float)):
                            sicil_no = str(int(sicil_raw)).strip()
                        else:
                            sicil_no = str(sicil_raw).strip()

                        ad_soyad = str(ad_soyad_raw).strip() if pd.notna(ad_soyad_raw) else ''

                        if not gorev or not sicil_no or not sicil_no.isdigit():
                            continue

                        baro_lawyer = baro_map.get(sicil_no)

                        memberships.append(CommitteeMembership(
                            gorev=gorev,
                            sicil_no=sicil_no,
                            ad_soyad=ad_soyad,
                            baro_lawyer=baro_lawyer,
                        ))
                        created += 1

                        if created % 1000 == 0:
                            self.stdout.write(f'İşlenen kayıt: {created}')

                    except Exception as e:
                        errors += 1
                        self.stdout.write(self.style.ERROR(f'Satır {idx+2} hatası: {e}'))

                CommitteeMembership.objects.bulk_create(memberships)

            self.stdout.write(self.style.SUCCESS('\n' + '='*50))
            self.stdout.write(self.style.SUCCESS('YÜKLEME TAMAMLANDI!'))
            self.stdout.write(self.style.SUCCESS('='*50))
            self.stdout.write(f'Yeni kayıt: {created}')
            if errors > 0:
                self.stdout.write(self.style.ERROR(f'Hata sayısı: {errors}'))

            total = CommitteeMembership.objects.count()
            self.stdout.write(f'Toplam kurul üyeliği kaydı: {total}')

            # Görev dağılımı
            from django.db.models import Count
            gorev_counts = CommitteeMembership.objects.values('gorev').annotate(count=Count('id')).order_by('-count')[:10]
            self.stdout.write('\nEn çok üyelik olan kurullar:')
            for g in gorev_counts:
                self.stdout.write(f'  {g["gorev"]}: {g["count"]} üye')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Kritik hata: {e}'))
            raise
