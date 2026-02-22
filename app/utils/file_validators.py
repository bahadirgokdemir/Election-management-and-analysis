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
    ESNEK VALİDASYON:
    - Boş olamaz
    - Minimum 1 karakter (tek haneli siciller olabilir)
    - Float'tan gelen .0 temizlenir
    """
    if not sicil_no or not str(sicil_no).strip():
        return False, "Sicil No boş olamaz"

    sicil_str = str(sicil_no).strip()

    # Float'tan gelen .0'ları temizle
    if sicil_str.endswith('.0'):
        sicil_str = sicil_str[:-2]

    # nan/None kontrolü
    if sicil_str.lower() in ('nan', 'none', 'null', ''):
        return False, "Sicil No boş olamaz"

    # Minimum uzunluk (esnek - tek haneli olabilir)
    if len(sicil_str) < 1:
        return False, f"Sicil No çok kısa: '{sicil_str}'"

    # Maksimum uzunluk
    if len(sicil_str) > 30:
        return False, f"Sicil No çok uzun: '{sicil_str}' (Maksimum 30 karakter)"

    return True, "OK"


def validate_dataframe_structure(df: pd.DataFrame, required_columns: List[str]) -> Tuple[bool, str, List[str]]:
    """
    DataFrame yapısını kontrol eder.
    - Boş olmamalı
    - Gerekli kolonlar mevcut olmalı (esnek eşleşme)
    - En az bir veri satırı olmalı

    Returns: (success, message, missing_columns)
    """
    # Boş mu?
    if df.empty:
        return False, "Dosya boş veya okunabilir veri içermiyor", []

    # Sütun adlarını normalize et
    normalized_cols = [str(c).strip().lower().replace('ı', 'i').replace(' ', '').replace('_', '') for c in df.columns]

    # Gerekli kolonları kontrol et (esnek eşleşme)
    missing_cols = []
    for col in required_columns:
        col_normalized = col.lower().strip().replace('ı', 'i').replace(' ', '').replace('_', '')
        # Sicilno için alternatif isimler
        sicil_alternatives = ['sicilno', 'sicilno', 'kisisicilno']
        if col_normalized in ['sicilno', 'sicil_no']:
            found = any(nc in sicil_alternatives or 'sicil' in nc for nc in normalized_cols)
        else:
            found = col_normalized in normalized_cols

        if not found:
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
    ESNEK VALİDASYON: Sadece sicilno zorunlu, diğerleri Baro'dan tamamlanabilir.

    Returns: (success, message, errors_list)
        errors_list: [{'row': satır_no, 'field': alan_adı, 'value': değer, 'error': hata_mesajı}]
    """
    warnings = []
    valid_rows = 0

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel'de 1 başlık, 2'den başlar

        # Sicil No kontrolü (tek zorunlu alan)
        sicil = row.get('sicilno') or row.get('kisi_sicilno') or row.get('sicil_no')
        if pd.isna(sicil) or str(sicil).strip() == '' or str(sicil).strip().lower() == 'nan':
            # Boş satır - atla (hata değil)
            continue

        # Sicil no'yu temizle
        sicil_str = str(sicil).strip().replace('.0', '')

        # Minimum uzunluk kontrolü
        if len(sicil_str) < 1:
            warnings.append({
                'row': row_num,
                'field': 'sicilno',
                'value': sicil,
                'error': 'Sicil No çok kısa'
            })
            continue

        # Ad/soyad opsiyonel - uyarı olarak kaydet
        ad = row.get('ad')
        soyad = row.get('soyad')

        if (pd.isna(ad) or str(ad).strip() == '') and (pd.isna(soyad) or str(soyad).strip() == ''):
            warnings.append({
                'row': row_num,
                'field': 'ad/soyad',
                'value': f"ad={ad}, soyad={soyad}",
                'error': 'Ad ve soyad eksik - Baro kayıtlarından tamamlanacak'
            })

        # Email validasyonu (opsiyonel - sadece format kontrolü)
        mail = row.get('mail')
        if mail and not pd.isna(mail) and str(mail).strip() and str(mail).strip().lower() != 'nan':
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, str(mail).strip()):
                warnings.append({
                    'row': row_num,
                    'field': 'mail',
                    'value': mail,
                    'error': f'Geçersiz e-posta formatı (düzeltilecek)'
                })
                # Email hatası kritik değil

        valid_rows += 1

    # Hiç veri yoksa
    if valid_rows == 0:
        return False, "Dosyada geçerli satır bulunamadı", warnings

    # Uyarılar var ama geçerli satırlar da var - başarılı kabul et
    if warnings:
        return True, f"{valid_rows} satır geçerli, {len(warnings)} uyarı", warnings

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
