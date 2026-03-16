import os
import tempfile
from pathlib import Path
from typing import Tuple, Dict, List, Optional

import pandas as pd
from django.db import transaction

from app.models import UploadBatch, UploadRowStaging, Lawyer, StatusOption, BaroLawyer
from app.utils.normalization import normalize_email, normalize_phone
from app.utils.file_validators import (
    validate_upload_file,
    validate_sicil_no,
    ValidationError
)

# Minimum gerekli kolon - sadece sicilno zorunlu, ad/soyad Baro'dan tamamlanabilir
REQUIRED_COLS = ["sicilno"]

# Türkçe karakter → ASCII eşlemesi (isim karşılaştırması için)
_TR_MAP = str.maketrans('İŞĞÜÖÇışğüöç', 'ISGUOCisgüoc'.replace('ü', 'U').replace('ö', 'O').replace('ç', 'C'))
_TR_MAP = str.maketrans({
    'İ': 'I', 'Ş': 'S', 'Ğ': 'G', 'Ü': 'U', 'Ö': 'O', 'Ç': 'C',
    'ı': 'I', 'ş': 'S', 'ğ': 'G', 'ü': 'U', 'ö': 'O', 'ç': 'C',
})


def _normalize_name(name: str) -> str:
    """İsim karşılaştırması için normalize et (büyük harf, Türkçe karakter, boşluk)."""
    if not name:
        return ""
    return name.strip().upper().translate(_TR_MAP)

# Tüm kabul edilen kolon isimleri
HEADER_MAP = {
    # gelen sütun adını → standart alan
    'sicilno': 'kisi_sicilno',
    'sicil_no': 'kisi_sicilno',
    'sicil no': 'kisi_sicilno',
    'kisi_sicilno': 'kisi_sicilno',
    'ad': 'ad',
    'soyad': 'soyad',
    'cevapdurumu': 'cevap_status_key',
    'cevap_durumu': 'cevap_status_key',
    'cevap durumu': 'cevap_status_key',
    'durum': 'cevap_status_key',
    'telno': 'telno',
    'tel_no': 'telno',
    'tel': 'telno',
    'telefon': 'telno',
    'mail': 'mail',
    'email': 'mail',
    'e-posta': 'mail',
    'eposta': 'mail',
    'ilce': 'ilce',
    'ilçe': 'ilce',
    'adres': 'adres_aciklama',
    'adres_aciklama': 'adres_aciklama',
    'notlar': 'notlar',
    'not': 'notlar',
    'aciklama': 'notlar',
}


def _detect_header_row(df_raw: pd.DataFrame) -> int:
    """
    Excel'de başlık satırını tespit eder.
    Başlık satırı: sicilno/sicil_no/sicil no içeren satır
    """
    header_keywords = ['sicilno', 'sicil_no', 'sicil no', 'kisi_sicilno']

    for idx in range(min(10, len(df_raw))):  # İlk 10 satıra bak
        row_values = [str(v).strip().lower() for v in df_raw.iloc[idx] if pd.notna(v)]
        for keyword in header_keywords:
            if any(keyword in val for val in row_values):
                return idx
    return 0  # Bulunamazsa ilk satır başlık kabul edilir


def _is_data_row(row_values: list) -> bool:
    """
    Satırın veri satırı olup olmadığını kontrol eder.
    Veri satırı: İlk hücrede sayısal sicil no benzeri değer var
    """
    if not row_values:
        return False
    first_val = str(row_values[0]).strip()
    # Sicil no genelde sayı veya sayı ile başlar
    return first_val.isdigit() or (len(first_val) >= 3 and first_val[0].isdigit())


def _read_to_df(file_path: str) -> Tuple[pd.DataFrame, Dict]:
    """
    Excel/CSV dosyasını akıllıca okur.

    Desteklenen formatlar:
    1. Basit format: İlk satır başlık, ikinci satırdan itibaren veri
    2. Gönderici formatlı: Üstte avukat bilgileri, sonra başlık ve veri
    3. Özel formatlar: VEYSEL, ÖN SEÇİM gibi başlıklı dosyalar

    :return: (dataframe, lawyer_info_dict)
    """
    suffix = Path(file_path).suffix.lower()
    lawyer_info = {}

    if suffix in ('.xlsx', '.xlsm', '.xltx', '.xltm', '.xls'):
        # Önce tüm dosyayı header olmadan oku
        try:
            df_raw = pd.read_excel(file_path, engine='openpyxl', header=None, nrows=20)
        except Exception:
            # Eski xls formatı için xlrd dene
            df_raw = pd.read_excel(file_path, header=None, nrows=20)

        if df_raw.empty:
            raise ValueError("Dosya boş veya okunamıyor")

        first_cell = str(df_raw.iloc[0, 0]) if pd.notna(df_raw.iloc[0, 0]) else ""
        first_cell_upper = first_cell.upper().strip()

        # Format 1: Modern minimal format - "Gönderici Bilgileri"
        if "GÖNDERİCİ" in first_cell_upper or "GÖNDEREN" in first_cell_upper:
            try:
                lawyer_info['sicil_no'] = str(df_raw.iloc[1, 0]).strip() if pd.notna(df_raw.iloc[1, 0]) else None
                lawyer_info['ad'] = str(df_raw.iloc[1, 1]).strip() if pd.notna(df_raw.iloc[1, 1]) else None
                lawyer_info['soyad'] = str(df_raw.iloc[1, 2]).strip() if pd.notna(df_raw.iloc[1, 2]) else None
                lawyer_info['telno'] = str(df_raw.iloc[1, 3]).strip() if pd.notna(df_raw.iloc[1, 3]) else None
                lawyer_info['mail'] = str(df_raw.iloc[1, 4]).strip() if pd.notna(df_raw.iloc[1, 4]) else None
            except:
                pass
            df = pd.read_excel(file_path, engine='openpyxl', skiprows=5)

        # Format 2: VEYSEL/ÖN SEÇİM formatlı
        elif "VEYSEL" in first_cell_upper or "ÖN SEÇİM" in first_cell_upper:
            try:
                lawyer_info['sicil_no'] = str(df_raw.iloc[3, 0]).strip() if pd.notna(df_raw.iloc[3, 0]) else None
                lawyer_info['ad'] = str(df_raw.iloc[3, 1]).strip() if pd.notna(df_raw.iloc[3, 1]) else None
                lawyer_info['soyad'] = str(df_raw.iloc[3, 2]).strip() if pd.notna(df_raw.iloc[3, 2]) else None
                lawyer_info['telno'] = str(df_raw.iloc[3, 3]).strip() if pd.notna(df_raw.iloc[3, 3]) else None
                lawyer_info['mail'] = str(df_raw.iloc[3, 4]).strip() if pd.notna(df_raw.iloc[3, 4]) else None
            except:
                pass
            df = pd.read_excel(file_path, engine='openpyxl', skiprows=7)

        else:
            # Format 3: Basit format - Başlık satırını bul
            header_row = _detect_header_row(df_raw)

            # Başlığı bulduktan sonra veriyi oku
            try:
                df = pd.read_excel(file_path, engine='openpyxl', header=header_row)
            except Exception:
                df = pd.read_excel(file_path, header=header_row)

    elif suffix in ('.csv', '.txt'):
        # CSV için de başlık satırını tespit et
        try:
            df_raw = pd.read_csv(file_path, header=None, nrows=10)
            header_row = _detect_header_row(df_raw)
            df = pd.read_csv(file_path, header=header_row)
        except Exception:
            # Encoding sorunu varsa farklı encoding'ler dene
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1254']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    break
                except:
                    continue
            else:
                raise ValueError("CSV dosyası okunamadı - encoding sorunu olabilir")
    else:
        raise ValueError(f"Desteklenmeyen dosya türü: {suffix}")

    # Kolon adlarını normalize et
    df.columns = [str(c).strip().lower().replace('ı', 'i').replace('İ', 'i') for c in df.columns]

    # Boş satırları temizle
    df = df.dropna(how='all')

    return df, lawyer_info


def _find_column(df: pd.DataFrame, target: str) -> Optional[str]:
    """DataFrame'de hedef kolonu bul (farklı isimlendirmelerle)"""
    target_lower = target.lower().replace('ı', 'i')

    # Direkt eşleşme
    for col in df.columns:
        col_normalized = str(col).lower().replace('ı', 'i').replace(' ', '').replace('_', '')
        target_normalized = target_lower.replace(' ', '').replace('_', '')
        if col_normalized == target_normalized:
            return col

    # HEADER_MAP'teki eşleşmeler
    for header_key, mapped_name in HEADER_MAP.items():
        if mapped_name == target or header_key == target:
            header_normalized = header_key.replace(' ', '').replace('_', '')
            for col in df.columns:
                col_normalized = str(col).lower().replace('ı', 'i').replace(' ', '').replace('_', '')
                if col_normalized == header_normalized:
                    return col
    return None


def _ensure_required(df: pd.DataFrame) -> List[str]:
    """
    Gerekli kolonları kontrol eder.
    Eksik kolonları döndürür (boş liste = tüm kolonlar mevcut).
    Sadece sicilno zorunlu - ad/soyad Baro'dan tamamlanabilir.
    """
    # Sicilno kolonunu bul (farklı isimlendirmelerle)
    sicil_col = _find_column(df, 'kisi_sicilno')
    if not sicil_col:
        sicil_col = _find_column(df, 'sicilno')
    if not sicil_col:
        sicil_col = _find_column(df, 'sicil_no')

    if not sicil_col:
        return ['sicilno']

    return []


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame kolonlarını standart isimlere eşler.
    Esnek eşleştirme: boşluk, alt çizgi, büyük/küçük harf farklarını tolere eder.
    """
    mapped = {}

    for col in df.columns:
        # Kolon adını normalize et
        key = str(col).replace('ı', 'i').replace('İ', 'i').lower()
        key = key.replace('.', '').replace(' ', '').replace('_', '').strip()

        # Direkt eşleşme
        if key in HEADER_MAP:
            mapped[HEADER_MAP[key]] = df[col]
        else:
            # Alternatif eşleşmeler
            for header_key, mapped_name in HEADER_MAP.items():
                header_normalized = header_key.replace(' ', '').replace('_', '')
                if key == header_normalized:
                    mapped[mapped_name] = df[col]
                    break

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
def parse_and_stage(uploaded_file, lawyer_id: int, created_by: str = None) -> Tuple[int, int, list]:
    """
    Yüklenen dosyayı geçici olarak işler, veritabanına yazar.

    Esnek validasyon:
    - Sadece sicilno zorunlu
    - Ad/soyad eksikse Baro'dan tamamlanır
    - Telefon, mail, adres opsiyonel - Baro'dan tamamlanabilir
    - Boş satırlar otomatik atlanır

    :return: (batch_id, row_count, name_mismatches)
             name_mismatches: [{'kisi_sicilno', 'row_num', 'excel_ad', 'excel_soyad', 'baro_ad', 'baro_soyad'}, ...]
    :raises ValidationError: Ciddi validasyon hatası durumunda
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
        # 2) Avukat doğrula
        try:
            lawyer = Lawyer.objects.select_for_update().get(id=lawyer_id)
        except Lawyer.DoesNotExist:
            raise ValidationError(f"Avukat bulunamadı (ID: {lawyer_id})")

        # 3) Dosyayı oku
        try:
            df_raw, lawyer_info_from_excel = _read_to_df(file_path)
        except Exception as e:
            raise ValidationError(f"Dosya okunamadı: {str(e)}")

        # Debug: DataFrame içeriğini kontrol et
        if df_raw.empty:
            raise ValidationError("Dosya boş veya okunabilir veri içermiyor")

        # Excel'den avukat bilgileri geldiyse, mevcut avukatı güncelle
        if lawyer_info_from_excel and lawyer_info_from_excel.get('sicil_no'):
            excel_sicil = lawyer_info_from_excel['sicil_no']
            excel_ad = lawyer_info_from_excel.get('ad')
            excel_soyad = lawyer_info_from_excel.get('soyad')

            if excel_sicil and excel_ad and excel_soyad:
                if not lawyer.sicil_no or lawyer.sicil_no != excel_sicil:
                    lawyer.sicil_no = excel_sicil
                if not lawyer.ad or lawyer.ad != excel_ad:
                    lawyer.ad = excel_ad
                if not lawyer.soyad or lawyer.soyad != excel_soyad:
                    lawyer.soyad = excel_soyad
                if lawyer_info_from_excel.get('telno'):
                    lawyer.telno = normalize_phone(lawyer_info_from_excel['telno'])
                if lawyer_info_from_excel.get('mail'):
                    lawyer.mail = normalize_email(lawyer_info_from_excel['mail'])
                lawyer.save()

        # 4) Gerekli kolon kontrolü
        missing_cols = _ensure_required(df_raw)
        if missing_cols:
            available_cols = list(df_raw.columns)
            raise ValidationError(
                f"Gerekli sütun bulunamadı: sicilno",
                [f"Mevcut sütunlar: {', '.join(available_cols)}"]
            )

        # 5) Batch oluştur
        batch = UploadBatch.objects.create(
            lawyer=lawyer,
            original_filename=uploaded_file.name,
            file_path=None,
            row_count=0,
            status=UploadBatch.STAGED,
            created_by=created_by,
        )

        # 6) Kolonları eşle ve normalize et
        df = _map_columns(df_raw)
        df = _normalize_df(df)

        # 7) Satırları işle - BaroLawyer ile akıllı tamamlama
        rows = []
        skipped_rows = []
        missing_in_baro = []
        completed_from_baro = []
        validation_warnings = []
        name_mismatches = []  # Sicil no - isim uyuşmazlıkları (staging'e eklenmeyen)

        for idx, r in df.iterrows():
            row_num = idx + 2  # Excel satır numarası (1 başlık)

            # Sicil no al
            ks = str(r.get('kisi_sicilno') or '').strip()

            # Boş satırları atla
            if not ks or ks == 'nan' or ks == 'None':
                continue

            # Sicil no validasyonu (esnek)
            ks_clean = ks.replace('.0', '')  # Float'tan gelen .0'ları temizle
            if not ks_clean or len(ks_clean) < 1:
                skipped_rows.append((row_num, "Sicil no boş"))
                continue

            # Excel'den bilgileri al
            excel_ad = _clean_value(r.get('ad'))
            excel_soyad = _clean_value(r.get('soyad'))

            # Fix: Bazı listelerde "Ad Soyad" full name ad kolonuna, "Soyad" ise soyad kolonuna yazılır.
            # Örn: ad="AHMET YILMAZ", soyad="YILMAZ" → ad="AHMET", soyad="YILMAZ"
            if excel_ad and excel_soyad:
                norm_ad = _normalize_name(excel_ad).upper().strip()
                norm_soyad = _normalize_name(excel_soyad).upper().strip()
                if norm_ad.endswith(' ' + norm_soyad) and len(norm_ad) > len(norm_soyad) + 1:
                    # ad alanı "FirstName LastName" formatında, son kelimesi soyad ile aynı
                    excel_ad = excel_ad.strip()[:-(len(excel_soyad))].strip()

            excel_telno = _clean_value(r.get('telno'))
            excel_mail = _clean_value(r.get('mail'))
            excel_ilce = _clean_value(r.get('ilce'))
            excel_adres = _clean_value(r.get('adres_aciklama'))
            excel_notlar = _clean_value(r.get('notlar'))
            excel_status = _clean_value(r.get('cevap_status_key'))
            if excel_status:
                excel_status = excel_status.lower()

            # BaroLawyer'den eksik bilgileri tamamla ve isim doğrulaması yap
            baro_lawyer = None
            try:
                baro_lawyer = BaroLawyer.objects.get(sicil_no=ks_clean)
            except BaroLawyer.DoesNotExist:
                missing_in_baro.append((row_num, ks_clean))

            # --- İSİM / SOYİSİM DOĞRULAMASI ---
            # Excel'de isim varsa ve Baro'da bu sicil varsa: karşılaştır.
            # Her ikisinde de isim varsa, normalize edilmiş hallerini eşleştir.
            if baro_lawyer and (excel_ad or excel_soyad):
                baro_ad_norm = _normalize_name(baro_lawyer.ad)
                baro_soyad_norm = _normalize_name(baro_lawyer.soyad)
                excel_ad_norm = _normalize_name(excel_ad or '')
                excel_soyad_norm = _normalize_name(excel_soyad or '')

                ad_mismatch = excel_ad_norm and (excel_ad_norm != baro_ad_norm)
                soyad_mismatch = excel_soyad_norm and (excel_soyad_norm != baro_soyad_norm)

                if ad_mismatch or soyad_mismatch:
                    name_mismatches.append({
                        'kisi_sicilno': ks_clean,
                        'row_num': row_num,
                        'excel_ad': excel_ad or '',
                        'excel_soyad': excel_soyad or '',
                        'baro_ad': baro_lawyer.ad,
                        'baro_soyad': baro_lawyer.soyad,
                    })
                    skipped_rows.append((row_num, (
                        f"İsim uyuşmazlığı: Listedeki '{excel_ad} {excel_soyad}' "
                        f"≠ Baro'daki '{baro_lawyer.ad} {baro_lawyer.soyad}'"
                    )))
                    continue  # Bu satırı staging'e EKLEME

            # Ad/Soyad: Excel > Baro > Boş bırak
            ad = excel_ad
            soyad = excel_soyad

            if baro_lawyer:
                if not ad and baro_lawyer.ad:
                    ad = baro_lawyer.ad
                    completed_from_baro.append(f"Satır {row_num}: Ad")
                if not soyad and baro_lawyer.soyad:
                    soyad = baro_lawyer.soyad
                    completed_from_baro.append(f"Satır {row_num}: Soyad")

            # Ad/soyad hala boşsa uyar ama devam et
            if not ad or not soyad:
                validation_warnings.append(f"Satır {row_num} ({ks_clean}): Ad veya soyad eksik")
                if not ad:
                    ad = "Bilinmiyor"
                if not soyad:
                    soyad = "Bilinmiyor"

            # Diğer alanları tamamla
            telno = excel_telno
            mail = excel_mail
            ilce = excel_ilce
            adres_aciklama = excel_adres

            if baro_lawyer:
                if not telno and baro_lawyer.tel:
                    telno = baro_lawyer.tel
                    completed_from_baro.append(f"Satır {row_num}: Telefon")
                if not mail and baro_lawyer.mail:
                    mail = baro_lawyer.mail
                    completed_from_baro.append(f"Satır {row_num}: E-posta")
                if not adres_aciklama and baro_lawyer.adres:
                    adres_aciklama = baro_lawyer.adres
                    completed_from_baro.append(f"Satır {row_num}: Adres")

            rows.append(UploadRowStaging(
                batch=batch,
                kisi_sicilno=ks_clean,
                ad=ad,
                soyad=soyad,
                telno=telno,
                mail=mail,
                ilce=ilce,
                adres_aciklama=adres_aciklama,
                notlar=excel_notlar,
                cevap_status_key=excel_status
            ))

        # 8) Hiç geçerli satır yoksa hata ver
        if not rows:
            batch.delete()
            error_details = [f"DataFrame'de {len(df)} satır bulundu"]
            if skipped_rows:
                error_details.append(f"{len(skipped_rows)} satır atlandı:")
                for row_info in skipped_rows[:5]:
                    if isinstance(row_info, tuple):
                        error_details.append(f"  • Satır {row_info[0]}: {row_info[1]}")
                    else:
                        error_details.append(f"  • Satır {row_info}")
            error_details.append(f"Mevcut kolonlar: {', '.join(df.columns)}")
            raise ValidationError("Dosyada geçerli kayıt bulunamadı", error_details)

        # 9) Bulk insert
        UploadRowStaging.objects.bulk_create(rows, batch_size=1000)
        batch.row_count = len(rows)

        # Batch notları
        notes_parts = []
        if missing_in_baro:
            notes_parts.append(f"{len(missing_in_baro)} sicil Baro'da bulunamadı")
        if completed_from_baro:
            notes_parts.append(f"{len(set(completed_from_baro))} alan Baro'dan tamamlandı")
        if validation_warnings:
            notes_parts.append(f"{len(validation_warnings)} uyarı")
        if name_mismatches:
            notes_parts.append(f"{len(name_mismatches)} kişi isim uyuşmazlığı nedeniyle eklenmedi")

        if notes_parts:
            batch.notes = " | ".join(notes_parts)

        batch.save(update_fields=['row_count', 'notes'])

        # 10) Status seçeneklerini seed et
        keys = {r.cevap_status_key for r in rows if r.cevap_status_key}
        if keys:
            existing = set(StatusOption.objects.filter(key__in=keys).values_list('key', flat=True))
            for key in (keys - existing):
                StatusOption.objects.get_or_create(key=key, defaults={'label': key.title()})

        return batch.id, batch.row_count, name_mismatches

    finally:
        # Geçici dosyayı temizle
        try:
            os.unlink(file_path)
        except:
            pass


def _clean_value(val) -> Optional[str]:
    """Değeri temizle - None, nan, boş string kontrolü"""
    if val is None:
        return None
    if pd.isna(val):
        return None
    val_str = str(val).strip()
    if val_str.lower() in ('nan', 'none', 'null', ''):
        return None
    return val_str
