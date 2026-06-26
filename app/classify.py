"""
case_type classification from the complaint text (Evidence Reasoning, part of 35 pts).

Priority-ordered and SAFETY-FIRST: phishing/social-engineering is checked before any
money case, because a scam message often also mentions "send money", "failed", etc.
Trilingual keyword banks: English + Bangla (Unicode) + Romanized "banglish".

Pure functions, total determinism: same input -> same case_type.
"""
from __future__ import annotations

from .schemas import CaseType
from .text_utils import normalize

# --- keyword banks (lowercased substring match; Bangla kept verbatim) ---------

PHISHING_KW = [
    "otp", "ওটিপি", "o.t.p", "one time password", "one-time password",
    "pin", "পিন", "password", "পাসওয়ার্ড", "passcode", "pass code", "cvv",
    "card number", "card no", "verification code", "login code", "security code",
    "someone called", "ke jeno call", "keu call", "phone diye", "unknown number",
    "asking my otp", "asking for otp", "asking my pin", "asked for my otp",
    "asked for my pin", "otp chaiteche", "otp chacche", "pin chacche",
    "pin chaiteche", "share korte bolse", "scam", "প্রতারণা", "প্রতারক", "fraud",
    "ফ্রড", "phishing", "fishing", "suspicious", "সন্দেহজনক", "fake", "ভুয়া",
    "fake message", "fake sms", "fake call", "click this link", "click the link",
    "link e click", "ei link", "won a prize", "you won", "lottery", "লটারি",
    "puroskar", "প্রাইজ", "verify your account", "account verify korun",
    "bkash office theke", "bikash office theke", "shared my otp", "gave my otp",
    "diye dilam", "bole dilam", "claiming to be", "pretending to be",
]

DUPLICATE_KW = [
    "twice", "two times", "2 times", "double", "doubly", "duplicate", "duplicated",
    "deducted twice", "charged twice", "twice deducted", "charged two times",
    "double charge", "double charged", "duibar", "dui bar", "দুইবার", "দু'বার",
    "দুই বার", "duto", "duplicate payment", "paid once", "only paid once",
    "ekbar dewar kotha", "kete niyeche duibar",
]

CASHIN_INDICATORS = [
    "cash in", "cash-in", "cashin", "cash in korechi", "ক্যাশ ইন", "ক্যাশইন",
    "ক্যাশ-ইন", "ক্যাশ ইন করেছি", "deposit", "deposited", "জমা", "জমা দিয়েছি",
    "add money through agent", "agent e taka",
]
AGENT_INDICATORS = ["agent", "এজেন্ট", "ajent", "ejent", "agent-", "agent ", "এজেন্টের"]

SETTLEMENT_KW = [
    "settlement", "settle", "settled", "not settled", "settlement delay",
    "settlement hoyni", "নিষ্পত্তি", "payout", "disbursement", "settle hoyni",
    "merchant settlement", "sales not", "todays sales", "today's sales",
]

WRONG_TRANSFER_KW = [
    "wrong number", "ভুল নম্বরে", "ভুল নম্বর", "bhul number", "bhul nombor",
    "vul number", "wrong recipient", "wrong person", "wrong account",
    "sent to wrong", "wrong e pathiye", "vul e pathiye", "bhul e pathaisi",
    "mistakenly sent", "accidentally sent", "vul kore pathiye", "bhul kore pathiye",
    "wrong send money", "to the wrong", "another number by mistake", "incorrect number",
    "ভুল মানুষ", "ভুল জায়গায়", "wrong cash out to",
]

SEND_INDICATORS = [
    "sent", "send money", "i send", "transferred", "transfer korechi",
    "pathiyechi", "pathaisi", "পাঠিয়েছি", "পাঠিয়েছিলাম", "diyechilam", "diyechi",
]
NOT_RECEIVED_INDICATORS = [
    "didn't get it", "didn't get", "did not get", "didn't receive", "did not receive",
    "hasn't received", "haven't received", "not received it", "he didn't get",
    "she didn't get", "he says he didn't", "she says she didn't", "never received",
    "pai nai", "paini", "পাইনি", "পায়নি", "টাকা পায়নি", "received hoyni",
    " পায় নাই", "pay nai", "kintu pay nai",
]

PAYMENT_FAILED_KW = [
    "payment failed", "transaction failed", "failed transaction", "trx failed",
    "failed but", "deducted but", "balance deducted", "money deducted",
    "amount deducted", "taka kete", "টাকা কাটল", "টাকা কেটে", "kete niyeche",
    "kete nise", "kete nilo", "cash out failed", "send money failed",
    "add money failed", "recharge failed", "payment hoyni", "fail hoyeche",
    "fail hoise", "lenden bifol", "showed failed", "shows failed", "payment stuck",
    "transaction stuck", "atke geche", "stuck",
]
# Strong "money actually left the account" signal (raises payment_failed severity).
DEDUCTION_KW = [
    "deducted", "deduct", "kete", "কাটল", "কেটে", "cut", "charged", "kete niyeche",
    "balance kome", "taka chole", "debited", "টাকা চলে গেছে",
]

REFUND_KW = [
    "refund", "ফেরত", "ferot", "ferot chai", "taka ferot", "money back",
    "return my money", "want my money back", "give back my money", "cancel my order",
    "cancel the payment", "changed my mind", "mind change", "don't want it anymore",
    "do not want it", "no longer want", "refund chai", "refund chacchi",
    "ফেরত চাই", "টাকা ফেরত",
]
CONTESTED_REFUND_KW = [
    "not received", "didn't receive", "didn't get", "did not get",
    "merchant cheated", "merchant didn't", "scam", "fraud", "defective",
    "damaged", "wrong product", "service kharap", "did not deliver", "didn't deliver",
    "fake product", "cheated", "not delivered", "never delivered", "ঠকিয়েছে",
    "পণ্য পাইনি", "ডেলিভারি পাইনি",
]

ACCOUNT_RISK_KW = [
    "account locked", "account blocked", "locked", "blocked", "suspended",
    "account banned", "kyc", "nid", "অ্যাকাউন্ট লক", "অ্যাকাউন্ট বন্ধ",
]

PROBLEM_INDICATORS = [
    "আসেনি", "ashe ni", "asheni", "did not", "didn't", "not reflected",
    "not received", "missing", "hoyni", "hoy nai", "pai nai", "paini", "পাইনি",
    "dekhchi na", "দেখছি না", "নেই", "but", "kintu", "কিন্তু", "problem", "issue",
    "atke", "stuck", "ব্যালেন্সে আসেনি", "show korche na",
]


def _hits(text: str, bank: list[str]) -> list[str]:
    return [kw for kw in bank if kw in text]


def _any(text: str, bank: list[str]) -> bool:
    return any(kw in text for kw in bank)


def classify_case_type(complaint: str, flags: dict, history: list,
                       user_type: str | None) -> tuple[CaseType, list[str]]:
    """Return (case_type, matched_keywords)."""
    t = normalize(complaint)
    if not t:
        return CaseType.other, []

    # Prompt-injection text often mentions OTP/PIN as an instruction to the bot.
    # Keep real financial issue classification when a money pattern is present.
    defer_phishing = bool(flags.get("prompt_injection"))

    # 1. PHISHING / SOCIAL ENGINEERING (safety first) -------------------------
    ph = _hits(t, PHISHING_KW)
    if (ph or flags.get("fraud_signal") or flags.get("user_shared_secret")) and not defer_phishing:
        return CaseType.phishing_or_social_engineering, ph[:5] or ["fraud_signal"]

    # 2. DUPLICATE PAYMENT ----------------------------------------------------
    dup = _hits(t, DUPLICATE_KW)
    history_dup = _history_has_duplicate(history)
    if dup or (history_dup and _any(t, ["paid", "payment", "bill", "charged",
                                        "deducted", "kete", "kata"])):
        return CaseType.duplicate_payment, (dup[:5] or ["duplicate_in_history"])

    # 3. AGENT CASH-IN ISSUE --------------------------------------------------
    cashin = _any(t, CASHIN_INDICATORS)
    cashin_problem = _any(t, PROBLEM_INDICATORS) or _history_has_pending_type(history, "cash_in")
    if cashin and cashin_problem and (_any(t, AGENT_INDICATORS)
                                      or _history_has_type(history, "cash_in")):
        ev = _hits(t, CASHIN_INDICATORS)[:3]
        return CaseType.agent_cash_in_issue, ev or ["agent_cash_in"]

    # 4. MERCHANT SETTLEMENT DELAY -------------------------------------------
    settle = _hits(t, SETTLEMENT_KW)
    if settle or ((user_type or "").lower() == "merchant"
                  and _history_has_type(history, "settlement")):
        return CaseType.merchant_settlement_delay, (settle[:5] or ["settlement"])

    # 5. WRONG TRANSFER -------------------------------------------------------
    wrong = _hits(t, WRONG_TRANSFER_KW)
    transfer_not_received = _any(t, SEND_INDICATORS) and _any(t, NOT_RECEIVED_INDICATORS)
    if wrong or transfer_not_received:
        return CaseType.wrong_transfer, (wrong[:5] or ["transfer_not_received"])

    # 6. PAYMENT FAILED -------------------------------------------------------
    failed = _hits(t, PAYMENT_FAILED_KW)
    if failed:
        return CaseType.payment_failed, failed[:5]

    # 7. REFUND REQUEST -------------------------------------------------------
    refund = _hits(t, REFUND_KW)
    if refund:
        return CaseType.refund_request, refund[:5]

    if ph or flags.get("fraud_signal") or flags.get("user_shared_secret"):
        return CaseType.phishing_or_social_engineering, ph[:5] or ["fraud_signal"]

    # 8. OTHER ----------------------------------------------------------------
    return CaseType.other, _hits(t, ACCOUNT_RISK_KW)[:5]


# --- history helpers ---------------------------------------------------------

def _history_has_type(history: list, typ: str) -> bool:
    return any((getattr(x, "type", None) or "").lower() == typ for x in history)


def _history_has_pending_type(history: list, typ: str) -> bool:
    for x in history:
        if (getattr(x, "type", None) or "").lower() == typ and \
                (getattr(x, "status", None) or "").lower() in {"pending", "failed"}:
            return True
    return False


def _history_has_duplicate(history: list) -> bool:
    """Two+ transactions sharing amount AND counterparty (a duplicate-charge shape)."""
    seen: dict[tuple, int] = {}
    for x in history:
        amt = getattr(x, "amount", None)
        cp = getattr(x, "counterparty", None)
        if amt is None or cp is None:
            continue
        key = (round(float(amt), 2), str(cp))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 2:
            return True
    return False
