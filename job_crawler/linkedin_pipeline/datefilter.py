#!/usr/bin/env python3
"""Stage 3 — DATE FILTER. Fetch each candidate's public LinkedIn guest posting,
parse its posted date + open/closed state, and keep only postings published in
the last N months that are still open. Paced + backoff + incremental save so a
rate-limit stall never loses progress. Deterministic (no model cost).

Marks every fetched id into pipeline_seen.json so future runs skip it.
Usage: python3 datefilter.py [--months 3] [--delay 6]
"""
import os, sys, re, json, time, argparse, urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(__file__)
ap = argparse.ArgumentParser()
ap.add_argument("--cand", default=os.path.join(HERE, "candidates.json"))
ap.add_argument("--months", type=int, default=3)
ap.add_argument("--delay", type=float, default=6.0)
ap.add_argument("--out", default=os.path.join(HERE, "recent.json"))
ap.add_argument("--md", default=os.path.join(HERE, "recent.md"))
ap.add_argument("--seen", default=os.path.join(HERE, "pipeline_seen.json"))
args = ap.parse_args()

cutoff = datetime.now(timezone.utc) - timedelta(days=30 * args.months)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"

def parse_date(html):
    m = re.search(r'"datePosted"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})', html)
    if m:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    m = re.search(r'datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})', html)
    if m:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    return None   # unknown

def is_closed(html):
    return "No longer accepting applications" in html or "no-longer-accepting" in html

cand = json.load(open(args.cand))
try:
    results = {r["id"]: r for r in json.load(open(args.out))}   # resume
except Exception:
    results = {}
try:
    seen = set(json.load(open(args.seen)))
except Exception:
    seen = set()

stats = dict(fetched=0, ratelimited=0, tooold=0, closed=0, kept=0, unknown=0)
for i, j in enumerate(cand):
    jid = j["id"]
    if jid in results:      # already processed in a prior (resumed) run
        continue
    url = GUEST.format(jid)
    html = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers=UA)
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            break
        except Exception as e:
            if "429" in str(e) and attempt == 1:
                print(f"  429 at {i}/{len(cand)} — backing off 60s", file=sys.stderr)
                time.sleep(60); continue
            html = None
    seen.add(jid)
    if html is None:
        stats["ratelimited"] += 1
        json.dump(sorted(seen), open(args.seen, "w"))
        time.sleep(args.delay); continue
    stats["fetched"] += 1
    dt = parse_date(html)
    closed = is_closed(html)
    verdict = "keep"
    if closed:
        stats["closed"] += 1; verdict = "closed"
    elif dt is None:
        stats["unknown"] += 1; verdict = "keep?"    # keep, flag unknown date
    elif dt < cutoff:
        stats["tooold"] += 1; verdict = "old"
    if verdict in ("keep", "keep?"):
        stats["kept"] += 1
        j = dict(j); j["posted"] = dt.date().isoformat() if dt else "unknown"; j["verdict"] = verdict
        results[jid] = j
    # persist progress every iteration
    json.dump(list(results.values()), open(args.out, "w"), indent=1)
    json.dump(sorted(seen), open(args.seen, "w"))
    time.sleep(args.delay)

kept = sorted(results.values(), key=lambda x: (-x["_score"]))
with open(args.md, "w") as f:
    f.write(f"# LinkedIn pipeline — recent & open (last {args.months} months)\n\n")
    f.write("| Score | Title | Location | Posted | Link |\n|---|---|---|---|---|\n")
    for j in kept:
        f.write(f"| {j['_score']} | {j['title'][:58]} | {j['location'][:20]} | "
                f"{j.get('posted','?')} | [open]({j['url']}) |\n")
print("datefilter:", json.dumps(stats), file=sys.stderr)
print(f"-> {args.md} ({len(kept)} recent/open for the fit-check stage)", file=sys.stderr)
