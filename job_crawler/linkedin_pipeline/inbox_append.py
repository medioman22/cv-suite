#!/usr/bin/env python3
"""Stage 2b — append the LinkedIn pipeline shortlist into tracking/INBOX.md
(LinkedIn section), so pipeline hits are visible in the inbox like crawler hits.
Deduped against INBOX + JOBS, capped, most-recent-alert first. Reads
candidates.json (post-score, from score.py).

  python3 inbox_append.py

Env: INBOX_CAP (default 12) caps how many links land in one run.
"""
import json, os, re, sys
from datetime import date

HERE = os.path.dirname(__file__)
CAND = os.path.join(HERE, "candidates.json")
INBOX = os.path.join(HERE, "..", "..", "tracking", "INBOX.md")
JOBS = os.path.join(HERE, "..", "..", "tracking", "JOBS.md")
CAP = int(os.environ.get("INBOX_CAP", "12"))
SECTION = "## 🔗 LinkedIn (email / bookmarklet)"

cand = json.load(open(CAND)) if os.path.exists(CAND) else []
inbox = open(INBOX).read() if os.path.exists(INBOX) else ""
jobs = open(JOBS).read() if os.path.exists(JOBS) else ""
seen = set(re.findall(r"jobs/view/(\d+)", inbox + jobs))

new = []
for j in sorted(cand, key=lambda x: x.get("alert_date", ""), reverse=True):
    m = re.search(r"jobs/view/(\d+)", j["url"])
    jid = m.group(1) if m else str(j.get("id", ""))
    if not jid or jid in seen:
        continue
    seen.add(jid)
    new.append(j)
    if len(new) >= CAP:
        break

if not new:
    print("inbox_append: 0 new LinkedIn links to add")
    sys.exit(0)

block = "\n".join(f"{j['url']}  # {j['title'][:64]} (score {j['_score']})" for j in new)
add = f"<!-- linkedin pipeline {date.today()}: {len(new)} shortlisted -->\n{block}\n"
if SECTION in inbox:
    inbox = inbox.replace(SECTION, SECTION + "\n" + add, 1)
else:
    inbox = inbox.rstrip() + "\n\n" + SECTION + "\n" + add
open(INBOX, "w").write(inbox)
print(f"inbox_append: added {len(new)} LinkedIn link(s) to INBOX.md")
