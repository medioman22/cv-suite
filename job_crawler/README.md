# Job Crawler

A small, dependency-free job aggregator. It pulls from several job sources,
**scores each posting** against your keywords/locations, drops anything already
tracked in `../tracking/JOBS.md`, and writes a ranked `suggestions.md`. It also
drips the top new links into `../tracking/INBOX.md` so the workflow ("collect
links → tell Claude *inbox* → get tailored CVs") stays fed automatically.

```
job_crawler/
├── config.py      # all the knobs (keywords, locations, sources, output)
├── sources.py     # one function per job source
├── bigtech.py     # direct big-tech career-site APIs
├── crawler.py     # fetch → score → dedupe → write
├── suggestions.md # ranked output (created on first run)
└── seen.json      # dedupe memory (created on first run)
```

## Requirements
Just **Python 3.9+**. No pip install, no third-party packages.

## Run
```bash
cd job_crawler
python3 crawler.py --dry-run     # preview, writes nothing
python3 crawler.py               # write suggestions.md + feed INBOX.md
python3 crawler.py --no-inbox    # write suggestions.md only
python3 crawler.py --min-score 8 # stricter/looser threshold
```

## Sources

| Source | Key needed? | Notes |
|--------|:-----------:|-------|
| **Arbeitnow / Remotive / RemoteOK** | no | EU + remote job-board APIs |
| **Greenhouse / Lever / Ashby** | no | per-company boards — precise, reliable. Add company slugs in `config.py` |
| **jobs.ch** | no | largest Swiss board; official public JSON search API (Switzerland-wide) |
| **Adzuna** | **yes (free)** | good Switzerland coverage. Key at <https://developer.adzuna.com/>, then set `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` (in `.env` or env) |
| **Big-tech** (`bigtech.py`) | no | direct career APIs — Amazon, NVIDIA (Workday), Netflix (Eightfold), Snap |
| **LinkedIn (guest)** | no | ⚠️ **unofficial & against LinkedIn ToS** — off by default; use the email pipeline instead |

### Adding company ATS boards (highest signal/noise)
Target the companies you want. Find the board token by opening:
- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<token>/jobs`
- Lever: `https://api.lever.co/v0/postings/<token>?mode=json`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/<token>`

If the URL returns JSON, put `<token>` in the matching list in `config.py`.

## Tuning
`config.py` is the whole control panel. **Retune it to your field:**
`CORE_TITLE_TERMS` (hard title gate), `KEYWORDS` (weighted signals),
`NEGATIVE_KEYWORDS` (downranks), the location lists, and `MIN_SCORE`.
`crawler.py::score()` adds keyword weights (title matches count double),
subtracts negatives, and applies a location bonus/penalty.

## The LinkedIn ToS-safe path
Don't scrape LinkedIn. Use **your own alert emails** via
`linkedin_pipeline/` (see its README) plus the one-click `bookmarklet.md`.
The crawler's `linkedin_guest` source hits LinkedIn's unauthenticated endpoint,
**violates their User Agreement**, and is rate-limited — it's off by default.

## Run it periodically (optional)
**cron** (`crontab -e`) — daily at 08:00:
```
0 8 * * *  cd /path/to/cv-suite/job_crawler && /usr/bin/python3 crawler.py >> /tmp/jobcrawler.log 2>&1
```
> **macOS note:** if the repo lives under `~/Documents`, cron/launchd needs
> **System Settings → Privacy & Security → Full Disk Access → add `/bin/bash`**,
> or just run `bash job_crawler/run.sh` yourself from Terminal (no grant needed).

## The loop
1. Crawler runs → refreshes `suggestions.md`, adds top new links to `../tracking/INBOX.md`.
2. You skim `INBOX.md`, delete anything you don't want.
3. Tell Claude **"inbox"** → it fetches, assesses fit, builds tailored CVs, files them.

_Personal-use tool. Respect each site's terms; keep request volumes modest._
