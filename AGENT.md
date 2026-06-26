# CLAUDE.md / AGENT.md — Engineering guide (single source of truth)

> `CLAUDE.md` and `AGENT.md` are kept **identical**. Edit both together.

## Project purpose

**QueueStorm Investigator** — a backend AI/API copilot for a digital-finance (bKash-style)
support desk, built for the SUST Codex hackathon preliminary. It receives one customer
complaint plus that customer's recent `transaction_history` and returns one structured
JSON verdict. It is judged by an **automated harness** (then manual review of shortlisted
teams). The whole goal is the automated score: schema-exactness, evidence reasoning,
safety, reliability.

## The exact schema + enums (verbatim from CONTRACT.md)

**Endpoints:** `GET /health` → `{"status":"ok"}`; `POST /analyze-ticket` → response below.

**Response fields (all required except `confidence`/`reason_codes`):**
`ticket_id` (str, echoed) · `relevant_transaction_id` (str | **null**) ·
`evidence_verdict` (enum) · `case_type` (enum) · `severity` (enum) · `department` (enum) ·
`agent_summary` (str) · `recommended_next_action` (str) · `customer_reply` (str) ·
`human_review_required` (bool) · `confidence` (float 0..1) · `reason_codes` (str[]).

**Enums — character-exact (a variant = schema violation):**
- `case_type`: `wrong_transfer`, `payment_failed`, `refund_request`, `duplicate_payment`,
  `merchant_settlement_delay`, `agent_cash_in_issue`, `phishing_or_social_engineering`, `other`
- `department`: `customer_support`, `dispute_resolution`, `payments_ops`,
  `merchant_operations`, `agent_operations`, `fraud_risk`
- `severity`: `low`, `medium`, `high`, `critical`
- `evidence_verdict`: `consistent`, `inconsistent`, `insufficient_data`

**Status codes:** 200 success · 400 malformed (bad JSON / missing required) · 422 empty
complaint · 500 internal (no stack traces). Valid requests must **never** 5xx.

## Hard rules (do not break)

1. **Schema is exact.** Response enums are strict Pydantic enums in `schemas.py` — an invalid value cannot be emitted. Don't loosen them.
2. **Never 5xx on a valid request.** `main.py` wraps the pipeline in try/except → safe 200 fallback. Malformed → controlled 400/422 JSON.
3. **Safety is non-negotiable** (tie-breaker #1; ≥2 critical violations = disqualified). `customer_reply` / `recommended_next_action` must never solicit PIN/OTP/password/card, never promise a refund/reversal/unblock, never redirect to a suspicious third party. `safety.py` is the final gate — keep it.
4. **Rules-first; LLM optional & OFF.** The deterministic engine is a complete solution. The LLM (`llm.py`) is fallback-only, validated against enums, and may only *promote a low-confidence `other`*. It never writes the reply, severity, or escalation.
5. **No hardcoding the public samples.** They are calibration; hidden tests are broader. Generalize.
6. **No Docker. No database** (task is stateless — see CONTRACT §12). No real secrets in the repo.

## Architecture map (file-by-file)

- `app/schemas.py` — strict response enums + `TicketResponse`; lenient `TicketRequest` (request enums are plain optional strings) + defensive `TransactionEntry` (bad entries dropped).
- `app/text_utils.py` — `to_ascii_digits`, `extract_amounts`, `reply_language`, `has_bangla`.
- `app/classify.py` — `classify_case_type(...)`: priority-ordered, trilingual keyword banks (phishing → duplicate → agent_cash_in → settlement → wrong_transfer → payment_failed → refund → other).
- `app/evidence.py` — `investigate(...)`: picks `relevant_transaction_id` and the `evidence_verdict` (the 35-pt core).
- `app/rules.py` — `decide(...)`: severity, department, confidence, reason_codes; `_apply_escalation(...)` is the **single** source of truth for `human_review_required`.
- `app/replies.py` — EN/BN templates for the three text fields, grounded in the matched txn.
- `app/safety.py` — `detect_safety_flags`, `sanitize_customer_reply/action/summary`, `reply_is_safe`.
- `app/llm.py` — optional fallback (OFF by default).
- `app/main.py` — FastAPI app, `/health`, `/analyze-ticket`, error handlers, safe fallback.
- `index.py` — root Vercel entrypoint re-exporting the app (also `uvicorn index:app`).
- `tests/test_matrix.py` — 54-case matrix (must stay green).

## Escalation rule (human_review_required = true)

Phishing OR duplicate_payment OR agent_cash_in_issue OR (wrong_transfer with a specific
`relevant_transaction_id`) OR `severity == critical` OR `evidence_verdict == inconsistent`
OR effective amount ≥ 50000 OR user-shared-secret / money-loss. *(Reproduces all 10
public samples, including SAMPLE-08 = false.)*

## Run + test locally

```bash
python -m venv .venv && source .venv/Scripts/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --port 8000      # serve
pytest -q                              # 54 tests must pass
```

## Deploy (Vercel) + keep-warm

Vercel's FastAPI backend framework auto-detects the top-level `app` in the root
`index.py` (+ `requirements.txt`) and serves it at the base URL, so routes resolve at
the root (not `/api`); no `vercel.json` rewrites needed. Set env vars (e.g. `USE_LLM`) in
the Vercel project, not the repo. Cold starts can exceed p95≤5s on first hit — **ping
`/health` ~every 30s during judging** to stay warm. The app also runs on
Render/Railway/Fly/EC2 via `uvicorn app.main:app`.

## DO NOT

- Build a frontend, add Docker, or add a database.
- Let an LLM write the final response object or relax safety.
- Hardcode the public sample answers.
- Commit `.env`, `.env.local`, `Api.txt`, or any key. Only `.env.example` (names) is committed.
- Refactor in the final minutes — freeze and protect a working, deployed, green submission.

## For the second agent

- Tests live in `tests/test_matrix.py`. **Every change must keep `pytest` green and the schema exact.**
- Safety + escalation are rule-driven only. If you touch `safety.py`, re-run the adversarial tests and confirm `reply_is_safe` holds on all sample replies.
- Calibrate new logic against `tests/sample_cases.json`, but design for the broader hidden set described in `CONTRACT.md`.
