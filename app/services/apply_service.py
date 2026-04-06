from typing import Dict
from django.db import transaction
from django.db.models import Q

from app.models import (
    UploadBatch, UploadRowStaging, LawyerPerson, Person, StatusOption, BatchDiff, AuditLog
)


@transaction.atomic
def apply_diff(batch_id: int, actor: str = None, merge_mode: bool = True) -> Dict:
    """
    Varsayılan: merge_mode=True → yeni listede olmayan eski kayıtlar korunur.
    Status değişimleri AuditLog'a yazılır (geçmiş takibi için).
    """
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

    # 2) REMOVED → Yeni listede olmayanlar
    # Artık her zaman korunur (merge_mode=True default); parametre uyumluluk için bırakıldı
    removed_ks_list = [row['kisi_sicilno'] for row in removed]
    actually_removed = 0
    if removed_ks_list and not merge_mode:
        actually_removed = LawyerPerson.objects.filter(
            lawyer_id=batch.lawyer_id,
            kisi_sicilno__in=removed_ks_list
        ).update(active=False)

    # 3) CHANGED → LawyerPerson alanlarını güncelle + status değişimini logla
    for item in changed:
        ks = item['kisi_sicilno']
        after = item['after']
        before = item['before']

        # Person referansı
        p, _ = Person.objects.get_or_create(
            kisi_sicilno=ks,
            defaults={'ad': after.get('ad', ''), 'soyad': after.get('soyad', '')}
        )

        # Status objesini al
        key = after.get('cevap_status_key')
        status_obj = StatusOption.objects.filter(key=key).first() if key else None

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

        # Cevap durumu değiştiyse AuditLog'a yaz
        old_key = before.get('cevap_status_key') or ''
        new_key = after.get('cevap_status_key') or ''
        if 'cevap_status_key' in item.get('fields', []) and old_key != new_key:
            AuditLog.objects.create(
                entity='StatusChange',
                entity_id=batch_id,
                action='STATUS_CHANGE',
                before_json={
                    'kisi_sicilno': ks,
                    'ad': before.get('ad', ''),
                    'soyad': before.get('soyad', ''),
                    'lawyer_id': batch.lawyer_id,
                    'status': old_key,
                    'batch_id': batch_id,
                },
                after_json={'status': new_key},
                actor=actor,
            )

    # audit
    AuditLog.objects.create(
        entity='UploadBatch', entity_id=batch.id, action='APPLY',
        before_json={'status': batch.status}, after_json={'status': UploadBatch.APPLIED}, actor=actor
    )
    batch.status = UploadBatch.APPLIED
    batch.save(update_fields=['status'])

    base_counts = diff.get('counts', {})
    return {
        "ok": True,
        "message": "Uygulandı",
        "counts": {
            "added": base_counts.get("added", 0),
            "changed": base_counts.get("changed", 0),
            "removed": actually_removed,
            "would_remove": len(removed_ks_list) if merge_mode else 0,
        }
    }
