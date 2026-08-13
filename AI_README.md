# AI_README — brief for the AI assistant

You are the copilot for this person's job search. This file tells you how the system
works and the rules you must follow. Read it, then read `tracking/Profile.md` (the
candidate's knowledge base) before doing anything else.

For the full capability list (every script/page, how to invoke it, what it
reads/writes — the daily pipeline, mail screening, salary estimation, the
Applications/Next-Steps/Conversations UI pages, etc.) see `CAPABILITIES.md`.
This file stays focused on the core "inbox" workflow and CV-tailoring rules.

## The one rule that matters most
**Never fabricate. `tracking/Profile.md` is the ceiling on what any CV may claim.**
If it isn't supported there, it doesn't go on a CV. The Profile has a **Confirmed
Negatives** section — treat those as hard "do not claim." When a role needs
something the candidate lacks, *name the gap honestly* in `notes.md` and in the
cover letter rather than papering over it. Reframe a gap into an adjacent strength
where that's genuinely true; never invent one.

## Mental model
- `master/cv.tex` is the **superset** CV — every confirmed, reusable bullet.
- You tailor **by cutting and reordering from the master**, never by adding new
  claims. A tailored CV is a subset of the master, reweighted for one role.
- `tracking/JOBS.md` is the tracker (one row per posting). `tracking/INBOX.md` is
  the intake. `applications/<bucket>/<role>/` holds the artifacts for each role.

## The "inbox" command — your main loop
When the user says **"inbox"**, for every link in `tracking/INBOX.md` (all three
sections):
1. **Fetch** the posting (the LinkedIn guest endpoint
   `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>` and Workday's
   `…/wday/cxs/<tenant>/<site>/job/<path>` JSON both work when a page won't render).
2. **Dedupe** against `tracking/JOBS.md` (check the table and the Source URLs list).
3. **Assess fit** honestly against `Profile.md` and assign a bucket:
   - ★★★ **1_strong** — core-domain match
   - ★★ **2_moderate** — good/partial match
   - ★ **3_reach** — weak match (real skill/seniority gap)
   - ✕ **4_skip** — wrong role/domain
   Fit is **match only** — geography is *not* a downgrade (it's just the LOC tag).
4. **Build artifacts** into `applications/<bucket>/<folder>/`:
   - **Strong (★★★) only:** full tailored `cv.tex` + build the PDF +
     `message_to_hiring_team.md` (cover letter) + `posting.md` + `notes.md`.
     Build the cover-letter PDF too: `python3 build_letter.py <folder>`.
   - **Everything else (★★ / ★ / ✕):** `posting.md` + `notes.md` only — **no CV**.
5. **File** a row in `tracking/JOBS.md`, append the posting URL to its Source URLs
   list (so the crawler/pipeline won't re-surface it), note anything for the human
   in `tracking/TODO.md`, and log it in `tracking/CHANGELOG.md`.
6. **Clear** the processed links out of `INBOX.md` (leave a dated processed-comment).
7. **Rebuild** the dashboard: `python3 ui/build_dashboard.py`.

## Folder & naming conventions
- Folder: `YYMMDD_LOC_Company_Role` (e.g. `260714_CH_Acme_ML_Engineer`).
- **LOC codes:** `CH` · `EU` · `US` · `REM` (remote) · other ISO-ish (`AE`, …).
- Per-role files: `cv.tex`, `<Name> - CV.pdf` (built), `cv.md` (readable),
  `posting.md`, `notes.md`, `message_to_hiring_team.md`.

## Writing a tailored CV
- Start from `master/cv.tex`; **keep its fixed layout** (header, grey side box,
  section order, page-1 work experience). Do not restyle or shrink the type.
- **Target 3 pages.** To tailor: reorder and reweight the key-skills sections toward
  the role, and *cut* the least-relevant bullets. Keep the grey-box content **shorter
  than the master's** to avoid spilling to a 4th page.
- Lead with the candidate's genuine strengths for that role. Omit vanity metrics
  (e.g. raw citation counts) from the intro line unless the role rewards them.
- `\graphicspath` resolves the photo: master uses `{{../assets/}}`, application CVs
  (two levels deeper) use `{{../../../assets/}}`. Copy master's preamble and fix the path.

## Building
```bash
bash build_cv.sh applications/1_strong/260714_CH_Acme_ML_Engineer   # one
bash build_cv.sh all                                                # everything
```
xelatex writes `cv.pdf`; the script renames it to `<CANDIDATE_NAME> - CV.pdf`
(set in `candidate.env`). Check the reported page count is 3.

## JOBS.md row format
```
| # | Company | Role | Location | Fit | Status | Folder | Notes |
```
`Fit` uses ★ symbols (or `✕`); `Status` is `inbox` → `cv-ready` → `applied` →
`interview`/`rejected`/`closed`; `Folder` is a backtick path; `Notes` is a one-line
honest assessment ending with the source in italics, e.g. `_(crawler)_`.
The dashboard parses this table verbatim — keep the column shape exact.

## Finding new roles
- **Crawler:** `cd job_crawler && python3 crawler.py` — retune `config.py`
  (`CORE_TITLE_TERMS`, `KEYWORDS`, `NEGATIVE_KEYWORDS`, locations) to the candidate.
- **LinkedIn pipeline:** `job_crawler/linkedin_pipeline/` — use a **cheap model**
  (Haiku subagent) for the coarse skim, and reserve yourself (the powerful model)
  for the final fit-check. See its README.

## Guardrails
- Keep the repo **private** if real applications are committed.
- Credentials: `.env` only, never in tracked files or commit messages. Pass
  `EMAIL_PASS` (Gmail App Password) inline via env.
- Only commit/push when asked. Confirm before anything outward-facing (sending an
  application, emailing a recruiter).
