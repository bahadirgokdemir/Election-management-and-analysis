"""
Kişi bazlı analiz servisi
Her kişi için avukat ve cevap durumu istatistikleri
"""
from typing import Dict, List, Any, Optional
from collections import defaultdict
from django.db.models import Count

from app.models import LawyerPerson


class PersonAnalyticsService:
    """Kişi bazlı analiz servisi"""

    @staticmethod
    def get_person_analytics(kisi_sicilno: str) -> Optional[Dict[str, Any]]:
        """
        Belirli bir kişi için detaylı analiz verisi

        Args:
            kisi_sicilno: Kişi sicil numarası

        Returns:
            Analiz verisi (avukat bazlı, durum bazlı istatistikler)
        """
        # Kişiye ait tüm kayıtları getir
        records = LawyerPerson.objects.select_related(
            'lawyer', 'cevap_status'
        ).filter(
            kisi_sicilno=kisi_sicilno,
            active=True
        ).order_by('lawyer__ad', 'lawyer__soyad')

        if not records.exists():
            return None

        # Temel bilgiler (ilk kayıttan al)
        first_record = records.first()
        person_info = {
            'kisi_sicilno': kisi_sicilno,
            'ad': first_record.ad,
            'soyad': first_record.soyad,
            'full_name': f"{first_record.ad} {first_record.soyad}",
        }

        # Avukat bazlı analiz
        lawyer_stats = defaultdict(lambda: {
            'lawyer_name': '',
            'lawyer_sicil': '',
            'status_counts': defaultdict(int),
            'total_records': 0,
            'districts': set(),
            'emails': set(),
            'phones': set(),
        })

        # Durum bazlı analiz
        status_stats = defaultdict(int)

        # İlçe bazlı analiz
        district_stats = defaultdict(int)

        # Toplam istatistikler
        total_records = 0
        unique_districts = set()
        unique_emails = set()
        unique_phones = set()

        for record in records:
            total_records += 1

            # Avukat bilgileri
            lawyer_key = record.lawyer.id
            lawyer_stats[lawyer_key]['lawyer_name'] = f"{record.lawyer.ad} {record.lawyer.soyad}"
            lawyer_stats[lawyer_key]['lawyer_sicil'] = record.lawyer.sicil_no
            lawyer_stats[lawyer_key]['total_records'] += 1

            # Durum istatistikleri
            status_label = record.cevap_status.label if record.cevap_status else 'Belirtilmemiş'
            lawyer_stats[lawyer_key]['status_counts'][status_label] += 1
            status_stats[status_label] += 1

            # İlçe bilgileri
            if record.ilce:
                lawyer_stats[lawyer_key]['districts'].add(record.ilce)
                unique_districts.add(record.ilce)
                district_stats[record.ilce] += 1

            # Email bilgileri
            if record.mail:
                lawyer_stats[lawyer_key]['emails'].add(record.mail)
                unique_emails.add(record.mail)

            # Telefon bilgileri
            if record.telno:
                lawyer_stats[lawyer_key]['phones'].add(record.telno)
                unique_phones.add(record.telno)

        # Avukat istatistiklerini formatlı hale getir
        formatted_lawyer_stats = []
        for lawyer_id, stats in lawyer_stats.items():
            formatted_lawyer_stats.append({
                'lawyer_id': lawyer_id,
                'lawyer_name': stats['lawyer_name'],
                'lawyer_sicil': stats['lawyer_sicil'],
                'total_records': stats['total_records'],
                'status_breakdown': dict(stats['status_counts']),
                'districts': sorted(list(stats['districts'])),
                'emails': sorted(list(stats['emails'])),
                'phones': sorted(list(stats['phones'])),
            })

        # Durum dağılımı (pasta grafik için)
        status_distribution = [
            {'label': label, 'count': count}
            for label, count in sorted(status_stats.items(), key=lambda x: -x[1])
        ]

        # Avukat dağılımı (sütun grafik için)
        lawyer_distribution = [
            {
                'lawyer_name': stats['lawyer_name'],
                'count': stats['total_records'],
                'statuses': stats['status_breakdown']
            }
            for stats in formatted_lawyer_stats
        ]

        # İlçe dağılımı
        district_distribution = [
            {'label': district, 'count': count}
            for district, count in sorted(district_stats.items(), key=lambda x: -x[1])
        ]

        return {
            'person_info': person_info,
            'total_records': total_records,
            'unique_lawyers': len(lawyer_stats),
            'unique_statuses': len(status_stats),
            'unique_districts': sorted(list(unique_districts)),
            'unique_emails': sorted(list(unique_emails)),
            'unique_phones': sorted(list(unique_phones)),

            # Detaylı istatistikler
            'lawyer_stats': formatted_lawyer_stats,
            'status_distribution': status_distribution,
            'lawyer_distribution': lawyer_distribution,
            'district_distribution': district_distribution,

            # Grafik verisi (Chart.js formatı)
            'chart_data': {
                # Pasta grafik: Durum dağılımı
                'status_pie': {
                    'labels': [item['label'] for item in status_distribution],
                    'data': [item['count'] for item in status_distribution],
                },
                # Sütun grafik: Avukat bazlı dağılım
                'lawyer_bar': {
                    'labels': [item['lawyer_name'] for item in lawyer_distribution],
                    'data': [item['count'] for item in lawyer_distribution],
                    'status_breakdown': [item['statuses'] for item in lawyer_distribution],
                },
                # Pasta grafik: İlçe dağılımı
                'district_pie': {
                    'labels': [item['label'] for item in district_distribution],
                    'data': [item['count'] for item in district_distribution],
                },
            }
        }

    @staticmethod
    def get_comparison_stats(kisi_sicilno: str) -> Optional[Dict[str, Any]]:
        """
        Kişinin farklı avukatlarla ilişkilerini karşılaştır

        Returns:
            Karşılaştırmalı istatistikler
        """
        analytics = PersonAnalyticsService.get_person_analytics(kisi_sicilno)

        if not analytics:
            return None

        # En çok kayıt olan avukat
        max_records_lawyer = max(
            analytics['lawyer_stats'],
            key=lambda x: x['total_records']
        ) if analytics['lawyer_stats'] else None

        # En yaygın durum
        most_common_status = analytics['status_distribution'][0] if analytics['status_distribution'] else None

        # En yaygın ilçe
        most_common_district = analytics['district_distribution'][0] if analytics['district_distribution'] else None

        return {
            'max_records_lawyer': max_records_lawyer,
            'most_common_status': most_common_status,
            'most_common_district': most_common_district,
            'has_multiple_lawyers': analytics['unique_lawyers'] > 1,
            'has_multiple_statuses': analytics['unique_statuses'] > 1,
        }
