"""
Test ortamı için minimal seed verisi oluşturur.

Çalıştır:
    python manage.py seed_test_data
    python manage.py seed_test_data --reset   (önce siler, sonra oluşturur)
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from app.models import (
    StatusOption, BaroLawyer, Lawyer, Person, LawyerPerson, BaroLawyerTag
)

# Sistem avukat sicil numaraları (views_ui.py ile aynı)
_KARA_LISTE_SICIL = '_KARALIST_'
_BEYAZ_LISTE_SICIL = '_BEYAZLIST_'

# Test kişileri — BaroLawyer ve LawyerPerson ikisinde de olmalı
TEST_BARO_PERSONS = [
    {"sicil_no": "T001", "ad": "Ahmet",   "soyad": "Yılmaz",  "ilce": "Çankaya",  "mail": "ahmet@test.com",   "tel": "05551112233"},
    {"sicil_no": "T002", "ad": "Ayşe",    "soyad": "Kaya",    "ilce": "Keçiören", "mail": "ayse@test.com",    "tel": "05552223344"},
    {"sicil_no": "T003", "ad": "Mehmet",  "soyad": "Demir",   "ilce": "Mamak",    "mail": "mehmet@test.com",  "tel": "05553334455"},
    {"sicil_no": "T004", "ad": "Fatma",   "soyad": "Çelik",   "ilce": "Altındağ", "mail": "fatma@test.com",   "tel": "05554445566"},
    {"sicil_no": "T005", "ad": "Ali",     "soyad": "Şahin",   "ilce": "Sincan",   "mail": "ali@test.com",     "tel": "05555556677"},
    {"sicil_no": "T006", "ad": "Zeynep",  "soyad": "Arslan",  "ilce": "Etimesgut","mail": "zeynep@test.com",  "tel": "05556667788"},
    {"sicil_no": "T007", "ad": "Mustafa", "soyad": "Koç",     "ilce": "Gölbaşı",  "mail": "mustafa@test.com", "tel": "05557778899"},
    {"sicil_no": "T008", "ad": "Elif",    "soyad": "Kurt",    "ilce": "Çankaya",  "mail": "elif@test.com",    "tel": "05558889900"},
    {"sicil_no": "T009", "ad": "Hasan",   "soyad": "Özkan",   "ilce": "Keçiören", "mail": "hasan@test.com",   "tel": "05559990011"},
    {"sicil_no": "T010", "ad": "Selin",   "soyad": "Aydın",   "ilce": "Mamak",    "mail": "selin@test.com",   "tel": "05550001122"},
    {"sicil_no": "T011", "ad": "İbrahim", "soyad": "Güneş",   "ilce": "Altındağ", "mail": "ibrahim@test.com", "tel": "05551230001"},
    {"sicil_no": "T012", "ad": "Merve",   "soyad": "Yıldız",  "ilce": "Sincan",   "mail": "merve@test.com",   "tel": "05552340002"},
    {"sicil_no": "T013", "ad": "Emre",    "soyad": "Polat",   "ilce": "Etimesgut","mail": "emre@test.com",    "tel": "05553450003"},
    {"sicil_no": "T014", "ad": "Büşra",   "soyad": "Güler",   "ilce": "Gölbaşı",  "mail": "busra@test.com",   "tel": "05554560004"},
    {"sicil_no": "T015", "ad": "Sercan",  "soyad": "Doğan",   "ilce": "Çankaya",  "mail": "sercan@test.com",  "tel": "05555670005"},
]

# Avukat 1 → T001–T010 (bazıları Avukat 2 ile ortak)
LAWYER1_PERSONS = [
    {"sicil_no": "T001", "status": "geliyor"},
    {"sicil_no": "T002", "status": "gelmiyor"},
    {"sicil_no": "T003", "status": "geliyor"},
    {"sicil_no": "T004", "status": None},
    {"sicil_no": "T005", "status": "nötr"},
    {"sicil_no": "T006", "status": "geliyor"},
    {"sicil_no": "T007", "status": "gelmiyor"},
    {"sicil_no": "T008", "status": None},
]

# Avukat 2 → T006–T015 (T006–T008 Avukat 1 ile ortak → net kişi listesinde görünür)
LAWYER2_PERSONS = [
    {"sicil_no": "T006", "status": "gelmiyor"},  # Avukat 1'de geliyor, burada gelmiyor → çakışma
    {"sicil_no": "T007", "status": "geliyor"},
    {"sicil_no": "T008", "status": "nötr"},
    {"sicil_no": "T009", "status": "geliyor"},
    {"sicil_no": "T010", "status": "geliyor"},
    {"sicil_no": "T011", "status": None},
    {"sicil_no": "T012", "status": "gelmiyor"},
    {"sicil_no": "T013", "status": "geliyor"},
]


class Command(BaseCommand):
    help = 'Test ortamı için minimal seed verisi oluşturur'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Önce mevcut test verisini sil, sonra oluştur',
        )
        parser.add_argument(
            '--excel',
            action='store_true',
            help='Test Excel dosyaları da oluştur (test_fixtures/)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        self._seed_status()
        self._seed_baro_persons()
        lawyer1, lawyer2 = self._seed_lawyers()
        self._seed_lawyer_persons(lawyer1, LAWYER1_PERSONS)
        self._seed_lawyer_persons(lawyer2, LAWYER2_PERSONS)
        self._seed_tags()
        self._seed_user()

        if options['excel']:
            self._generate_excel_fixtures(lawyer1, lawyer2)

        self.stdout.write(self.style.SUCCESS('\n✅ Test verisi hazır!'))
        self.stdout.write('')
        self.stdout.write('  Giriş: admin / testpass123')
        self.stdout.write(f'  Avukat 1: TEST-AV-001 (Orhan Test) — {len(LAWYER1_PERSONS)} kişi')
        self.stdout.write(f'  Avukat 2: TEST-AV-002 (Aylin Test) — {len(LAWYER2_PERSONS)} kişi')
        self.stdout.write(f'  Ortak kişi: T006, T007, T008 (net listede çakışma testi için)')
        if options['excel']:
            self.stdout.write('  Excel: test_fixtures/avukat1_liste.xlsx, avukat2_liste.xlsx')

    def _reset(self):
        self.stdout.write('🗑  Mevcut test verisi siliniyor...')
        sicil_nos = [p['sicil_no'] for p in TEST_BARO_PERSONS]
        LawyerPerson.objects.filter(kisi_sicilno__in=sicil_nos).delete()
        Person.objects.filter(kisi_sicilno__in=sicil_nos).delete()
        BaroLawyerTag.objects.filter(baro_lawyer__sicil_no__in=['T003', 'T005']).delete()
        BaroLawyer.objects.filter(sicil_no__in=sicil_nos).delete()
        Lawyer.objects.filter(sicil_no__in=['TEST-AV-001', 'TEST-AV-002']).delete()
        self.stdout.write('  Silindi.')

    def _seed_status(self):
        statuses = [
            ("geliyor",  "Geliyor",  "#22c55e"),
            ("gelmiyor", "Gelmiyor", "#ef4444"),
            ("nötr",     "Nötr",     "#a3a3a3"),
        ]
        for key, label, color in statuses:
            StatusOption.objects.get_or_create(key=key, defaults={"label": label, "color": color})
        self.stdout.write('  StatusOption: 3 durum hazır')

    def _seed_baro_persons(self):
        count = 0
        for p in TEST_BARO_PERSONS:
            _, created = BaroLawyer.objects.get_or_create(
                sicil_no=p['sicil_no'],
                defaults={
                    'ad': p['ad'],
                    'soyad': p['soyad'],
                    'ilce': p.get('ilce', ''),
                    'mail': p.get('mail', ''),
                    'tel': p.get('tel', ''),
                    'uye': 'Aktif',
                    'cinsiyet': 'E',
                }
            )
            if created:
                count += 1
        self.stdout.write(f'  BaroLawyer: {count} yeni, {len(TEST_BARO_PERSONS) - count} zaten vardı')

    def _seed_lawyers(self):
        # Sistem avukatları (kara/beyaz liste)
        Lawyer.objects.get_or_create(
            sicil_no=_KARA_LISTE_SICIL,
            defaults={'ad': 'Kara', 'soyad': 'Liste'}
        )
        Lawyer.objects.get_or_create(
            sicil_no=_BEYAZ_LISTE_SICIL,
            defaults={'ad': 'Beyaz', 'soyad': 'Liste'}
        )

        lawyer1, c1 = Lawyer.objects.get_or_create(
            sicil_no='TEST-AV-001',
            defaults={'ad': 'Orhan', 'soyad': 'Test'}
        )
        lawyer2, c2 = Lawyer.objects.get_or_create(
            sicil_no='TEST-AV-002',
            defaults={'ad': 'Aylin', 'soyad': 'Test'}
        )
        self.stdout.write(f'  Lawyer: {"oluşturuldu" if c1 else "vardı"} TEST-AV-001, {"oluşturuldu" if c2 else "vardı"} TEST-AV-002')
        return lawyer1, lawyer2

    def _seed_lawyer_persons(self, lawyer, persons):
        status_map = {s.key: s for s in StatusOption.objects.all()}
        count = 0
        for entry in persons:
            ks = entry['sicil_no']
            baro = next((p for p in TEST_BARO_PERSONS if p['sicil_no'] == ks), {})
            person, _ = Person.objects.get_or_create(
                kisi_sicilno=ks,
                defaults={'ad': baro.get('ad', ''), 'soyad': baro.get('soyad', '')}
            )
            status_obj = status_map.get(entry['status']) if entry.get('status') else None
            _, created = LawyerPerson.objects.get_or_create(
                lawyer=lawyer,
                kisi_sicilno=ks,
                defaults={
                    'person': person,
                    'ad': baro.get('ad', ''),
                    'soyad': baro.get('soyad', ''),
                    'mail': baro.get('mail', ''),
                    'telno': baro.get('tel', ''),
                    'ilce': baro.get('ilce', ''),
                    'cevap_status': status_obj,
                    'active': True,
                }
            )
            if created:
                count += 1
        self.stdout.write(f'  LawyerPerson ({lawyer.sicil_no}): {count} yeni kayıt')

    def _seed_tags(self):
        # T003 kara liste, T005 beyaz liste
        for sicil, tag_type, note in [
            ('T003', 'blacklist', 'Test kara liste notu'),
            ('T005', 'whitelist', 'Test beyaz liste notu'),
        ]:
            baro = BaroLawyer.objects.filter(sicil_no=sicil).first()
            if not baro:
                continue
            kara_lawyer = Lawyer.objects.filter(sicil_no=_KARA_LISTE_SICIL).first()
            beyaz_lawyer = Lawyer.objects.filter(sicil_no=_BEYAZ_LISTE_SICIL).first()
            target_lawyer = kara_lawyer if tag_type == 'blacklist' else beyaz_lawyer
            if not target_lawyer:
                continue
            BaroLawyerTag.objects.get_or_create(
                baro_lawyer=baro,
                defaults={'tag_type': tag_type, 'note': note, 'lawyer': target_lawyer}
            )
        self.stdout.write('  BaroLawyerTag: T003 kara, T005 beyaz liste')

    def _seed_user(self):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@test.com', 'testpass123')
            self.stdout.write('  User: admin oluşturuldu (testpass123)')
        else:
            self.stdout.write('  User: admin zaten var')

    def _generate_excel_fixtures(self, lawyer1, lawyer2):
        try:
            import openpyxl
        except ImportError:
            self.stdout.write(self.style.WARNING('  openpyxl bulunamadı, Excel oluşturulamadı. pip install openpyxl'))
            return

        from pathlib import Path
        fixtures_dir = Path('test_fixtures')
        fixtures_dir.mkdir(exist_ok=True)

        # Avukat 1 listesi (T001-T008) — tam liste
        self._write_excel(
            fixtures_dir / 'avukat1_liste.xlsx',
            [p for p in TEST_BARO_PERSONS if p['sicil_no'] in [e['sicil_no'] for e in LAWYER1_PERSONS]],
            LAWYER1_PERSONS,
            'TEST-AV-001'
        )

        # Avukat 2 listesi (T006-T013) — tam liste
        self._write_excel(
            fixtures_dir / 'avukat2_liste.xlsx',
            [p for p in TEST_BARO_PERSONS if p['sicil_no'] in [e['sicil_no'] for e in LAWYER2_PERSONS]],
            LAWYER2_PERSONS,
            'TEST-AV-002'
        )

        # Avukat 1 güncel liste — T003 çıkarıldı, T001 durumu değişti (merge testi için)
        updated = [e for e in LAWYER1_PERSONS if e['sicil_no'] != 'T003']
        for e in updated:
            if e['sicil_no'] == 'T001':
                e = dict(e, status='gelmiyor')  # durum değişikliği testi
        self._write_excel(
            fixtures_dir / 'avukat1_guncelleme.xlsx',
            [p for p in TEST_BARO_PERSONS if p['sicil_no'] in [e['sicil_no'] for e in updated]],
            updated,
            'TEST-AV-001'
        )
        self.stdout.write(f'  Excel dosyaları: {fixtures_dir.resolve()}')

    def _write_excel(self, path, baro_persons, status_entries, lawyer_sicil):
        import openpyxl
        status_map = {e['sicil_no']: e.get('status', '') or '' for e in status_entries}

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Liste'
        headers = ['kisi_sicilno', 'ad', 'soyad', 'ilce', 'mail', 'telno', 'cevap_status_key']
        ws.append(headers)
        for p in baro_persons:
            ws.append([
                p['sicil_no'],
                p['ad'],
                p['soyad'],
                p.get('ilce', ''),
                p.get('mail', ''),
                p.get('tel', ''),
                status_map.get(p['sicil_no'], ''),
            ])
        wb.save(path)
