# app/services/diff_service.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from django.db.models import Prefetch

from app.models import (
    UploadBatch,  # staging batch
    UploadRowStaging,    # staging rows (parse_and_stage buraya yazar)
    Lawyer, Person, LawyerPerson, StatusOption
)

# Karşılaştırmada kullanılacak alanlar
COMPARE_FIELDS = [
    "ad", "soyad", "mail", "telno", "ilce", "adres_aciklama", "notlar", "cevap_status_key"
]


def _status_key_of_lp(lp: LawyerPerson) -> str:
    """LawyerPerson.cevap_status varsa key'ini döndürür."""
    if lp.cevap_status_id:
        try:
            return lp.cevap_status.key
        except StatusOption.DoesNotExist:  # teorik
            return ""
    return ""


def _snapshot_for_lawyer(lawyer_id: int) -> Dict[str, Dict[str, Any]]:
    """
    Veritabanındaki mevcut (onaylanmış) kayıtlar.
    Dönen sözlük: kisi_sicilno -> alanlar
    ÖNEMLI: Artık LawyerPerson'dan direkt okuyoruz, Person'a bakmıyoruz.
    Her avukatın kendi verisi LawyerPerson'da saklanıyor.
    """
    # Bu avukata bağlı AKTIF kayıtları çek
    lp_qs = LawyerPerson.objects.filter(
        lawyer_id=lawyer_id,
        active=True  # KRITIK: Sadece aktif kayıtlar
    ).select_related("cevap_status")

    result: Dict[str, Dict[str, Any]] = {}

    for lp in lp_qs:
        ks = (lp.kisi_sicilno or "").strip()
        if not ks:
            continue

        result[ks] = {
            "kisi_sicilno": ks,
            "ad": lp.ad or "",
            "soyad": lp.soyad or "",
            "mail": lp.mail or "",
            "telno": lp.telno or "",
            "ilce": lp.ilce or "",
            "adres_aciklama": lp.adres_aciklama or "",
            "notlar": lp.notlar or "",
            "cevap_status_key": _status_key_of_lp(lp) or "",
        }

    return result


def _snapshot_from_batch(batch_id: int) -> Dict[str, Dict[str, Any]]:
    """
    Staging (yeni yüklenen) satırlar.
    Dönen sözlük: kisi_sicilno -> alanlar
    """
    rows = UploadRowStaging.objects.filter(batch_id=batch_id)
    snap: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        ks = (r.kisi_sicilno or "").strip()
        if not ks:
            # Sicil numarası yoksa satır atlanır
            continue

        snap[ks] = {
            "kisi_sicilno": ks,
            "ad": (getattr(r, "ad", "") or "").strip(),
            "soyad": (getattr(r, "soyad", "") or "").strip(),
            "mail": (getattr(r, "mail", "") or "").strip(),
            "telno": (getattr(r, "telno", "") or "").strip(),
            "ilce": (getattr(r, "ilce", "") or "").strip(),
            "adres_aciklama": (getattr(r, "adres_aciklama", "") or "").strip(),
            "notlar": (getattr(r, "notlar", "") or "").strip(),
            "cevap_status_key": (getattr(r, "cevap_status_key", "") or "").strip(),
        }

    return snap


def _field_changed(before: Dict[str, Any], after: Dict[str, Any], field: str) -> bool:
    """Metin alanlarını trim’leyerek karşılaştır; None -> '' normalize et."""
    b = (before.get(field) or "").strip()
    a = (after.get(field) or "").strip()
    return b != a


def _diff_dicts(
    current: Dict[str, Dict[str, Any]],
    new: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    current: mevcut sistem (lawyer'a bağlı kişiler)
    new:     batch'ten gelen yeni liste

    return:
      added[], removed[], changed[]
    """
    cur_keys = set(current.keys())
    new_keys = set(new.keys())

    added_keys = sorted(list(new_keys - cur_keys))
    removed_keys = sorted(list(cur_keys - new_keys))
    inter_keys = sorted(list(cur_keys & new_keys))

    added = [new[k] for k in added_keys]
    removed = [current[k] for k in removed_keys]

    changed: List[Dict[str, Any]] = []
    for ks in inter_keys:
        before = current[ks]
        after = new[ks]
        changed_fields = [f for f in COMPARE_FIELDS if _field_changed(before, after, f)]
        if changed_fields:
            changed.append({
                "kisi_sicilno": ks,
                "fields": changed_fields,
                "before": before,
                "after": after,
            })

    return added, removed, changed


def compute_diff(batch_id: int) -> Dict[str, Any]:
    """
    UI ve apply servislerinin beklediği diff sözlüğü.
    Şema:
    {
      "batchId": ...,
      "lawyer": {"id":..., "sicilNo":"...", "ad":"...", "soyad":"..."},
      "counts": {"added":N1, "removed":N2, "changed":N3},
      "added": [ {row...}, ... ],
      "removed": [ {row...}, ... ],
      "changed": [ { "kisi_sicilno":"...", "fields":[...], "before":{...}, "after":{...} }, ... ]
    }
    """
    batch: UploadBatch = UploadBatch.objects.select_related("lawyer").get(id=batch_id)
    lawyer: Lawyer = batch.lawyer

    current = _snapshot_for_lawyer(lawyer.id)
    new = _snapshot_from_batch(batch_id)

    added, removed, changed = _diff_dicts(current, new)

    return {
        "batchId": batch.id,
        "lawyer": {
            "id": lawyer.id,
            "sicilNo": lawyer.sicil_no,
            "ad": lawyer.ad,
            "soyad": lawyer.soyad,
        },
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }
