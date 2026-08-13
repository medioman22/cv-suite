#!/usr/bin/env python3
"""Promote triaged backlog picks (top tiers, see DEFAULT_TIERS) into the curated
tracker JOBS.md so they show on the dashboard, and stash their rich details
(seniority, salary, description, fit subscores) in tracking/job_details.json for
the UI drawer.

Dedup is two-level and idempotent:
  1. LinkedIn job-id already present in JOBS.md  -> skip.
  2. (company, title) normalized key — collapses harvest repeats (the same role
     posted under slightly different company/title spellings) AND anything
     already curated in JOBS.md -> skip.
Promoted backlog rows are flagged so re-runs never double-add.

  python3 pipeline/promote.py [--tiers star3,star3,star2] [--dry]

Never commits — review JOBS.md yourself after running it.
"""
import os, re, sys, json, html, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKLOG = os.path.join(ROOT, "tracking", "backlog.jsonl")
JOBS = os.path.join(ROOT, "tracking", "JOBS.md")
DETAILS = os.path.join(ROOT, "tracking", "job_details.json")
TODAY = datetime.date.today().isoformat()
DEFAULT_TIERS = ("🌟", "★★★", "★★")

CORP = re.compile(r"\b(inc|llc|ltd|gmbh|ag|se|sa|co|corp|corporation|labs?|"
                  r"technologies|technology|research|america|ai|"
                  r"group|holding|studios?|the)\b", re.I)
ROLEWORD = re.compile(r"\b(engineer|scientist|manager|director|lead|researcher|"
                      r"architect|analyst|developer|designer|intern|consultant|"
                      r"specialist|president|founder|officer|head of|vp of)\b", re.I)


def unswap(company, title):
    """Some LinkedIn digest rows land company/title swapped (a job-title-looking
    string as the company, the real company name as the title). If the company
    reads like a job title and the title doesn't, put them back."""
    if ROLEWORD.search(company or "") and not ROLEWORD.search(title or ""):
        return title, company
    return company, title


def cnorm(c):
    c = html.unescape(c or "").lower()
    c = re.sub(r"[^a-z0-9 ]", " ", c)
    c = CORP.sub(" ", c)
    return re.sub(r"\s+", " ", c).strip()


def tnorm(t):
    t = html.unescape(t or "").lower()
    t = re.sub(r"\([^)]*\)", " ", t)          # drop parentheticals (salary, m/w/d, loc)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def key(company, title):
    return (cnorm(company), tnorm(title))


FIT_GLYPH = {"🌟": "🌟", "★★★": "★★★", "★★": "★★"}


def load_jobs_text():
    return open(JOBS, encoding="utf-8").read()


def existing_keys_and_ids(text):
    keys, ids, maxnum = set(), set(), 0
    ids |= set(re.findall(r"/jobs/view/(\d+)", text))
    for ln in text.splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 8 or c[1] in ("Company", "") or set(c[0]) <= set("-"):
            continue
        m = re.match(r"\s*(\d+)", c[0])
        if m:
            maxnum = max(maxnum, int(m.group(1)))
        company = c[1].strip()
        role = c[2].replace("**", "")
        keys.add(key(company, role))
    return keys, ids, maxnum


def main():
    tiers = tuple((_arg("--tiers", "") or "").split(",")) if "--tiers" in sys.argv else DEFAULT_TIERS
    tiers = tuple(t for t in tiers if t) or DEFAULT_TIERS
    dry = "--dry" in sys.argv

    rows = [json.loads(l) for l in open(BACKLOG, encoding="utf-8")]
    text = load_jobs_text()
    seen_keys, seen_ids, maxnum = existing_keys_and_ids(text)
    details = json.load(open(DETAILS, encoding="utf-8")) if os.path.exists(DETAILS) else {}

    picks = [r for r in rows if r.get("tier") in tiers and not r.get("promoted")]
    # highest tier first, then longest description -> the kept representative of a dup group
    rank = {"🌟": 0, "★★★": 1, "★★": 2}
    picks.sort(key=lambda r: (rank.get(r["tier"], 9), -len(r.get("desc") or "")))

    new_lines, added, skipped = [], 0, 0
    for r in picks:
        jid = str(r.get("id", ""))
        comp0, title0 = unswap(html.unescape(r.get("company", "")).strip(),
                               html.unescape(r.get("title", "")).strip())
        k = key(comp0, title0)
        if (jid and jid in seen_ids) or k in seen_keys or k == ("", ""):
            r["promoted"] = True            # collapse: mark so it won't be revisited
            skipped += 1
            continue
        seen_keys.add(k)
        if jid:
            seen_ids.add(jid)
        maxnum += 1
        num = str(maxnum)
        company = comp0.replace("|", "/")
        role = title0.replace("|", "/")
        loc = html.unescape(r.get("location", "")).strip().replace("|", "/") or "—"
        fit = FIT_GLYPH.get(r["tier"], "★★")
        url = r.get("url", "")
        sen = r.get("seniority") or "?"
        sal = r.get("salary") or "—"
        reason = (r.get("reason") or "").strip().rstrip(".")
        link = f"[link]({url})" if url else ""
        notes = f"{reason} · {sen} · {sal}. {link} _(auto-triage)_".strip()
        new_lines.append(f"| {num} | {company} | {role} | {loc} | {fit} | inbox |  | {notes} |")
        ss = r.get("subscores") or {}
        details[num] = {"seniority": sen, "salary": sal, "desc": r.get("desc") or "",
                        "subscores": ss, "reason": reason, "url": url, "location": loc,
                        "tier": r["tier"], "promoted": TODAY}
        r["promoted"] = True
        added += 1

    print(f"promote: {added} new rows, {skipped} deduped (from {len(picks)} candidates in {'/'.join(tiers)})")
    if dry:
        print("\n".join(new_lines[:15]) + ("\n… (--dry, nothing written)" if new_lines else ""))
        return
    if new_lines:
        # insert at the END of the main table — NOT EOF (a '## Source URLs' section
        # follows the table). Find the last '|' row that precedes any later '## ' heading.
        lines = text.split("\n")
        limit = next((i for i, l in enumerate(lines)
                      if l.startswith("## ") and i > 20), len(lines))
        last_tbl = max(i for i in range(limit) if lines[i].startswith("|"))
        lines[last_tbl + 1:last_tbl + 1] = new_lines
        with open(JOBS, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        json.dump(details, open(DETAILS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        with open(BACKLOG, "w", encoding="utf-8") as f:                # persist promoted flags
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> appended to {os.path.relpath(JOBS, ROOT)} + wrote {os.path.relpath(DETAILS, ROOT)}")


def _arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


if __name__ == "__main__":
    main()
