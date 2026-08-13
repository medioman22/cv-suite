"""
Job sources. Each function returns a list of normalized dicts:
    {id, title, company, location, url, description, source, remote}
All failures are caught and logged so one dead source never kills a run.
Standard library only.
"""
from __future__ import annotations
import json, re, html, time, os
import urllib.request, urllib.parse, urllib.error

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def _get(url: str, headers: dict | None = None, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json, text/html",
                                               **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _json(url: str, headers: dict | None = None):
    return json.loads(_get(url, headers))


def _clean(t: str | None) -> str:
    t = re.sub(r"<[^>]+>", " ", t or "")
    return html.unescape(re.sub(r"\s+", " ", t)).strip()


# ── Keyless aggregators ────────────────────────────────────────────────────
def arbeitnow():
    out = []
    try:
        for j in _json("https://www.arbeitnow.com/api/job-board-api").get("data", []):
            out.append(dict(id="arbeitnow:" + str(j.get("slug", "")), title=j.get("title", ""),
                            company=j.get("company_name", ""), location=j.get("location", ""),
                            url=j.get("url", ""), description=_clean(j.get("description", "")),
                            source="arbeitnow", remote=bool(j.get("remote"))))
    except Exception as e:
        print("  [arbeitnow] error:", e)
    return out


def remotive(queries):
    out = []
    for q in queries:
        try:
            data = _json("https://remotive.com/api/remote-jobs?search=" + urllib.parse.quote(q))
            for j in data.get("jobs", []):
                out.append(dict(id="remotive:" + str(j.get("id")), title=j.get("title", ""),
                                company=j.get("company_name", ""),
                                location=j.get("candidate_required_location", "Remote"),
                                url=j.get("url", ""), description=_clean(j.get("description", "")),
                                source="remotive", remote=True))
        except Exception as e:
            print(f"  [remotive:{q}] error:", e)
    return out


def remoteok():
    out = []
    try:
        for j in _json("https://remoteok.com/api"):
            if not isinstance(j, dict) or "id" not in j:
                continue
            out.append(dict(id="remoteok:" + str(j.get("id")), title=j.get("position", ""),
                            company=j.get("company", ""), location=j.get("location") or "Remote",
                            url=j.get("url", ""), description=_clean(j.get("description", "")),
                            source="remoteok", remote=True))
    except Exception as e:
        print("  [remoteok] error:", e)
    return out


# ── Per-company ATS boards ─────────────────────────────────────────────────
def greenhouse(companies):
    out = []
    for c in companies:
        try:
            data = _json(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs?content=true")
            for j in data.get("jobs", []):
                out.append(dict(id="gh:" + str(j.get("id")), title=j.get("title", ""), company=c,
                                location=(j.get("location") or {}).get("name", ""),
                                url=j.get("absolute_url", ""), description=_clean(j.get("content", "")),
                                source="greenhouse", remote=False))
        except Exception as e:
            print(f"  [greenhouse:{c}] error:", e)
    return out


def lever(companies):
    out = []
    for c in companies:
        try:
            for j in _json(f"https://api.lever.co/v0/postings/{c}?mode=json"):
                out.append(dict(id="lever:" + str(j.get("id")), title=j.get("text", ""), company=c,
                                location=(j.get("categories") or {}).get("location", ""),
                                url=j.get("hostedUrl", ""),
                                description=_clean(j.get("descriptionPlain") or j.get("description", "")),
                                source="lever", remote=False))
        except Exception as e:
            print(f"  [lever:{c}] error:", e)
    return out


def ashby(companies):
    out = []
    for c in companies:
        try:
            data = _json(f"https://api.ashbyhq.com/posting-api/job-board/{c}")
            for j in data.get("jobs", []):
                out.append(dict(id="ashby:" + str(j.get("id")), title=j.get("title", ""), company=c,
                                location=j.get("location", ""), url=j.get("jobUrl", ""),
                                description=_clean(j.get("descriptionPlain", "")),
                                source="ashby", remote=bool(j.get("isRemote"))))
        except Exception as e:
            print(f"  [ashby:{c}] error:", e)
    return out


# ── Adzuna (needs free API key in env) ─────────────────────────────────────
def adzuna(country, queries):
    out = []
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("  [adzuna] set ADZUNA_APP_ID / ADZUNA_APP_KEY in env to enable — skipping")
        return out
    for q in queries:
        try:
            url = (f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id={app_id}"
                   f"&app_key={app_key}&results_per_page=50&what={urllib.parse.quote(q)}"
                   f"&content-type=application/json")
            for j in _json(url).get("results", []):
                out.append(dict(id="adzuna:" + str(j.get("id")), title=j.get("title", ""),
                                company=(j.get("company") or {}).get("display_name", ""),
                                location=(j.get("location") or {}).get("display_name", ""),
                                url=j.get("redirect_url", ""), description=_clean(j.get("description", "")),
                                source="adzuna", remote=False))
        except Exception as e:
            print(f"  [adzuna:{q}] error:", e)
    return out


# ── jobs.ch — largest Swiss board (public JSON search API) ─────────────────
def jobs_ch(queries, pages=1, rows=20):   # jobs.ch caps rows at ~20; paginate with page
    """jobs.ch — Switzerland-wide. Official public search API, one call per query/page."""
    out = []
    base = "https://www.jobs.ch/api/v1/public/search"
    for q in queries:
        for pg in range(1, pages + 1):
            try:
                data = _json(f"{base}?query={urllib.parse.quote(q)}&rows={rows}&page={pg}")
            except Exception as e:
                print(f"  [jobs.ch:{q} p{pg}] error:", e)
                break
            docs = data.get("documents") or []
            if not docs:
                break
            for j in docs:
                links = j.get("_links") or {}
                href = ""
                for key in ("detail_en", "detail_de", "detail_fr", "detail_it"):
                    lk = links.get(key)
                    if isinstance(lk, dict) and lk.get("href"):
                        href = lk["href"]
                        break
                if not href and j.get("job_id"):
                    href = f"https://www.jobs.ch/en/vacancies/detail/{j['job_id']}/"
                out.append(dict(id="jobsch:" + str(j.get("job_id", "")),
                                title=j.get("title", ""), company=j.get("company_name", ""),
                                location=j.get("place") or "Switzerland", url=href,
                                description=_clean(j.get("preview", "")),
                                source="jobs.ch", remote=False))
            if pg >= (data.get("num_pages") or 1):
                break
    return out


# ── LinkedIn guest search — UNOFFICIAL, ToS-violating, opt-in only ─────────
def linkedin_guest(queries, location, max_per_query, delay):
    out = []
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    for q in queries:
        start = 0
        while start < max_per_query:
            try:
                page = _get(f"{base}?keywords={urllib.parse.quote(q)}"
                            f"&location={urllib.parse.quote(location)}&start={start}")
            except Exception as e:
                print(f"  [linkedin:{q}] error (likely rate-limited):", e)
                break
            ids = re.findall(r'urn:li:jobPosting:(\d+)', page) or re.findall(r'/jobs/view/(\d+)', page)
            titles = re.findall(r'<h3[^>]*job-search-card__title[^>]*>(.*?)</h3>', page, re.S) \
                or re.findall(r'<h3[^>]*>(.*?)</h3>', page, re.S)
            comps = re.findall(r'<h4[^>]*>(.*?)</h4>', page, re.S)
            if not ids:
                break
            seen_local = set()
            for i, jid in enumerate(ids):
                if jid in seen_local:
                    continue
                seen_local.add(jid)
                out.append(dict(id="linkedin:" + jid,
                                title=_clean(titles[i]) if i < len(titles) else "",
                                company=_clean(comps[i]) if i < len(comps) else "",
                                location=location, url=f"https://www.linkedin.com/jobs/view/{jid}/",
                                description="", source="linkedin", remote=False))
            start += 25
            time.sleep(delay)
    return out
