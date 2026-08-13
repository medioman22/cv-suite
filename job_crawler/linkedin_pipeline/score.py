#!/usr/bin/env python3
"""Stage 2 — SCORE & DEDUPE. Read raw.json, apply the crawler's title gate +
keyword scoring + Swiss-first location bonus, drop anything already tracked in
JOBS.md or already screened (pipeline_seen.json), and write candidates.json +
candidates.md. Deterministic, no model cost.

Usage: python3 score.py [--min-score 14] [--swiss-only]
"""
import os, sys, re, json, argparse
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))   # reuse ../config.py knobs
import config as cfg

ap = argparse.ArgumentParser()
ap.add_argument("--raw", default=os.path.join(HERE, "raw.json"))
ap.add_argument("--min-score", type=int, default=14)
ap.add_argument("--swiss-only", action="store_true", default=True)
ap.add_argument("--jobs-md", default=os.path.join(HERE, "..", "..", "tracking", "JOBS.md"))
ap.add_argument("--seen", default=os.path.join(HERE, "pipeline_seen.json"))
ap.add_argument("--out", default=os.path.join(HERE, "candidates.json"))
ap.add_argument("--md", default=os.path.join(HERE, "candidates.md"))
args = ap.parse_args()

CH = ["zurich", "zürich", "geneva", "genève", "lausanne", "basel", "bern",
      "zug", "lugano", "vaud", "ticino", "aargau", "switzerland", "schweiz", "suisse"]

def swiss(loc): return any(c in loc.lower() for c in CH)

def score(job):
    title = job["title"].lower()
    if not any(t in title for t in cfg.CORE_TITLE_TERMS):
        return None
    if any(w in title for w in ("intern", "praktikum", "working student", "apprentice", "thesis")):
        return None
    s = 0
    for kw, w in cfg.KEYWORDS.items():
        if kw in title: s += w * 2
    for kw, w in cfg.NEGATIVE_KEYWORDS.items():
        if kw in title: s -= w * 2
    loc = job["location"].lower()
    if any(l in loc for l in cfg.LOCATIONS_PRIMARY): s += cfg.LOC_BONUS_PRIMARY
    elif "remote" in loc: s += cfg.LOC_BONUS_REMOTE
    elif any(l in loc for l in cfg.LOCATIONS_SECONDARY): s += cfg.LOC_BONUS_SECONDARY
    elif any(b in loc for b in getattr(cfg, "LOCATIONS_BLOCK", [])): s -= cfg.LOC_PENALTY_OFF
    else: s += getattr(cfg, "LOC_BONUS_US", 1)   # US / Canada / unlabeled — keep
    return s

# already-tracked LinkedIn ids (so we never re-surface a role we've filed)
tracked = set()
try:
    tracked = set(re.findall(r"jobs/view/(\d+)", open(args.jobs_md).read()))
except Exception:
    pass
try:
    seen = set(json.load(open(args.seen)))
except Exception:
    seen = set()

raw = json.load(open(args.raw))
cand, dedup = [], set()
for j in raw:
    if j["id"] in tracked or j["id"] in seen:
        continue
    sc = score(j)
    if sc is None or sc < args.min_score:
        continue
    if any(b in j["location"].lower() for b in getattr(cfg, "LOCATIONS_BLOCK", [])):
        continue   # drop out-of-scope regions; keep CH / EU / US / remote / unlabeled
    key = re.sub(r"[^a-z0-9]", "", j["title"].lower())[:38]
    if key in dedup:
        continue
    dedup.add(key)
    j["_score"] = sc
    cand.append(j)

cand.sort(key=lambda x: x["_score"], reverse=True)
json.dump(cand, open(args.out, "w"), indent=1)
with open(args.md, "w") as f:
    f.write(f"# LinkedIn pipeline — candidates (score >= {args.min_score}, deduped)\n\n")
    f.write("| Score | Title | Location | Latest alert | Link |\n|---|---|---|---|---|\n")
    for j in cand:
        f.write(f"| {j['_score']} | {j['title'][:60]} | {j['location'][:22]} | "
                f"{j.get('alert_date','')[:10]} | [open]({j['url']}) |\n")
print(f"score: {len(cand)} candidates (of {len(raw)} raw; {len(tracked)} tracked, "
      f"{len(seen)} previously screened) -> {args.out}", file=sys.stderr)
