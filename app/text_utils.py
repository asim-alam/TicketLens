"""
Small, dependency-free text helpers shared by the reasoning engine.

Trilingual support is a scoring lever (Bangla/Banglish tie-breaker), so we:
  * map Bangla (Bengali) digits to ASCII before extracting money amounts,
  * extract amount-like numbers while ignoring phone numbers / times,
  * decide which language to answer the customer in.
"""
from __future__ import annotations

import re

# Bengali (Bangla) digit -> ASCII digit.
_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Any character in the Bengali Unicode block.
_BANGLA_RE = re.compile(r"[ঀ-৿]")

# A standalone number of 2..7 digits (optionally grouped/decimal). 2+ digits skips
# stray "2pm"; <=7 digits skips 11-digit phone numbers like 01712345678.
_NUMBER_RE = re.compile(r"\b\d{2,7}(?:\.\d+)?\b")


def to_ascii_digits(text: str) -> str:
    return (text or "").translate(_BANGLA_DIGITS)


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace. Bangla script is preserved for keyword hits."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def has_bangla(text: str) -> bool:
    return bool(_BANGLA_RE.search(text or ""))


def extract_amounts(text: str) -> set[float]:
    """Return the set of amount-like numbers mentioned in the complaint (BDT)."""
    t = to_ascii_digits(text or "")
    # Drop thousands separators: "15,000" -> "15000".
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    out: set[float] = set()
    for m in _NUMBER_RE.findall(t):
        try:
            out.add(float(m))
        except ValueError:
            continue
    return out


def reply_language(language: str | None, complaint: str) -> str:
    """
    Choose the language for customer_reply: "bn" or "en".

    Bangla reply when the request says bn, or (no/short hint) the complaint is
    written predominantly in Bangla script. Romanized "banglish" and "mixed" get
    an English reply (clear and unambiguous, which is the safer default).
    """
    lang = (language or "").strip().lower()
    if lang == "bn":
        return "bn"
    if lang in {"en", "mixed"}:
        return "en"
    # No reliable hint: infer from script.
    text = complaint or ""
    bangla = len(_BANGLA_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if bangla > 0 and bangla >= latin:
        return "bn"
    return "en"
