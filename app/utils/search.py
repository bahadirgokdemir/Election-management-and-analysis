"""
Turkish-aware search utilities.

Handles:
- Turkish character case-insensitivity (ı/i, İ/I, ş/s, Ş/S, etc.)
- Full name (Ad Soyad) combined search when query contains spaces
"""

from django.db.models import Q, Value
from django.db.models.functions import Upper, Replace

_TR_TABLE = str.maketrans({
    'İ': 'I', 'Ş': 'S', 'Ğ': 'G', 'Ü': 'U', 'Ö': 'O', 'Ç': 'C',
    'ı': 'I', 'ş': 'S', 'ğ': 'G', 'ü': 'U', 'ö': 'O', 'ç': 'C',
})


def normalize_tr(s: str) -> str:
    """Normalize Turkish characters to ASCII equivalents, uppercase."""
    if not s:
        return ''
    return s.upper().translate(_TR_TABLE)


def _normalize_db_expr(field):
    """
    Build a Django ORM expression that normalizes a DB field for Turkish comparison.
    Replaces Turkish chars (both cases) then uppercases.
    """
    expr = Replace(field, Value('ı'), Value('I'))
    expr = Replace(expr, Value('İ'), Value('I'))
    expr = Replace(expr, Value('ş'), Value('S'))
    expr = Replace(expr, Value('Ş'), Value('S'))
    expr = Replace(expr, Value('ğ'), Value('G'))
    expr = Replace(expr, Value('Ğ'), Value('G'))
    expr = Replace(expr, Value('ü'), Value('U'))
    expr = Replace(expr, Value('Ü'), Value('U'))
    expr = Replace(expr, Value('ö'), Value('O'))
    expr = Replace(expr, Value('Ö'), Value('O'))
    expr = Replace(expr, Value('ç'), Value('C'))
    expr = Replace(expr, Value('Ç'), Value('C'))
    return Upper(expr)


def apply_name_search(qs, q: str, ad_field='ad', soyad_field='soyad', extra_fields=None):
    """
    Apply Turkish-aware, full-name-aware search to a queryset.

    - Normalizes both query and DB ad/soyad fields for Turkish ı/İ etc.
    - Handles "Ad Soyad" combined search when query contains spaces
    - extra_fields: list of other field names to search with __icontains (original query)

    Returns filtered queryset.
    """
    if not q:
        return qs

    norm_q = normalize_tr(q)
    parts = norm_q.split()

    # Annotate normalized ad/soyad for comparison
    qs = qs.annotate(
        _srch_ad=_normalize_db_expr(ad_field),
        _srch_soyad=_normalize_db_expr(soyad_field),
    )

    # Name search (normalized)
    q_filter = Q(_srch_ad__icontains=norm_q) | Q(_srch_soyad__icontains=norm_q)

    # Full name: "Ahmet Yılmaz" → ad contains "AHMET" AND soyad contains "YILMAZ"
    if len(parts) >= 2:
        q_filter |= (
            Q(_srch_ad__icontains=parts[0]) & Q(_srch_soyad__icontains=' '.join(parts[1:]))
        ) | (
            Q(_srch_ad__icontains=' '.join(parts[:-1])) & Q(_srch_soyad__icontains=parts[-1])
        )

    # Extra fields searched with original query (email, phone, sicil, etc.)
    if extra_fields:
        for field in extra_fields:
            q_filter |= Q(**{f'{field}__icontains': q})

    return qs.filter(q_filter)
