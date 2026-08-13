# CAPABILITIES — everything this starter kit can do

A catalogue of every capability in the repo: how to invoke it, what it reads,
what it writes. `AI_README.md` is the workflow brief (hand it to your AI
assistant); this file is the reference for every script/page individually.

---

## 1. Daily automated routine — `pipeline/daily_run.sh`

Orchestrates the full mail → scrape → triage → report loop in one command,
with a per-step timeout so a single hung step can't stall the run.

```bash
bash pipeline/daily_run.sh
```

Steps, in order (each wrapped in a timeout; failures/timeouts are logged and
skipped, never fatal to the rest of the run):

| Step | Script | Does |
|---|---|---|
| 1 | `job_crawler/mail_scan.py --days 2` | recruiter/comms email triage (see §2) |
| 2 | `job_crawler/crawler.py --no-inbox` | scrape ATS/aggregators/big-tech (writes `suggestions.md`, not `INBOX.md` directly) |
| 3 | `pipeline/backlog_update.py` | harvest crawler suggestions + LinkedIn alert emails into `tracking/backlog.jsonl` |
| 4 | `pipeline/enrich.py` | fetch real title/description for LinkedIn-alert rows that only have digest text |
| 5 | `pipeline/triage.py` | cheap-LLM tier + reason for every untriaged backlog row; writes `tracking/DAILY_REPORT.md` |
| 6 | `pipeline/superstar_cap.py` | deterministic cap on the top triage tier (see §12) |
| 7 | `pipeline/salary.py` | salary cache + backfill (see §11) |
| 8 | `pipeline/refresh_status.py --cap 90` | check if tracked postings are still open (see §11) |
| 9 | `pipeline/sync_folders.py` | create `applications/` folders for anything triaged that doesn't have one yet |

Nothing here ever commits or applies to anything — review `tracking/DAILY_REPORT.md`
(and whatever else changed) yourself. Logs to `tracking/pipeline.log`.

**Schedule it (macOS launchd):** `pipeline/com.candidate.cvdaily.plist` — edit the
placeholder paths inside first (see the comment at the top of the file), then:
```bash
cp pipeline/com.candidate.cvdaily.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.candidate.cvdaily.plist
```
Runs daily at 07:00 (catches up on wake if the Mac was asleep). Logs to
`tracking/pipeline.launchd.log`.

---

## 2. Mail check / inbox screening

Two independent things read your inbox — keep them straight:

- **`job_crawler/mail_scan.py [--days N] [--bodies]`** — the general recruiter/
  comms triage: "what needs a human reply." Scans INBOX + Sent Mail, drops
  known newsletter/digest noise, flags subjects that look like real recruiting
  threads. Retune `NOISE`/`HARD_NOISE` in the script to your own inbox.
- **`job_crawler/linkedin_pipeline/`** (`ingest.py` → `score.py` → `inbox_append.py`
  → `datefilter.py`, or `bash job_crawler/linkedin_pipeline/run.sh`) — turns
  LinkedIn job-*alert* emails specifically into a scored, deduped shortlist
  that lands in `tracking/INBOX.md`. See `job_crawler/linkedin_pipeline/README.md`
  for the full stage breakdown.

Both read `EMAIL_USER`/`EMAIL_PASS` (Gmail App Password) from env or
`job_crawler/.env`.

---

## 3. Job scraper

```bash
cd job_crawler && python3 crawler.py            # scrape + append top hits to INBOX.md
python3 crawler.py --no-inbox                   # scrape, write suggestions.md only
python3 crawler.py --dry-run                    # score without touching seen.json
```
Pulls from ATS boards (Greenhouse/Ashby/Lever/Workday), Adzuna, jobs.ch, and
big-tech career APIs (`bigtech.py`); scores every hit against `config.py`'s
keyword/location knobs. See `job_crawler/README.md`.

---

## 4. The "inbox" command

Unchanged — see `AI_README.md`'s "The inbox command" section. Cross-checked
against everything added here: it still fully describes the loop; the new
pipeline scripts just mean more candidates land in `INBOX.md`/`JOBS.md`
automatically before you ever say "inbox."

---

## 5. Tidy-up / dedupe pass — `tracking/tidy.py`

```bash
python3 tracking/tidy.py            # sort JOBS.md/INBOX.md in place + export jobs.csv
python3 tracking/tidy.py --check    # validate only, non-zero exit on problems
```
Non-destructively reorders `JOBS.md`'s table by `#` (stable — numbers are
never reassigned), flags structural issues (wrong column count, duplicate
`#`s), and sorts each loose run of pasted LinkedIn URLs in `INBOX.md`. Run it
occasionally once the tracker has grown past the point of eyeballing it.

---

## 6. Saving job URLs from the browser — two paths

- **`job_crawler/bookmarklet.md`** — a bookmarklet that grabs every job link
  **visible on the LinkedIn page you're looking at** and copies it to your
  clipboard, to paste into `INBOX.md` yourself. Runs in your logged-in
  session; no scraping, no automation of your account.
- **`save_open_urls.py`** (double-click **`save_urls.command`**) — reads
  **every open Chrome tab across all windows** (any site, not just LinkedIn)
  and writes straight into `tracking/INBOX.md`, deduped, with a summary
  dialog. Handy after a browsing session where you opened a batch of
  postings in tabs to look at later.

Both write to the same `## ✍️ Manual / pasted` section of `INBOX.md` and
dedupe against each other and the rest of the tracker — use whichever fits
the moment.

```bash
python3 save_open_urls.py              # or just double-click save_urls.command
python3 save_open_urls.py --no-dialog  # terminal use
```

---

## 7. CV personalization / tailoring workflow

Unchanged in the default path — see `AI_README.md`. **Optional addition:**
`master/content/` — a shared content-library pattern (`\defitem`/`\I`/`\IL`
LaTeX macros) for when you've got enough tailored CVs that hand-syncing
wording fixes across them gets old. Not wired into `master/cv.tex` by
default; read `master/content/README.md` before adopting it. Review the
whole library at a glance:
```bash
bash build_review.sh    # -> master/content/review.pdf
```

---

## 8. Cover letter building — `build_letter.py`

```bash
python3 build_letter.py applications/1_strong/260714_CH_Acme_ML_Engineer
python3 build_letter.py all
```
Reads a folder's `message_to_hiring_team.md`, converts it to LaTeX, renders it
through `master/letter.tex` (matches the CV letterhead — edit the placeholder
name/contact line in that file to match your own), and writes
`<Your Name> - Cover Letter.pdf` (name from `candidate.env`) into the folder.
Requires xelatex.

---

## 9. Dashboard + Applications + Next Steps + Conversations UI

```bash
./run.sh                                  # build everything + serve + open browser
python3 ui/build_dashboard.py             # -> ui/dashboard.html  (from JOBS.md + INBOX.md)
python3 ui/build_applications.py          # -> ui/applications.html  (from APPLICATIONS.md + JOBS.md)
python3 ui/build_nextsteps.py             # -> ui/nextsteps.html  (from NEXT_STEPS.md)
python3 ui/build_conversations.py         # -> ui/conversations.html  (from CONVERSATIONS.md)
```
`ui/serve.py` serves all four live at `/`, `/applications.html`,
`/nextsteps.html`, `/conversations.html` (rebuilding each from its source
`.md` on every request when running live, so edits show up on refresh), plus
a small POST API so the pages themselves can write back:

| Page | Shows | Live-edit API |
|---|---|---|
| **Board** (`/`) | every `JOBS.md` row: fit, status, notes, search/filter; run the crawler/mail/build tasks with streaming output | task buttons only (no per-row edit in the starter build) |
| **Applications** (`/applications.html`) | the real pipeline — one card per stage (applied/interviewing/offer/rejected/withdrawn), contacts, ready-to-send drafts | `POST /api/app-status` (change stage — moves the folder to `applications/0_applied/` on "applied"), `POST /api/draft-sent` (delete a sent draft) |
| **Next Steps** (`/nextsteps.html`) | action items grouped by section, drag-to-reorder, a recent-meetings log | `POST /api/nextstep-done` (toggle), `POST /api/nextstep-reorder` (persist drag order to `tracking/nextsteps_order.json`) |
| **Conversations** (`/conversations.html`) | LinkedIn-style threads with a suggested reply that pops up on hover, copy-to-clipboard | read-only (no write endpoint — replies are pasted by hand into the actual thread) |

All three new tracking docs (`APPLICATIONS.md`, `NEXT_STEPS.md`,
`CONVERSATIONS.md`) ship with one deletable example row each so the pages
render something on first run — delete the example rows once you have real
data.

---

## 10. Triage / enrich / promote / superstar-cap pipeline (detail)

The backlog (`tracking/backlog.jsonl`) is the staging area between "found a
posting" and "worth a curated `JOBS.md` row." Pipeline order:

1. **`pipeline/backlog_update.py`** — harvest new rows (crawler suggestions +
   LinkedIn alert-email cards) into `backlog.jsonl`, deduped against `JOBS.md`
   and the backlog itself.
2. **`pipeline/enrich.py`** — LinkedIn-alert rows only have digest text (badge/
   location, often no real title); fetch the actual posting so triage scores
   real content, not brand-name guessing.
3. **`pipeline/triage.py`** — cheap-LLM (Gemini Flash by default) tier + one-
   line reason per row: 🌟 (rare top tier) / ★★★ / ★★ / ★ / skip, plus a
   seniority + domain/seniority subscore pair. Writes `tracking/DAILY_REPORT.md`.
   **Read `pipeline/triage.py`'s `PROMPT`/`build_prompt()` once and tune the
   rubric to your own field** — it pulls your name + a summary from
   `tracking/Profile.md` automatically but the tiering rules themselves are a
   generic starting point.
4. **`pipeline/superstar_cap.py`** — the LLM's top-tier bar drifts across
   batches; this re-imposes a deterministic rule (bullseye domain + Staff+
   seniority + a frontier/marquee employer) and a hard cap, demoting the rest
   to ★★★. Only ever demotes, never promotes.
5. **`pipeline/salary.py`** — see §11.
6. **`pipeline/promote.py`** — separately from `daily_run.sh` (call it
   yourself when you want to curate): promotes the top-tier backlog rows into
   `tracking/JOBS.md` + `tracking/job_details.json`, deduped by LinkedIn id and
   by normalized (company, title) so repeat harvests of the same posting collapse.
   ```bash
   python3 pipeline/promote.py [--tiers 🌟,★★★,★★] [--dry]
   ```
7. **`pipeline/sync_folders.py`** — every promoted, non-skip/closed `JOBS.md`
   row gets an `applications/<bucket>/` folder (posting.md + notes.md;
   `cv.tex` too if your `ui/build_dashboard.py` has template-matching logic
   that supplies one — the starter kit doesn't ship one by default, so this
   step degrades gracefully to notes-only).

---

## 11. Salary estimation & posting-status refresh

- **`pipeline/salary.py [--no-fetch]`** — harvests posted pay ranges from
  registered Ashby companies (`config.ASHBY_COMPANIES`) and mines ranges out
  of backlog descriptions (pay-transparency-law postings), caches per company
  in `tracking/salary_cache.json`, and backfills/estimates for rows with no
  posted figure. The region factors / seniority priors / equity-heavy company
  list at the top of the file are illustrative — retune to your own market.
- **`pipeline/refresh_status.py [--cap N] [--cooldown-days N]`** — fetches
  each active row's posting URL and asks a cheap LLM whether it still reads as
  open. `inbox`/`cv-ready` rows get silently flipped to `closed`; anything
  further along (applied/interviewing) only ever gets a note appended, never
  a silent overwrite. State lives in `tracking/job_refresh_state.json` so a
  periodic run only re-checks what's due.

Both read `GEMINI_API_KEY` from `job_crawler/.env`.

---

## Env / secrets summary

Everything above reads from `job_crawler/.env` (copy from `.env.example`):
`EMAIL_USER` / `EMAIL_PASS` (Gmail App Password, for mail_scan.py +
linkedin_pipeline), `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` (crawler), and
`GEMINI_API_KEY` / `GEMINI_MODEL` (triage.py, refresh_status.py). All
git-ignored; never commit real credentials.
