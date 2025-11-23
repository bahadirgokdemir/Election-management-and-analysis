import re


def normalize_phone(s: str) -> str:
    if not s:
        return s
    return re.sub(r'\D+', '', s)


def normalize_email(s: str) -> str:
    return s.strip().lower() if s else s