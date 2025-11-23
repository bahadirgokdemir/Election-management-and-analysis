import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from app.models import UploadRowStaging, UploadBatch, Person

print('UploadBatch count:', UploadBatch.objects.count())
print('UploadRowStaging count:', UploadRowStaging.objects.count())
print('Person count:', Person.objects.count())

if UploadBatch.objects.exists():
    batch = UploadBatch.objects.last()
    print(f'\nSon batch: {batch.id}')
    print(f'  Dosya: {batch.original_filename}')
    print(f'  row_count: {batch.row_count}')
    print(f'  status: {batch.status}')

    staging_rows = UploadRowStaging.objects.filter(batch=batch)[:5]
    print(f'\nStaging rows (ilk 5):')
    for r in staging_rows:
        print(f'  {r.kisi_sicilno} - {r.ad} {r.soyad} - status_key: {r.cevap_status_key}')

if Person.objects.exists():
    print(f'\nPerson tablodaki ilk 3:')
    for p in Person.objects.all()[:3]:
        print(f'  {p.kisi_sicilno} - {p.ad} {p.soyad} - status: {p.cevap_status}')
