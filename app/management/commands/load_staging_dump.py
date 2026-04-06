"""
dump_for_staging.py çıktısını staging ortamına yükler.

Kullanım:
    python manage.py load_staging_dump staging_dump.json
    python manage.py load_staging_dump staging_dump.json --reset
"""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.models import (
    StatusOption, BaroLawyer, BaroLawyerTag, Lawyer, LawyerPerson, Person
)


class Command(BaseCommand):
    help = 'dump_for_staging çıktısını staging ortamına yükler'

    def add_arguments(self, parser):
        parser.add_argument('dump_file', type=str, help='JSON dump dosya yolu')
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Önce ilgili tabloları temizle',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dump_file = options['dump_file']
        try:
            with open(dump_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'Dosya bulunamadı: {dump_file}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Geçersiz JSON: {e}')

        if options['reset']:
            self.stdout.write('Mevcut veri temizleniyor...')
            LawyerPerson.objects.all().delete()
            BaroLawyerTag.objects.all().delete()
            Lawyer.objects.all().delete()
            BaroLawyer.objects.all().delete()
            StatusOption.objects.all().delete()
            Person.objects.all().delete()
            self.stdout.write('  Temizlendi.')

        counts = {'created': {}, 'skipped': {}}

        # 1) StatusOption
        n_new = 0
        for item in data.get('status_options', []):
            _, created = StatusOption.objects.get_or_create(
                key=item['key'],
                defaults={'label': item['label'], 'color': item.get('color') or ''}
            )
            if created:
                n_new += 1
        self.stdout.write(f'  StatusOption: {n_new} yeni / {len(data.get("status_options", []))} toplam')

        # 2) BaroLawyer
        n_new = 0
        for item in data.get('baro_lawyers', []):
            _, created = BaroLawyer.objects.get_or_create(
                sicil_no=item['sicil_no'],
                defaults={k: v for k, v in item.items() if k != 'sicil_no'}
            )
            if created:
                n_new += 1
        self.stdout.write(f'  BaroLawyer:   {n_new} yeni / {len(data.get("baro_lawyers", []))} toplam')

        # 3) Lawyer
        n_new = 0
        for item in data.get('lawyers', []):
            _, created = Lawyer.objects.get_or_create(
                sicil_no=item['sicil_no'],
                defaults={'ad': item['ad'], 'soyad': item['soyad']}
            )
            if created:
                n_new += 1
        self.stdout.write(f'  Lawyer:       {n_new} yeni / {len(data.get("lawyers", []))} toplam')

        # 4) BaroLawyerTag
        n_new = 0
        for item in data.get('baro_lawyer_tags', []):
            baro = BaroLawyer.objects.filter(sicil_no=item['baro_lawyer_sicil']).first()
            lawyer = Lawyer.objects.filter(sicil_no=item['lawyer_sicil']).first() if item.get('lawyer_sicil') else None
            if not baro:
                continue
            _, created = BaroLawyerTag.objects.get_or_create(
                baro_lawyer=baro,
                defaults={
                    'lawyer': lawyer,
                    'tag_type': item['tag_type'],
                    'note': item.get('note', ''),
                }
            )
            if created:
                n_new += 1
        self.stdout.write(f'  Tag:          {n_new} yeni / {len(data.get("baro_lawyer_tags", []))} toplam')

        # 5) LawyerPerson
        status_map = {s.key: s for s in StatusOption.objects.all()}
        n_new = 0
        for item in data.get('lawyer_persons', []):
            lawyer = Lawyer.objects.filter(sicil_no=item['lawyer_sicil']).first()
            if not lawyer:
                continue
            ks = item['kisi_sicilno']
            person, _ = Person.objects.get_or_create(
                kisi_sicilno=ks,
                defaults={'ad': item['ad'], 'soyad': item['soyad']}
            )
            status_obj = status_map.get(item.get('cevap_status_key', ''))
            _, created = LawyerPerson.objects.get_or_create(
                lawyer=lawyer,
                kisi_sicilno=ks,
                defaults={
                    'person': person,
                    'ad': item['ad'],
                    'soyad': item['soyad'],
                    'telno': item.get('telno', ''),
                    'mail': item.get('mail', ''),
                    'ilce': item.get('ilce', ''),
                    'notlar': item.get('notlar', ''),
                    'cevap_status': status_obj,
                    'active': item.get('active', True),
                }
            )
            if created:
                n_new += 1
        self.stdout.write(f'  LawyerPerson: {n_new} yeni / {len(data.get("lawyer_persons", []))} toplam')

        self.stdout.write(self.style.SUCCESS('\n✅ Staging dump yüklendi!'))
        self.stdout.write(f'   Exported at: {data.get("exported_at", "?")}')
