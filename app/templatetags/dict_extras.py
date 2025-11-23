# app/templatetags/dict_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    """Sözlükten key ile değer döndürür; yoksa boş string."""
    if isinstance(d, dict):
        return d.get(key, "")
    return ""
