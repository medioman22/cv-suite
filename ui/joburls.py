"""Shared job-URL resolution for the dashboard — used by BOTH build_dashboard.py
and serve.py so they can never diverge again.

resolve() picks, in order:
  1. the posting URL logged in JOBS.md's "## Source URLs" section (keyed by row #),
  2. the posting URL found in the row's application folder (posting.md / notes.md),
  3. a Google-search fallback so every card is still openable.
"""
import os, re
from urllib.parse import quote_plus

_JOB_HOST = re.compile(
    r"(linkedin\.com/jobs|greenhouse\.io|boards\.greenhouse|lever\.co|ashby|"
    r"myworkdayjobs|workday|amazon\.jobs|jobs\.ch|adzuna|smartrecruiters|workable|"
    r"icims|taleo|bamboohr|eightfold|join\.com|/careers|/jobs/|apply\.)", re.I)


def region(loc, folder_code=""):
    """(tag, cssclass) from a location string — shared by build_dashboard.py and
    serve.py so they never diverge. RETUNE the substring lists below to your own
    target regions/hubs; this starter set is CH-first / Europe / US / remote.
    folder_code (LOC tag parsed from the application folder name) is the fallback
    when the location text itself doesn't match anything below."""
    s = loc.lower()
    if "🇨🇭" in loc or any(x in s for x in (
            "switzerland", "zurich", "zürich", "lausanne", "geneva", "genève",
            "basel", "bern", "zug", "vaud")):
        return "CH", "ch"
    if "remote" in s or "anywhere" in s or "🌍" in loc:
        return "REM", "rem"
    if any(x in s for x in ("london", "(uk)", "united kingdom", "england", "scotland", " uk")):
        return "UK", "eu"
    if any(x in s for x in ("munich", "germany", "berlin", "(de)", "hamburg", "🇩🇪")):
        return "DE", "eu"
    if any(x in s for x in ("paris", "france", "(fr)")):
        return "FR", "eu"
    if "brussels" in s or "belgium" in s or "(be)" in s:
        return "BE", "eu"
    if "ireland" in s:
        return "IE", "eu"
    if any(x in s for x in ("(eu)", "emea", "europe", "european", "netherlands", "spain", "austria")):
        return "EU", "eu"
    if any(x in s for x in ("uae", "dubai", "abu dhabi", "🇦🇪")):
        return "UAE", "far"
    if any(x in s for x in (
            "(us)", "usa", "united states", "new york", " ny", "san francisco", "sf ",
            "seattle", "boston", "sunnyvale", "mountain view", "palo alto", "santa clara",
            "san jose", "redmond", "bay area", "(ca)")):
        return "US", "us"
    if re.search(r"\bu\.?k\.?\b", s):          # bare "UK"
        return "UK", "eu"
    if re.search(r"\bu\.?s\.?a?\b", s):         # bare "US" / "USA"
        return "US", "us"
    if folder_code:
        code = folder_code.upper()
        cls = ("ch" if code == "CH" else "us" if code in ("US", "USA")
               else "rem" if code in ("REM", "REMOTE") else "far" if code == "AE"
               else "eu" if code in ("EU", "UK", "DE", "FR", "IE", "BE") else "other")
        return code, cls
    return "—", "other"


def first_url(seg):
    m = re.search(r"https?://\S+", seg)
    if m:
        return m.group(0).rstrip(".,);\"'>")
    m = re.search(r"/jobs/view/(\d+)", seg)
    return f"https://www.linkedin.com/jobs/view/{m.group(1)}/" if m else ""


def _row_url(ln):
    """First posting URL in a table row, preferring a real job-host link."""
    urls = [u.rstrip(".,);\"'>") for u in re.findall(r"https?://[^\s)>\]]+", ln)]
    job = next((u for u in urls if _JOB_HOST.search(u)), "")
    if job:
        return job
    m = re.search(r"/jobs/view/(\d+)", ln)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    m = re.search(r"`(\d{8,})`", ln)          # LinkedIn id stashed in backticks
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    return urls[0] if urls else ""


def build_number_url_map(text):
    """opening # -> apply URL. Primary source: the inline link in each table row
    (| # | ... ([LinkedIn](url)) ...). The optional '## Source URLs' section
    overrides, for rows whose posting link isn't inline."""
    urlmap = {}
    # 1) inline row links — the URLs pasted straight into JOBS.md rows.
    for ln in text.splitlines():
        if not ln.startswith("|"):
            continue
        cells = ln.split("|")
        if len(cells) < 3 or not cells[1].strip().isdigit():
            continue
        u = _row_url(ln)
        if u:
            urlmap[int(cells[1].strip())] = u
    # 2) '## Source URLs' section — authoritative, overrides inline.
    m = re.search(r"## Source URLs.*", text, re.S)
    if not m:
        return urlmap
    for ln in m.group(0).splitlines():
        s = ln.strip()
        if not s.startswith("- "):
            continue
        rng = re.match(r"- #(\d+)-(\d+).*?:(.*)", s)
        if rng:
            n = int(rng.group(1)); end = int(rng.group(2))
            for seg in rng.group(3).split("·"):
                u = first_url(seg)
                if u and n <= end:
                    urlmap[n] = u
                n += 1
            continue
        nums = [int(x) for x in re.findall(r"#(\d+)", s)]
        u = first_url(s)
        if u:
            for n in nums:
                urlmap[n] = u
    return urlmap


def build_folder_url_map(root):
    """relpath 'applications/<bucket>/<folder>' -> the posting URL found in posting.md/notes.md."""
    out = {}
    appdir = os.path.join(root, "applications")
    if not os.path.isdir(appdir):
        return out
    for bucket in os.listdir(appdir):
        bpath = os.path.join(appdir, bucket)
        if not os.path.isdir(bpath):
            continue
        for folder in os.listdir(bpath):
            fpath = os.path.join(bpath, folder)
            if not os.path.isdir(fpath):
                continue
            url = ""
            for fn in ("posting.md", "notes.md"):
                p = os.path.join(fpath, fn)
                if not os.path.exists(p):
                    continue
                txt = open(p, encoding="utf-8", errors="ignore").read()
                urls = [u.rstrip(".,);\"'>") for u in re.findall(r"https?://[^\s)>\]]+", txt)]
                job = next((u for u in urls if _JOB_HOST.search(u)), "")
                url = job or (urls[0] if urls else "")
                if url:
                    break
            if url:
                out[f"applications/{bucket}/{folder}"] = url
    return out


def resolve(num, folder, company, role, number_map, folder_map):
    """Return (url, kind) where kind is 'posting' or 'search'."""
    rownums = [int(x) for x in re.findall(r"\d+", num)]
    url = next((number_map[n] for n in rownums if n in number_map), "")
    if not url and folder:
        url = folder_map.get(folder, "")
    if url:
        return url, "posting"
    q = quote_plus(f"{company} {role} job".strip())
    return f"https://www.google.com/search?q={q}", "search"
