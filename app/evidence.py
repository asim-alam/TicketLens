"""
The "investigator" core (Evidence Reasoning = 35 pts).

Given the case_type, the complaint, and the transaction_history, decide:
  * relevant_transaction_id : which transaction the complaint refers to (or None)
  * evidence_verdict        : consistent | inconsistent | insufficient_data

Guiding principle from the problem statement: "When the evidence is genuinely
unclear, the system must say so, not guess." So we only return `consistent` when a
transaction concretely supports the complaint, `inconsistent` when the data
contradicts it (e.g. an "established recipient" undercutting a wrong-transfer claim),
and `insufficient_data` whenever the match is absent or ambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .schemas import CaseType, EvidenceVerdict
from .text_utils import extract_amounts


@dataclass
class MatchResult:
    relevant_id: Optional[str]
    verdict: EvidenceVerdict
    matched_txn: object = None
    established_recipient: bool = False
    ambiguous: bool = False
    matched_status: Optional[str] = None
    matched_amount: Optional[float] = None


def _ts_key(txn) -> tuple:
    """Sortable timestamp key; falls back to a constant so order is stable."""
    raw = getattr(txn, "timestamp", None)
    if not raw:
        return (0, "")
    try:
        return (1, datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return (0, str(raw))


def _amount(txn) -> Optional[float]:
    a = getattr(txn, "amount", None)
    return float(a) if a is not None else None


def _type(txn) -> str:
    return (getattr(txn, "type", None) or "").lower()


def _status(txn) -> str:
    return (getattr(txn, "status", None) or "").lower()


def _cp(txn) -> str:
    return str(getattr(txn, "counterparty", None) or "")


def _id(txn) -> Optional[str]:
    return getattr(txn, "transaction_id", None)


def _most_recent(txns: list):
    return max(txns, key=_ts_key) if txns else None


def _amount_matches(txns: list, amounts: set[float]) -> list:
    if not amounts:
        return []
    return [t for t in txns if _amount(t) is not None and _amount(t) in amounts]


def _count_counterparty(history: list, cp: str) -> int:
    return sum(1 for t in history if _cp(t) == cp and cp != "")


def investigate(case_type: CaseType, complaint: str, history: list) -> MatchResult:
    amounts = extract_amounts(complaint)

    # Phishing: by definition not tied to a customer transaction in history.
    if case_type == CaseType.phishing_or_social_engineering:
        return MatchResult(None, EvidenceVerdict.insufficient_data)

    if not history:
        return MatchResult(None, EvidenceVerdict.insufficient_data)

    if case_type == CaseType.duplicate_payment:
        return _duplicate(history, amounts)
    if case_type == CaseType.wrong_transfer:
        return _wrong_transfer(history, amounts)
    if case_type == CaseType.payment_failed:
        return _by_type_status(history, amounts, types=("payment", "cash_out",
                               "transfer"), good_status=("failed", "pending"))
    if case_type == CaseType.agent_cash_in_issue:
        return _by_type_status(history, amounts, types=("cash_in",),
                               good_status=("pending", "failed"))
    if case_type == CaseType.merchant_settlement_delay:
        return _by_type_status(history, amounts, types=("settlement",),
                               good_status=("pending", "failed"))
    if case_type == CaseType.refund_request:
        return _refund(history, amounts)
    return _other(history, amounts)


# --- per-case matchers -------------------------------------------------------

def _duplicate(history: list, amounts: set[float]) -> MatchResult:
    # Group by (amount, counterparty); a group of 2+ is the duplicate shape.
    groups: dict[tuple, list] = {}
    for t in history:
        amt, cp = _amount(t), _cp(t)
        if amt is None or not cp:
            continue
        groups.setdefault((round(amt, 2), cp), []).append(t)

    dup_groups = [g for g in groups.values() if len(g) >= 2]
    if dup_groups:
        if amounts:
            preferred = [g for g in dup_groups if round(_amount(g[0]), 2) in amounts]
            dup_groups = preferred or dup_groups
        group = max(dup_groups, key=len)
        # The duplicate is the LATER charge: latest timestamp, tie-break by the
        # later position in history (so identical untimestamped entries still pick
        # the second one).
        pos = {id(t): i for i, t in enumerate(history)}
        later = max(group, key=lambda t: (_ts_key(t), pos[id(t)]))
        return MatchResult(_id(later), EvidenceVerdict.consistent, later,
                           matched_status=_status(later), matched_amount=_amount(later))

    # Claimed a duplicate but only one matching record -> cannot confirm.
    single = _amount_matches(history, amounts)
    if len(single) == 1:
        t = single[0]
        return MatchResult(_id(t), EvidenceVerdict.insufficient_data, t,
                           matched_status=_status(t), matched_amount=_amount(t))
    return MatchResult(None, EvidenceVerdict.insufficient_data)


def _wrong_transfer(history: list, amounts: set[float]) -> MatchResult:
    transfers = [t for t in history if _type(t) in ("transfer", "cash_out", "payment")]
    # Prefer real transfers; fall back to all if none typed as transfer.
    pure_transfers = [t for t in history if _type(t) == "transfer"]
    pool = pure_transfers or transfers or list(history)

    matched = _amount_matches(pool, amounts)

    if amounts and matched:
        distinct_cps = {_cp(t) for t in matched}
        if len(matched) == 1:
            t = matched[0]
            established = _count_counterparty(history, _cp(t)) >= 2
            verdict = (EvidenceVerdict.inconsistent if established
                       else EvidenceVerdict.consistent)
            return MatchResult(_id(t), verdict, t, established_recipient=established,
                               matched_status=_status(t), matched_amount=_amount(t))
        if len(distinct_cps) == 1:
            # Several transfers, all to the SAME counterparty -> established recipient.
            t = _most_recent(matched)
            return MatchResult(_id(t), EvidenceVerdict.inconsistent, t,
                               established_recipient=True, matched_status=_status(t),
                               matched_amount=_amount(t))
        # Several candidate transfers to DIFFERENT recipients -> ambiguous.
        return MatchResult(None, EvidenceVerdict.insufficient_data, ambiguous=True)

    if not amounts:
        if len(pool) == 1:
            t = pool[0]
            established = _count_counterparty(history, _cp(t)) >= 2
            verdict = (EvidenceVerdict.inconsistent if established
                       else EvidenceVerdict.consistent)
            return MatchResult(_id(t), verdict, t, established_recipient=established,
                               matched_status=_status(t), matched_amount=_amount(t))
        return MatchResult(None, EvidenceVerdict.insufficient_data, ambiguous=True)

    # Amount given but nothing matched it.
    return MatchResult(None, EvidenceVerdict.insufficient_data)


def _by_type_status(history: list, amounts: set[float], types: tuple,
                    good_status: tuple) -> MatchResult:
    typed = [t for t in history if _type(t) in types]
    pool = typed or list(history)

    matched = _amount_matches(pool, amounts)
    if amounts and not matched:
        # Amount mentioned but no transaction of the right type matches it.
        if not typed:
            return MatchResult(None, EvidenceVerdict.insufficient_data)
        matched = typed  # amount maybe paraphrased; still consider typed txns
    candidates = matched or typed
    if not candidates:
        return MatchResult(None, EvidenceVerdict.insufficient_data)

    # Prefer a candidate whose status matches the complaint shape (failed/pending).
    good = [t for t in candidates if _status(t) in good_status]
    chosen = _most_recent(good) if good else _most_recent(candidates)
    status = _status(chosen)

    if status in good_status:
        verdict = EvidenceVerdict.consistent
    elif status == "completed":
        # System shows the money moved/settled — contradicts the failure/non-receipt claim.
        verdict = EvidenceVerdict.inconsistent
    else:
        verdict = EvidenceVerdict.consistent
    return MatchResult(_id(chosen), verdict, chosen, matched_status=status,
                       matched_amount=_amount(chosen))


def _refund(history: list, amounts: set[float]) -> MatchResult:
    payments = [t for t in history if _type(t) in ("payment", "transfer")]
    pool = payments or list(history)
    matched = _amount_matches(pool, amounts)
    if matched:
        t = _most_recent(matched)
        return MatchResult(_id(t), EvidenceVerdict.consistent, t,
                           matched_status=_status(t), matched_amount=_amount(t))
    if not amounts and len(pool) == 1:
        t = pool[0]
        return MatchResult(_id(t), EvidenceVerdict.consistent, t,
                           matched_status=_status(t), matched_amount=_amount(t))
    return MatchResult(None, EvidenceVerdict.insufficient_data)


def _other(history: list, amounts: set[float]) -> MatchResult:
    matched = _amount_matches(history, amounts)
    if len(matched) == 1:
        t = matched[0]
        return MatchResult(_id(t), EvidenceVerdict.insufficient_data, t,
                           matched_status=_status(t), matched_amount=_amount(t))
    return MatchResult(None, EvidenceVerdict.insufficient_data)
