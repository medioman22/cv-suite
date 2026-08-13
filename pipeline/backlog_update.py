#!/usr/bin/env python3
"""Harvest new job openings into tracking/backlog.jsonl (the canonical, append-only
backlog the daily triage drains).

Sources:
  - LinkedIn saved-search alert emails (Gmail, via config.EMAIL_* knobs) — company/
    title/location parsed straight from the digest HTML, no per-URL fetch.
  - The crawler's suggestions.md (ATS/aggregators).

Dedup: never add anything already in JOBS.md or already in backlog.jsonl.
Records: {id, company, title, location, url, source, harvested, triaged, tier, reason}.

  python3 pipeline/backlog_update.py            # harvest into backlog.jsonl
  python3 pipeline/backlog_update.py --seed      # also import tracking/linkedin_backlog.md once

This is the "many small candidates, cheap to fetch" half of finding roles; the
pricier per-posting fetch + fit-check happens later, in triage.py / the "inbox"
loop. Stdlib only (imaplib/email for IMAP).
"""
import os, re, sys, json, email, imaplib, datetime
from email.policy import default

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # repo root
JC = os.path.join(ROOT, "job_crawler")
sys.path.insert(0, JC)
import config as cfg                                          # loads job_crawler/.env -> env

JOBS = os.path.join(ROOT, "tracking", "JOBS.md")
BACKLOG = os.path.join(ROOT, "tracking", "backlog.jsonl")
# crawler writes suggestions.md relative to its cwd — check both likely spots
SUGG = next((p for p in (os.path.join(JC, "suggestions.md"),
                         os.path.join(ROOT, "suggestions.md")) if os.path.exists(p)),
            os.path.join(JC, "suggestions.md"))
LEGACY_MD = os.path.join(ROOT, "tracking", "linkedin_backlog.md")
TODAY = datetime.date.today().isoformat()

BOILER = re.compile(r"^(this company is actively hiring|actively recruiting|view job|see all|"
                    r"unsubscribe|your job alert|results from|new jobs match|be an early applicant|"
                    r"\d+ new jobs?|view all jobs)", re.I)
# CH detector — retune to your own no-relocation region if you're not in Switzerland.
CH = re.compile(r"switzerland|schweiz|suisse|zurich|zürich|lausanne|geneva|genève|genf|basel|zug|"
                r"bern|lugano|ticino|neuch|vaud|luzern|lucerne|winterthur|"
                r"st\.?\s?gallen|aargau|thurgau|valais|wallis|fribourg|sion|biel|chur", re.I)

JOBID_RE = re.compile(r'(?:jobs/view/|currentJobId=|jobPosting[:/])(\d{6,})')


def ids_from_text(t):
    """Every LinkedIn job id mentioned in a blob of text (URL, query param, or id)."""
    return set(JOBID_RE.findall(t or ""))


def _html(msg):
    """Concatenated text/html (or text/plain fallback) parts of an email.message."""
    parts = []
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_type() in ("text/html", "text/plain"):
            try:
                parts.append(p.get_content())
            except Exception:
                try:
                    parts.append((p.get_payload(decode=True) or b"").decode("utf-8", "replace"))
                except Exception:
                    pass
    return "\n".join(parts)


def _strip(html):
    html = re.sub(r"(?i)</(p|div|td|tr|a|h\d|li|span)>", "\n", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"<[^>]+>", "", html)
    html = re.sub(r"&amp;", "&", html); html = re.sub(r"&[a-z]+;", " ", html)
    return [l.strip() for l in html.splitlines() if l.strip()]


def _cards(html):
    lines = _strip(html)
    for i, ln in enumerate(lines):
        m = re.search(r"/jobs/view/(\d+)", ln)
        if not m:
            continue
        prev = [l for l in lines[max(0, i - 7):i]
                if not BOILER.match(l) and "/jobs/view/" not in l and len(l) < 90]
        if len(prev) >= 3:
            yield m.group(1), prev[-3], prev[-2], prev[-1]


def from_linkedin():
    """[(id, title, company, location, url)] from the alert emails."""
    out = {}
    user, pw = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS")
    if not (user and pw):
        print("  [linkedin] no EMAIL_USER/EMAIL_PASS — skipping", file=sys.stderr); return out
    try:
        M = imaplib.IMAP4_SSL(cfg.EMAIL_HOST, timeout=30); M.login(user, pw)  # never hang
        M.select(cfg.EMAIL_FOLDER)
        _, d = M.search(None, cfg.EMAIL_SEARCH)
        for n in d[0].split()[-cfg.EMAIL_MAX:]:
            _, dd = M.fetch(n, "(RFC822)")
            html = _html(email.message_from_bytes(dd[0][1], policy=default))
            for jid, t, c, loc in _cards(html):
                out.setdefault(jid, (t, c, loc, f"https://www.linkedin.com/jobs/view/{jid}/"))
        M.logout()
    except Exception as e:
        print(f"  [linkedin] {e}", file=sys.stderr)
    return out


def from_crawler():
    """[(id, title, company, location, url)] from suggestions.md rows."""
    out = {}
    if not os.path.exists(SUGG):
        return out
    for ln in open(SUGG, encoding="utf-8"):
        if not ln.startswith("|") or "Score" in ln or set(ln.strip()) <= set("|:-"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        _, title, company, location, source, link = cells[:6]
        mu = re.search(r"\((https?://[^)]+)\)", link) or re.search(r"(https?://\S+)", link)
        if not mu:
            continue
        url = mu.group(1)
        mid = re.search(r"/jobs/view/(\d+)", url) or re.search(r"(\d{6,})", url)
        jid = mid.group(1) if mid else "c" + str(abs(hash(url)) % 10**10)
        out.setdefault(jid, (title, company, location, url, source))
    return out


def load_ids():
    ids = set()
    jm = open(JOBS, encoding="utf-8").read()
    ids |= ids_from_text(jm) | set(re.findall(r"`(\d{8,})`", jm))
    if os.path.exists(BACKLOG):
        for ln in open(BACKLOG, encoding="utf-8"):
            try:
                ids.add(json.loads(ln)["id"])
            except Exception:
                pass
    return ids


def seed_from_md():
    """One-time import of an existing tracking/linkedin_backlog.md table into
    backlog.jsonl, if you're migrating an older manual list. Safe to skip/ignore
    if you don't have one — most starters won't."""
    if not os.path.exists(LEGACY_MD):
        return []
    recs = []
    for ln in open(LEGACY_MD, encoding="utf-8"):
        m = re.match(r"\|\s*(\d{6,})\s*\|(.+?)\|\s*(https?://\S+?)\s*\|", ln)
        if not m:
            continue
        jid, meta, url = m.group(1), m.group(2).strip(), m.group(3)
        parts = [p.strip() for p in meta.split("·")]
        company = parts[0] if parts else ""
        title = parts[1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
        location = parts[-1] if parts else ""
        recs.append((jid, title, company, location, url, "linkedin-alert"))
    return recs


def main():
    seed = "--seed" in sys.argv
    known = load_ids()
    new = []

    def add(jid, title, company, location, url, source):
        if jid in known:
            return
        known.add(jid)
        new.append({"id": jid, "company": company, "title": title, "location": location,
                    "url": url, "source": source, "harvested": TODAY,
                    "triaged": False, "tier": None, "reason": None,
                    "ch": bool(CH.search(f"{company} {title} {location}"))})

    if seed:
        for jid, t, c, loc, url, src in seed_from_md():
            add(jid, t, c, loc, url, src)

    for jid, (t, c, loc, url) in from_linkedin().items():
        add(jid, t, c, loc, url, "linkedin-alert")
    for jid, (t, c, loc, url, src) in from_crawler().items():
        add(jid, t, c, loc, url, f"crawler:{src}")

    with open(BACKLOG, "a", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ch = sum(1 for r in new if r["ch"])
    print(f"backlog +{len(new)} new ({ch} CH) -> {os.path.relpath(BACKLOG, ROOT)}")


if __name__ == "__main__":
    main()
