"""
Benzersiz kişiler servisi - Tekrarlı kayıtları birleştirme
"""
from typing import List, Dict, Any, Optional
from django.db.models import Q, Count, Prefetch
from collections import defaultdict

from app.models import LawyerPerson, StatusOption


class UniquePerson:
    """Birleştirilmiş benzersiz kişi modeli"""

    def __init__(self, kisi_sicilno: str):
        self.kisi_sicilno = kisi_sicilno
        self.ad = None
        self.soyad = None
        self.emails = set()
        self.phones = set()
        self.districts = set()
        self.addresses = set()
        self.notes = []
        self.statuses = set()
        self.lawyers = []
        self.record_count = 0

    def add_record(self, lp: LawyerPerson):
        """LawyerPerson kaydını benzersiz kişiye ekle"""
        self.record_count += 1

        # İsim (en güncel/dolu olanı al)
        if lp.ad and lp.ad.strip():
            if not self.ad or len(lp.ad) > len(self.ad):
                self.ad = lp.ad
        if lp.soyad and lp.soyad.strip():
            if not self.soyad or len(lp.soyad) > len(self.soyad):
                self.soyad = lp.soyad

        # Email (tümünü topla)
        if lp.mail and lp.mail.strip():
            self.emails.add(lp.mail.strip())

        # Telefon (tümünü topla)
        if lp.telno and lp.telno.strip():
            self.phones.add(lp.telno.strip())

        # İlçe (tümünü topla)
        if lp.ilce and lp.ilce.strip():
            self.districts.add(lp.ilce.strip())

        # Adres (tümünü topla)
        if lp.adres_aciklama and lp.adres_aciklama.strip():
            self.addresses.add(lp.adres_aciklama.strip())

        # Notlar (tümünü topla)
        if lp.notlar and lp.notlar.strip():
            note_text = lp.notlar.strip()
            if note_text not in self.notes:
                self.notes.append(note_text)

        # Durum (tümünü topla)
        if lp.cevap_status:
            self.statuses.add(lp.cevap_status.label)

        # Avukat bilgisi (tekrarsız)
        lawyer_info = {
            'id': lp.lawyer.id,
            'sicil_no': lp.lawyer.sicil_no,
            'ad': lp.lawyer.ad,
            'soyad': lp.lawyer.soyad,
            'full_name': f"{lp.lawyer.ad} {lp.lawyer.soyad}"
        }
        if lawyer_info not in self.lawyers:
            self.lawyers.append(lawyer_info)

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary formatına çevir"""
        return {
            'kisi_sicilno': self.kisi_sicilno,
            'ad': self.ad or '',
            'soyad': self.soyad or '',
            'full_name': f"{self.ad or ''} {self.soyad or ''}".strip(),
            'emails': sorted(list(self.emails)),
            'phones': sorted(list(self.phones)),
            'districts': sorted(list(self.districts)),
            'addresses': list(self.addresses),
            'notes': self.notes,
            'statuses': sorted(list(self.statuses)),
            'lawyers': self.lawyers,
            'record_count': self.record_count,
            'lawyer_count': len(self.lawyers),
            # Display strings
            'email_display': ', '.join(sorted(self.emails)) if self.emails else '',
            'phone_display': ', '.join(sorted(self.phones)) if self.phones else '',
            'district_display': ', '.join(sorted(self.districts)) if self.districts else '',
            'status_display': ', '.join(sorted(self.statuses)) if self.statuses else '',
            'lawyer_display': ', '.join([l['full_name'] for l in self.lawyers]) if self.lawyers else '',
        }


class UniquePeopleService:
    """Benzersiz kişiler servisi"""

    @staticmethod
    def get_unique_people(
        search_query: Optional[str] = None,
        status_key: Optional[str] = None,
        lawyer_id: Optional[int] = None,
        district: Optional[str] = None,
        min_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Benzersiz kişileri getir ve filtrele.

        Args:
            search_query: Genel arama (isim, sicil, email, telefon)
            status_key: Durum filtresi
            lawyer_id: Avukat ID filtresi
            district: İlçe filtresi
            min_records: Minimum kayıt sayısı (tekrarlı kayıtları bulmak için)

        Returns:
            Benzersiz kişiler listesi (dict formatında)
        """
        # Base queryset
        qs = LawyerPerson.objects.select_related(
            'cevap_status', 'lawyer'
        ).filter(active=True).order_by('kisi_sicilno', '-id')

        # Filtreler
        if search_query:
            qs = qs.filter(
                Q(kisi_sicilno__icontains=search_query) |
                Q(ad__icontains=search_query) |
                Q(soyad__icontains=search_query) |
                Q(mail__icontains=search_query) |
                Q(telno__icontains=search_query) |
                Q(ilce__icontains=search_query) |
                Q(notlar__icontains=search_query)
            )

        if status_key:
            qs = qs.filter(cevap_status__key=status_key)

        if lawyer_id:
            qs = qs.filter(lawyer_id=lawyer_id)

        if district:
            qs = qs.filter(ilce=district)

        # Sicil no'ya göre grupla
        unique_people_dict: Dict[str, UniquePerson] = {}

        for lp in qs:
            sicil = lp.kisi_sicilno
            if sicil not in unique_people_dict:
                unique_people_dict[sicil] = UniquePerson(sicil)

            unique_people_dict[sicil].add_record(lp)

        # Dict'e çevir
        unique_people = [person.to_dict() for person in unique_people_dict.values()]

        # Minimum kayıt sayısı filtresi
        if min_records and min_records > 1:
            unique_people = [p for p in unique_people if p['record_count'] >= min_records]

        # Sicil no'ya göre sırala
        unique_people.sort(key=lambda x: x['kisi_sicilno'])

        return unique_people

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Benzersiz kişiler istatistikleri

        Returns:
            İstatistik verileri
        """
        # Toplam kayıt sayısı
        total_records = LawyerPerson.objects.filter(active=True).count()

        # Benzersiz sicil no sayısı
        unique_sicil_count = LawyerPerson.objects.filter(active=True).values('kisi_sicilno').distinct().count()

        # Tekrarlı kayıtlar (birden fazla avukatta olan kişiler)
        duplicates = LawyerPerson.objects.filter(active=True).values('kisi_sicilno').annotate(
            count=Count('id')
        ).filter(count__gt=1).count()

        # En çok tekrarlayan kişi
        most_duplicated = LawyerPerson.objects.filter(active=True).values(
            'kisi_sicilno', 'ad', 'soyad'
        ).annotate(
            count=Count('id')
        ).order_by('-count').first()

        return {
            'total_records': total_records,
            'unique_people': unique_sicil_count,
            'duplicate_people': duplicates,
            'single_record_people': unique_sicil_count - duplicates,
            'most_duplicated': most_duplicated,
        }

    @staticmethod
    def get_person_details(kisi_sicilno: str) -> Optional[Dict[str, Any]]:
        """
        Belirli bir sicil no için tüm detayları getir

        Args:
            kisi_sicilno: Kişi sicil numarası

        Returns:
            Kişi detayları (tüm kayıtlar dahil)
        """
        records = LawyerPerson.objects.select_related(
            'cevap_status', 'lawyer'
        ).filter(
            kisi_sicilno=kisi_sicilno,
            active=True
        ).order_by('-id')

        if not records.exists():
            return None

        unique_person = UniquePerson(kisi_sicilno)
        for lp in records:
            unique_person.add_record(lp)

        result = unique_person.to_dict()

        # Detaylı kayıt listesi ekle
        result['all_records'] = [
            {
                'id': lp.id,
                'lawyer': {
                    'id': lp.lawyer.id,
                    'sicil_no': lp.lawyer.sicil_no,
                    'full_name': f"{lp.lawyer.ad} {lp.lawyer.soyad}"
                },
                'ad': lp.ad,
                'soyad': lp.soyad,
                'mail': lp.mail or '',
                'telno': lp.telno or '',
                'ilce': lp.ilce or '',
                'adres_aciklama': lp.adres_aciklama or '',
                'notlar': lp.notlar or '',
                'cevap_status': lp.cevap_status.label if lp.cevap_status else '',
            }
            for lp in records
        ]

        return result
