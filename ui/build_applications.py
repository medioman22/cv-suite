#!/usr/bin/env python3
"""Regenerate ui/applications.html from tracking/APPLICATIONS.md.
Parses the Pipeline table and the Contacts table, and merges in every
tracking/JOBS.md row that's actually in an applied/interviewing/etc. state (so
this page is never out of sync with JOBS.md even if APPLICATIONS.md lags).
Run after updating either doc, or hit /applications live (serve.py parses the
same way).

Usage: python3 ui/build_applications.py
"""
import re, json, os
HERE = os.path.dirname(__file__)
APPS = os.path.join(HERE, "..", "tracking", "APPLICATIONS.md")
JOBS = os.path.join(HERE, "..", "tracking", "JOBS.md")
TPL  = os.path.join(HERE, "applications.template.html")
OUT  = os.path.join(HERE, "applications.html")

# JOBS.md statuses that mean "there's a real application/conversation in flight".
PIPE_STAGES = {"applied", "interviewing", "offer", "accepted", "rejected", "withdrawn"}
STAGE_ORDER = {"offer": 0, "interviewing": 1, "applied": 2,
               "accepted": 3, "withdrawn": 4, "rejected": 5}


def clean(s):
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = s.replace("**", "")
    s = re.sub(r"_([^_]+)_", r"\1", s)
    return s.strip()


def parse(path):
    pipeline, contacts = [], []
    mode = None
    for ln in open(path, encoding="utf-8"):
        if not ln.startswith("|"):
            if ln.strip() == "":
                mode = None
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        low = " | ".join(c.lower() for c in cells)
        if set("".join(cells)) <= set("-: "):        # separator row
            continue
        if "next step" in low and "stage" in low:     # pipeline header
            mode = "pipe"; continue
        if "handle" in low or (mode is None and "email" in low and "name" in low):
            mode = "contact"; continue
        if mode == "pipe" and len(cells) >= 6:
            company, role, stage, contact, last, nxt = [clean(c) for c in cells[:6]]
            pipeline.append({"company": company, "role": role,
                             "stage": stage.lower(), "contact": contact,
                             "last": last, "next": nxt})
        elif mode == "contact" and len(cells) >= 5:
            name, comp, role, email, notes = [clean(c) for c in cells[:5]]
            contacts.append({"name": name, "company": comp, "role": role,
                             "email": email, "notes": notes})
    return pipeline, contacts


def parse_drafts(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"## Follow-up drafts(.*?)(?=\n## |\Z)", txt, re.S)
    if not m:
        return []
    out = []
    for d in re.finditer(r"### (.+?)\n(.*?)(?=\n### |\Z)", m.group(1), re.S):
        head, blk = d.group(1), d.group(2)
        company, _, contact = head.partition("·")
        to = re.search(r"To:\**\s*(.+)", blk)
        subj = re.search(r"Subject:\**\s*(.+)", blk)
        body = re.sub(r"^\s*[-*].*?(To|Subject):.*$", "", blk, flags=re.M).strip()
        out.append({"company": clean(company), "contact": clean(contact),
                    "to": clean(to.group(1)) if to else "",
                    "subject": clean(subj.group(1)) if subj else "",
                    "body": body})
    return out


def _ck(c):
    return re.sub(r"[^a-z0-9]", "", (c or "").lower())[:14]


def _rtokens(r):
    r = re.sub(r"\(.*?\)", " ", (r or "").lower())
    return {w for w in re.findall(r"[a-z0-9]{5,}", r)}


def parse_jobs_applied(path=JOBS):
    """Every JOBS.md row whose Status is in the applied-family → pipeline dicts.
    This is the complete set of roles actually applied to / in conversation about;
    APPLICATIONS.md only enriches it with contact/next-step detail."""
    out = []
    for ln in open(path, encoding="utf-8"):
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        company, role, loc, status, folder = (clean(cells[1]), clean(cells[2]),
                                               clean(cells[3]), clean(cells[5]).lower(),
                                               clean(cells[6]))
        if company in ("Company", "") or set(company) <= set("-"):
            continue
        stage = status.split()[0] if status else ""
        if stage not in PIPE_STAGES:
            continue
        out.append({"company": company, "role": role, "stage": stage,
                    "contact": "", "last": "", "next": "", "location": loc,
                    "folder": "" if folder in ("", "—") else folder, "source": "jobs"})
    return out


def merged_pipeline():
    """All applied JOBS.md rows, each enriched with contact/last/next from a
    matching APPLICATIONS.md row; plus any APPLICATIONS-only rows. Sorted by stage."""
    apps, _ = parse(APPS)
    jobs = parse_jobs_applied()
    used = set()
    merged = []
    for j in jobs:
        jc, jt = _ck(j["company"]), _rtokens(j["role"])
        best = None
        for i, a in enumerate(apps):
            if i in used:
                continue
            ac = _ck(a["company"])
            if not (ac == jc or ac.startswith(jc) or jc.startswith(ac)):
                continue
            if _rtokens(a["role"]) & jt or not (jt or _rtokens(a["role"])):
                best = i
                break
        row = dict(j)
        if best is not None:
            a = apps[best]; used.add(best)
            row["contact"], row["last"], row["next"] = a["contact"], a["last"], a["next"]
            # Show the most informative signal from either doc: a recorded outcome
            # (offer/accepted/rejected/withdrawn) or interviewing beats a bare "applied".
            prio = ["offer", "accepted", "rejected", "withdrawn", "interviewing", "applied"]
            for s in prio:
                if row["stage"] == s or a["stage"] == s:
                    row["stage"] = s
                    break
        merged.append(row)
    for i, a in enumerate(apps):          # APPLICATIONS rows with no JOBS match
        if i not in used:
            merged.append({**a, "location": a.get("location", ""),
                           "folder": "", "source": "apps"})
    merged.sort(key=lambda r: (STAGE_ORDER.get(r["stage"], 9), r["company"].lower()))
    return merged


def data():
    """(pipeline, contacts, drafts) for both the static build and the live server."""
    _, contacts = parse(APPS)
    return merged_pipeline(), contacts, parse_drafts(APPS)


def build():
    pipeline, contacts, drafts = data()
    tpl = open(TPL).read()
    tpl = tpl.replace("__PIPELINE__", json.dumps(pipeline, ensure_ascii=False))
    tpl = tpl.replace("__CONTACTS__", json.dumps(contacts, ensure_ascii=False))
    tpl = tpl.replace("__DRAFTS__", json.dumps(drafts, ensure_ascii=False))
    open(OUT, "w").write(tpl)
    print(f"applications: {len(pipeline)} in pipeline "
          f"({sum(1 for p in pipeline if p.get('source')=='jobs')} from JOBS.md), "
          f"{len(contacts)} contacts, {len(drafts)} drafts -> {OUT}")


if __name__ == "__main__":
    build()
