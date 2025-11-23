"""
Veritabanı Sıfırlama Scripti
Tüm kayıtları siler ve temiz bir başlangıç yapar.

Kullanım:
    python reset_database.py
"""
import os
import sys
import django

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import transaction
from app.models import (
    Person, LawyerPerson, Lawyer, StatusOption,
    UploadBatch, UploadRowStaging, BatchDiff, AuditLog
)

def reset_all_data():
    """Tüm verileri siler (Lawyer ve StatusOption hariç)"""
    print("=" * 60)
    print("VERİTABANI SIFIRLAMA")
    print("=" * 60)

    # Mevcut kayit sayilari
    print("\nMevcut Kayitlar:")
    print(f"  - LawyerPerson iliskileri: {LawyerPerson.objects.count()}")
    print(f"  - Person kayitlari: {Person.objects.count()}")
    print(f"  - Upload Batch'leri: {UploadBatch.objects.count()}")
    print(f"  - Audit Loglari: {AuditLog.objects.count()}")
    print(f"  - Lawyer kayitlari: {Lawyer.objects.count()} (SILINMEYECEK)")
    print(f"  - Status Options: {StatusOption.objects.count()} (SILINMEYECEK)")

    # Onay al
    print("\nUYARI: Bu islem GERI ALINAMAZ!")
    print("   Tum kisi kayitlari, iliskiler, yuklemeler ve loglar silinecek.")
    print("   Avukat ve durum tanimlari korunacak.")

    confirm = input("\nDevam etmek icin 'EVET' yazin: ")
    if confirm != "EVET":
        print("Islem iptal edildi.")
        return

    try:
        with transaction.atomic():
            # Sirayla sil (foreign key'ler yuzunden)
            print("\nSiliniyor...")

            deleted_audit = AuditLog.objects.all().delete()[0]
            print(f"  - {deleted_audit} Audit log silindi")

            deleted_diff = BatchDiff.objects.all().delete()[0]
            print(f"  - {deleted_diff} Batch diff silindi")

            deleted_staging = UploadRowStaging.objects.all().delete()[0]
            print(f"  - {deleted_staging} Upload staging silindi")

            deleted_batch = UploadBatch.objects.all().delete()[0]
            print(f"  - {deleted_batch} Upload batch silindi")

            deleted_lp = LawyerPerson.objects.all().delete()[0]
            print(f"  - {deleted_lp} LawyerPerson iliskisi silindi")

            deleted_person = Person.objects.all().delete()[0]
            print(f"  - {deleted_person} Person kaydi silindi")

        print("\nVeritabani basariyla sifirlandi!")
        print(f"   Avukat sayisi: {Lawyer.objects.count()} (korundu)")
        print(f"   Status sayisi: {StatusOption.objects.count()} (korundu)")

    except Exception as e:
        print(f"\n❌ Hata oluştu: {e}")
        sys.exit(1)

def reset_everything():
    """HER ŞEYİ siler (Lawyer ve StatusOption dahil)"""
    print("=" * 60)
    print("TAM VERİTABANI SIFIRLAMA (HER ŞEY)")
    print("=" * 60)

    print("\nUYARI: Bu islem TAMAMEN GERI ALINAMAZ!")
    print("   AVUKATLAR ve DURUM TANIMLARI DAHIL HER SEY silinecek!")

    confirm = input("\nDevam etmek icin 'EVET EMINIM' yazin: ")
    if confirm != "EVET EMINIM":
        print("Islem iptal edildi.")
        return

    try:
        with transaction.atomic():
            print("\nSiliniyor...")

            AuditLog.objects.all().delete()
            BatchDiff.objects.all().delete()
            UploadRowStaging.objects.all().delete()
            UploadBatch.objects.all().delete()
            LawyerPerson.objects.all().delete()
            Person.objects.all().delete()

            deleted_lawyer = Lawyer.objects.all().delete()[0]
            print(f"  - {deleted_lawyer} Avukat silindi")

            deleted_status = StatusOption.objects.all().delete()[0]
            print(f"  - {deleted_status} Status option silindi")

        print("\nVeritabani TAMAMEN sifirlandi!")

    except Exception as e:
        print(f"\nHata olustu: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("\nSIFIRLAMA SECENEKLERI:")
    print("  1) Sadece Kayitlari Sil (Avukat ve Durumlari Koru)")
    print("  2) Her Seyi Sil (Avukat ve Durumlar Dahil)")
    print("  3) Iptal")

    choice = input("\nSeciminiz (1/2/3): ")

    if choice == "1":
        reset_all_data()
    elif choice == "2":
        reset_everything()
    else:
        print("Islem iptal edildi.")
