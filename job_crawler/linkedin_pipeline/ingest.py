#!/usr/bin/env python3
"""Stage 1 — INGEST (incremental). Pull LinkedIn job-alert emails via IMAP and
extract every (job id, title, location, latest-alert-date) into raw.json.

INCREMENTAL: caches processed IMAP UIDs + extracted postings in email_cache.json,
so each run only DOWNLOADS emails it hasn't seen before (the slow part). The first
run is a full fetch; later runs fetch just the new alert emails. Deterministic, no
model cost. ToS-safe: reads only your own mailbox.

Env: EMAIL_USER, EMAIL_PASS (Gmail App Password). Reuses ../.env if present.
Usage: python3 ingest.py [--full]   (--full ignores the cache and refetches all)
"""
import imaplib, email, os, re, html as H, json, sys, argparse
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
for envp in (os.path.join(HERE, "..", ".env"), os.path.join(HERE, ".env")):
    if os.path.exists(envp):
        for line in open(envp):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

ap = argparse.ArgumentParser()
ap.add_argument("--host", default=os.environ.get("EMAIL_HOST", "imap.gmail.com"))
ap.add_argument("--folder", default=os.environ.get("EMAIL_FOLDER", "INBOX"))
ap.add_argument("--search", default='(FROM "linkedin.com")')
ap.add_argument("--out", default=os.path.join(HERE, "raw.json"))
ap.add_argument("--cache", default=os.path.join(HERE, "email_cache.json"))
ap.add_argument("--full", action="store_true", help="ignore cache, refetch all emails")
args = ap.parse_args()

user, pw = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS")
if not user or not pw:
    sys.exit("EMAIL_USER / EMAIL_PASS not set (Gmail needs an App Password). "
             "Export them or add to job_crawler/.env")

def clean(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

SECONDARY = ("switzerland", "germany", "france", "italy", "austria",
             "united kingdom", "netherlands", "spain", "europe")

def find_loc(tail):
    m = re.search(r'([A-Z][A-Za-zäöüéè\-. ]+,\s*(?:%s))'
                  % "|".join(x.title() for x in SECONDARY), tail)
    if m: return m.group(1)
    if re.search(r'\bremote\b', tail, re.I): return "Remote"
    m = re.search(r'\b(Z[uü]rich|Geneva|Gen[eè]ve|Lausanne|Basel|Bern|Zug|Lugano|Switzerland)\b', tail)
    return m.group(1) if m else ""

# ── load cache ────────────────────────────────────────────────────────────
cache = {"uidvalidity": None, "processed_uids": [], "postings": {}}
if not args.full and os.path.exists(args.cache):
    try:
        cache = json.load(open(args.cache))
    except Exception:
        pass
processed = set(cache.get("processed_uids", []))
postings = cache.get("postings", {})

M = imaplib.IMAP4_SSL(args.host)
M.login(user, pw)
M.select(args.folder)

# UIDVALIDITY: if the mailbox was reset, our cached UIDs are meaningless → full refetch
try:
    _, d = M.status(f'"{args.folder}"', "(UIDVALIDITY)")
    uidvalidity = int(re.search(rb"UIDVALIDITY (\d+)", d[0]).group(1))
except Exception:
    uidvalidity = None
if cache.get("uidvalidity") not in (None, uidvalidity):
    print("ingest: UIDVALIDITY changed — cache invalidated, refetching all", file=sys.stderr)
    processed, postings = set(), {}

# UID SEARCH is cheap (returns ids only, no download); diff against processed
_, data = M.uid("SEARCH", None, args.search)
all_uids = [u.decode() for u in data[0].split()]
new_uids = [u for u in all_uids if u not in processed]
print(f"ingest: {len(all_uids)} LinkedIn emails; {len(new_uids)} new to fetch "
      f"({len(processed)} cached)", file=sys.stderr)

def merge(jid, title, loc, edate_iso):
    j = postings.get(jid)
    if not j:
        postings[jid] = {"id": jid, "title": title, "location": loc,
                         "alert_date": edate_iso,
                         "url": f"https://www.linkedin.com/jobs/view/{jid}/"}
    else:
        if loc and not j["location"]:
            j["location"] = loc
        if edate_iso > j["alert_date"]:
            j["alert_date"] = edate_iso

for uid in new_uids:
    _, d = M.uid("FETCH", uid, "(RFC822)")
    if not d or not d[0]:
        processed.add(uid); continue
    msg = email.message_from_bytes(d[0][1])
    try:
        edate = parsedate_to_datetime(msg.get("Date")).astimezone(timezone.utc).isoformat()
    except Exception:
        edate = "1970-01-01T00:00:00+00:00"
    html = ""
    for p in msg.walk():
        if p.get_content_type() == "text/html":
            html = p.get_payload(decode=True).decode("utf-8", "ignore"); break
    if "jobs/view" in html:
        for m in re.finditer(r'<a[^>]+jobs/view/(\d+)[^>]*>(.*?)</a>', html, re.S):
            jid, title = m.group(1), clean(m.group(2))
            if title and len(title) >= 3:
                merge(jid, title, find_loc(clean(html[m.end():m.end()+500])), edate)
    processed.add(uid)
M.logout()

# ── save cache + raw.json ─────────────────────────────────────────────────
cache = {"uidvalidity": uidvalidity, "processed_uids": sorted(processed, key=int),
         "postings": postings}
json.dump(cache, open(args.cache, "w"))
json.dump(list(postings.values()), open(args.out, "w"), indent=1)
print(f"ingest: {len(postings)} unique postings (fetched {len(new_uids)} new emails) "
      f"-> {args.out}", file=sys.stderr)
