from typing import Dict
from django.db import transaction
from django.db.models import Q

from app.models import (
    UploadBatch, UploadRowStaging, LawyerPerson, Person, StatusOption, BatchDiff, AuditLog
)


@transaction.atomic
def apply_diff(batch_id: int, actor: str = None) -> Dict:
    batch = UploadBatch.objects.select_for_update().select_related('lawyer').get(id=batch_id)
    if batch.status != UploadBatch.STAGED:
        return {"ok": False, "message": "Batch zaten uygulanmış veya reddedilmiş."}

    # diff’i hazırla (mevcut varsa kullan; yoksa hesaplanmış varsay)
    diff_obj = BatchDiff.objects.filter(batch_id=batch_id).first()
    diff = diff_obj.diff_json if diff_obj else None
    if not diff:
        # güvenlik için yeniden hesaplamak istenirse diff_service.compute_diff çağrılabilir
        from app.services.diff_service import compute_diff
        diff = compute_diff(batch_id)

    added = diff.get('added', [])
    removed = diff.get('removed', [])
    changed = diff.get('changed', [])

    # 1) ADDED → LawyerPerson'a ekle (her avukat için bağımsız)
    for row in added:
        ks = row['kisi_sicilno']

        # Person referansı oluştur/al (sadece sicilno için)
        p, _ = Person.objects.get_or_create(
            kisi_sicilno=ks,
            defaults={'ad': row.get('ad', ''), 'soyad': row.get('soyad', '')}
        )

        # Status objesini al
        key = row.get('cevap_status_key')
        status_obj = StatusOption.objects.filter(key=key).first() if key else None

        # KRITIK: LawyerPerson'a yaz - bu avukat için bağımsız kopya
        LawyerPerson.objects.update_or_create(
            lawyer_id=batch.lawyer_id,
            kisi_sicilno=ks,
            defaults={
                'person': p,
                'ad': row.get('ad', ''),
                'soyad': row.get('soyad', ''),
                'telno': row.get('telno'),
                'mail': row.get('mail'),
                'ilce': row.get('ilce'),
                'adres_aciklama': row.get('adres_aciklama'),
                'notlar': row.get('notlar'),
                'cevap_status': status_obj,
                'active': True
            }
        )

    # 2) REMOVED → Bu avukattan kaldır (hard delete veya soft delete)
    for row in removed:
        ks = row['kisi_sicilno']
        LawyerPerson.objects.filter(
            lawyer_id=batch.lawyer_id,
            kisi_sicilno=ks
        ).delete()

    # 3) CHANGED → LawyerPerson alanlarını güncelle (sadece bu avukat için)
    for item in changed:
        ks = item['kisi_sicilno']
        after = item['after']

        # Person referansı
        p, _ = Person.objects.get_or_create(
            kisi_sicilno=ks,
            defaults={'ad': after.get('ad', ''), 'soyad': after.get('soyad', '')}
        )

        # Status objesini al
        key = after.get('cevap_status_key')
        status_obj = StatusOption.objects.filter(key=key).first() if key else None

        # KRITIK: Sadece bu avukatın LawyerPerson kaydını güncelle
        LawyerPerson.objects.update_or_create(
            lawyer_id=batch.lawyer_id,
            kisi_sicilno=ks,
            defaults={
                'person': p,
                'ad': after.get('ad', ''),
                'soyad': after.get('soyad', ''),
                'telno': after.get('telno'),
                'mail': after.get('mail'),
                'ilce': after.get('ilce'),
                'adres_aciklama': after.get('adres_aciklama'),
                'notlar': after.get('notlar'),
                'cevap_status': status_obj,
                'active': True
            }
        )

    # audit
    AuditLog.objects.create(
        entity='UploadBatch', entity_id=batch.id, action='APPLY',
        before_json={'status': batch.status}, after_json={'status': UploadBatch.APPLIED}, actor=actor
    )
    batch.status = UploadBatch.APPLIED
    batch.save(update_fields=['status'])

    return {"ok": True, "message": "Uygulandı", "counts": diff.get('counts', {})}
