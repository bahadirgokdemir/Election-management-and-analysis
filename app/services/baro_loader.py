"""
Aktif.xlsx dosyasından baro kayıtlarını yükleyen modül
"""
import pandas as pd
from pathlib import Path
from typing import List, Dict


class BaroRecord:
    """Bir avukat kaydını temsil eder"""
    def __init__(self, data: Dict):
        def safe_str(val, default=''):
            if pd.isna(val) if not isinstance(val, str) else False:
                return default
            s = str(val).strip()
            return s if s.lower() not in ('nan', 'none', '') else default

        def safe_date(val):
            if pd.isna(val) if not isinstance(val, str) else False:
                return ''
            s = str(val).strip()
            if s.lower() in ('nan', 'none', ''):
                return ''
            # datetime objects
            if hasattr(val, 'strftime'):
                return val.strftime('%Y-%m-%d')
            return s[:10] if len(s) >= 10 else s

        raw_sicil = data.get('SICIL NO', data.get('SICIL_NO', ''))
        if pd.notna(raw_sicil) if not isinstance(raw_sicil, str) else True:
            if isinstance(raw_sicil, (int, float)):
                self.sicil_no = str(int(raw_sicil)).strip()
            else:
                self.sicil_no = str(raw_sicil).strip()
        else:
            self.sicil_no = ''

        self.ad = safe_str(data.get('ADI', data.get('AD', '')))
        self.soyad = safe_str(data.get('SOYADI', data.get('SOYAD', '')))
        self.tel = safe_str(data.get('CEP TELEFONU', data.get('CEP_TELEFONU', '')))
        self.mail = safe_str(data.get('E-POSTA', data.get('EPOSTA', data.get('MAIL', ''))))
        self.adres = safe_str(data.get('ADRES', ''))
        self.uye = safe_str(data.get('UYE', data.get('ÜYE', '')))
        self.cinsiyet = safe_str(data.get('CINSIYETI', data.get('CİNSİYETİ', '')))
        self.mesleğe_baslama = safe_date(data.get('MESLEĞE BAŞLAMA', data.get('MESLEGE_BASLAMA', '')))
        self.ilce = safe_str(data.get('ILCE', data.get('İLÇE', '')))
        self.dogum_yeri = safe_str(data.get('DOGUM YERI', data.get('DOĞUM YERİ', '')))
        self.dogum_tarihi = safe_date(data.get('DOGUM TARIHI', data.get('DOĞUM TARİHİ', '')))
        self.mahalle_koy = safe_str(data.get('MAHALLE/KOY', data.get('MAHALLE/KÖY', '')))
        self.nufus_ilce = safe_str(data.get('NUFUS ILCE', data.get('NÜFUS İLÇE', '')))
        self.nufus_il = safe_str(data.get('NUFUS IL', data.get('NÜFUS İL', '')))

    def is_valid(self) -> bool:
        if not self.sicil_no or not self.ad or not self.soyad:
            return False
        if not self.sicil_no.isdigit():
            return False
        if self.ad.isdigit() or self.soyad.isdigit():
            return False
        return True

    def to_dict(self) -> Dict:
        return {
            'sicil_no': self.sicil_no,
            'ad': self.ad,
            'soyad': self.soyad,
            'tel': self.tel,
            'mail': self.mail,
            'adres': self.adres,
            'uye': self.uye,
            'cinsiyet': self.cinsiyet,
            'mesleğe_baslama': self.mesleğe_baslama,
            'ilce': self.ilce,
            'dogum_yeri': self.dogum_yeri,
            'dogum_tarihi': self.dogum_tarihi,
            'mahalle_koy': self.mahalle_koy,
            'nufus_ilce': self.nufus_ilce,
            'nufus_il': self.nufus_il,
        }


class BaroLoader:
    """Excel dosyasından baro kayıtlarını yükler"""

    _cache = None
    _cache_file_path = None

    def __init__(self, file_path: str = None):
        if file_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            file_path = base_dir / 'Aktif.xlsx'
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Excel dosyası bulunamadı: {self.file_path}")

    def load_records(self, use_cache: bool = True) -> List[BaroRecord]:
        if use_cache and BaroLoader._cache is not None and BaroLoader._cache_file_path == str(self.file_path):
            return BaroLoader._cache

        try:
            df = pd.read_excel(self.file_path)

            # Normalize column names - uppercase and strip
            col_map = {}
            for col in df.columns:
                col_map[col] = col.strip().upper()
            df.rename(columns=col_map, inplace=True)

            records = []
            for idx, row in df.iterrows():
                try:
                    record = BaroRecord(row.to_dict())
                    if record.is_valid():
                        records.append(record)
                except Exception as e:
                    print(f"Satır {idx + 2} işlenirken hata: {e}")
                    continue

            if use_cache:
                BaroLoader._cache = records
                BaroLoader._cache_file_path = str(self.file_path)

            return records

        except Exception as e:
            raise Exception(f"Excel dosyası okunurken hata oluştu: {e}")

    def get_statistics(self) -> Dict:
        records = self.load_records()
        return {
            'total_records': len(records),
            'with_email': sum(1 for r in records if r.mail),
            'with_phone': sum(1 for r in records if r.tel),
            'with_address': sum(1 for r in records if r.adres),
        }
