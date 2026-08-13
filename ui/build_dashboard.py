#!/usr/bin/env python3
"""Regenerate ui/dashboard.html from tracking/JOBS.md + tracking/INBOX.md.
The dashboard is a read-only view of the tracker — run this after processing jobs.
Usage: python3 ui/build_dashboard.py
"""
import re, json, os
from inbox_parse import parse_inbox
HERE = os.path.dirname(__file__)
JOBS = os.path.join(HERE, "..", "tracking", "JOBS.md")
INBOX = os.path.join(HERE, "..", "tracking", "INBOX.md")
TPL  = os.path.join(HERE, "dashboard.template.html")
OUT  = os.path.join(HERE, "dashboard.html")

rows = []
for ln in open(JOBS):
    if not ln.startswith("|"):
        continue
    c = [x.strip() for x in ln.strip().strip("|").split("|")]
    if len(c) < 8 or c[0] in ("#", "---") or set(c[0]) <= set("-") or c[1] in ("Company", ""):
        continue
    num, company, role, location, fit, status, folder, notes = c[:8]
    stars = fit.count("★")
    tier = {3: "strong", 2: "moderate", 1: "reach", 0: "skip"}.get(stars, "skip")
    if ("—" in fit or fit == "") and "internal" in status:
        tier = "internal"
    m = re.search(r"/[0-9]{6}_([A-Z]{2,3})_", folder)
    src = ""
    ms = re.search(r"_\(([^)]+)\)_\s*$", notes)
    if ms:
        src = ms.group(1)
    notes_clean = re.sub(r"_\([^)]+\)_\s*$", "", notes).strip()
    notes_clean = notes_clean.replace("**", "")
    fp = re.search(r"`([^`]+)`", folder)
    rows.append({
        "company": company.replace("⚠️defense", "").strip(),
        "defense": "defense" in company,
        "role": role.replace("**", ""),
        "location": location.replace("🇨🇭", "").replace("**", "").strip(),
        "loc": m.group(1) if m else "",
        "stars": stars, "tier": tier,
        "status": status.replace("**", ""),
        "folder": fp.group(1) if fp else folder,
        "notes": notes_clean, "source": src,
    })

inbox = parse_inbox(INBOX)

tpl = open(TPL).read()
tpl = tpl.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
tpl = tpl.replace("__INBOX__", json.dumps(inbox, ensure_ascii=False))
open(OUT, "w").write(tpl)
print(f"dashboard: {len(rows)} openings, {len(inbox)} inbox -> {OUT}")
