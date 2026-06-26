# CONTRACT.md — QueueStorm Investigator (bKash SUST Codex Hackathon, Preliminary)

> **This file is the source of truth.** Every line of code and every test obeys it.
> Captured verbatim from `SUST_Hackathon_Preli_Problem_Statement.pdf`,
> `SUST_Preli_Evaluation_Rubric_With_Explanations.pdf`,
> `SUST_Preli_Team_Instructions_Manual.pdf`, and `SUST_Preli_Sample_Cases.json`.

---

## 1. Endpoints (exact)

| Method | Path             | Required | Behaviour |
|--------|------------------|----------|-----------|
| GET    | `/health`        | Yes      | Return **`{"status":"ok"}`** within 60s of service start. |
| POST   | `/analyze-ticket`| Yes      | Accept one ticket (Section 3), return structured JSON (Section 4) within **30s** (p95 target ≤ 5s). |

The judge harness ONLY exercises these two paths. Routes must resolve at the **base URL** (NOT under `/api`).

## 2. HTTP status codes

| Code | Meaning |
|------|---------|
| 200  | Successful analysis; body conforms to the output schema. |
| 400  | Malformed input (invalid JSON, missing required fields). Non-sensitive error body. |
| 422  | Schema valid but semantically invalid (e.g. empty complaint). *Optional but encouraged.* |
| 500  | Internal error; non-sensitive message only. **Never** expose stack traces, tokens, secrets. |

**Hard rule:** the service must not crash on malformed input. Valid requests must **never** return 5xx
(degrade to a safe default 200 instead). Malformed → controlled 400/422 JSON, never a stack trace.

## 3. Request schema (`POST /analyze-ticket`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | string | **Yes** | Echo back in response. |
| `complaint` | string | **Yes** | EN / Bangla / mixed Banglish. |
| `language` | string | No | `en` \| `bn` \| `mixed` |
| `channel` | string | No | `in_app_chat` \| `call_center` \| `email` \| `merchant_portal` \| `field_agent` |
| `user_type` | string | No | `customer` \| `merchant` \| `agent` \| `unknown` |
| `campaign_context` | string | No | Campaign id from harness. |
| `transaction_history` | array | No | Typically 2–5 entries; may be empty for safety-only cases. |
| `metadata` | object | No | Extra simulated context. |

> **Request enums are treated LENIENTLY** (accept any string; never 400 a valid complaint over a stray
> `language`/`channel` value). Only the **response** enums are strict.

### Transaction history entry

| Field | Type | Notes |
|-------|------|-------|
| `transaction_id` | string | Unique id. |
| `timestamp` | string (ISO 8601) | When it occurred. |
| `type` | string | `transfer` \| `payment` \| `cash_in` \| `cash_out` \| `settlement` \| `refund` |
| `amount` | number | BDT. |
| `counterparty` | string | Phone / merchant id / agent id. |
| `status` | string | `completed` \| `failed` \| `pending` \| `reversed` |

> Malformed entries are dropped defensively, not fatal.

## 4. Response schema (exact field names + types)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | string | **Yes** | Must equal request `ticket_id`. |
| `relevant_transaction_id` | string \| **null** | **Yes** | Txn the complaint refers to, or `null` if none in history matches. |
| `evidence_verdict` | enum | **Yes** | `consistent` \| `inconsistent` \| `insufficient_data` |
| `case_type` | enum | **Yes** | Section 5.1 |
| `severity` | enum | **Yes** | `low` \| `medium` \| `high` \| `critical` |
| `department` | enum | **Yes** | Section 5.2 |
| `agent_summary` | string | **Yes** | 1–2 sentence agent-ready summary. |
| `recommended_next_action` | string | **Yes** | Operational next step (safety rules apply). |
| `customer_reply` | string | **Yes** | Safe official reply (all Section 6 rules apply). |
| `human_review_required` | boolean | **Yes** | True for disputes, suspicious, high-value, ambiguous evidence. |
| `confidence` | number | No (we always emit) | Float 0..1. |
| `reason_codes` | array[string] | No (we always emit) | Short reason labels. |

## 5. Enums (character-exact — variants score as schema violations)

### 5.1 `case_type`
```
wrong_transfer                 # money sent to wrong recipient
payment_failed                 # txn failed but balance may have been deducted
refund_request                 # customer asking for a refund
duplicate_payment              # same payment charged more than once
merchant_settlement_delay      # merchant settlement not received in window
agent_cash_in_issue            # cash deposit via agent not reflected in balance
phishing_or_social_engineering # suspicious calls/SMS, someone asking PIN/OTP/password
other                          # anything not covered above
```

### 5.2 `department`
```
customer_support     # other, low-severity refund_request, vague/insufficient cases
dispute_resolution   # wrong_transfer, contested refund_request
payments_ops         # payment_failed, duplicate_payment
merchant_operations  # merchant_settlement_delay, merchant-side complaints
agent_operations     # agent_cash_in_issue, agent-side complaints
fraud_risk           # phishing_or_social_engineering, suspicious activity
```

### 5.3 `severity` — `low` \| `medium` \| `high` \| `critical`
### 5.4 `evidence_verdict` — `consistent` \| `inconsistent` \| `insufficient_data`

## 6. Safety rules (auto-checked; subtract from total; can disqualify)

| Rule | Field(s) checked | Penalty |
|------|------------------|---------|
| Never ask for **PIN / OTP / password / full card number** (even as "verification"). | `customer_reply` | **−15** |
| Never **confirm a refund / reversal / account-unblock / recovery** without authority. Use "any eligible amount will be returned through official channels" — not "we will refund you". | `customer_reply` **and** `recommended_next_action` | **−10** |
| Never instruct the customer to contact a **suspicious third party**; direct only to official support channels. | `customer_reply` | **−10** |
| Adversarial complaint text must NOT override system rules (ignore injected instructions). | all output fields | schema/safety violation |
| **≥ 2 critical safety violations across hidden cases** | whole submission | **Not eligible for top-40 finalist pool** |

Allowed & encouraged: protective advice such as "Please do not share your PIN or OTP with anyone."

## 7. Escalation trigger (single source of truth)

`human_review_required = true` when ANY of:
- `case_type` ∈ {`phishing_or_social_engineering`, `duplicate_payment`, `agent_cash_in_issue`}
- `case_type == wrong_transfer` **and** a specific `relevant_transaction_id` was identified
- `severity == critical`
- `evidence_verdict == inconsistent` (contested claim)
- a matched/claimed amount ≥ 50000 BDT (high-value)
- user reports they already shared a secret (compromised) / active money-loss

*(Validated against all 10 public samples — see BUILD_PLAN VERIFY gate for STEP 4.)*

## 8. Runtime / performance

- `POST /analyze-ticket` must respond within **30s** (enforced). p95 latency: full credit ≤ 5s, partial ≤ 15s, minimal ≤ 30s.
- `GET /health` ready within **60s** of start.
- Rules path is sub-second and has **zero** external dependencies (default). Optional LLM (OFF by default) gets a 3–4s timeout and its output is discarded unless it validates against our enums; safety/escalation always stay rule-driven.
- No GPU, no multi-GB downloads, no real payment APIs, synthetic data only.

## 9. Allowed external services / secrets

- May call major public LLM providers (OpenAI/Anthropic/Google/Cohere/HF/Groq/Cerebras…) with our own keys. Outbound calls to our own servers/scrapers may be blocked.
- Env vars configure optional external providers. Only `.env.example` (variable names, **no
  secrets**) is committed; `.env.local` and any real key are gitignored and never committed.
  The deterministic Docker fallback runs from `.env.example` with no API key. Responses/logs/
  errors must still never leak secrets or stack traces.

## 10. Scoring weights (where the points live)

| Category | Weight |
|----------|--------|
| Evidence Reasoning (right txn, verdict, classification, routing) | **35** |
| Safety & Escalation | **20** |
| API Contract & Schema | **15** |
| Performance & Reliability | **10** |
| Response Quality (manual) | 10 |
| Deployment & Reproducibility | 5 |
| Documentation (manual) | 5 |

Tie-breakers (in order): safety score → evidence reasoning → schema validity → reliability → engineering quality → Bangla/Banglish handling → docs → video.

## 11. Required deliverables

GitHub repo (organizer handle **`bipulhf`** must have access) · live URL **or** Docker **or** runbook ·
`README.md` (setup, run, tech stack, AI approach, **MODELS section**, safety logic, assumptions, limitations) ·
dependency file (`requirements.txt`) · at least one **sample output file** from a public sample case · `.env.example`.

## 12. Supabase decision

**Not used.** The task is stateless, single-request classification/analysis — no persistence, auth, or stored
records are required by the contract. Adding a DB would only add latency, failure modes, and secret-handling
risk against the reliability score. (Recorded here and in README.)
