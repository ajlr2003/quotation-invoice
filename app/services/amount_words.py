# =============================================================================
# app/services/amount_words.py
# -----------------------------------------------------------------------------
# "Amount in words" for the printed tax invoice, in English and Arabic, in the
# house style of the invoice:
#   THREE THOUSAND AND FORTY (USD) AND EIGHTY-NINE (CENT)
#   ثلاثة آلاف و أربعون (دولار) و تسعة و ثمانون (سنت فقط لاغير)
# =============================================================================

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from num2words import num2words

# currency -> (English unit, English sub-unit, Arabic unit, Arabic sub-unit)
_NAMES = {
    "SAR": ("SR", "HALAA", "ريال سعودي", "هللة"),
    "USD": ("USD", "CENT", "دولار", "سنت"),
    "EUR": ("EUR", "CENT", "يورو", "سنت"),
    "GBP": ("GBP", "PENCE", "جنيه إسترليني", "بنس"),
    "AED": ("AED", "FILS", "درهم إماراتي", "فلس"),
}


def amount_in_words(amount: float, currency: str) -> tuple[str, str]:
    """Return ``(english, arabic)`` wording for a money amount."""
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    major = int(d)
    minor = int((d - major) * 100)
    en_unit, en_sub, ar_unit, ar_sub = _NAMES.get(currency, (currency, "", currency, ""))

    en = f"{num2words(major, lang='en')} ({en_unit}) AND {num2words(minor, lang='en')}"
    en += f" ({en_sub})" if en_sub else ""
    ar = f"{num2words(major, lang='ar')} ({ar_unit}) و {num2words(minor, lang='ar')}"
    ar += f" ({ar_sub} فقط لاغير)" if ar_sub else " فقط لاغير"
    return en.upper(), ar
