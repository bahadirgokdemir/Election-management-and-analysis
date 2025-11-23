from typing import Dict, List
from django.db.models import Count, Q
from app.models import Person, LawyerPerson, Lawyer, AuditLog
from collections import defaultdict


def report_overview() -> Dict:
    # Toplam aktif ilişki sayısı (her avukat-kişi ilişkisi ayrı satır)
    total_relations = LawyerPerson.objects.filter(active=True).count()

    # Benzersiz kişi sayısı
    unique_people = Person.objects.filter(
        lawyerperson__active=True
    ).distinct().count()

    # Durum bazında sayılar (ilişki bazında, aynı kişi birden fazla sayılabilir)
    status_counts = (
        LawyerPerson.objects
        .filter(active=True)
        .values('person__cevap_status__key')
        .annotate(cnt=Count('id'))
        .order_by()
    )
    by_status = {(r['person__cevap_status__key'] or 'bos'): r['cnt'] for r in status_counts}

    # Avukat başına istatistikler
    lawyer_stats = (
        Lawyer.objects
        .annotate(
            person_count=Count('lawyerperson', filter=Q(lawyerperson__active=True))
        )
        .order_by('-person_count')
    )

    # Son 10 aktiviteyi getir
    recent_logs = AuditLog.objects.all().order_by('-at')[:10]

    # Benzersiz kişiler analizi
    unique_stats = get_unique_people_statistics()

    # İlçe bazlı analiz
    district_stats = get_district_statistics()

    # Avukat performans analizi
    lawyer_performance = get_lawyer_performance()

    # Trend analizi (aylık büyüme)
    growth_trend = get_growth_trend()

    return {
        'total': total_relations,
        'unique_people': unique_people,
        'byStatus': by_status,
        'lawyer_stats': lawyer_stats,
        'recent_logs': recent_logs,

        # Yeni analizler
        'unique_stats': unique_stats,
        'district_stats': district_stats,
        'lawyer_performance': lawyer_performance,
        'growth_trend': growth_trend,
    }


def report_by_lawyer(lawyer_id: int) -> Dict:
    total = LawyerPerson.objects.filter(lawyer_id=lawyer_id, active=True).count()
    status_counts = (Person.objects
                     .filter(lawyerperson__lawyer_id=lawyer_id, lawyerperson__active=True)
                     .values('cevap_status__key')
                     .annotate(cnt=Count('id')))
    by_status = {(r['cevap_status__key'] or 'bos'): r['cnt'] for r in status_counts}
    return {'lawyerId': lawyer_id, 'total': total, 'byStatus': by_status}


def report_status_breakdown(status_key: str) -> Dict:
    # hangi avukatlardan gelmiş
    lawyers = (Lawyer.objects
               .filter(lawyerperson__person__cevap_status__key=status_key,
                       lawyerperson__active=True)
               .annotate(cnt=Count('lawyerperson__id'))
               .values('id', 'sicil_no', 'ad', 'soyad', 'cnt'))
    return {'status': status_key, 'lawyers': list(lawyers)}


def get_unique_people_statistics() -> Dict:
    """
    Benzersiz kişiler için detaylı istatistikler
    """
    # Benzersiz sicil no'lar
    unique_sicil_nos = LawyerPerson.objects.filter(active=True).values_list('kisi_sicilno', flat=True).distinct()
    total_unique = len(set(unique_sicil_nos))

    # Sicil no bazında kayıt sayısı
    sicil_counts = defaultdict(int)
    for sicil in LawyerPerson.objects.filter(active=True).values_list('kisi_sicilno', flat=True):
        sicil_counts[sicil] += 1

    # Tekrarlı kayıtlar (birden fazla avukatta olan kişiler)
    duplicate_count = sum(1 for count in sicil_counts.values() if count > 1)
    single_count = sum(1 for count in sicil_counts.values() if count == 1)

    # En çok tekrarlayan kişi
    if sicil_counts:
        max_sicil = max(sicil_counts.items(), key=lambda x: x[1])
        max_duplicate_person = LawyerPerson.objects.filter(
            kisi_sicilno=max_sicil[0], active=True
        ).first()
    else:
        max_duplicate_person = None

    # Benzersiz kişilerde durum dağılımı
    unique_status_counts = defaultdict(int)
    processed_sicil_status = set()

    for lp in LawyerPerson.objects.filter(active=True).select_related('cevap_status'):
        key = (lp.kisi_sicilno, lp.cevap_status.key if lp.cevap_status else 'bos')
        if key not in processed_sicil_status:
            processed_sicil_status.add(key)
            status_key = lp.cevap_status.label if lp.cevap_status else 'Belirtilmemiş'
            unique_status_counts[status_key] += 1

    return {
        'total_unique': total_unique,
        'duplicate_count': duplicate_count,
        'single_count': single_count,
        'duplicate_percentage': round((duplicate_count / total_unique * 100) if total_unique > 0 else 0, 1),
        'max_duplicate': {
            'sicil_no': max_sicil[0] if max_duplicate_person else '',
            'ad': max_duplicate_person.ad if max_duplicate_person else '',
            'soyad': max_duplicate_person.soyad if max_duplicate_person else '',
            'count': max_sicil[1] if max_duplicate_person else 0
        } if max_duplicate_person else None,
        'status_distribution': dict(unique_status_counts),
    }


def get_district_statistics() -> Dict:
    """
    İlçe bazlı istatistikler
    """
    # İlçe bazında kişi sayısı
    district_counts = (
        LawyerPerson.objects
        .filter(active=True)
        .exclude(ilce__isnull=True)
        .exclude(ilce='')
        .values('ilce')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # Benzersiz kişi sayısı (ilçe bazında)
    unique_district_counts = defaultdict(int)
    processed_sicil_district = set()

    for lp in LawyerPerson.objects.filter(active=True).exclude(ilce__isnull=True).exclude(ilce=''):
        key = (lp.kisi_sicilno, lp.ilce)
        if key not in processed_sicil_district:
            processed_sicil_district.add(key)
            unique_district_counts[lp.ilce] += 1

    # Sırala ve top 10 al
    top_unique_districts = sorted(
        unique_district_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    return {
        'total_districts': LawyerPerson.objects.filter(active=True).exclude(ilce__isnull=True).exclude(ilce='').values('ilce').distinct().count(),
        'top_districts': [
            {'ilce': item['ilce'], 'count': item['count']}
            for item in district_counts
        ],
        'top_unique_districts': [
            {'ilce': ilce, 'count': count}
            for ilce, count in top_unique_districts
        ],
    }


def get_lawyer_performance() -> Dict:
    """
    Avukat performans analizi
    """
    # Her avukat için benzersiz kişi sayısı
    lawyer_unique_counts = {}
    for lawyer in Lawyer.objects.all():
        unique_people = LawyerPerson.objects.filter(
            lawyer=lawyer, active=True
        ).values_list('kisi_sicilno', flat=True).distinct().count()

        total_records = LawyerPerson.objects.filter(
            lawyer=lawyer, active=True
        ).count()

        lawyer_unique_counts[lawyer.id] = {
            'lawyer_name': f"{lawyer.ad} {lawyer.soyad}",
            'sicil_no': lawyer.sicil_no,
            'unique_people': unique_people,
            'total_records': total_records,
            'duplicate_rate': round(((total_records - unique_people) / total_records * 100) if total_records > 0 else 0, 1),
        }

    # En çok benzersiz kişi olan avukat
    top_performer = max(
        lawyer_unique_counts.values(),
        key=lambda x: x['unique_people']
    ) if lawyer_unique_counts else None

    return {
        'lawyer_unique_counts': lawyer_unique_counts,
        'top_performer': top_performer,
    }


def get_growth_trend() -> Dict:
    """
    Büyüme trendi (basit versiyon - timestamp yoksa sadece toplam)
    """
    total_relations = LawyerPerson.objects.filter(active=True).count()
    total_unique = LawyerPerson.objects.filter(active=True).values('kisi_sicilno').distinct().count()

    return {
        'total_relations': total_relations,
        'total_unique': total_unique,
        'average_relations_per_person': round(total_relations / total_unique, 2) if total_unique > 0 else 0,
    }
