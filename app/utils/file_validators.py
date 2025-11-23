"""
Dosya ve veri validasyon fonksiyonları
"""
import re
from typing import Tuple, List, Optional
import pandas as pd
from pathlib import Path


class ValidationError(Exception):
    """Validasyon hatası"""
    def __init__(self, message: str, details: Optional[List[str]] = None):
        self.message = message
        self.details = details or []
        super().__init__(self.message)


def validate_file_extension(filename: str) -> Tuple[bool, str]:
    """
    Dosya uzantısını kontrol eder.
    Sadece .xlsx, .xls, .csv uzantılarına izin verilir.
    """
    allowed_extensions = ['.xlsx', '.xls', '.xlsm', '.csv', '.txt']
    suffix = Path(filename).suffix.lower()

    if suffix not in allowed_extensions:
        return False, f"Desteklenmeyen dosya formatı: {suffix}. İzin verilen formatlar: {', '.join(allowed_extensions)}"

    return True, "OK"


def validate_file_size(file_size: int, max_size_mb: int = 10) -> Tuple[bool, str]:
    """
    Dosya boyutunu kontrol eder.
    Default max: 10 MB
    """
    max_size_bytes = max_size_mb * 1024 * 1024

    if file_size > max_size_bytes:
        size_mb = file_size / (1024 * 1024)
        return False, f"Dosya çok büyük: {size_mb:.2f} MB. Maksimum boyut: {max_size_mb} MB"

    if file_size == 0:
        return False, "Dosya boş"

    return True, "OK"


def validate_sicil_no(sicil_no: str) -> Tuple[bool, str]:
    """
    Sicil numarasını validasyon yapar.
    - Boş olamaz
    - Sadece rakam ve harf içerebilir
    - Minimum 3, maksimum 20 karakter
    - Başında/sonunda boşluk olmamalı
    """
    if not sicil_no or not str(sicil_no).strip():
        return False, "Sicil No boş olamaz"

    sicil_str = str(sicil_no).strip()

    # Uzunluk kontrolü
    if len(sicil_str) < 3:
        return False, f"Sicil No çok kısa: '{sicil_str}' (Minimum 3 karakter)"

    if len(sicil_str) > 20:
        return False, f"Sicil No çok uzun: '{sicil_str}' (Maksimum 20 karakter)"

    # Sadece alfanumerik ve bazı özel karakterler (-, /, _)
    if not re.match(r'^[A-Za-z0-9\-/_.]+$', sicil_str):
        return False, f"Sicil No geçersiz karakterler içeriyor: '{sicil_str}'. Sadece harf, rakam, -, /, _ kullanılabilir"

    return True, "OK"


def validate_dataframe_structure(df: pd.DataFrame, required_columns: List[str]) -> Tuple[bool, str, List[str]]:
    """
    DataFrame yapısını kontrol eder.
    - Boş olmamalı
    - Gerekli kolonlar mevcut olmalı
    - En az bir veri satırı olmalı

    Returns: (success, message, missing_columns)
    """
    errors = []

    # Boş mu?
    if df.empty:
        return False, "Dosya boş veya okunabilir veri içermiyor", []

    # Sütun adlarını normalize et (küçük harf, boşluksuz)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Gerekli kolonları kontrol et
    missing_cols = []
    for col in required_columns:
        col_normalized = col.lower().strip()
        if col_normalized not in df.columns:
            missing_cols.append(col)

    if missing_cols:
        return False, f"Gerekli sütunlar eksik: {', '.join(missing_cols)}", missing_cols

    # En az bir satır var mı?
    if len(df) == 0:
        return False, "Dosyada veri satırı bulunamadı", []

    return True, "OK", []


def validate_dataframe_data(df: pd.DataFrame) -> Tuple[bool, str, List[dict]]:
    """
    DataFrame içindeki verileri satır satır kontrol eder.

    Returns: (success, message, errors_list)
        errors_list: [{'row': satır_no, 'field': alan_adı, 'value': değer, 'error': hata_mesajı}]
    """
    errors = []
    valid_rows = 0

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel'de 1 başlık, 2'den başlar

        # Sicil No validasyonu
        sicil = row.get('sicilno') or row.get('kisi_sicilno')
        if pd.isna(sicil) or str(sicil).strip() == '':
            errors.append({
                'row': row_num,
                'field': 'sicilno',
                'value': sicil,
                'error': 'Sicil No boş olamaz'
            })
            continue

        is_valid, error_msg = validate_sicil_no(sicil)
        if not is_valid:
            errors.append({
                'row': row_num,
                'field': 'sicilno',
                'value': sicil,
                'error': error_msg
            })
            continue

        # Ad validasyonu
        ad = row.get('ad')
        if pd.isna(ad) or str(ad).strip() == '':
            errors.append({
                'row': row_num,
                'field': 'ad',
                'value': ad,
                'error': 'Ad boş olamaz'
            })
            continue

        if len(str(ad).strip()) < 2:
            errors.append({
                'row': row_num,
                'field': 'ad',
                'value': ad,
                'error': 'Ad en az 2 karakter olmalı'
            })
            continue

        # Soyad validasyonu
        soyad = row.get('soyad')
        if pd.isna(soyad) or str(soyad).strip() == '':
            errors.append({
                'row': row_num,
                'field': 'soyad',
                'value': soyad,
                'error': 'Soyad boş olamaz'
            })
            continue

        if len(str(soyad).strip()) < 2:
            errors.append({
                'row': row_num,
                'field': 'soyad',
                'value': soyad,
                'error': 'Soyad en az 2 karakter olmalı'
            })
            continue

        # Email validasyonu (opsiyonel ama varsa doğru formatta olmalı)
        mail = row.get('mail')
        if mail and not pd.isna(mail) and str(mail).strip():
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, str(mail).strip()):
                errors.append({
                    'row': row_num,
                    'field': 'mail',
                    'value': mail,
                    'error': f'Geçersiz e-posta formatı: {mail}'
                })
                # Email hatası kritik değil, devam et

        valid_rows += 1

    # Tüm satırlar hatalıysa
    if valid_rows == 0 and errors:
        return False, f"Dosyada geçerli satır bulunamadı. Toplam {len(errors)} hata.", errors

    # Bazı hatalar var ama geçerli satırlar da var
    if errors:
        error_summary = f"{len(errors)} satırda hata bulundu, {valid_rows} satır geçerli."
        # İlk 10 hatayı döndür
        return False, error_summary, errors[:10]

    return True, f"Tüm {valid_rows} satır geçerli", []


def validate_upload_file(uploaded_file, max_size_mb: int = 10) -> Tuple[bool, str, Optional[List[dict]]]:
    """
    Yüklenen dosyanın tüm validasyonlarını yapar.

    Returns: (success, message, error_details)
    """
    # 1. Dosya uzantısı kontrolü
    is_valid, msg = validate_file_extension(uploaded_file.name)
    if not is_valid:
        return False, msg, None

    # 2. Dosya boyutu kontrolü
    is_valid, msg = validate_file_size(uploaded_file.size, max_size_mb)
    if not is_valid:
        return False, msg, None

    return True, "Dosya formatı geçerli", None
