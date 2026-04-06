"""
Production verisini staging'e taşımak için JSON dump üretir.

PRODUCTION'da çalıştır:
    python manage.py dump_for_staging > staging_dump.json

STAGING'de yükle:
    python manage.py load_staging_dump staging_dump.json
"""
import json
import sys
from django.core.management.base import BaseCommand
from django.utils import timezone

from app.models import (
    StatusOption, BaroLawyer, BaroLawyerTag, Lawyer, LawyerPerson, Person
)


class Command(BaseCommand):
    help = 'Production verisini staging dump JSON olarak yazar (stdout)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default=None,
            help='Dosya yolu (belirtilmezse stdout)',
        )
        parser.add_argument(
            '--skip-lawyer-persons',
            action='store_true',
            help='LawyerPerson kayıtlarını atla (sadece referans veri)',
        )

    def handle(self, *args, **options):
        self.stdout.write('Veri toplanıyor...', ending='\n' if options['output'] else '')

        data = {
            'exported_at': timezone.now().isoformat(),
            'status_options': list(StatusOption.objects.values('key', 'label', 'color')),
            'baro_lawyers': list(BaroLawyer.objects.values(
                'sicil_no', 'ad', 'soyad', 'tel', 'mail', 'adres',
                'uye', 'cinsiyet', 'ilce', 'dogum_yeri', 'mahalle_koy',
                'nufus_ilce', 'nufus_il', 'mesleğe_baslama', 'dogum_tarihi'
                # photo_url dahil değil — staging'de gerek yok
            )),
            'lawyers': list(Lawyer.objects.values('sicil_no', 'ad', 'soyad')),
            'baro_lawyer_tags': [],
            'lawyer_persons': [],
        }

        # Tags (kara/beyaz liste)
        for tag in BaroLawyerTag.objects.select_related('baro_lawyer', 'lawyer').all():
            data['baro_lawyer_tags'].append({
                'baro_lawyer_sicil': tag.baro_lawyer.sicil_no,
                'lawyer_sicil': tag.lawyer.sicil_no if tag.lawyer else None,
                'tag_type': tag.tag_type,
                'note': tag.note or '',
            })

        # LawyerPerson (isteğe bağlı)
        if not options['skip_lawyer_persons']:
            for lp in LawyerPerson.objects.select_related('lawyer', 'cevap_status').filter(active=True):
                data['lawyer_persons'].append({
                    'lawyer_sicil': lp.lawyer.sicil_no,
                    'kisi_sicilno': lp.kisi_sicilno,
                    'ad': lp.ad,
                    'soyad': lp.soyad,
                    'telno': lp.telno or '',
                    'mail': lp.mail or '',
                    'ilce': lp.ilce or '',
                    'notlar': lp.notlar or '',
                    'cevap_status_key': lp.cevap_status.key if lp.cevap_status else '',
                    'active': lp.active,
                })

        counts = {
            'status_options': len(data['status_options']),
            'baro_lawyers': len(data['baro_lawyers']),
            'lawyers': len(data['lawyers']),
            'tags': len(data['baro_lawyer_tags']),
            'lawyer_persons': len(data['lawyer_persons']),
        }

        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as f:
                f.write(json_str)
            self.stdout.write(self.style.SUCCESS(
                f"Dump yazıldı: {options['output']}\n"
                f"  StatusOption:  {counts['status_options']}\n"
                f"  BaroLawyer:    {counts['baro_lawyers']}\n"
                f"  Lawyer:        {counts['lawyers']}\n"
                f"  Tag:           {counts['tags']}\n"
                f"  LawyerPerson:  {counts['lawyer_persons']}\n"
            ))
        else:
            # stdout'a yaz — pipe ile dosyaya yönlendir
            sys.stdout.write(json_str)
