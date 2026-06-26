"""
Text generation for agent_summary, recommended_next_action, customer_reply.

These are built from fixed, safe templates grounded in the matched transaction — never
from the raw complaint — so they cannot hallucinate and cannot be steered by prompt
injection. customer_reply is produced in English or Bangla (SAMPLE-07 expects a Bangla
reply to a Bangla complaint). safety.py still scrubs every field on the way out.

Each template obeys the Section-8 safety rules:
  * never solicits PIN/OTP/password/card,
  * never promises a refund/reversal/unblock ("any eligible amount will be returned
    through official channels"),
  * directs only to official support channels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .schemas import CaseType, EvidenceVerdict

PROTECT_EN = " Please do not share your PIN or OTP with anyone."
PROTECT_BN = " অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"


@dataclass
class ReplyContext:
    case_type: CaseType
    verdict: EvidenceVerdict
    relevant_id: Optional[str]
    amount: Optional[float]
    counterparty: Optional[str]
    status: Optional[str]
    established_recipient: bool
    ambiguous: bool
    lang: str  # "en" | "bn"
    contested_refund: bool = False


def _amt(amount: Optional[float]) -> str:
    if amount is None:
        return ""
    if float(amount).is_integer():
        return f"{int(amount)} BDT"
    return f"{amount} BDT"


def _txn_ref(rid: Optional[str]) -> str:
    return rid or "the relevant transaction"


def build_texts(ctx: ReplyContext) -> tuple[str, str, str]:
    """Return (agent_summary, recommended_next_action, customer_reply)."""
    summary = _summary(ctx)
    action = _action(ctx)
    reply = _reply_bn(ctx) if ctx.lang == "bn" else _reply_en(ctx)
    return summary, action, reply


# --- agent_summary (English; agent-facing, neutral) --------------------------

def _summary(c: ReplyContext) -> str:
    amt, rid, cp = _amt(c.amount), _txn_ref(c.relevant_id), c.counterparty or "the recipient"
    ct = c.case_type
    if ct == CaseType.wrong_transfer:
        if c.ambiguous or c.relevant_id is None:
            return ("Customer reports a transfer was not received; multiple "
                    "transactions of the stated amount exist to different recipients, "
                    "so the specific transaction cannot be confirmed without more detail.")
        if c.established_recipient:
            return (f"Customer claims {rid} ({amt} to {cp}) was a wrong transfer, but "
                    f"transaction history shows prior activity with the same "
                    f"counterparty, suggesting an established recipient.")
        return (f"Customer reports sending {amt} via {rid} to {cp}, which they now "
                f"believe was the wrong recipient.")
    if ct == CaseType.payment_failed:
        return (f"Customer reports that payment {rid} ({amt}) failed but the balance "
                f"may have been deducted; requires payments operations review.")
    if ct == CaseType.duplicate_payment:
        return (f"Customer reports a duplicate {amt} payment; two matching "
                f"transactions exist and {rid} is the likely duplicate.")
    if ct == CaseType.agent_cash_in_issue:
        return (f"Customer reports an agent cash-in of {amt} ({rid}, status "
                f"{c.status or 'unknown'}) not reflected in their balance.")
    if ct == CaseType.merchant_settlement_delay:
        return (f"Merchant reports settlement {rid} ({amt}, status "
                f"{c.status or 'pending'}) is delayed beyond the expected window.")
    if ct == CaseType.refund_request:
        if c.contested_refund:
            return (f"Customer requests refund review for {rid} ({amt}) due to a "
                    f"reported merchant delivery or service failure.")
        return (f"Customer requests a refund of {amt} for {rid}; appears to be a "
                f"change-of-mind request rather than a service failure.")
    if ct == CaseType.phishing_or_social_engineering:
        return ("Customer reports a suspected scam / social-engineering attempt "
                "soliciting credentials; likely fraud, requires fraud-risk handling.")
    return ("Customer raises a general concern without enough detail to identify a "
            "specific transaction; needs clarification.")


# --- recommended_next_action (English; agent-facing, conditional, no promises) -

def _action(c: ReplyContext) -> str:
    rid = _txn_ref(c.relevant_id)
    ct = c.case_type
    if ct == CaseType.wrong_transfer:
        if c.ambiguous or c.relevant_id is None:
            return ("Ask the customer for the recipient's number to identify the "
                    "correct transaction before initiating any dispute.")
        if c.established_recipient:
            return (f"Flag for human review; confirm with the customer whether {rid} "
                    f"was genuinely a wrong transfer given prior activity with this "
                    f"recipient.")
        return (f"Verify {rid} with the customer and initiate the wrong-transfer "
                f"dispute workflow per policy.")
    if ct == CaseType.payment_failed:
        return (f"Investigate the ledger status of {rid}. If the amount was deducted "
                f"on a failed payment, initiate the reversal flow within standard SLA.")
    if ct == CaseType.duplicate_payment:
        return (f"Verify the duplicate with payments operations. If the biller "
                f"confirms a single charge, initiate reversal of {rid} per policy.")
    if ct == CaseType.agent_cash_in_issue:
        return (f"Investigate the pending cash-in {rid} with agent operations and "
                f"confirm the settlement state within the standard SLA.")
    if ct == CaseType.merchant_settlement_delay:
        return (f"Route to merchant operations to verify the settlement batch status "
                f"for {rid} and communicate a revised ETA if it is delayed.")
    if ct == CaseType.refund_request:
        if c.contested_refund:
            return ("Flag for human review; collect merchant/order context and assess "
                    "the disputed delivery or service claim per policy.")
        return ("Inform the customer that refund eligibility depends on the merchant's "
                "policy and guide them through the standard refund process.")
    if ct == CaseType.phishing_or_social_engineering:
        return ("Escalate to the fraud-risk team immediately, confirm to the customer "
                "that the company never asks for OTP/PIN, and log the reported contact "
                "for fraud pattern analysis.")
    return ("Reply to the customer requesting the transaction ID, amount, and a short "
            "description of the issue so it can be investigated.")


# --- customer_reply (English) ------------------------------------------------

def _reply_en(c: ReplyContext) -> str:
    rid = c.relevant_id
    ct = c.case_type
    if ct == CaseType.wrong_transfer:
        if c.ambiguous or rid is None:
            return ("Thank you for reaching out. We see more than one transaction of "
                    "that amount on the date in question. Could you share the "
                    "recipient's number so we can identify the correct transaction?"
                    + PROTECT_EN)
        return (f"We have noted your concern about transaction {rid}. Our dispute team "
                f"will review the case and contact you through official support "
                f"channels." + PROTECT_EN)
    if ct == CaseType.payment_failed:
        ref = f"transaction {rid}" if rid else "your transaction"
        return (f"We have noted that {ref} may have caused an unexpected balance "
                f"deduction. Our payments team will review it and any eligible amount "
                f"will be returned through official channels." + PROTECT_EN)
    if ct == CaseType.duplicate_payment:
        ref = f"transaction {rid}" if rid else "the reported payment"
        return (f"We have noted the possible duplicate payment for {ref}. Our payments "
                f"team will verify with the biller and any eligible amount will be "
                f"returned through official channels." + PROTECT_EN)
    if ct == CaseType.agent_cash_in_issue:
        ref = f"cash-in transaction {rid}" if rid else "your reported cash-in"
        return (f"We have noted your concern about {ref}. Our agent operations team "
                f"will verify it and update you through official channels." + PROTECT_EN)
    if ct == CaseType.merchant_settlement_delay:
        ref = f"settlement {rid}" if rid else "your settlement"
        return (f"We have noted your concern about {ref}. Our merchant operations team "
                f"will check the batch status and update you on the expected settlement "
                f"time through official channels.")
    if ct == CaseType.refund_request:
        return ("Thank you for reaching out. Refunds for completed merchant payments "
                "depend on the merchant's own policy. We recommend contacting the "
                "merchant directly, and we can guide you through official support "
                "channels if needed." + PROTECT_EN)
    if ct == CaseType.phishing_or_social_engineering:
        return ("Thank you for reaching out before sharing any information. We never "
                "ask for your PIN, OTP, or password under any circumstances, and you "
                "should never share them with anyone, even if they claim to be from us. "
                "Our fraud team has been notified of this incident.")
    return ("Thank you for reaching out. To help you faster, please share the "
            "transaction ID, the amount involved, and a short description of what went "
            "wrong." + PROTECT_EN)


# --- customer_reply (Bangla) -------------------------------------------------

def _reply_bn(c: ReplyContext) -> str:
    rid = c.relevant_id
    ct = c.case_type
    if ct == CaseType.wrong_transfer:
        if c.ambiguous or rid is None:
            return ("আপনার বার্তার জন্য ধন্যবাদ। ওই দিনে একই পরিমাণের একাধিক লেনদেন "
                    "রয়েছে। সঠিক লেনদেনটি শনাক্ত করতে অনুগ্রহ করে প্রাপকের নম্বরটি জানান।"
                    + PROTECT_BN)
        return (f"আপনার লেনদেন {rid} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের ডিসপিউট দল বিষয়টি "
                f"যাচাই করে অফিসিয়াল চ্যানেলের মাধ্যমে আপনার সাথে যোগাযোগ করবে।" + PROTECT_BN)
    if ct == CaseType.payment_failed:
        ref = f"লেনদেন {rid}" if rid else "আপনার লেনদেন"
        return (f"{ref} এ অপ্রত্যাশিত ব্যালেন্স কর্তন হয়ে থাকতে পারে বলে আমরা অবগত হয়েছি। "
                f"আমাদের পেমেন্ট দল এটি যাচাই করবে এবং প্রযোজ্য কোনো অর্থ অফিসিয়াল চ্যানেলের "
                f"মাধ্যমে ফেরত দেওয়া হবে।" + PROTECT_BN)
    if ct == CaseType.duplicate_payment:
        ref = f"লেনদেন {rid}" if rid else "উল্লেখিত পেমেন্ট"
        return (f"{ref} এ সম্ভাব্য ডাবল পেমেন্টের বিষয়ে আমরা অবগত হয়েছি। আমাদের পেমেন্ট দল "
                f"বিলারের সাথে যাচাই করবে এবং প্রযোজ্য কোনো অর্থ অফিসিয়াল চ্যানেলের মাধ্যমে "
                f"ফেরত দেওয়া হবে।" + PROTECT_BN)
    if ct == CaseType.agent_cash_in_issue:
        ref = f"লেনদেন {rid}" if rid else "আপনার ক্যাশ-ইন"
        return (f"আপনার {ref} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত "
                f"যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে।" + PROTECT_BN)
    if ct == CaseType.merchant_settlement_delay:
        ref = f"সেটেলমেন্ট {rid}" if rid else "আপনার সেটেলমেন্ট"
        return (f"আপনার {ref} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের মার্চেন্ট অপারেশন্স দল ব্যাচ "
                f"স্ট্যাটাস যাচাই করে প্রত্যাশিত সময় সম্পর্কে অফিসিয়াল চ্যানেলে আপনাকে জানাবে।")
    if ct == CaseType.refund_request:
        return ("আপনার বার্তার জন্য ধন্যবাদ। সম্পন্ন হওয়া মার্চেন্ট পেমেন্টের রিফান্ড "
                "মার্চেন্টের নিজস্ব নীতির উপর নির্ভর করে। আমরা সরাসরি মার্চেন্টের সাথে "
                "যোগাযোগের পরামর্শ দিচ্ছি এবং প্রয়োজনে অফিসিয়াল চ্যানেলে আপনাকে সহায়তা করব।"
                + PROTECT_BN)
    if ct == CaseType.phishing_or_social_engineering:
        return ("কোনো তথ্য শেয়ার করার আগে যোগাযোগ করার জন্য ধন্যবাদ। আমরা কখনোই আপনার পিন, "
                "ওটিপি বা পাসওয়ার্ড চাই না; কেউ আমাদের পরিচয় দিলেও এগুলো কারো সাথে শেয়ার "
                "করবেন না। আমাদের ফ্রড দলকে এই বিষয়ে অবহিত করা হয়েছে।")
    return ("আপনার বার্তার জন্য ধন্যবাদ। দ্রুত সহায়তার জন্য অনুগ্রহ করে লেনদেন আইডি, অর্থের "
            "পরিমাণ এবং সমস্যার সংক্ষিপ্ত বিবরণ জানান।" + PROTECT_BN)
