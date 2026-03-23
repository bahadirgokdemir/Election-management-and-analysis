from typing import Dict, List
from django.db.models import Count, Q
from app.models import Person, LawyerPerson, Lawyer, AuditLog, BaroLawyer, BaroLawyerTag, StatusOption, CommitteeMembership
from collections import defaultdict


def report_overview() -> Dict:
    # Toplam aktif ilişki sayısı (her avukat-kişi ilişkisi ayrı satır)
    total_relations = LawyerPerson.objects.filter(active=True).count()

    # Benzersiz kişi sayısı
    unique_people = LawyerPerson.objects.filter(active=True).values('kisi_sicilno').distinct().count()

    # Durum bazında sayılar (LawyerPerson.cevap_status kullanılıyor - doğru alan)
    status_counts = (
        LawyerPerson.objects
        .filter(active=True)
        .values('cevap_status__key')
        .annotate(cnt=Count('id'))
        .order_by()
    )
    by_status = {(r['cevap_status__key'] or 'bos'): r['cnt'] for r in status_counts}

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

    # Baro ve ulaşım istatistikleri
    baro_stats = get_baro_statistics()

    # Cevap istatistikleri
    response_stats = get_response_statistics()

    # Baro analitikleri (cinsiyet, ilçe, doğum yeri, kurul)
    baro_analytics = get_baro_analytics()

    return {
        'total': total_relations,
        'unique_people': unique_people,
        'byStatus': by_status,
        'lawyer_stats': lawyer_stats,
        'recent_logs': recent_logs,

        # Analizler
        'unique_stats': unique_stats,
        'district_stats': district_stats,
        'lawyer_performance': lawyer_performance,
        'growth_trend': growth_trend,

        # Baro ve cevap istatistikleri
        'baro_stats': baro_stats,
        'response_stats': response_stats,

        # Baro veri analitikleri
        'baro_analytics': baro_analytics,
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

    # Benzersiz kişilerde durum dağılımı: her kişi için en son durum (id'ye göre)
    unique_status_counts = defaultdict(int)
    sicil_status_map = {}

    for lp in LawyerPerson.objects.filter(active=True).select_related('cevap_status').order_by('kisi_sicilno', '-id'):
        if lp.kisi_sicilno not in sicil_status_map:
            sicil_status_map[lp.kisi_sicilno] = lp.cevap_status.label if lp.cevap_status else 'Belirtilmemiş'

    for label in sicil_status_map.values():
        unique_status_counts[label] += 1

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
    Avukat performans analizi — kişiler arası kesişim (shared) bilgisi ile.
    unique_people = sadece bu avukatın listesinde olan kişi sayısı (exclusive)
    shared_people = birden fazla avukat listesinde bulunan kişi sayısı
    total_records = bu avukatın toplam kişi sayısı
    """
    # Tüm aktif kayıtları çek: sicil → avukat kümesi
    sicil_lawyer_map = defaultdict(set)
    for item in LawyerPerson.objects.filter(active=True).values('kisi_sicilno', 'lawyer_id'):
        sicil_lawyer_map[item['kisi_sicilno']].add(item['lawyer_id'])

    lawyer_unique_counts = {}
    for lawyer in Lawyer.objects.all():
        lawyer_sicils = set(
            LawyerPerson.objects.filter(lawyer=lawyer, active=True).values_list('kisi_sicilno', flat=True)
        )
        total_records = len(lawyer_sicils)
        # Paylaşılan: başka avukat listesinde de olan kişiler
        shared = sum(1 for s in lawyer_sicils if len(sicil_lawyer_map.get(s, set())) > 1)
        exclusive = total_records - shared

        lawyer_unique_counts[lawyer.id] = {
            'lawyer_name': f"{lawyer.ad} {lawyer.soyad}",
            'sicil_no': lawyer.sicil_no,
            'unique_people': exclusive,    # Sadece bu listede
            'shared_people': shared,       # Başka listede de var
            'total_records': total_records,
            'duplicate_rate': round((shared / total_records * 100) if total_records > 0 else 0, 1),
        }

    top_performer = max(
        lawyer_unique_counts.values(),
        key=lambda x: x['total_records']
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


def get_baro_statistics() -> Dict:
    """
    Baro kayıtları ve ulaşım istatistikleri
    """
    # Toplam Baro avukat sayısı
    total_baro_lawyers = BaroLawyer.objects.count()

    # Sisteme eklenen avukat sayısı
    system_lawyers = Lawyer.objects.count()

    # Ulaşma oranı
    reach_percentage = round((system_lawyers / total_baro_lawyers * 100) if total_baro_lawyers > 0 else 0, 1)

    # Benzersiz kişi sayısı (sicil bazında)
    unique_people_count = LawyerPerson.objects.filter(active=True).values('kisi_sicilno').distinct().count()

    # Baro avukatlarına göre benzersiz kişi oranı
    people_percentage = round((unique_people_count / total_baro_lawyers * 100) if total_baro_lawyers > 0 else 0, 1)

    blacklist_count = BaroLawyerTag.objects.filter(tag_type='blacklist').count()
    whitelist_count = BaroLawyerTag.objects.filter(tag_type='whitelist').count()

    return {
        'total_baro_lawyers': total_baro_lawyers,
        'system_lawyers': system_lawyers,
        'reach_percentage': reach_percentage,
        'unique_people_count': unique_people_count,
        'people_percentage': people_percentage,
        'not_reached': total_baro_lawyers - system_lawyers,
        'blacklist_count': blacklist_count,
        'whitelist_count': whitelist_count,
        'untagged_count': total_baro_lawyers - blacklist_count - whitelist_count,
    }


def get_response_statistics() -> Dict:
    """
    Cevap istatistikleri - Kişilerin verdiği cevaplar
    """
    # Benzersiz kişi sayısı
    unique_people = LawyerPerson.objects.filter(active=True).values('kisi_sicilno').distinct().count()

    # Cevap durumu olan kişiler (sicil bazında benzersiz)
    # Her sicil için en son cevap durumunu al
    sicil_statuses = {}
    for lp in LawyerPerson.objects.filter(active=True).select_related('cevap_status').order_by('kisi_sicilno', '-id'):
        if lp.kisi_sicilno not in sicil_statuses:
            sicil_statuses[lp.kisi_sicilno] = lp.cevap_status

    # Cevap verenleri say (status != None olanlar)
    responded_count = sum(1 for status in sicil_statuses.values() if status is not None)

    # Cevap oranı
    response_percentage = round((responded_count / unique_people * 100) if unique_people > 0 else 0, 1)

    # Durum bazında dağılım (benzersiz kişiler için)
    status_distribution = defaultdict(int)
    for status in sicil_statuses.values():
        key = status.label if status else 'Cevap Yok'
        status_distribution[key] += 1

    # En çok verilen cevap
    if status_distribution:
        most_common_response = max(status_distribution.items(), key=lambda x: x[1])
    else:
        most_common_response = ('Belirtilmemiş', 0)

    return {
        'unique_people': unique_people,
        'responded_count': responded_count,
        'no_response_count': unique_people - responded_count,
        'response_percentage': response_percentage,
        'no_response_percentage': round(100 - response_percentage, 1),
        'status_distribution': dict(status_distribution),
        'most_common_response': {
            'status': most_common_response[0],
            'count': most_common_response[1],
            'percentage': round((most_common_response[1] / unique_people * 100) if unique_people > 0 else 0, 1),
        },
    }


def get_baro_analytics() -> Dict:
    """
    Baro veritabanı analitikleri: cinsiyet, ilçe, doğum yeri, nüfus il, kurul üyelikleri
    """
    # Cinsiyet dağılımı
    cinsiyet_counts = (
        BaroLawyer.objects
        .exclude(cinsiyet='').exclude(cinsiyet__isnull=True)
        .values('cinsiyet').annotate(count=Count('id')).order_by('-count')
    )
    cinsiyet_dist = {}
    for r in cinsiyet_counts:
        label = 'Kadın' if r['cinsiyet'] in ('K', 'KADIN', 'F') else ('Erkek' if r['cinsiyet'] in ('E', 'ERKEK', 'M') else r['cinsiyet'])
        cinsiyet_dist[label] = cinsiyet_dist.get(label, 0) + r['count']
    unknown_cinsiyet = BaroLawyer.objects.filter(Q(cinsiyet='') | Q(cinsiyet__isnull=True)).count()
    if unknown_cinsiyet:
        cinsiyet_dist['Belirtilmemiş'] = unknown_cinsiyet

    # Baro İlçe dağılımı (BaroLawyer.ilce) - her zaman dolu
    baro_ilce_qs = (
        BaroLawyer.objects.exclude(ilce='').exclude(ilce__isnull=True)
        .values('ilce').annotate(count=Count('id')).order_by('-count')[:12]
    )
    baro_ilce = [{'ilce': r['ilce'], 'count': r['count']} for r in baro_ilce_qs]

    # Doğum yeri dağılımı
    dogum_yeri_qs = (
        BaroLawyer.objects.exclude(dogum_yeri='').exclude(dogum_yeri__isnull=True)
        .values('dogum_yeri').annotate(count=Count('id')).order_by('-count')[:12]
    )
    dogum_yeri = [{'yer': r['dogum_yeri'], 'count': r['count']} for r in dogum_yeri_qs]

    # Nüfusa kayıtlı il dağılımı
    nufus_il_qs = (
        BaroLawyer.objects.exclude(nufus_il='').exclude(nufus_il__isnull=True)
        .values('nufus_il').annotate(count=Count('id')).order_by('-count')[:12]
    )
    nufus_il = [{'il': r['nufus_il'], 'count': r['count']} for r in nufus_il_qs]

    # Kurul üyelikleri özeti
    total_memberships = CommitteeMembership.objects.count()
    gorev_counts = (
        CommitteeMembership.objects.values('gorev')
        .annotate(count=Count('id')).order_by('-count')[:8]
    )
    top_gorevler = [{'gorev': r['gorev'][:50] + ('…' if len(r['gorev']) > 50 else ''), 'count': r['count']} for r in gorev_counts]

    # Mesleğe başlama yılı dağılımı (son 20 yıl)
    meslek_years = defaultdict(int)
    for bl in BaroLawyer.objects.exclude(
        **{'mesleğe_baslama': ''}
    ).exclude(**{'mesleğe_baslama__isnull': True}).values_list('mesleğe_baslama', flat=True):
        try:
            year = str(bl).strip()[:4]
            if year.isdigit() and 1950 <= int(year) <= 2030:
                meslek_years[year] += 1
        except Exception:
            pass
    meslek_dist = dict(sorted(meslek_years.items(), key=lambda x: x[0]))

    return {
        'cinsiyet_distribution': cinsiyet_dist,
        'baro_ilce': baro_ilce,
        'dogum_yeri': dogum_yeri,
        'nufus_il': nufus_il,
        'total_memberships': total_memberships,
        'top_gorevler': top_gorevler,
        'meslek_dist': meslek_dist,
    }
