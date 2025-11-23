import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from app.services.importer import parse_and_stage
from app.services.apply_service import apply_diff
from app.models import Lawyer, Person, LawyerPerson

print("=== TEST 2: GUNCELLEME VE SILME ===\n")

lawyer = Lawyer.objects.first()
print(f"[OK] Avukat: {lawyer}")

# Mevcut durum
print(f"\nBAŞLANGIÇ:")
print(f"  Person sayisi: {Person.objects.count()}")
for p in Person.objects.all():
    print(f"    {p.kisi_sicilno} - {p.ad} {p.soyad} - tel: {p.telno} - mail: {p.mail}")

# Yeni bir Excel oluştur: 1001 güncellenecek, 1004 silinecek (listede yok), 1007 yeni eklenecek
data = {
    'sicilno': [1001, 1005, 1006, 1007],
    'ad': ['Ali', 'Veli', 'Deniz', 'Ayse'],
    'soyad': ['Kaya', 'Arslan', 'Ersoy', 'Demir'],
    'cevapDurumu': ['geliyor', 'geliyor', 'notr', 'gelmiyor'],  # 1001 status değişti
    'telno': [5301112233, 5332224455, '', 5559998877],  # 1001 tel değişti
    'mail': ['ali@updated.com', 'veli@example.com', '', 'ayse@new.com'],  # 1001 mail değişti
    'ilce': ['Cankaya', 'Altindag', '', 'Kecioren'],
    'adres_aciklama': ['yeni adres', 'yeni adres', '', 'ilk adres'],
    'notlar': ['guncellendi', 'yeni eklendi', '', 'yeni kisi']
}

df = pd.DataFrame(data)
file_path = 'media/uploads/test_update.xlsx'
df.to_excel(file_path, index=False, engine='openpyxl')
print(f"\n[OK] Test dosyasi olusturuldu: {file_path}")
print("  Degisiklikler:")
print("    - 1001: telefon ve mail guncellendi, status notr->geliyor")
print("    - 1004: listede YOK (silinmemeli!)")
print("    - 1007: yeni eklendi")

# Dosyayı yükle
with open(file_path, 'rb') as f:
    file_content = f.read()

uploaded_file = SimpleUploadedFile(
    name="test_update.xlsx",
    content=file_content,
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# Yükle ve uygula
batch_id, row_count = parse_and_stage(uploaded_file, lawyer.id, created_by="test2")
print(f"\n[OK] Staging: batch_id={batch_id}, row_count={row_count}")

result = apply_diff(batch_id, actor="test2")
print(f"[OK] Apply: {result}")

# Sonuç
print(f"\nSONUC:")
print(f"  Person sayisi: {Person.objects.count()}")
print("\nTUM KISILER:")
for p in Person.objects.all().order_by('kisi_sicilno'):
    lp = LawyerPerson.objects.filter(person=p, lawyer=lawyer).first()
    active = lp.active if lp else "N/A"
    print(f"  {p.kisi_sicilno} - {p.ad} {p.soyad} - tel: {p.telno} - mail: {p.mail} - status: {p.cevap_status} - active: {active}")

print("\nBEKLENEN:")
print("  1001: telefon ve mail guncellenmis olmali")
print("  1004: HALA MEVCUT olmali (silinmemeli!) - active: True")
print("  1007: yeni eklenmis olmali")
print("  Toplam: 5 kisi olmali")

print("\n=== TEST 2 BITTI ===")
