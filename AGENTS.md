# QueueStorm Investigator - Agent Guide

This is a backend-only API challenge for the bKash SUST CSE Carnival 2026 Codex Community Hackathon preliminary round. Optimize for automated scoring first: exact schema, evidence reasoning, safety, reliability, Docker/public deployment, then documentation.

## Project Overview

The app receives one support complaint plus optional `transaction_history` and returns a schema-exact investigation verdict. It is deterministic and rules-first. The optional LLM path is off by default and must never be required for tests, Docker, local runs, or deployment health.

## Official Endpoints

- `GET /health` returns exactly `{"status":"ok"}`.
- `POST /analyze-ticket` returns the response schema defined in `CONTRACT.md`.

## Important Files

- `app/main.py` - FastAPI app, endpoints, controlled errors, safe fallback.
- `app/schemas.py` - strict response enums and response model; lenient request parsing.
- `app/classify.py` - priority-ordered EN/Bangla/Banglish classification.
- `app/evidence.py` - transaction matching and evidence verdicts.
- `app/rules.py` - severity, department, confidence, reason codes, escalation.
- `app/replies.py` - safe templated agent/customer text.
- `app/safety.py` - final sanitizers and safety flags.
- `app/llm.py` - optional fallback-only LLM hinting, disabled by default.
- `tests/test_matrix.py` - hidden-test-style matrix. Keep it green.
- `CONTRACT.md` - source of truth for schema/enums/safety.

## Run Commands

```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Test Commands

```bash
pytest -q
```

If Windows PowerShell does not have the venv on PATH, activate it first:

```powershell
.\.venv\Scripts\activate
pytest -q
```

## Docker Commands

```bash
docker build -t queuestorm .
docker run --rm -p 8000:8000 --env-file .env.example queuestorm
curl http://localhost:8000/health
```

Compose is also supported:

```bash
docker compose up --build
docker compose exec -T queuestorm pytest -q
docker compose down
```

## Public Deployment Commands

Vercel is the intended public endpoint path. The root `index.py` exports the FastAPI `app`, so `/health` and `/analyze-ticket` must resolve at the base URL.

```bash
vercel
vercel --prod
curl https://YOUR_PUBLIC_URL/health
```

## API Contract Rules

- Do not rename fields or enum values.
- Response enums must stay character-exact.
- Valid requests must not return 5xx.
- Missing required fields and malformed JSON must return controlled JSON errors.
- Extra request fields should not break the service.
- Bad transaction entries should be ignored, not crash the service.

## Safety Rules

- Never ask for OTP, PIN, password, CVV, full card number, login code, or verification code.
- Never promise guaranteed refund, reversal, recovery, unblock, or approval.
- Never direct customers to suspicious third parties or unknown links.
- Never copy unsafe complaint text into `customer_reply`.
- Phishing and credential-sharing cases must route to `fraud_risk`, critical severity, and human review.

## Environment Variable Rules

- The app must run even if env values are missing.
- The committed `.env.example` (names only — no secrets) is the Docker env file, so judging needs no API key.
- `.env.local` is gitignored and never committed; copy `.env.example` to it only to test the optional LLM.
- `USE_LLM=false` or missing means deterministic rules-only mode.
- Real LLM keys belong only in local/Vercel environment settings.

## LLM Usage Rules

- LLM is optional and fallback-only for low-confidence `other` cases.
- LLM output may only suggest a `case_type` and must validate against enums.
- LLM must never write final JSON, customer reply, severity, department, or escalation.
- Any LLM timeout/error must fall back to the rules result.

## Hidden-Test Strategy

Preserve broad coverage for empty/malformed input, no history, bad history entries, wrong-transfer ambiguity, contradictory evidence, duplicate payment, merchant settlement, agent cash-in, phishing, shared OTP/PIN, prompt injection, Bangla, Romanized Bangla, mixed language, long complaints, high values, and irrelevant complaints.

## Judge / Docker / Deployment Instructions

The judge should be able to run:

```bash
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or:

```bash
docker build -t queuestorm .
docker run --rm -p 8000:8000 --env-file .env.example queuestorm
curl http://localhost:8000/health
```

The expected health response is:

```json
{"status":"ok"}
```

The app must not require real API keys, a database, GPU, local model downloads, or external services to pass tests and serve the core API.

## Do-Not-Break List

- No frontend, database, payment integration, auth dashboard, GPU dependency, or large model download.
- Do not hardcode official sample answers.
- Do not commit `.env`, `Api.txt`, logs, caches, or unrelated secrets.
- Do not loosen response models or remove safety sanitizers.
- Do not make the LLM required.

## Final Submission Checklist

- `pytest -q` passes.
- `/health` returns exactly `{"status":"ok"}` locally, in Docker, and on the public URL.
- `POST /analyze-ticket` returns schema-valid JSON for an official sample.
- Docker build/run works with no secrets.
- Public endpoint is reachable at root paths, not `/api/*`.
- README includes local, Docker, and public endpoint test commands.
- `git status` shows no generated caches or local secret files to commit.
