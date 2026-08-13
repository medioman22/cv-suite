#!/usr/bin/env python3
"""Check whether tracked postings are still open, and log it when they're not.

Fetches each row's posting URL, asks a cheap LLM whether the page reads as a
live/open listing or closed/filled/removed, and writes the finding back to
tracking/JOBS.md:
  - inbox / cv-ready rows (nothing sent yet) get auto-flipped to status=closed —
    low stakes, no real process to protect.
  - applied / interviewing / offer rows are NEVER silently overwritten — a note
    is appended instead ("Posting appears closed (auto-check DATE): ...") so
    you see it without losing the real state of an active conversation.
Shared by the dashboard's per-job "Check if still open" button (ui/serve.py)
and this script, which the daily pipeline runs on a capped, cooldown-gated
sample so a periodic run never re-checks everything or hammers Gemini/ATS sites.

  python3 pipeline/refresh_status.py [--cap 30] [--cooldown-days 7]

Reads GEMINI_API_KEY from job_crawler/.env. Stdlib only (urllib).
"""
import os, re, sys, json, time, urllib.request, urllib.error, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JOBS = os.path.join(ROOT, "tracking", "JOBS.md")
STATE = os.path.join(ROOT, "tracking", "job_refresh_state.json")   # num -> {date, state}
ENV = os.path.join(ROOT, "job_crawler", ".env")

CAP = 90                 # postings checked per run — tune to your JOBS.md size / cooldown window
COOLDOWN_DAYS = 7        # don't re-check a row sooner than this
ACTIVE_STATUSES = {"inbox", "cv-ready", "applied", "interviewing"}   # skip closed/rejected/offer
MODEL = "gemini-2.5-flash"


def load_env():
    try:
        for ln in open(ENV, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def fetch_text(url):
    """-> (text, err). text is stripped/truncated page text; err set on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; job-tracker/1.0)"})
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read(400000).decode("utf-8", "ignore")
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()[:6000]
        return (text, "" if text else "empty response")
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except Exception as e:
        return "", str(e)[:200]


def gemini_check(key, text, err, model=MODEL):
    """-> (state, reason). state in open|closed|unknown."""
    prompt = ("You are checking whether a job posting is still open and accepting applications.\n"
        + (f"The page failed to load ({err}).\n" if err else "Fetched page text (may include nav/boilerplate):\n" + text)
        + '\n\nReply with ONLY a JSON object: {"state":"open|closed|unknown","reason":"<=15 words"}. '
        + "state=closed if the page clearly says filled/closed/no longer accepting applications/expired, "
        + "or is a 404/removed listing. state=open if it reads as a live, applyable posting. "
        + "state=unknown if you truly can't tell.")
    try:
        gurl = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}}).encode()
        greq = urllib.request.Request(gurl, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(greq, timeout=30) as r:
            gdata = json.load(r)
        result = json.loads(gdata["candidates"][0]["content"]["parts"][0]["text"])
        return str(result.get("state", "unknown")), str(result.get("reason", "")).replace("|", "/")[:150]
    except Exception as e:
        return "unknown", f"check failed: {str(e)[:150]}"


def check_url(key, url):
    """-> (state, reason) for one posting URL — fetch + LLM, or 'unknown' if no key."""
    if not key:
        return "unknown", "no GEMINI_API_KEY in job_crawler/.env"
    text, err = fetch_text(url)
    return gemini_check(key, text, err)


def apply_result(cells, state, reason):
    """Mutate a JOBS.md row's cells in place per the policy in the module docstring.
    cells = [num, company, role, location, fit, status, folder, notes]. -> changed bool."""
    if state != "closed":
        return False
    status_now = re.sub(r"\*\*", "", cells[5])
    if status_now in ("inbox", "cv-ready"):
        cells[5] = "closed"
        return True
    if "auto-check" not in cells[7]:
        today = time.strftime("%Y-%m-%d")
        cells[7] = cells[7].rstrip() + f" ⚠️ **Posting appears closed (auto-check {today}):** {reason}"
        return True
    return False


def _row_url(cells):
    um = re.search(r"https?://\S+", cells[7])
    return um.group(0).rstrip(".,);\"'>") if um else ""


def _arg(flag, default):
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    return default


def main():
    load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("no GEMINI_API_KEY (job_crawler/.env) — skipping refresh", file=sys.stderr); return
    cap = int(_arg("--cap", CAP))
    cooldown = int(_arg("--cooldown-days", COOLDOWN_DAYS))
    today = datetime.date.today()

    try:
        state = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        state = {}

    lines = open(JOBS, encoding="utf-8").read().split("\n")
    rows = []   # (line_idx, cells)
    for i, ln in enumerate(lines):
        if not ln.startswith("|"):
            continue
        cells = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(cells) < 8 or cells[0] in ("#", "") or set(cells[0]) <= set("-") or cells[1] in ("Company", ""):
            continue
        status_now = re.sub(r"\*\*", "", cells[5])
        if status_now not in ACTIVE_STATUSES:
            continue
        if not _row_url(cells):
            continue
        rows.append((i, cells))

    def last_checked(num):
        rec = state.get(num)
        if not rec:
            return None
        try:
            return datetime.date.fromisoformat(rec["date"])
        except Exception:
            return None

    def due(row):
        lc = last_checked(row[1][0])
        return lc is None or (today - lc).days >= cooldown

    candidates = [r for r in rows if due(r)]
    candidates.sort(key=lambda r: last_checked(r[1][0]) or datetime.date.min)
    batch = candidates[:cap]

    changed_any = False
    n_closed = n_open = n_unknown = 0
    for i, cells in batch:
        num = cells[0]
        url = _row_url(cells)
        st, reason = check_url(key, url)
        state[num] = {"date": today.isoformat(), "state": st}
        if apply_result(cells, st, reason):
            lines[i] = "| " + " | ".join(cells) + " |"
            changed_any = True
        if st == "closed":
            n_closed += 1
        elif st == "open":
            n_open += 1
        else:
            n_unknown += 1
        time.sleep(0.5)   # be polite to ATS hosts

    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if changed_any:
        with open(JOBS, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    print(f"refresh-status: checked {len(batch)} of {len(candidates)} due "
          f"({len(rows)} active total) — {n_open} open, {n_closed} closed, {n_unknown} unknown")


if __name__ == "__main__":
    main()
