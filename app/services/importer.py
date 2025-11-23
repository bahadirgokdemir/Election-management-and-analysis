import os
import tempfile
from pathlib import Path
from typing import Tuple, Dict, List

import pandas as pd
from django.db import transaction

from app.models import UploadBatch, UploadRowStaging, Lawyer, StatusOption
from app.utils.normalization import normalize_email, normalize_phone
from app.utils.file_validators import (
    validate_upload_file,
    validate_dataframe_structure,
    validate_dataframe_data,
    validate_sicil_no,
    ValidationError
)

REQUIRED_COLS = ["sicilno", "ad", "soyad"]

HEADER_MAP = {
    # gelen sütun adını → standart alan
    'sicilno': 'kisi_sicilno',
    'ad': 'ad',
    'soyad': 'soyad',
    'cevapdurumu': 'cevap_status_key',
    'telno': 'telno',
    'mail': 'mail',
    'ilce': 'ilce',
    'adres': 'adres_aciklama',
    'adres_aciklama': 'adres_aciklama',
    'notlar': 'notlar',
}


def _read_to_df(file_path: str) -> pd.DataFrame:
    suffix = Path(file_path).suffix.lower()
    if suffix in ('.xlsx', '.xlsm', '.xltx', '.xltm'):
        df = pd.read_excel(file_path, engine='openpyxl')
    elif suffix in ('.csv', '.txt'):
        df = pd.read_csv(file_path)
    else:
        raise ValueError(f"Desteklenmeyen dosya türü: {suffix}")
    # kolon adlarını normalize et
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _ensure_required(df: pd.DataFrame):
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Eksik zorunlu sütun(lar): {', '.join(missing)}")


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapped = {}
    for col in df.columns:
        key = col.replace('ı', 'i').replace('İ', 'i').lower()
        key = key.replace('.', '').replace(' ', '')
        if key in HEADER_MAP:
            mapped[HEADER_MAP[key]] = df[col]
    out = pd.DataFrame(mapped)
    return out


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if 'mail' in df.columns:
        df['mail'] = df['mail'].astype(str).apply(lambda x: normalize_email(x) if x and x != 'nan' else None)
    if 'telno' in df.columns:
        df['telno'] = df['telno'].astype(str).apply(lambda x: normalize_phone(x) if x and x != 'nan' else None)
    for col in df.columns:
        df[col] = df[col].apply(
            lambda x: None if (isinstance(x, float) and pd.isna(x)) or (isinstance(x, str) and x.strip() == '') else x)
    return df


@transaction.atomic
def parse_and_stage(uploaded_file, lawyer_id: int, created_by: str = None) -> Tuple[int, int]:
    """
    Yüklenen dosyayı geçici olarak işler, veritabanına yazar.
    Dosya kalıcı olarak saklanmaz, sadece parse edilir.

    Validasyonlar:
    - Dosya formatı kontrolü (xlsx, csv)
    - Dosya boyutu kontrolü (max 10MB)
    - Gerekli sütunlar kontrolü
    - Sicil no validasyonu
    - Veri satırı validasyonu

    :return: (batch_id, row_count)
    :raises ValidationError: Validasyon hatası durumunda
    """
    # 0) Dosya validasyonu (format ve boyut)
    is_valid, msg, _ = validate_upload_file(uploaded_file, max_size_mb=10)
    if not is_valid:
        raise ValidationError(msg)

    # 1) Geçici dosyaya yaz
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        for chunk in uploaded_file.chunks():
            tmp_file.write(chunk)
        file_path = tmp_file.name

    try:
        # 2) avukat doğrula
        try:
            lawyer = Lawyer.objects.select_for_update().get(id=lawyer_id)
        except Lawyer.DoesNotExist:
            raise ValidationError(f"Avukat bulunamadı (ID: {lawyer_id})")

        # 3) Dosyayı oku
        try:
            df_raw = _read_to_df(file_path)
        except Exception as e:
            raise ValidationError(f"Dosya okunamadı: {str(e)}")

        # 4) DataFrame yapı validasyonu
        is_valid, msg, missing_cols = validate_dataframe_structure(df_raw, REQUIRED_COLS)
        if not is_valid:
            details = [f"Eksik sütunlar: {', '.join(missing_cols)}"] if missing_cols else []
            raise ValidationError(msg, details)

        # 5) DataFrame veri validasyonu
        is_valid, msg, errors = validate_dataframe_data(df_raw)
        if not is_valid:
            error_details = []
            for err in errors[:5]:  # İlk 5 hatayı göster
                error_details.append(
                    f"Satır {err['row']}, {err['field']}: {err['error']} (Değer: '{err['value']}')"
                )
            if len(errors) > 5:
                error_details.append(f"... ve {len(errors) - 5} hata daha")

            raise ValidationError(msg, error_details)

        # 6) batch oluştur
        batch = UploadBatch.objects.create(
            lawyer=lawyer,
            original_filename=uploaded_file.name,
            file_path=None,  # Artık dosya saklanmıyor
            row_count=0,
            status=UploadBatch.STAGED,
            created_by=created_by,
        )

        # 7) kolonları eşle → normalize
        _ensure_required(df_raw)
        df = _map_columns(df_raw)
        df = _normalize_df(df)

        # 8) satırları staging'e yaz
        rows = []
        skipped_rows = []

        for idx, r in df.iterrows():
            row_num = idx + 2  # Excel satır numarası

            ks = str(r.get('kisi_sicilno') or r.get('sicilno') or '').strip()
            ad = str(r.get('ad') or '').strip()
            soyad = str(r.get('soyad') or '').strip()

            # Zorunlu alanlar kontrolü
            if not ks or not ad or not soyad:
                skipped_rows.append(row_num)
                continue

            # Sicil no validasyonu
            is_valid, error_msg = validate_sicil_no(ks)
            if not is_valid:
                skipped_rows.append(row_num)
                continue

            rows.append(UploadRowStaging(
                batch=batch,
                kisi_sicilno=ks,
                ad=ad,
                soyad=soyad,
                telno=r.get('telno'),
                mail=r.get('mail'),
                ilce=r.get('ilce'),
                adres_aciklama=r.get('adres_aciklama'),
                notlar=r.get('notlar'),
                cevap_status_key=(str(r.get('cevap_status_key')).lower() if r.get('cevap_status_key') else None)
            ))

        # Hiç geçerli satır yoksa
        if not rows:
            batch.delete()  # Boş batch oluşturma
            raise ValidationError(
                "Dosyada geçerli kayıt bulunamadı",
                [f"Toplam {len(df)} satır kontrol edildi, hepsi geçersiz"] if len(df) > 0 else []
            )

        # 9) Bulk insert
        UploadRowStaging.objects.bulk_create(rows, batch_size=1000)
        batch.row_count = len(rows)
        batch.save(update_fields=['row_count'])

        # 10) Yeni status seçeneklerini seed et
        keys = {r.cevap_status_key for r in rows if r.cevap_status_key}
        if keys:
            existing = set(StatusOption.objects.filter(key__in=keys).values_list('key', flat=True))
            for key in (keys - existing):
                StatusOption.objects.get_or_create(key=key, defaults={'label': key})

        return batch.id, batch.row_count
    finally:
        # Geçici dosyayı temizle
        try:
            os.unlink(file_path)
        except:
            pass
