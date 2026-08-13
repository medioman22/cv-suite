# LinkedIn Email → Shortlist Pipeline

Turns your LinkedIn job-alert emails into a small, ranked, **recent** shortlist of
roles worth a tailored CV — cheaply. The heavy, high-volume work is deterministic
Python or a **cheap model** (Haiku); only the final fit-check uses the **powerful
model** (this Claude session). That keeps the expensive allowance for judgement.

## Why it exists
LinkedIn digests contain hundreds of postings. Reading each on the expensive model
would burn the budget. This pipeline filters first (title relevance → location →
posted recently → still open → coarse relevance) so the powerful model only ever
sees ~a dozen real candidates.

## Prerequisites
- LinkedIn job alerts arriving in Gmail (set up saved searches with email alerts).
- A **Gmail App Password** (not your normal password): Google Account → Security →
  2-Step Verification → App passwords. Pass it via env only — never commit it.

## Stages

| # | Stage | Runs on | Script | In → Out |
|---|-------|---------|--------|----------|
| 1 | **Ingest** | deterministic | `ingest.py` | IMAP emails → `raw.json`. **Incremental** — caches processed UIDs in `email_cache.json`, so each run only downloads *new* alert emails (`--full` forces a refetch) |
| 2 | **Score & dedupe** | deterministic | `score.py` | `raw.json` → `candidates.json` (title-gate + score; drops interns, already-tracked, already-seen) |
| 2b | **Surface to inbox** | deterministic | `inbox_append.py` | `candidates.json` → appended into `../../tracking/INBOX.md`'s LinkedIn section (capped, deduped, most-recent-alert first) — so pipeline hits show up next to crawler/bookmarklet hits without extra steps |
| 3 | **Date filter** | deterministic | `datefilter.py` | fetch each posting → keep last-N-months & open → `recent.json` |
| 3b | **Coarse skim** | cheap model | subagent | `recent.json` → STRONG / MAYBE / WEAK tag |
| 4 | **Fit-check + CVs** | powerful model | this session | STRONG/MAYBE → tailored CVs, filed into `../../tracking/JOBS.md` |

## Run stages 1–3 (one command)
```bash
EMAIL_USER=you@gmail.com EMAIL_PASS='xxxx xxxx xxxx xxxx' bash run.sh
```
Knobs (env): `MIN_SCORE` (default 14), `MONTHS` (default 3), `DELAY` (default 6s/request).
`datefilter.py` saves progress each request and **resumes** if interrupted — just re-run.
Every fetched id is recorded in `pipeline_seen.json` so later runs only look at new postings.

## Stage 3b — cheap-model skim
From the Claude session, spawn a **Haiku** subagent:
> Read `recent.json`. For each posting, tag relevance STRONG / MAYBE / WEAK for
> **<the candidate — see tracking/Profile.md>**. STRONG = their core domains; WEAK =
> their confirmed-negative areas. Write `recent_tagged.md` sorted STRONG-first and
> report the STRONG/MAYBE list.

## Stage 4 — fit-check (powerful model)
The session reviews the STRONG/MAYBE survivors, confirms honest fit against
`../../tracking/Profile.md`, builds tailored CVs + cover letters for strong matches,
and files everything into `../../tracking/JOBS.md` and `../../tracking/CHANGELOG.md`.

## Files
- `ingest.py`, `score.py`, `inbox_append.py`, `datefilter.py`, `run.sh` — the pipeline.
- `raw.json` → `candidates.json` → `recent.json` — intermediates (regenerated each run).
- `pipeline_seen.json` — ids already screened (delete to re-screen everything).
