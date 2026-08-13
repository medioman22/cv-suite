"""Big-tech career-site sources — direct company APIs (no public ATS).

Returns the same normalized dict shape as sources.py so crawler.py can score,
dedupe, and rank them with the Swiss-first location tiering. Big-tech is mostly
US-heavy, so most roles land below threshold unless they're a strong keyword
match or in a Swiss/EU office (Google/Meta/Apple/MS/NVIDIA/Amazon all have Zurich).

Confirmed working 2026-07-14: Amazon, NVIDIA (Workday), Netflix (Eightfold), Snap.
Meta/Google/Apple/Microsoft block direct API access → covered via Adzuna + the
LinkedIn email pipeline instead.
"""
import json, urllib.request, urllib.parse, time

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
       "Accept": "application/json"}


def _get(url, data=None, timeout=20):
    req = urllib.request.Request(
        url, data=(json.dumps(data).encode() if data is not None else None), headers=_UA)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore"))


def _norm(jid, title, company, location, url, desc="", remote=False, source="bigtech"):
    return {"id": f"{source}:{jid}", "title": title or "", "company": company,
            "location": location or "", "url": url, "description": desc or "",
            "source": source, "remote": bool(remote)}


# ── Amazon — amazon.jobs public search JSON ────────────────────────────────
def amazon(queries, loc="", limit=20):
    out = []
    for q in queries:
        qs = urllib.parse.urlencode({"base_query": q, "loc_query": loc,
                                     "result_limit": limit, "sort": "relevant"})
        try:
            j = _get(f"https://www.amazon.jobs/en/search.json?{qs}")
        except Exception as e:
            print("  [amazon]", e); continue
        for x in j.get("jobs", []):
            if x.get("is_intern"):
                continue
            out.append(_norm(x.get("id_icims") or x.get("id"), x.get("title"), "Amazon",
                             x.get("normalized_location") or x.get("location"),
                             "https://www.amazon.jobs" + (x.get("job_path") or ""),
                             x.get("description_short") or x.get("basic_qualifications", ""),
                             source="amazon"))
        time.sleep(0.5)
    return out


# ── Generic Workday (NVIDIA + any other Workday tenant) ────────────────────
def workday(companies, queries, limit=20):
    """companies: list of {label, host, tenant, site}. host e.g. 'nvidia.wd5'."""
    out = []
    for c in companies:
        base = f"https://{c['host']}.myworkdayjobs.com"
        api = f"{base}/wday/cxs/{c['tenant']}/{c['site']}/jobs"
        for q in queries:
            try:
                j = _get(api, {"limit": limit, "offset": 0, "searchText": q, "appliedFacets": {}})
            except Exception as e:
                print(f"  [workday {c['label']}]", e); break
            for x in j.get("jobPostings", []):
                path = x.get("externalPath", "")
                jid = (x.get("bulletFields") or [path])[0]
                out.append(_norm(jid, x.get("title"), c["label"], x.get("locationsText"),
                                 f"{base}/en-US/{c['site']}{path}", "", source=c["label"].lower()))
            time.sleep(0.5)
    return out


# ── Netflix — Eightfold ATS ────────────────────────────────────────────────
def netflix(queries, limit=20):
    out = []
    for q in queries:
        qs = urllib.parse.urlencode({"domain": "netflix.com", "query": q,
                                     "start": 0, "num": limit})
        try:
            j = _get(f"https://explore.jobs.netflix.net/api/apply/v2/jobs?{qs}")
        except Exception as e:
            print("  [netflix]", e); continue
        for x in j.get("positions", []):
            loc = x.get("location") or (x.get("locations") or [""])[0]
            out.append(_norm(x.get("id") or x.get("display_job_id"), x.get("name"), "Netflix",
                             loc, x.get("canonicalPositionUrl") or x.get("job_url") or "",
                             x.get("job_description", ""),
                             remote="remote" in str(x.get("location_flexibility", "")).lower(),
                             source="netflix"))
        time.sleep(0.5)
    return out


# ── Snap — careers.snap.com public jobs API (returns all; filter by title) ──
def snap(queries):
    try:
        j = _get("https://careers.snap.com/api/jobs")
    except Exception as e:
        print("  [snap]", e); return []
    ql = [q.lower() for q in queries]
    out = []
    for row in j.get("body", []):
        s = row.get("_source", {})
        title = s.get("title", "")
        if not any(q in title.lower() for q in ql):
            continue
        loc = s.get("primary_location") or ", ".join(s.get("offices", []) or [])
        out.append(_norm(s.get("id") or row.get("_id"), title, "Snap", loc,
                         s.get("absolute_url", ""), s.get("role", ""), source="snap"))
    return out
