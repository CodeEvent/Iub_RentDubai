# RERA statutory date math: 12-month (365-day) notices under Article
# 25(2), 30-day breach notices under Article 25(1). Ported 1:1 from
# legacy-v1/shared/dateRules.js.
from __future__ import annotations

import datetime

EN_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
AR_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]


def _parse(d: str | datetime.date | None) -> datetime.date | None:
    if not d:
        return None
    if isinstance(d, datetime.date):
        return d
    return datetime.date.fromisoformat(d)


def format_date_en(d: str | datetime.date | None) -> str:
    dt = _parse(d)
    if not dt:
        return "[Notice Date]"
    return f"{dt.day:02d} {EN_MONTHS[dt.month - 1]} {dt.year}"


def format_date_ar(d: str | datetime.date | None) -> str:
    dt = _parse(d)
    if not dt:
        return "[تاريخ الإنذار]"
    return f"{dt.day:02d} {AR_MONTHS[dt.month - 1]} {dt.year}"


def get_expiry_date(d: str | datetime.date | None, days: int = 365) -> datetime.date | None:
    dt = _parse(d)
    if not dt:
        return None
    return dt + datetime.timedelta(days=days)


def format_expiry_en(d: str | datetime.date | None, days: int = 365) -> str:
    dt = get_expiry_date(d, days)
    if not dt:
        return "[Expiry Date]"
    return f"{dt.day:02d} {EN_MONTHS[dt.month - 1]} {dt.year}"


def format_expiry_ar(d: str | datetime.date | None, days: int = 365) -> str:
    dt = get_expiry_date(d, days)
    if not dt:
        return "[تاريخ الانتهاء]"
    return f"{dt.day:02d} {AR_MONTHS[dt.month - 1]} {dt.year}"


def fallback(val, placeholder: str) -> str:
    return str(val).strip() if val and str(val).strip() else placeholder
