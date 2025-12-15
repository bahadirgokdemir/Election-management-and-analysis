"""
Aktif.xlsx dosyasından baro kayıtlarını yükleyen modül
"""
import pandas as pd
from pathlib import Path
from typing import List, Dict
from functools import lru_cache


class BaroRecord:
    """Bir avukat kaydını temsil eder"""
    def __init__(self, data: Dict):
        # Sicil No'yu temizle ve validate et
        raw_sicil = data.get('SICIL NO', '')
        if pd.notna(raw_sicil):
            # Float ise int'e çevir (Excel'den gelebilir)
            if isinstance(raw_sicil, (int, float)):
                self.sicil_no = str(int(raw_sicil)).strip()
            else:
                self.sicil_no = str(raw_sicil).strip()
        else:
            self.sicil_no = ''

        # Ad ve Soyad'ı temizle
        self.ad = str(data.get('ADI', '')).strip() if pd.notna(data.get('ADI')) else ''
        self.soyad = str(data.get('SOYADI', '')).strip() if pd.notna(data.get('SOYADI')) else ''

        # Diğer alanlar
        self.tel = str(data.get('CEP TELEFONU', '')).strip() if pd.notna(data.get('CEP TELEFONU')) else ''
        self.mail = str(data.get('E-POSTA', '')).strip() if pd.notna(data.get('E-POSTA')) else ''
        self.adres = str(data.get('ADRES', '')).strip() if pd.notna(data.get('ADRES')) else ''

    def is_valid(self) -> bool:
        """Kaydın geçerli olup olmadığını kontrol eder"""
        # Sicil no olmalı, numeric olmalı, ad ve soyad olmalı
        if not self.sicil_no or not self.ad or not self.soyad:
            return False

        # Sicil no sadece rakam içermeli (harf varsa geçersiz)
        if not self.sicil_no.isdigit():
            return False

        # Ad ve soyad rakam olamaz (veri karışıklığı kontrolü)
        if self.ad.isdigit() or self.soyad.isdigit():
            return False

        return True

    def to_dict(self) -> Dict:
        """Kayıt bilgilerini sözlük olarak döndürür"""
        return {
            'sicil_no': self.sicil_no,
            'ad': self.ad,
            'soyad': self.soyad,
            'tel': self.tel,
            'mail': self.mail,
            'adres': self.adres,
        }


class BaroLoader:
    """Excel dosyasından baro kayıtlarını yükler"""

    # Cache için sınıf değişkeni
    _cache = None
    _cache_file_path = None

    def __init__(self, file_path: str = None):
        if file_path is None:
            # Proje kök dizinindeki Aktif.xlsx dosyasını kullan
            base_dir = Path(__file__).resolve().parent.parent.parent
            file_path = base_dir / 'Aktif.xlsx'

        self.file_path = Path(file_path)

        if not self.file_path.exists():
            raise FileNotFoundError(f"Excel dosyası bulunamadı: {self.file_path}")

    def load_records(self, use_cache: bool = True) -> List[BaroRecord]:
        """
        Excel dosyasından tüm kayıtları yükler

        Returns:
            List[BaroRecord]: Geçerli kayıtların listesi
        """
        # Cache kontrolü
        if use_cache and BaroLoader._cache is not None and BaroLoader._cache_file_path == str(self.file_path):
            return BaroLoader._cache

        try:
            # Excel dosyasını oku
            df = pd.read_excel(self.file_path)

            # Sütun adlarını normalize et
            column_mapping = {}
            for col in df.columns:
                normalized = col.strip().upper()
                # Türkçe karakter sorunlarını düzelt
                if 'AD' in normalized and 'SOYAD' not in normalized and 'ADRES' not in normalized:
                    column_mapping[col] = 'ADI'
                elif 'SOYAD' in normalized:
                    column_mapping[col] = 'SOYADI'
                elif 'CEP' in normalized or 'TELEFON' in normalized:
                    column_mapping[col] = 'CEP TELEFONU'
                elif 'E-POSTA' in normalized or 'EPOSTA' in normalized or 'MAIL' in normalized:
                    column_mapping[col] = 'E-POSTA'
                else:
                    column_mapping[col] = normalized

            df.rename(columns=column_mapping, inplace=True)

            # Her satırı BaroRecord nesnesine dönüştür
            records = []
            for idx, row in df.iterrows():
                try:
                    record = BaroRecord(row.to_dict())
                    if record.is_valid():
                        records.append(record)
                except Exception as e:
                    print(f"Satır {idx + 2} işlenirken hata: {e}")
                    continue

            # Cache'e kaydet
            if use_cache:
                BaroLoader._cache = records
                BaroLoader._cache_file_path = str(self.file_path)

            return records

        except Exception as e:
            raise Exception(f"Excel dosyası okunurken hata oluştu: {e}")

    def get_statistics(self) -> Dict:
        """
        Yüklenen kayıtlar hakkında istatistik bilgisi döndürür

        Returns:
            Dict: İstatistik bilgileri
        """
        records = self.load_records()

        return {
            'total_records': len(records),
            'with_email': sum(1 for r in records if r.mail),
            'with_phone': sum(1 for r in records if r.tel),
            'with_address': sum(1 for r in records if r.adres),
        }
