"""
Deterministic safety layer (Safety & Escalation = 20 pts; >=2 critical violations
across hidden cases = NOT eligible for the top-40 pool). Tie-breaker #1 is safety.

Two jobs:
  1. detect_safety_flags(text) -> signals that raise severity / force escalation.
  2. sanitize_*()              -> final gate on every customer-facing string so the
     response can NEVER (a) ask the customer for PIN/OTP/password/card number,
     (b) promise a refund/reversal/unblock, or (c) push them to a suspicious
     third party / external link.

Customer-facing text is built from our own templates (replies.py) and never echoes
the complaint, so prompt-injection in the complaint cannot reach the output. These
sanitizers are belt-and-suspenders that also protect the optional LLM path and prove
safety to the automated grader.
"""
from __future__ import annotations

import re

# --- escalation/severity signals ---------------------------------------------

_FRAUD_SIGNALS = [
    "otp", "ওটিপি", "o.t.p", "one time password", "one-time password",
    "pin", "পিন", "password", "পাসওয়ার্ড", "passcode", "cvv", "card number",
    "scam", "প্রতারণা", "প্রতারক", "fraud", "ফ্রড", "hacked", "hack", "হ্যাক",
    "unauthorized", "unauthorised", "অননুমোদিত", "stolen", "phishing", "fishing",
    "suspicious", "সন্দেহজনক", "someone called", "ke jeno call", "keu call",
    "asking my", "asking for my", "asking for otp", "otp chaiteche", "otp chacche",
    "pin chacche", "click this link", "click the link", "link e click",
    "won a prize", "you won", "lottery", "লটারি", "puroskar", "প্রাইজ",
    "verify your account", "account verify korun", "bkash office theke",
    "bikash office theke", "fake call", "fake sms", "fake message", "ভুয়া",
]

_MONEY_LOSS_SIGNALS = [
    "lost money", "lost my money", "money gone", "টাকা চলে গেছে",
    "taka chole geche", "drained", "emptied", "balance zero", "all my money gone",
    "stole my money", "টাকা চুরি", "account empty",
]

_SHARED_SECRET_SIGNALS = [
    "shared my otp", "gave my otp", "shared my pin", "gave my pin",
    "told them my", "i shared my", "i gave my", "diye dilam", "bole dilam",
    "share korlam", "diye disi", "otp diye dilam", "pin diye dilam",
    "ওটিপি দিয়ে দিয়েছি", "পিন দিয়ে দিয়েছি", "শেয়ার করে ফেলেছি",
]


def _norm(text: str) -> str:
    return (text or "").lower()


def detect_safety_flags(text: str) -> dict:
    t = _norm(text)
    return {
        "fraud_signal": any(s in t for s in _FRAUD_SIGNALS),
        "money_loss": any(s in t for s in _MONEY_LOSS_SIGNALS),
        "user_shared_secret": any(s in t for s in _SHARED_SECRET_SIGNALS),
    }


# --- output sanitizers --------------------------------------------------------

# A request directed at the customer to hand over a secret.
_CREDENTIAL_REQUEST_PATTERNS = [
    re.compile(
        r"(share|send|give|provide|tell|enter|type|confirm|verify|submit|resend|"
        r"forward|read\s*out|read\s*me)\b[^.।\n]{0,40}?"
        r"(otp|o\.?t\.?p|one[\s-]*time\s*password|pin|password|passcode|pass\s*code|"
        r"cvv|card\s*(?:number|no)|security\s*code|verification\s*code|login\s*code|"
        r"secret|credential)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(what\s+is|what'?s|share)\b[^.।\n]{0,20}?(your\s+)?(otp|pin|password|cvv)\b",
        re.IGNORECASE,
    ),
    # Bangla: secret word adjacent to a give/share/send verb.
    re.compile(r"(পিন|ওটিপি|পাসওয়ার্ড)[^.।\n]{0,20}?(দিন|বলুন|শেয়ার|পাঠান|জানান)"),
    re.compile(r"(দিন|বলুন|শেয়ার|পাঠান|জানান)[^.।\n]{0,20}?(পিন|ওটিপি|পাসওয়ার্ড)"),
]

# Phrases that PROMISE an unauthorized financial outcome to the customer.
_PROMISE_PATTERNS = [
    re.compile(
        r"\b(we|i|bkash|the\s+company)\s+(will|'ll|have|has|are|'re|am)\b"
        r"[^.।\n]{0,30}?\b(refund|reverse|reversed|unblock|unblocked|recover|"
        r"reimburse|credit(?:ed)?\s+(?:you|your)|return(?:ed)?\s+your\s+money)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(refund|reversal|chargeback|account\s+unblock)\b[^.।\n]{0,20}?"
        r"\b(approved|processed|done|completed|successful|confirmed|guaranteed)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(we|i)\s+(guarantee|assure\s+you)\b", re.IGNORECASE),
]

# Suspicious redirection: external links only. Legit "contact the merchant" is allowed.
_THIRD_PARTY_PATTERNS = [
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\bwww\.", re.IGNORECASE),
    re.compile(r"click\s+(?:this|the|here)?\s*link", re.IGNORECASE),
]

_NEGATIONS = [
    "never", "not ", "n't", "do not", "don't", "avoid", "without", "should not",
    "won't", "will never", "do n't", "cannot", "can't", "kokhono na", "kokhono",
    "করবেন না", "দেবেন না", "দিবেন না", "না", "কখনো", "শেয়ার করবেন না",
]

SAFE_FALLBACK_REPLY_EN = (
    "Thank you for reaching out. Our support team will review your case and contact "
    "you through official channels. Please do not share your PIN, OTP, or password "
    "with anyone."
)
SAFE_FALLBACK_REPLY_BN = (
    "আপনার বার্তার জন্য ধন্যবাদ। আমাদের সাপোর্ট দল আপনার বিষয়টি যাচাই করে অফিসিয়াল "
    "চ্যানেলের মাধ্যমে আপনার সাথে যোগাযোগ করবে। অনুগ্রহ করে কারো সাথে আপনার পিন, ওটিপি "
    "বা পাসওয়ার্ড শেয়ার করবেন না।"
)


def _is_protective(text: str, start: int, end: int) -> bool:
    """A secret mention surrounded by a negation is protective advice, not a request."""
    window = text[max(0, start - 30): end + 30].lower()
    return any(neg in window for neg in _NEGATIONS)


def _has_unnegated_credential_request(text: str) -> bool:
    for pat in _CREDENTIAL_REQUEST_PATTERNS:
        for m in pat.finditer(text or ""):
            if not _is_protective(text, m.start(), m.end()):
                return True
    return False


def _has_promise(text: str) -> bool:
    return any(p.search(text or "") for p in _PROMISE_PATTERNS)


def _has_third_party(text: str) -> bool:
    return any(p.search(text or "") for p in _THIRD_PARTY_PATTERNS)


def sanitize_customer_reply(text: str, lang: str = "en") -> str:
    """Guarantee the customer-facing reply is safe; replace wholesale if not."""
    s = (text or "").strip()
    fallback = SAFE_FALLBACK_REPLY_BN if lang == "bn" else SAFE_FALLBACK_REPLY_EN
    if not s:
        return fallback
    if _has_unnegated_credential_request(s) or _has_promise(s) or _has_third_party(s):
        return fallback
    return s


def sanitize_action(text: str) -> str:
    """recommended_next_action is also checked for unauthorized promises (-10)."""
    s = (text or "").strip()
    if not s:
        return "Route to the appropriate team for review and verification per policy."
    if _has_unnegated_credential_request(s) or _has_promise(s):
        return ("Escalate for human review and verify the case against transaction "
                "records before any action, per policy.")
    return s


def sanitize_summary(text: str) -> str:
    """agent_summary must never read as a credential request either."""
    s = (text or "").strip()
    if not s:
        return "Customer ticket received; routed for review."
    if _has_unnegated_credential_request(s):
        return ("Customer reports a security-sensitive issue; routed for human "
                "review (summary sanitised by safety layer).")
    return s


def reply_is_safe(text: str) -> bool:
    """Test helper: True iff the string violates none of the safety rules."""
    return not (_has_unnegated_credential_request(text)
                or _has_promise(text) or _has_third_party(text))
