# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FastAPI web portal that wraps the ikus.pesc.ru JSON REST API for submitting monthly meter readings. Includes an async Python client library, a web UI with Jinja2 templates, APScheduler for automated daily submission, and SQLite for persistence.

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the server (system Python 3.10, not the linuxbrew python3)
uvicorn portal.main:app --reload --port 8003
python3.10 -m uvicorn portal.main:app --reload --port 8003

# Run tests
python3.10 -m pytest tests/ -v
/home/hram/projects/running-portal/.venv/bin/python3 -m pytest tests/ -v

# Run a single test
python3.10 -m pytest tests/test_totp.py -v

# Trigger scheduler manually (bypasses submission window gate)
curl -X POST "http://localhost:8003/api/accounts/trigger?force=true"
```

## Configuration

Copy `.env.example` to `.env` and fill in:
- `PESC_LOGIN`, `PESC_PASSWORD` — required
- `PESC_AUTH_VERIFICATION` — required (value from browser DevTools → Network → `/api/v8/users/auth` → Request Headers)
- `PESC_TOTP_SECRET` — only if 2FA is enabled on the account
- `PESC_PROXY_URL` — only if running outside Russia
- `SCHEDULER_HOUR`, `SCHEDULER_MINUTE` — auto-submit time in Moscow TZ (default 12:00)
- `DATA_DIR` — SQLite location (default `./data`)

## Architecture

**`src/pesc/`** — standalone async client library for ikus.pesc.ru. No FastAPI dependency. `PescClient` is an async context manager with low-level methods (`fetch_session_cookie`, `login`, `fetch_meters`, `submit_reading`, etc.) and a high-level `run_for_account(cookie, bearer, account_id)` that fetches + submits + verifies in one call.

**Auth flow**: `GET /existence` → cookie → `POST /v8/users/auth` → bearer token. Both cookie and bearer are required on every subsequent request. The `Auth-Verification` header is also required on the auth request (portal-specific, stored in env).

**`portal/`** — FastAPI app. Routers: `meters` (API endpoints), `account_settings` (per-account settings + manual trigger), `pages` (HTML pages). `db.py` is synchronous sqlite3 — fast enough for a single-user local portal.

**`portal/schedule.py`** — submission window gate: 15–21 of each month, weekdays only (Moscow time). Mirrors `ru-meters-bot/src/schedule.ts` exactly. `should_submit(date)` returns `(bool, reason)`.

**`portal/scheduler.py`** — APScheduler `AsyncIOScheduler` started in FastAPI lifespan. Runs `run_auto_submit()` daily at configured time. Checks the window gate first, then submits for all accounts with `auto_submit=true` in DB. Results written to `scheduler_log` table.

**`portal/db.py`** — two tables: `account_settings` (per-account `auto_submit` flag), `scheduler_log` (run history shown at `/log`). `upsert_account()` is called on every page load to register accounts seen from pesc.ru.

**`portal/routers/pages.py`** — renders Jinja2 templates. Applies `_NAME_MAP` to expand abbreviations (ГВС → Горячее водоснабжение, ХВС → Холодное водоснабжение). Registers a `datetimeformat` filter on the Jinja2 env.

## Python environment note

The system has two Python installations. `python3` resolves to linuxbrew Python 3.14 (no packages). All project packages (`fastapi`, `uvicorn`, `httpx`, etc.) are installed under `python3.10` (`/usr/bin/python3.10`). Always use `python3.10` explicitly or `uvicorn` from `~/.local/bin`.
