"""
Excel dosyasından baro verilerini database'e yükleyen management command
Kullanım: python manage.py load_baro_data
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from app.models import BaroLawyer
from app.services.baro_loader import BaroLoader


class Command(BaseCommand):
    help = 'Aktif.xlsx dosyasından baro verilerini database\'e yükler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Mevcut verileri temizle ve yeniden yükle',
        )

    def handle(self, *args, **options):
        clear = options.get('clear', False)

        self.stdout.write('Baro verileri yükleniyor...')

        try:
            # Excel'den verileri oku
            loader = BaroLoader()
            records = loader.load_records(use_cache=False)

            self.stdout.write(f'Excel dosyasından {len(records)} kayıt okundu.')

            # Mevcut verileri temizle
            if clear:
                deleted_count = BaroLawyer.objects.count()
                BaroLawyer.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'{deleted_count} mevcut kayıt silindi.'))

            # Verileri database'e aktar
            created = 0
            updated = 0
            errors = 0

            with transaction.atomic():
                for record in records:
                    try:
                        obj, created_flag = BaroLawyer.objects.update_or_create(
                            sicil_no=record.sicil_no,
                            defaults={
                                'ad': record.ad,
                                'soyad': record.soyad,
                                'tel': record.tel,
                                'mail': record.mail,
                                'adres': record.adres,
                            }
                        )
                        if created_flag:
                            created += 1
                        else:
                            updated += 1

                        # Her 1000 kayıtta bir ilerleme göster
                        if (created + updated) % 1000 == 0:
                            self.stdout.write(f'İşlenen kayıt: {created + updated}')

                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(f'Hata (Sicil: {record.sicil_no}): {e}')
                        )

            # Özet
            self.stdout.write(self.style.SUCCESS('\n' + '='*50))
            self.stdout.write(self.style.SUCCESS('YÜKLEME TAMAMLANDI!'))
            self.stdout.write(self.style.SUCCESS('='*50))
            self.stdout.write(f'Yeni kayıt: {created}')
            self.stdout.write(f'Güncellenen kayıt: {updated}')
            if errors > 0:
                self.stdout.write(self.style.ERROR(f'Hata sayısı: {errors}'))
            self.stdout.write(f'Toplam başarılı: {created + updated}')

            # İstatistikler
            total = BaroLawyer.objects.count()
            with_email = BaroLawyer.objects.exclude(mail='').count()
            with_phone = BaroLawyer.objects.exclude(tel='').count()
            with_address = BaroLawyer.objects.exclude(adres='').count()

            self.stdout.write('\nVERİTABANI İSTATİSTİKLERİ:')
            self.stdout.write(f'Toplam kayıt: {total}')
            self.stdout.write(f'E-posta olan: {with_email} ({with_email*100/total:.1f}%)')
            self.stdout.write(f'Telefon olan: {with_phone} ({with_phone*100/total:.1f}%)')
            self.stdout.write(f'Adres olan: {with_address} ({with_address*100/total:.1f}%)')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Kritik hata: {e}'))
            raise
