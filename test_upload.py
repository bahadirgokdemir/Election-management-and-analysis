import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from app.services.importer import parse_and_stage
from app.services.apply_service import apply_diff
from app.models import Lawyer, Person, LawyerPerson, UploadBatch, UploadRowStaging

# Test için örnek veri
print("=== TEST BAŞLIYOR ===\n")

# 1) Avukat var mı kontrol et
lawyer = Lawyer.objects.first()
if not lawyer:
    lawyer = Lawyer.objects.create(sicil_no="TEST001", ad="Test", soyad="Avukat")
    print(f"[OK] Yeni avukat olusturuldu: {lawyer}")
else:
    print(f"[OK] Mevcut avukat kullaniliyor: {lawyer}")

# 2) Mevcut verileri göster
print(f"\nBAŞLANGIÇ DURUMU:")
print(f"  Person sayısı: {Person.objects.count()}")
print(f"  LawyerPerson sayısı: {LawyerPerson.objects.count()}")
print(f"  UploadBatch sayısı: {UploadBatch.objects.count()}")

# 3) Test dosyasını yükle
file_path = "media/uploads/liste2.xlsx"
if os.path.exists(file_path):
    with open(file_path, 'rb') as f:
        file_content = f.read()

    uploaded_file = SimpleUploadedFile(
        name="liste2.xlsx",
        content=file_content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    print(f"\n[OK] Dosya okundu: {file_path}")

    # 4) parse_and_stage çağır
    batch_id, row_count = parse_and_stage(uploaded_file, lawyer.id, created_by="test_script")
    print(f"[OK] Staging tamamlandi: batch_id={batch_id}, row_count={row_count}")

    # 5) Staging verilerini göster
    staging = UploadRowStaging.objects.filter(batch_id=batch_id)
    print(f"\nSTAGING VERİLERİ ({staging.count()} satır):")
    for s in staging[:5]:
        print(f"  {s.kisi_sicilno} - {s.ad} {s.soyad} - {s.cevap_status_key}")

    # 6) apply_diff çağır (otomatik approve)
    result = apply_diff(batch_id, actor="test_script")
    print(f"\n[OK] Apply tamamlandi: {result}")

    # 7) Person tablosunu kontrol et
    print(f"\nSONUÇ:")
    print(f"  Person sayısı: {Person.objects.count()}")
    print(f"  LawyerPerson sayısı: {LawyerPerson.objects.count()}")

    persons = Person.objects.all()[:10]
    print(f"\nPERSON TABLOSU (ilk 10):")
    for p in persons:
        lp = LawyerPerson.objects.filter(person=p, lawyer=lawyer).first()
        active = lp.active if lp else "N/A"
        print(f"  {p.kisi_sicilno} - {p.ad} {p.soyad} - status: {p.cevap_status} - active: {active}")

else:
    print(f"HATA: Dosya bulunamadı: {file_path}")

print("\n=== TEST BİTTİ ===")
