#!/usr/bin/env python3
"""Parse tracking/INBOX.md into the pending-triage queue the dashboard shows.

The inbox holds raw job URLs dropped under source sections (Manual / Crawler /
LinkedIn), added by the crawler, the LinkedIn pipeline, or pasted by hand. They
sit here until Claude runs the "inbox" step and files them into JOBS.md. This
turns those bare URLs into readable {source, company, title, url} rows.

Stdlib only. Shared by build_dashboard.py (static bake) and serve.py (live).
"""
import re, os
from urllib.parse import urlparse

KNOWN_CO = {
    "nvidia": "NVIDIA", "amazon": "Amazon", "ibm": "IBM", "sap": "SAP",
    "openai": "OpenAI", "ai": "", "elevenlabs": "ElevenLabs",
}


def _section(line):
    """Map a '## ...' heading to a short source label, or None."""
    low = line.lower()
    if "manual" in low or "pasted" in low:
        return "Manual"
    if "crawler" in low:
        return "Crawler"
    if "linkedin" in low:
        return "LinkedIn"
    return None


def _pretty_company(c):
    c = re.sub(r"[-_]+", " ", c).strip()
    return KNOWN_CO.get(c.lower(), c[:1].upper() + c[1:] if c else c)


def _pretty_title(seg):
    if not seg:
        return ""
    seg = seg.split("?")[0].split("#")[0]
    seg = re.sub(r"_[A-Za-z]{1,4}\d{3,}.*$", "", seg)   # drop trailing req id (_JR2020173)
    seg = re.sub(r"[-/]?\d{5,}[-/]?", " ", seg)          # drop long numeric ids
    seg = seg.replace("---", " — ").replace("--", " — ").replace("-", " ").replace("_", " ")
    seg = re.sub(r"\s+", " ", seg).strip()
    if seg and seg == seg.lower():                       # only title-case all-lowercase slugs
        seg = seg.title()
    return seg


def _company_title(url):
    p = urlparse(url)
    host = p.netloc.lower()
    parts = [s for s in p.path.split("/") if s]
    company, title = "", (parts[-1] if parts else "")
    if any(h in host for h in ("greenhouse.io", "lever.co", "ashbyhq.com")):
        company = parts[0] if parts else ""
    elif "myworkdayjobs" in host:
        company = host.split(".")[0]
    elif "amazon.jobs" in host:
        company = "Amazon"
    elif "linkedin.com" in host:
        company, title = "LinkedIn posting", ""
    else:
        labels = host.replace("www.", "").split(".")
        company = labels[0] if labels else host
    return _pretty_company(company), _pretty_title(title), host


def parse_inbox(path):
    """Return a list of pending items: {source, company, title, url, host}."""
    if not os.path.exists(path):
        return []
    items, seen, section, in_comment = [], set(), "Manual", False
    for ln in open(path, encoding="utf-8"):
        s = ln.strip()
        if "<!--" in s:
            in_comment = "-->" not in s
            continue
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("## "):
            lbl = _section(s)
            if lbl:
                section = lbl
            continue
        if s.startswith("http"):
            url = s.split()[0]
            if url in seen:
                continue
            seen.add(url)
            co, title, host = _company_title(url)
            items.append({"source": section, "company": co, "title": title,
                          "url": url, "host": host})
    return items


if __name__ == "__main__":
    import json, sys
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "tracking", "INBOX.md")
    print(json.dumps(parse_inbox(p), indent=2, ensure_ascii=False))
