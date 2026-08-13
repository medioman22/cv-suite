#!/usr/bin/env python3
"""
Job crawler — fetch jobs from configured sources, score them against your
profile (see config.py), drop duplicates (incl. anything already in JOBS.md), and write a ranked
suggestions.md. Optionally feeds the top new links into ../INBOX.md so the normal
"inbox" workflow can turn them into tailored CVs.

Usage:
    python3 crawler.py                 # run everything enabled in config.py
    python3 crawler.py --dry-run       # print results, write nothing
    python3 crawler.py --no-inbox      # write suggestions.md but don't touch INBOX
    python3 crawler.py --min-score 8   # override threshold
"""
from __future__ import annotations
import argparse, json, os, re, sys, datetime
import config as cfg
import sources


def score(job):
    """Return an int score, or None if the posting fails the hard title gate."""
    title = job["title"].lower()
    if not any(term in title for term in cfg.CORE_TITLE_TERMS):
        return None                         # not an ML/CV/robotics role — reject
    if any(w in title for w in ("intern", "co-op", "working student", "apprentice",
                                "new grad", "new college grad", "graduate program", "praktik")):
        return None                         # junior / student roles — reject
    desc = job.get("description", "").lower()
    s = 0
    for kw, w in cfg.KEYWORDS.items():
        if kw in title:
            s += w * 2                      # title match counts double
        elif kw in desc:
            s += max(1, w // 2)             # description match counts ~half
    for kw, w in cfg.NEGATIVE_KEYWORDS.items():
        if kw in title:
            s -= w * 2
        elif kw in desc:
            s -= w
    # Tiered location scoring (no-relocation search: Swiss roles rank first).
    loc_field = job.get("location", "").lower()          # structured location only
    loc = (loc_field + " " + desc).lower()               # full text for city matches
    # Trust remote only from the flag or the location field — "remote" in a
    # description is often "this role is not remote" and misleads the score.
    is_remote = bool(job.get("remote")) or "remote" in loc_field
    if any(l in loc for l in cfg.LOCATIONS_PRIMARY):
        s += cfg.LOC_BONUS_PRIMARY
    elif cfg.ALLOW_REMOTE and is_remote:
        s += cfg.LOC_BONUS_REMOTE
    elif any(l in loc for l in cfg.LOCATIONS_SECONDARY):
        s += cfg.LOC_BONUS_SECONDARY
    elif any(b in loc for b in getattr(cfg, "LOCATIONS_BLOCK", [])):
        s -= cfg.LOC_PENALTY_OFF            # out-of-scope region (Asia/ME/…) — drop
    else:
        s += getattr(cfg, "LOC_BONUS_US", 1)  # US / Canada / unlabeled — keep as reach
    return s


def load_seen() -> set:
    seen = set()
    try:
        seen = set(json.load(open(cfg.SEEN_PATH)))
    except Exception:
        pass
    # Never re-suggest anything already tracked in JOBS.md (LinkedIn ids).
    try:
        jm = open(cfg.JOBS_MD_PATH).read()
        for jid in re.findall(r"/jobs/view/(\d+)", jm):
            seen.add("linkedin:" + jid)
    except Exception:
        pass
    return seen


def gather():
    jobs = []
    if cfg.ENABLE_ARBEITNOW:
        print("· arbeitnow");        jobs += sources.arbeitnow()
    if cfg.ENABLE_REMOTIVE:
        print("· remotive");         jobs += sources.remotive(cfg.REMOTIVE_QUERIES)
    if cfg.ENABLE_REMOTEOK:
        print("· remoteok");         jobs += sources.remoteok()
    if cfg.GREENHOUSE_COMPANIES:
        print("· greenhouse");       jobs += sources.greenhouse(cfg.GREENHOUSE_COMPANIES)
    if cfg.LEVER_COMPANIES:
        print("· lever");            jobs += sources.lever(cfg.LEVER_COMPANIES)
    if cfg.ASHBY_COMPANIES:
        print("· ashby");            jobs += sources.ashby(cfg.ASHBY_COMPANIES)
    if cfg.ENABLE_ADZUNA:
        print("· adzuna");           jobs += sources.adzuna(cfg.ADZUNA_COUNTRY, cfg.ADZUNA_QUERIES)
    if getattr(cfg, "ENABLE_JOBSCH", False):
        print("· jobs.ch");          jobs += sources.jobs_ch(cfg.JOBSCH_QUERIES, getattr(cfg, "JOBSCH_PAGES", 1))
    if getattr(cfg, "ENABLE_BIGTECH", False):
        import bigtech
        q, lim = cfg.BIGTECH_QUERIES, cfg.BIGTECH_LIMIT
        if getattr(cfg, "ENABLE_AMAZON", False):
            print("· amazon");        jobs += bigtech.amazon(q, cfg.AMAZON_LOC, lim)
        if getattr(cfg, "WORKDAY_COMPANIES", None):
            print("· workday");       jobs += bigtech.workday(cfg.WORKDAY_COMPANIES, q, lim)
        if getattr(cfg, "ENABLE_NETFLIX", False):
            print("· netflix");       jobs += bigtech.netflix(q, lim)
        if getattr(cfg, "ENABLE_SNAP", False):
            print("· snap");          jobs += bigtech.snap(q)
    if cfg.ENABLE_LINKEDIN:
        print("· linkedin (guest, unofficial)")
        jobs += sources.linkedin_guest(cfg.LINKEDIN_QUERIES, cfg.LINKEDIN_LOCATION,
                                        cfg.LINKEDIN_MAX_PER_QUERY, cfg.LINKEDIN_DELAY_SEC)
    return jobs


def write_suggestions(ranked):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Crawler suggestions — {now}", "",
             f"{len(ranked)} new job(s) above threshold (score ≥ {cfg.MIN_SCORE}), best first.", "",
             "| Score | Title | Company | Location | Source | Link |",
             "|:---:|-------|---------|----------|--------|------|"]
    for j in ranked:
        t = j["title"].replace("|", "/")[:70]
        c = (j["company"] or "").replace("|", "/")[:28]
        loc = (j["location"] or "").replace("|", "/")[:26]
        lines.append(f"| {j['_score']} | {t} | {c} | {loc} | {j['source']} | [open]({j['url']}) |")
    open(cfg.SUGGESTIONS_FILE, "w").write("\n".join(lines) + "\n")
    print(f"→ wrote {cfg.SUGGESTIONS_FILE} ({len(ranked)} suggestions)")


def append_to_inbox(ranked):
    if not ranked:
        return
    try:
        inbox = open(cfg.INBOX_PATH).read()
    except Exception as e:
        print("  [inbox] could not read INBOX:", e); return
    existing = set(re.findall(r"https?://\S+", inbox))
    picks = [j for j in ranked if j["url"] not in existing][: cfg.MAX_INBOX_APPEND]
    if not picks:
        print("  [inbox] nothing new to add"); return
    block = "\n".join(j["url"] for j in picks)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    add = f"<!-- crawler {stamp}: {len(picks)} suggestion(s) -->\n{block}\n"
    marker = getattr(cfg, "INBOX_SECTION_CRAWLER", "")
    if marker and marker in inbox:                      # drop under the Crawler section
        inbox = inbox.replace(marker, marker + "\n" + add, 1)
    elif "\n---\n" in inbox:
        inbox = inbox.replace("\n---\n", "\n---\n\n" + add, 1)
    else:
        inbox += "\n" + add
    open(cfg.INBOX_PATH, "w").write(inbox)
    print(f"→ added {len(picks)} link(s) to {cfg.INBOX_PATH} (review, then tell Claude \"inbox\")")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-inbox", action="store_true")
    ap.add_argument("--min-score", type=int, default=cfg.MIN_SCORE)
    args = ap.parse_args()

    seen = load_seen()
    jobs = gather()
    print(f"fetched {len(jobs)} raw postings")

    # dedupe by id, score, threshold, sort
    uniq, ids = [], set()
    for j in jobs:
        if j["id"] in ids or j["id"] in seen or not j.get("url"):
            continue
        ids.add(j["id"])
        sc = score(j)
        if sc is None:
            continue                        # failed title gate
        j["_score"] = sc
        if sc >= args.min_score:
            uniq.append(j)
    ranked = sorted(uniq, key=lambda x: x["_score"], reverse=True)
    cap = getattr(cfg, "MAX_PER_COMPANY", 0)
    if cap:
        capped, counts = [], {}
        for j in ranked:
            c = (j["company"] or "?").lower()
            counts[c] = counts.get(c, 0) + 1
            if counts[c] <= cap:
                capped.append(j)
        ranked = capped
    print(f"{len(ranked)} pass the score threshold ({args.min_score}), capped {cap}/company")

    if args.dry_run:
        for j in ranked[:25]:
            print(f"  {j['_score']:>3}  {j['title'][:60]:60}  {j['company'][:20]:20}  {j['source']}")
        print("(dry-run: nothing written)")
        return

    write_suggestions(ranked)
    # remember everything we saw this run (so it isn't re-suggested next time)
    json.dump(sorted(seen | ids), open(cfg.SEEN_PATH, "w"))
    if cfg.APPEND_TO_INBOX and not args.no_inbox:
        append_to_inbox(ranked)


if __name__ == "__main__":
    sys.exit(main())
