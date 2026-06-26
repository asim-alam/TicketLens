# QueueStorm Investigator

A safe, evidence-grounded **complaint investigation API** for a digital-finance support
desk, built for the **bKash SUST CSE Carnival 2026 · Codex Community Hackathon**
(Online Preliminary). It reads one customer complaint plus that customer's recent
transaction history and returns a single structured JSON verdict: which transaction the
complaint refers to, whether the data supports the claim, what kind of case it is, who
should handle it, and a **safe** customer reply.

> Not a classifier — an **investigator**. The complaint says one thing; the data may say
> another. The service decides what is true, and says "insufficient data" rather than
> guessing.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Returns `{"status":"ok"}`. |
| `POST` | `/analyze-ticket` | Analyses one ticket and returns the structured response below. |

### Sample request
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today...",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {"transaction_id": "TXN-9101", "timestamp": "2026-04-14T14:08:22Z",
     "type": "transfer", "amount": 5000, "counterparty": "+8801719876543",
     "status": "completed"}
  ]
}
```

### Sample response
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to +8801719876543, which they now believe was the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 with the customer and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case and contact you through official support channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match"]
}
```
More worked examples (incl. a phishing case and a Bangla reply) are in
[`sample_output.json`](sample_output.json), generated from the public sample pack.

## Tech stack

- **Python 3.13**, **FastAPI** + **Pydantic v2** (strict response enums; lenient request parsing).
- **Deterministic rule engine** — no GPU, no database, no required network calls.
- **uvicorn** for local serving; deployable on **Vercel** (serverless) or any host.

## How it works (architecture)

```
app/
  schemas.py     Strict response enums + TicketResponse; lenient TicketRequest / TransactionEntry.
  text_utils.py  Bangla→ASCII digits, amount extraction, reply-language detection.
  classify.py    case_type from complaint text (EN + Bangla + Romanized), safety-first priority.
  evidence.py    THE INVESTIGATOR: relevant_transaction_id + evidence_verdict from history.
  rules.py       Orchestrator: severity, department, confidence, reason_codes + single escalation rule.
  replies.py     EN/BN agent_summary / recommended_next_action / customer_reply templates.
  safety.py      Detection flags + output sanitizers (the final safety gate).
  llm.py         OPTIONAL, OFF-by-default LLM fallback (case_type hint only; safety stays rule-driven).
  main.py        FastAPI app, error handlers, safe 200 fallback.
index.py         Root Vercel entrypoint (re-exports the FastAPI app; also `uvicorn index:app`).
tests/           54-case matrix: 10 samples + adversarial + malformed + multilingual + edge.
```

**Reasoning pipeline:** classify the case (priority-ordered, trilingual) → match the
relevant transaction by amount / type / status / recency → judge the evidence
(`consistent` / `inconsistent` / `insufficient_data`, e.g. an "established recipient"
makes a wrong-transfer claim *inconsistent*) → set severity + route to a department →
apply the single escalation rule → generate a safe, grounded reply.

## AI / MODELS

| Model | Where it runs | Why | Default |
|-------|---------------|-----|---------|
| **None (deterministic rules)** | In-process | The task is fully solvable with rules; gives zero-latency, zero-cost, zero-dependency, fully reproducible behaviour and cannot leak a credential request. | **Active** |
| Optional OpenAI-compatible LLM (Groq `llama-3.3-70b-versatile`; Cerebras / Gemini by swapping `LLM_BASE_URL`+`LLM_MODEL`) | External API (your key) | *Fallback only*: may suggest a more specific `case_type` for a low-confidence `other` ticket. Output is validated against our enums and discarded otherwise. | **Off** (`USE_LLM=0`) |

The LLM **never** writes the `customer_reply`, sets severity/escalation, or relaxes
safety — those are 100% rule-driven. With `USE_LLM=0` (the judging default) the service
makes no external calls.

## Safety logic

The `customer_reply` and `recommended_next_action` pass through `safety.py`, which
guarantees the output:
- **never asks for** PIN / OTP / password / CVV / card number (protective advice like
  "never share your OTP" is preserved; a genuine request is replaced with a safe reply);
- **never promises** a refund / reversal / account-unblock ("any eligible amount will be
  returned through official channels", not "we will refund you");
- **never redirects** to a suspicious third party or external link — only official channels.

Customer-facing text is built from our own templates and never echoes the complaint, so
**prompt injection in the complaint cannot reach the output**. Phishing/credential
reports are forced to `critical` + `fraud_risk` + human review.

## Run locally

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Then:
```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/analyze-ticket \
  -H "content-type: application/json" \
  -d '{"ticket_id":"TKT-001","complaint":"I sent 5000 to a wrong number","transaction_history":[{"transaction_id":"TXN-9101","type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}]}'
```

## Run the tests

```bash
pip install -r requirements.txt
pytest -q       # 54 cases: samples, safety/adversarial, malformed, multilingual, edge
```

## Deploy (Vercel)

Vercel's FastAPI backend framework auto-detects the top-level `app` exposed in the
root `index.py` (plus `requirements.txt`) and serves it at the **base URL**, so `/health`
and `/analyze-ticket` resolve at the root (not under `/api`). No `vercel.json` rewrites
are required. Set any optional env vars (e.g. `USE_LLM`) in the Vercel **project
settings**, never in the repo. The service also runs unchanged on Render / Railway / Fly
/ EC2 (`uvicorn app.main:app`), or via the local runbook above.

> **Keep-warm note:** serverless cold starts can exceed the p95≤5s target on the first
> hit. Ping `/health` ~every 30s during the judging window to keep an instance warm.

## Assumptions & known limitations

- **No persistence / DB / auth.** The task is stateless single-request analysis (recorded
  in `CONTRACT.md` §12); a database would only add latency and secret-handling risk.
- Amount matching uses numbers in the complaint (Bangla digits + comma grouping handled);
  a complaint that paraphrases the amount ("a few thousand") yields `insufficient_data`
  rather than a guess — by design.
- Classification is keyword/heuristic-based across EN/Bangla/Romanized; very unusual
  phrasings may fall back to `other` with `human_review_required`.
- The optional LLM path depends on your own key/quota and is off by default; reliability
  never depends on it.
- Only synthetic data is used; no real customer data and no real payment integration.

## Repository docs

- [`CONTRACT.md`](CONTRACT.md) — the verbatim API/enum/safety contract (source of truth).
- [`BUILD_PLAN.md`](BUILD_PLAN.md) — phased build plan with VERIFY gates.
- [`CLAUDE.md`](CLAUDE.md) / [`AGENT.md`](AGENT.md) — engineering guide for contributors/agents.
- [`.env.example`](.env.example) — environment variable names (no secrets).
