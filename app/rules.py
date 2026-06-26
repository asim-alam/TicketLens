"""
Deterministic decision orchestrator. Wires classify -> investigate -> severity ->
routing -> escalation -> text -> safety, and returns a fully-populated, SAFE dict of
response fields. No network, no randomness: same input -> same output.

This module owns the single source of truth for human_review_required
(`_apply_escalation`) and for severity/department/confidence/reason_codes.
"""
from __future__ import annotations

from .classify import (CONTESTED_REFUND_KW, DEDUCTION_KW, classify_case_type)
from .evidence import MatchResult, investigate
from .replies import ReplyContext, build_texts
from .safety import (detect_safety_flags, sanitize_action, sanitize_customer_reply,
                     sanitize_summary)
from .schemas import CaseType, Department, EvidenceVerdict, Severity
from .text_utils import extract_amounts, normalize, reply_language

_SEV_ORDER = [Severity.low, Severity.medium, Severity.high, Severity.critical]

_DEPARTMENT = {
    CaseType.wrong_transfer: Department.dispute_resolution,
    CaseType.payment_failed: Department.payments_ops,
    CaseType.duplicate_payment: Department.payments_ops,
    CaseType.agent_cash_in_issue: Department.agent_operations,
    CaseType.merchant_settlement_delay: Department.merchant_operations,
    CaseType.phishing_or_social_engineering: Department.fraud_risk,
    CaseType.refund_request: Department.customer_support,
    CaseType.other: Department.customer_support,
}


def _bump(sev: Severity, steps: int = 1) -> Severity:
    i = min(len(_SEV_ORDER) - 1, _SEV_ORDER.index(sev) + steps)
    return _SEV_ORDER[i]


def _effective_amount(complaint: str, match: MatchResult) -> float:
    if match.matched_amount is not None:
        return float(match.matched_amount)
    amounts = extract_amounts(complaint)
    return max(amounts) if amounts else 0.0


def _severity(case_type: CaseType, match: MatchResult, complaint: str,
              flags: dict) -> Severity:
    t = normalize(complaint)
    if case_type == CaseType.phishing_or_social_engineering:
        base = Severity.critical
    elif case_type == CaseType.wrong_transfer:
        base = (Severity.high if match.verdict == EvidenceVerdict.consistent
                else Severity.medium)
    elif case_type == CaseType.payment_failed:
        deducted = any(k in t for k in DEDUCTION_KW)
        base = Severity.high if deducted else Severity.medium
    elif case_type == CaseType.duplicate_payment:
        base = Severity.high
    elif case_type == CaseType.agent_cash_in_issue:
        base = Severity.high
    elif case_type == CaseType.merchant_settlement_delay:
        base = Severity.medium
    elif case_type == CaseType.refund_request:
        contested = any(k in t for k in CONTESTED_REFUND_KW)
        base = Severity.medium if contested else Severity.low
    else:  # other
        risky = any(k in t for k in ("account locked", "account blocked", "locked",
                                     "blocked", "suspended", "kyc", "nid"))
        base = Severity.medium if risky else Severity.low

    if flags.get("money_loss") or flags.get("user_shared_secret"):
        base = _bump(base)
    if _effective_amount(complaint, match) >= 50000:
        base = _bump(base)
    return base


def _department(case_type: CaseType, complaint: str) -> Department:
    if case_type == CaseType.refund_request:
        if any(k in normalize(complaint) for k in CONTESTED_REFUND_KW):
            return Department.dispute_resolution
        return Department.customer_support
    return _DEPARTMENT.get(case_type, Department.customer_support)


def _confidence(case_type: CaseType, match: MatchResult) -> float:
    v = match.verdict
    table = {
        CaseType.phishing_or_social_engineering: 0.95,
        CaseType.wrong_transfer: {EvidenceVerdict.consistent: 0.9,
                                  EvidenceVerdict.inconsistent: 0.75,
                                  EvidenceVerdict.insufficient_data: 0.65},
        CaseType.payment_failed: {EvidenceVerdict.consistent: 0.9,
                                  EvidenceVerdict.inconsistent: 0.7,
                                  EvidenceVerdict.insufficient_data: 0.6},
        CaseType.duplicate_payment: {EvidenceVerdict.consistent: 0.92,
                                     EvidenceVerdict.inconsistent: 0.7,
                                     EvidenceVerdict.insufficient_data: 0.7},
        CaseType.agent_cash_in_issue: {EvidenceVerdict.consistent: 0.88,
                                       EvidenceVerdict.inconsistent: 0.7,
                                       EvidenceVerdict.insufficient_data: 0.6},
        CaseType.merchant_settlement_delay: {EvidenceVerdict.consistent: 0.92,
                                             EvidenceVerdict.inconsistent: 0.7,
                                             EvidenceVerdict.insufficient_data: 0.6},
        CaseType.refund_request: 0.85,
        CaseType.other: 0.6,
    }
    entry = table.get(case_type, 0.6)
    if isinstance(entry, dict):
        return entry.get(v, 0.6)
    return entry


def _reason_codes(case_type: CaseType, match: MatchResult, severity: Severity,
                  complaint: str, flags: dict) -> list[str]:
    codes: list[str] = [case_type.value if case_type != CaseType.phishing_or_social_engineering
                        else "phishing"]
    v = match.verdict
    if v == EvidenceVerdict.consistent:
        codes.append("transaction_match")
    elif v == EvidenceVerdict.inconsistent:
        codes.append("established_recipient_pattern" if match.established_recipient
                     else "evidence_inconsistent")
    else:
        codes.append("ambiguous_match" if match.ambiguous else "needs_clarification")

    if case_type == CaseType.phishing_or_social_engineering:
        codes.append("credential_protection")
    elif case_type == CaseType.payment_failed and any(k in normalize(complaint)
                                                      for k in DEDUCTION_KW):
        codes.append("potential_balance_deduction")
    elif case_type == CaseType.duplicate_payment and v == EvidenceVerdict.consistent:
        codes.append("biller_verification_required")
    elif case_type == CaseType.merchant_settlement_delay:
        codes.append("settlement_delay")
    elif case_type == CaseType.agent_cash_in_issue and (match.matched_status == "pending"):
        codes.append("pending_transaction")

    if flags.get("prompt_injection"):
        codes.append("prompt_injection")

    if severity == Severity.critical:
        codes.append("critical_escalation")
    # De-dup, keep order, cap at 4.
    seen, out = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:4]


def _apply_escalation(case_type: CaseType, severity: Severity, match: MatchResult,
                      complaint: str, flags: dict) -> bool:
    """SINGLE source of truth for human_review_required (validated on all 10 samples)."""
    contested_refund = (case_type == CaseType.refund_request
                        and any(k in normalize(complaint) for k in CONTESTED_REFUND_KW))
    if case_type in (CaseType.phishing_or_social_engineering,
                     CaseType.duplicate_payment, CaseType.agent_cash_in_issue):
        return True
    if case_type == CaseType.wrong_transfer and match.relevant_id is not None:
        return True
    if contested_refund:
        return True
    if match.ambiguous:
        return True
    if severity == Severity.critical:
        return True
    if match.verdict == EvidenceVerdict.inconsistent:
        return True
    if _effective_amount(complaint, match) >= 50000:
        return True
    if flags.get("user_shared_secret") or flags.get("money_loss") or flags.get("prompt_injection"):
        return True
    return False


def decide(complaint: str, language: str | None, channel: str | None,
           user_type: str | None, history: list,
           case_type_override: CaseType | None = None) -> dict:
    flags = detect_safety_flags(complaint)
    case_type, _kw = classify_case_type(complaint, flags, history, user_type)
    # The OPTIONAL LLM may only promote a genuinely-ambiguous "other" to a specific
    # type. It can never override a safety-driven (phishing) or rule-matched case.
    if case_type_override is not None and case_type == CaseType.other:
        case_type = case_type_override
    match = investigate(case_type, complaint, history)

    severity = _severity(case_type, match, complaint, flags)
    department = _department(case_type, complaint)
    confidence = _confidence(case_type, match)
    human_review = _apply_escalation(case_type, severity, match, complaint, flags)
    reason_codes = _reason_codes(case_type, match, severity, complaint, flags)

    lang = reply_language(language, complaint)
    ctx = ReplyContext(
        case_type=case_type,
        verdict=match.verdict,
        relevant_id=match.relevant_id,
        amount=match.matched_amount,
        counterparty=getattr(match.matched_txn, "counterparty", None),
        status=match.matched_status,
        established_recipient=match.established_recipient,
        ambiguous=match.ambiguous,
        contested_refund=(case_type == CaseType.refund_request
                          and any(k in normalize(complaint) for k in CONTESTED_REFUND_KW)),
        lang=lang,
    )
    summary, action, reply = build_texts(ctx)

    return {
        "relevant_transaction_id": match.relevant_id,
        "evidence_verdict": match.verdict,
        "case_type": case_type,
        "severity": severity,
        "department": department,
        "agent_summary": sanitize_summary(summary),
        "recommended_next_action": sanitize_action(action),
        "customer_reply": sanitize_customer_reply(reply, lang),
        "human_review_required": human_review,
        "confidence": round(float(confidence), 2),
        "reason_codes": reason_codes,
    }
