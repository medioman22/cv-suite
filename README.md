# CV Suite — a tailored job-search toolkit

A small, self-contained system for running a serious job search with an AI copilot:
one **master CV**, a tailored CV + cover letter per role, a **job tracker**, a
**crawler** that finds new roles, a **LinkedIn email pipeline**, and a local
**dashboard** to drive it all. No frameworks, no accounts required to start —
just Python and LaTeX.

The idea: you collect job links, say **"inbox"** to your AI (Claude), and it fetches
each posting, honestly assesses fit against your profile, and builds a tailored,
no-fabrication CV for the strong matches — filing everything into the tracker.

That loop works on its own with zero setup beyond `tracking/Profile.md`. There's
also an optional daily-automation layer (`pipeline/`) and a few extra UI pages
(Applications / Next Steps / Conversations) for once you're running a bigger,
faster-moving search — see **[`CAPABILITIES.md`](CAPABILITIES.md)** for the
full list of what's here and how to turn each piece on.

---

## What's in the box

```
master/cv.tex           Your master CV — the superset. Tailor by CUTTING from it.
master/letter.tex       Cover-letter template (used by build_letter.py)
master/content/         OPTIONAL shared bullet-library pattern — see its README
assets/pic.png          Header photo (referenced by the CV via \graphicspath)
applications/           One folder per role, grouped by fit (1_strong … 4_skip)
tracking/               Profile.md (your knowledge base), JOBS.md (tracker),
                        INBOX.md (paste links), APPLICATIONS.md, NEXT_STEPS.md,
                        CONVERSATIONS.md, CHANGELOG.md, TODO.md, tidy.py
pipeline/               Daily automation: backlog harvest → enrich → triage →
                        salary → status-refresh → applications/ sync. Optional
                        — the "inbox" workflow alone doesn't need it.
job_crawler/            ATS + Adzuna + jobs.ch crawler, mail_scan.py (comms
                        triage), and the LinkedIn email pipeline
ui/                     Local dashboard (serve.py) — buttons to run everything,
                        plus Applications / Next Steps / Conversations pages
build_cv.sh             Compile one CV, or all of them, to "<Your Name> - CV.pdf"
build_letter.py         Compile a cover-letter PDF from message_to_hiring_team.md
build_review.sh         OPTIONAL: proofread master/content/items.tex as one PDF
save_open_urls.py       Save every open Chrome tab into tracking/INBOX.md
                        (double-click save_urls.command)
run.sh                  One-word launch: builds the board + starts the dashboard
AI_README.md            ← hand this to your AI so it knows the workflow
CAPABILITIES.md         Full capability reference — every script/page, in/out
```

## Prerequisites
- **Python 3.9+** (standard library only — nothing to pip install)
- **XeLaTeX** (TeX Live or MacTeX) and the system font used in `cv.tex`
  (default is *Avenir Next*; swap it in `cv.tex` if you don't have it)
- An AI coding assistant (this was built with **Claude Code**)

## First-time setup (about 15 minutes)
1. **Put your name on the deliverable:** edit `candidate.env` →
   `CANDIDATE_NAME="Your Name"`.
2. **Make it your CV:** replace `master/cv.tex` with your own content (keep the
   layout), and drop your photo in `assets/pic.png` (or remove the photo line).
3. **Fill in `tracking/Profile.md`.** This is the most important step — it's the
   single source of truth your AI reasons from. Be complete *and honest*, and fill
   in the **Confirmed Negatives** section especially (it's what stops the AI from
   overclaiming). See `AI_README.md` for how it's used.
4. **Build to check it compiles:**
   ```bash
   bash build_cv.sh all      # → "Your Name - CV.pdf" in master/
   ```
5. *(Optional, for the crawler/mail features)* copy `job_crawler/.env.example` to
   `job_crawler/.env` and add an [Adzuna key](https://developer.adzuna.com/) and/or
   a Gmail App Password. Retune `job_crawler/config.py` keywords to your field.

## The daily loop
1. **Find roles** — run the crawler and/or the LinkedIn mail pipeline (or just paste
   links yourself). New links land in `tracking/INBOX.md`.
2. **Triage** — tell your AI **"inbox"**. It fetches each posting, assesses fit,
   builds a tailored CV + cover letter for **strong** matches (notes + posting only
   for weaker ones), and files each into `tracking/JOBS.md`.
3. **Review & apply** — open the dashboard, read the assessments, send the ones you like.

## The dashboard
```bash
./run.sh                 # builds the board, starts a local server, opens the browser
```
It runs on `localhost:8765` and gives you clickable buttons — **Scrape**, **Mail run**,
**Build CVs**, **Refresh** — that execute on your machine and stream output live, plus
a searchable board of every tracked role and an inbox triage view. Everything stays
local; the server binds to localhost only and runs a fixed allow-list of commands.

## Finding new roles (details)
- **Crawler:** `cd job_crawler && python3 crawler.py` — pulls from ATS boards,
  Adzuna, jobs.ch, and big-tech career APIs; scores by match; feeds the inbox.
  See [`job_crawler/README.md`](job_crawler/README.md).
- **LinkedIn pipeline:** turns *your own* job-alert emails into a shortlist — the
  ToS-safe way in. See [`job_crawler/linkedin_pipeline/README.md`](job_crawler/linkedin_pipeline/README.md).

## Secrets
`job_crawler/.env` and all mail credentials are git-ignored. Pass
`EMAIL_USER` / `EMAIL_PASS` (a Gmail **App Password**, never your real password)
via the environment. Keep this repo **private** if you commit real applications.

---

*Built with Claude Code. `AI_README.md` briefs the AI on the conventions — point your
assistant at it at the start of a session.*
