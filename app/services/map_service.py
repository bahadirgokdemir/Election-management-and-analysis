"""
Harita servisi - İlçe bazlı avukat ve seçmen verisi
"""

from app.models import LawyerPerson, BaroLawyer, StatusOption

# Ankara ilçe koordinatları (lat, lng)
ANKARA_DISTRICTS = {
    'Çankaya': (39.9179, 32.8627),
    'Keçiören': (39.9923, 32.8371),
    'Mamak': (39.9304, 32.9187),
    'Altındağ': (39.9636, 32.8584),
    'Sincan': (39.9667, 32.5833),
    'Etimesgut': (39.9519, 32.6731),
    'Yenimahalle': (39.9433, 32.7253),
    'Gölbaşı': (39.7917, 32.8083),
    'Pursaklar': (40.0333, 33.0167),
    'Kazan': (40.2167, 32.6833),
    'Elmadağ': (39.9167, 33.2333),
    'Beypazarı': (40.1667, 31.9167),
    'Bala': (39.5500, 33.1167),
    'Güdül': (40.2167, 32.2500),
    'Haymana': (39.4333, 32.5000),
    'Kalecik': (40.1000, 33.4167),
    'Kızılcahamam': (40.4667, 32.6500),
    'Nallıhan': (40.1833, 31.3500),
    'Polatlı': (39.5833, 32.1500),
    'Şereflikoçhisar': (38.9333, 33.5333),
    'Ayaş': (40.0167, 32.3333),
    'Çamlıdere': (40.4833, 32.4167),
    'Çubuk': (40.2333, 33.0500),
    'Akyurt': (40.1333, 33.0833),
}

# Bilinmeyen ilçeler için Ankara merkezi
ANKARA_CENTER = (39.9334, 32.8597)

# Status → renk eşlemeleri
STATUS_COLORS = {
    'geliyor': '#22c55e',
    'gelmiyor': '#ef4444',
}
DEFAULT_STATUS_COLOR = '#f59e0b'
UNKNOWN_STATUS_COLOR = '#9ca3af'


def _normalize_district(ilce):
    """İlçe adını normalize et: büyük/küçük harf duyarsız eşleme."""
    if not ilce:
        return None
    ilce = ilce.strip()
    # Doğrudan eşleme
    if ilce in ANKARA_DISTRICTS:
        return ilce
    # Büyük/küçük harf duyarsız eşleme
    ilce_lower = ilce.lower()
    for district_name in ANKARA_DISTRICTS:
        if district_name.lower() == ilce_lower:
            return district_name
    return None


def _get_district_coords(ilce):
    """İlçe koordinatlarını döndür, bilinmiyorsa Ankara merkezi."""
    normalized = _normalize_district(ilce)
    if normalized:
        return ANKARA_DISTRICTS[normalized]
    return ANKARA_CENTER


def _jitter_coords(sicil_no, lat, lng):
    """Deterministic küçük kaydırma - aynı sicil her zaman aynı noktada."""
    lat_offset = hash(str(sicil_no)) % 1000 / 100000.0
    lng_offset = hash(str(sicil_no) + 'lng') % 1000 / 100000.0
    return lat + lat_offset, lng + lng_offset


def get_map_data(lawyer_id=None, status_filter=None, layer='all'):
    """
    Harita sayfası için veri döndür.

    Args:
        lawyer_id: Filtre uygulanacak avukat ID'si (opsiyonel)
        status_filter: Filtre uygulanacak durum anahtarı (opsiyonel)
        layer: Hangi katmanların hesaplanacağı: 'all', 'districts', 'persons', 'baro'

    Returns:
        dict: districts, lawyer_persons, baro_lawyers, stats
    """

    # --- LawyerPerson sorgusu ---
    lp_qs = LawyerPerson.objects.select_related('cevap_status', 'lawyer').filter(active=True)

    if lawyer_id:
        lp_qs = lp_qs.filter(lawyer_id=lawyer_id)

    if status_filter:
        if status_filter == '__none__':
            lp_qs = lp_qs.filter(cevap_status__isnull=True)
        else:
            lp_qs = lp_qs.filter(cevap_status__key=status_filter)

    # Tüm LawyerPerson kayıtlarını bir kez çek
    all_lp = list(lp_qs)

    # --- İlçe bazlı istatistikler ---
    # Her ilçe için sayaçlar
    district_lp_stats = {}  # {normalized_ilce: {total, positive, negative, neutral, unknown}}

    for lp in all_lp:
        normalized = _normalize_district(lp.ilce) or '__other__'
        if normalized not in district_lp_stats:
            district_lp_stats[normalized] = {
                'total': 0, 'positive': 0, 'negative': 0, 'neutral': 0, 'unknown': 0
            }
        stats_entry = district_lp_stats[normalized]
        stats_entry['total'] += 1
        if lp.cevap_status is None:
            stats_entry['unknown'] += 1
        elif lp.cevap_status.key == 'geliyor':
            stats_entry['positive'] += 1
        elif lp.cevap_status.key == 'gelmiyor':
            stats_entry['negative'] += 1
        else:
            stats_entry['neutral'] += 1

    # BaroLawyer ilçe sayıları (tüm katmanlar için, district hesaplamasında kullanılır)
    baro_ilce_counts = {}
    if layer in ('all', 'districts', 'baro'):
        from django.db.models import Count
        baro_counts_qs = BaroLawyer.objects.values('ilce').annotate(count=Count('id'))
        for row in baro_counts_qs:
            raw_ilce = row['ilce']
            normalized = _normalize_district(raw_ilce) or raw_ilce
            baro_ilce_counts[normalized] = baro_ilce_counts.get(normalized, 0) + row['count']

    # --- Districts katmanı ---
    districts = []
    all_known_districts = set(district_lp_stats.keys()) | set(baro_ilce_counts.keys())
    # Boş olsa bile tüm ANKARA_DISTRICTS ilçelerini dahil et
    all_known_districts |= set(ANKARA_DISTRICTS.keys())
    all_known_districts.discard('__other__')

    for ilce_name in all_known_districts:
        coords = ANKARA_DISTRICTS.get(ilce_name, ANKARA_CENTER)
        lp_stats = district_lp_stats.get(ilce_name, {'total': 0, 'positive': 0, 'negative': 0, 'neutral': 0, 'unknown': 0})
        baro_total = baro_ilce_counts.get(ilce_name, 0)
        districts.append({
            'ilce': ilce_name,
            'lat': coords[0],
            'lng': coords[1],
            'lp_total': lp_stats['total'],
            'lp_positive': lp_stats['positive'],
            'lp_negative': lp_stats['negative'],
            'lp_neutral': lp_stats['neutral'],
            'lp_unknown': lp_stats['unknown'],
            'baro_total': baro_total,
        })

    # Toplam istatistikler
    total_persons = sum(d['lp_total'] for d in districts)
    total_positive = sum(d['lp_positive'] for d in districts)
    total_negative = sum(d['lp_negative'] for d in districts)
    # __other__ ilçesini de dahil et
    if '__other__' in district_lp_stats:
        other = district_lp_stats['__other__']
        total_persons += other['total']
        total_positive += other['positive']
        total_negative += other['negative']

    total_baro = sum(baro_ilce_counts.values()) if baro_ilce_counts else BaroLawyer.objects.count()
    districts_with_data = len([d for d in districts if d['lp_total'] > 0])

    # --- Lawyer Persons katmanı ---
    lawyer_persons = []
    if layer in ('all', 'persons'):
        for lp in all_lp:
            ilce_normalized = _normalize_district(lp.ilce)
            if ilce_normalized:
                coords = ANKARA_DISTRICTS[ilce_normalized]
            else:
                coords = ANKARA_CENTER

            lat, lng = _jitter_coords(lp.kisi_sicilno, coords[0], coords[1])

            if lp.cevap_status:
                status_key = lp.cevap_status.key
                status_label = lp.cevap_status.label
                status_color = lp.cevap_status.color or STATUS_COLORS.get(status_key, DEFAULT_STATUS_COLOR)
            else:
                status_key = None
                status_label = 'Belirsiz'
                status_color = UNKNOWN_STATUS_COLOR

            lawyer_persons.append({
                'sicil': lp.kisi_sicilno,
                'ad': lp.ad,
                'soyad': lp.soyad,
                'full_name': f"{lp.ad} {lp.soyad}".strip(),
                'ilce': ilce_normalized or (lp.ilce or ''),
                'lat': round(lat, 6),
                'lng': round(lng, 6),
                'status_key': status_key,
                'status_label': status_label,
                'status_color': status_color,
                'lawyer_ad': f"{lp.lawyer.ad} {lp.lawyer.soyad}".strip(),
                'lawyer_sicil': lp.lawyer.sicil_no,
                'notlar': lp.notlar or '',
            })

    # --- Baro Lawyers katmanı ---
    baro_lawyers = []
    if layer in ('all', 'baro'):
        # Verimli in_lists kontrolü için LawyerPerson sicil setini oluştur
        lp_sicil_set = {lp.kisi_sicilno for lp in all_lp}
        # Eğer lawyer_id filtresi yoksa tüm LP sicillerini al (daha geniş kontrol)
        if lawyer_id or status_filter:
            all_lp_sicils = set(
                LawyerPerson.objects.filter(active=True).values_list('kisi_sicilno', flat=True)
            )
        else:
            all_lp_sicils = lp_sicil_set

        baro_qs = BaroLawyer.objects.select_related('tag').all()

        for bl in baro_qs:
            ilce_normalized = _normalize_district(bl.ilce)
            if ilce_normalized:
                coords = ANKARA_DISTRICTS[ilce_normalized]
            else:
                coords = ANKARA_CENTER

            lat, lng = _jitter_coords(bl.sicil_no, coords[0], coords[1])

            # Tag bilgisi
            tag_type = None
            tag_note = ''
            try:
                tag = bl.tag
                tag_type = tag.tag_type
                tag_note = tag.note or ''
            except Exception:
                pass

            baro_lawyers.append({
                'sicil': bl.sicil_no,
                'ad': bl.ad,
                'soyad': bl.soyad,
                'full_name': f"{bl.ad} {bl.soyad}".strip(),
                'ilce': ilce_normalized or (bl.ilce or ''),
                'lat': round(lat, 6),
                'lng': round(lng, 6),
                'tag_type': tag_type,
                'tag_note': tag_note,
                'in_lists': bl.sicil_no in all_lp_sicils,
            })

    return {
        'districts': districts,
        'lawyer_persons': lawyer_persons,
        'baro_lawyers': baro_lawyers,
        'stats': {
            'total_persons': total_persons,
            'total_positive': total_positive,
            'total_negative': total_negative,
            'total_baro': total_baro,
            'districts_count': districts_with_data,
        },
    }
