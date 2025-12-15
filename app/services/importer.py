import os
import tempfile
from pathlib import Path
from typing import Tuple, Dict, List

import pandas as pd
from django.db import transaction

from app.models import UploadBatch, UploadRowStaging, Lawyer, StatusOption, BaroLawyer
from app.utils.normalization import normalize_email, normalize_phone
from app.utils.file_validators import (
    validate_upload_file,
    validate_dataframe_structure,
    validate_dataframe_data,
    validate_sicil_no,
    ValidationError
)

# ESKİ FORMAT: Tüm alanlar mevcut, BaroLawyer'den eksik alanlar tamamlanır
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

        # 8) satırları staging'e yaz - BaroLawyer tamamlama ile
        rows = []
        skipped_rows = []
        missing_in_baro = []  # Baro'da bulunamayan siciller
        completed_from_baro = []  # Baro'dan tamamlanan alanlar

        for idx, r in df.iterrows():
            row_num = idx + 2  # Excel satır numarası

            ks = str(r.get('kisi_sicilno') or r.get('sicilno') or '').strip()

            # Excel'den bilgileri al
            excel_ad = str(r.get('ad') or '').strip()
            excel_soyad = str(r.get('soyad') or '').strip()
            excel_telno = r.get('telno')
            excel_mail = r.get('mail')
            excel_ilce = r.get('ilce')
            excel_adres = r.get('adres_aciklama')
            excel_notlar = r.get('notlar')
            excel_status = str(r.get('cevap_status_key')).lower() if r.get('cevap_status_key') else None

            # Zorunlu alanlar kontrolü
            if not ks or not excel_ad or not excel_soyad:
                skipped_rows.append(row_num)
                continue

            # Sicil no validasyonu
            is_valid, error_msg = validate_sicil_no(ks)
            if not is_valid:
                skipped_rows.append(row_num)
                continue

            # BaroLawyer'den eksik bilgileri tamamla
            try:
                baro_lawyer = BaroLawyer.objects.get(sicil_no=ks)

                # Excel'de boş olanları Baro'dan al
                ad = excel_ad or baro_lawyer.ad or ''
                soyad = excel_soyad or baro_lawyer.soyad or ''
                telno = excel_telno or baro_lawyer.tel or None
                mail = excel_mail or baro_lawyer.mail or None
                adres_aciklama = excel_adres or baro_lawyer.adres or None
                ilce = excel_ilce  # İlçe sadece Excel'den

                # Baro'dan tamamlanan alan varsa kaydet
                if not excel_telno and baro_lawyer.tel:
                    completed_from_baro.append(f"Satır {row_num} ({ks}): Telefon")
                if not excel_mail and baro_lawyer.mail:
                    completed_from_baro.append(f"Satır {row_num} ({ks}): E-posta")
                if not excel_adres and baro_lawyer.adres:
                    completed_from_baro.append(f"Satır {row_num} ({ks}): Adres")

            except BaroLawyer.DoesNotExist:
                # Baro'da bulunamadı - sadece Excel'den al ve uyar
                missing_in_baro.append((row_num, ks))
                ad = excel_ad
                soyad = excel_soyad
                telno = excel_telno
                mail = excel_mail
                ilce = excel_ilce
                adres_aciklama = excel_adres

            rows.append(UploadRowStaging(
                batch=batch,
                kisi_sicilno=ks,
                ad=ad,
                soyad=soyad,
                telno=telno,
                mail=mail,
                ilce=ilce,
                adres_aciklama=adres_aciklama,
                notlar=excel_notlar,
                cevap_status_key=excel_status
            ))

        # Hiç geçerli satır yoksa
        if not rows:
            batch.delete()  # Boş batch oluşturma
            error_details = []
            if len(df) > 0:
                error_details.append(f"Toplam {len(df)} satır kontrol edildi, hepsi geçersiz")
            if missing_in_baro:
                error_details.append(f"{len(missing_in_baro)} sicil no Baro kayıtlarında bulunamadı")
                for row_num, sicil in missing_in_baro[:5]:
                    error_details.append(f"  • Satır {row_num}: {sicil}")
            raise ValidationError("Dosyada geçerli kayıt bulunamadı", error_details)

        # 9) Bulk insert
        UploadRowStaging.objects.bulk_create(rows, batch_size=1000)
        batch.row_count = len(rows)

        # Batch notları - Baro bilgilendirmeleri
        notes_parts = []
        if missing_in_baro:
            notes_parts.append(f"⚠️ {len(missing_in_baro)} sicil no Baro kayıtlarında bulunamadı")
        if completed_from_baro:
            notes_parts.append(f"✓ {len(completed_from_baro)} alan Baro kayıtlarından tamamlandı")

        if notes_parts:
            batch.notes = " | ".join(notes_parts)

        batch.save(update_fields=['row_count', 'notes'])

        # 10) Yeni status seçeneklerini seed et
        keys = {r.cevap_status_key for r in rows if r.cevap_status_key}
        if keys:
            existing = set(StatusOption.objects.filter(key__in=keys).values_list('key', flat=True))
            for key in (keys - existing):
                StatusOption.objects.get_or_create(key=key, defaults={'label': key})

        # Sonuç tuple'ına bilgi ekle
        result_info = {
            'batch_id': batch.id,
            'row_count': batch.row_count,
            'missing_in_baro_count': len(missing_in_baro),
            'missing_in_baro': missing_in_baro[:10]  # İlk 10'unu döndür
        }
        return batch.id, batch.row_count
    finally:
        # Geçici dosyayı temizle
        try:
            os.unlink(file_path)
        except:
            pass
