"""
Harita servisi - İlçe bazlı avukat ve seçmen verisi
"""

from django.db.models import Count, Q

from app.models import LawyerPerson, BaroLawyer

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
    if ilce in ANKARA_DISTRICTS:
        return ilce
    ilce_lower = ilce.lower()
    for district_name in ANKARA_DISTRICTS:
        if district_name.lower() == ilce_lower:
            return district_name
    return None


def _jitter_coords(sicil_no, lat, lng):
    """Deterministic küçük kaydırma - aynı sicil her zaman aynı noktada."""
    lat_offset = hash(str(sicil_no)) % 1000 / 100000.0
    lng_offset = hash(str(sicil_no) + 'lng') % 1000 / 100000.0
    return lat + lat_offset, lng + lng_offset


def get_map_data(lawyer_id=None, status_filter=None, layer='all',
                 ilce=None, q=None, note_q=None, tag_filter=None):
    """
    Harita sayfası için veri döndür.

    Args:
        lawyer_id:     Avukat ID filtresi
        status_filter: Durum anahtarı filtresi (veya '__none__')
        layer:         'all' | 'districts' | 'persons' | 'baro'
        ilce:          İlçe adı filtresi (iexact)
        q:             Ad/soyad/sicil araması (her iki katmana uygulanır)
        note_q:        Not alanı araması (sadece LawyerPerson)
        tag_filter:    Baro etiketi: 'blacklist' | 'whitelist' | 'none'

    Returns:
        dict: districts, lawyer_persons, baro_lawyers, stats
    """

    # ── LawyerPerson sorgusu ──────────────────────────────────────────────────
    lp_qs = LawyerPerson.objects.select_related('cevap_status', 'lawyer').filter(active=True)

    if lawyer_id:
        lp_qs = lp_qs.filter(lawyer_id=lawyer_id)

    if status_filter:
        if status_filter == '__none__':
            lp_qs = lp_qs.filter(cevap_status__isnull=True)
        else:
            lp_qs = lp_qs.filter(cevap_status__key=status_filter)

    if ilce:
        lp_qs = lp_qs.filter(ilce__iexact=ilce)

    if q:
        lp_qs = lp_qs.filter(
            Q(ad__icontains=q) | Q(soyad__icontains=q) | Q(kisi_sicilno__icontains=q)
        )

    if note_q:
        lp_qs = lp_qs.filter(notlar__icontains=note_q)

    all_lp = list(lp_qs)

    # ── BaroLawyer sorgusu ────────────────────────────────────────────────────
    baro_qs = BaroLawyer.objects.select_related('tag').all()

    if ilce:
        baro_qs = baro_qs.filter(ilce__iexact=ilce)

    if tag_filter == 'blacklist':
        baro_qs = baro_qs.filter(tag__tag_type='blacklist')
    elif tag_filter == 'whitelist':
        baro_qs = baro_qs.filter(tag__tag_type='whitelist')
    elif tag_filter == 'none':
        baro_qs = baro_qs.filter(tag__isnull=True)

    if q:
        baro_qs = baro_qs.filter(
            Q(ad__icontains=q) | Q(soyad__icontains=q) | Q(sicil_no__icontains=q)
        )

    # ── in_lists: her zaman tüm aktif LP setine göre (filtreden bağımsız) ────
    all_lp_sicils = set(
        LawyerPerson.objects.filter(active=True).values_list('kisi_sicilno', flat=True)
    )

    # ── İlçe bazlı LP istatistikleri ─────────────────────────────────────────
    district_lp_stats = {}

    for lp in all_lp:
        normalized = _normalize_district(lp.ilce) or '__other__'
        if normalized not in district_lp_stats:
            district_lp_stats[normalized] = {
                'total': 0, 'positive': 0, 'negative': 0, 'neutral': 0, 'unknown': 0
            }
        s = district_lp_stats[normalized]
        s['total'] += 1
        if lp.cevap_status is None:
            s['unknown'] += 1
        elif lp.cevap_status.key == 'geliyor':
            s['positive'] += 1
        elif lp.cevap_status.key == 'gelmiyor':
            s['negative'] += 1
        else:
            s['neutral'] += 1

    # ── İlçe bazlı Baro sayıları (filtrelenmiş) ───────────────────────────────
    baro_ilce_counts = {}
    if layer in ('all', 'districts', 'baro'):
        # Filtrelenmiş baro_qs üzerinden ilçe sayısı
        baro_counts_qs = baro_qs.values('ilce').annotate(count=Count('id'))
        for row in baro_counts_qs:
            normalized = _normalize_district(row['ilce']) or (row['ilce'] or '__unknown__')
            baro_ilce_counts[normalized] = baro_ilce_counts.get(normalized, 0) + row['count']

    # ── Districts katmanı ─────────────────────────────────────────────────────
    districts = []
    all_known = set(district_lp_stats.keys()) | set(baro_ilce_counts.keys())
    all_known |= set(ANKARA_DISTRICTS.keys())
    all_known.discard('__other__')
    all_known.discard('__unknown__')

    for ilce_name in all_known:
        coords = ANKARA_DISTRICTS.get(ilce_name, ANKARA_CENTER)
        lp_s = district_lp_stats.get(ilce_name,
                                      {'total': 0, 'positive': 0, 'negative': 0, 'neutral': 0, 'unknown': 0})
        districts.append({
            'ilce': ilce_name,
            'lat': coords[0],
            'lng': coords[1],
            'lp_total': lp_s['total'],
            'lp_positive': lp_s['positive'],
            'lp_negative': lp_s['negative'],
            'lp_neutral': lp_s['neutral'],
            'lp_unknown': lp_s['unknown'],
            'baro_total': baro_ilce_counts.get(ilce_name, 0),
        })

    # Toplam istatistikler
    total_persons = sum(d['lp_total'] for d in districts)
    total_positive = sum(d['lp_positive'] for d in districts)
    total_negative = sum(d['lp_negative'] for d in districts)
    total_neutral = sum(d['lp_neutral'] for d in districts)
    total_unknown = sum(d['lp_unknown'] for d in districts)
    if '__other__' in district_lp_stats:
        other = district_lp_stats['__other__']
        total_persons += other['total']
        total_positive += other['positive']
        total_negative += other['negative']
        total_neutral += other['neutral']
        total_unknown += other['unknown']

    districts_with_data = len([d for d in districts if d['lp_total'] > 0])

    # ── Lawyer Persons katmanı ────────────────────────────────────────────────
    lawyer_persons = []
    if layer in ('all', 'persons'):
        for lp in all_lp:
            ilce_normalized = _normalize_district(lp.ilce)
            coords = ANKARA_DISTRICTS[ilce_normalized] if ilce_normalized else ANKARA_CENTER
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

    # ── Baro Lawyers katmanı ──────────────────────────────────────────────────
    baro_lawyers = []
    total_baro = 0
    if layer in ('all', 'baro'):
        all_baro = list(baro_qs)
        total_baro = len(all_baro)

        for bl in all_baro:
            ilce_normalized = _normalize_district(bl.ilce)
            coords = ANKARA_DISTRICTS[ilce_normalized] if ilce_normalized else ANKARA_CENTER
            lat, lng = _jitter_coords(bl.sicil_no, coords[0], coords[1])

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
    else:
        # districts katmanı için baro count
        total_baro = sum(baro_ilce_counts.values())

    return {
        'districts': districts,
        'lawyer_persons': lawyer_persons,
        'baro_lawyers': baro_lawyers,
        'stats': {
            'total_persons': total_persons,
            'total_positive': total_positive,
            'total_negative': total_negative,
            'total_neutral': total_neutral,
            'total_unknown': total_unknown,
            'total_baro': total_baro,
            'districts_count': districts_with_data,
        },
    }
