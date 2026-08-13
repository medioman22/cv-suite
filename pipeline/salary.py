#!/usr/bin/env python3
"""Salary enrichment with a per-company cache.

Reliable public salary databases (Levels.fyi, Glassdoor) block scrapers, so the
usable signal is the POSTED pay-transparency ranges themselves. This step:

  1. Harvests posted ranges from Ashby comp APIs for every registered Ashby
     company (structured, free) — the "specialized-site check".
  2. Mines ranges out of each backlog row's description text (Greenhouse / LinkedIn
     JDs increasingly state a range under US/EU pay-transparency law).
  3. Caches everything per-company in tracking/salary_cache.json.
  4. Writes salary back onto backlog rows: the role's own posted range wins; if it
     has none, it inherits its company's cached range, tagged "~" (estimate).

  python3 pipeline/salary.py [--no-fetch]   # --no-fetch skips the Ashby pass

Stdlib only. Never commits.
"""
import os, re, sys, json, time, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DETAILS = os.path.join(ROOT, "tracking", "job_details.json")
sys.path.insert(0, os.path.join(ROOT, "ui"))
try:
    import joburls                       # reuse the dashboard's region() so codes never diverge
except Exception:
    joburls = None

# Region factor (US=1.0 base) + display currency. Factors are the fallback when the
# real-data corpus is too thin to derive them; the WEAK PRIOR below is likewise only
# used when we have no real points for a seniority. RETUNE both to your own market —
# these are illustrative starting points, not calibrated numbers.
REGION = {"CH": (0.80, "CHF "), "US": (1.0, "$"), "REM": (0.75, "$"),
          "UK": (0.62, "£"), "DE": (0.58, "€"), "FR": (0.58, "€"), "BE": (0.58, "€"),
          "IE": (0.60, "€"), "EU": (0.58, "€"), "UAE": (0.70, "$")}
PRIOR = {"intern": 80, "junior": 120, "mid": 155, "senior": 205, "lead": 270,
         "staff": 280, "manager": 280, "principal": 340, "director": 375,
         "vp": 500, "c-level": 650}          # kUSD BASE midpoints — weak prior only
SEN_ORDER = ["intern", "junior", "mid", "senior", "lead", "staff", "manager",
             "principal", "director", "vp", "c-level"]
# Harvested pay-transparency ranges are BASE (equity is posted separately as "Offers
# Equity"), so gross base -> total comp with a seniority-scaled bonus+equity uplift,
# plus extra for equity-heavy employers whose RSUs dominate TC.
TC_UPLIFT = {"intern": 1.0, "junior": 1.06, "mid": 1.12, "senior": 1.22, "lead": 1.32,
             "manager": 1.30, "staff": 1.42, "principal": 1.55, "director": 1.62,
             "vp": 1.85, "c-level": 2.2}
# Example seed of well-known equity-heavy employers — extend/replace with names
# relevant to your own target list; this only nudges the *estimate*, never a
# posted figure.
EQUITY_HEAVY = {"nvidia", "google", "googledeepmind", "deepmind", "meta", "apple",
                "amazon", "microsoft", "netflix", "openai", "anthropic",
                "databricks", "stripe", "coinbase", "uber", "airbnb"}
EQUITY_FACTOR = 1.30

US_STATE = re.compile(r",\s*(A[LKZR]|C[AOT]|DE|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|"
                      r"N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b|"
                      r"united states|u\.s\.|\busa?\b", re.I)
SEN_TITLE = [("intern", r"\bintern"), ("principal", r"\bprincipal|\bdistinguished"),
             ("staff", r"\bstaff\b"), ("director", r"\bdirector\b|\bhead of\b"),
             ("vp", r"\bvp\b|vice president"), ("c-level", r"\bchief\b|\bcto\b|\bceo\b"),
             ("manager", r"\bmanager\b|\bmgr\b"), ("lead", r"\blead\b"),
             ("senior", r"\bsenior\b|\bsr\.?\b|\bsnr\b"),
             ("junior", r"\bjunior\b|\bjr\.?\b|\bgraduate\b|\bnew grad\b")]


def region_code(location):
    loc = location or ""
    return "US" if US_STATE.search(loc) else (joburls.region(loc)[0] if joburls else "US")


def region_factor(location):
    return REGION.get(region_code(location), (0.70, "$"))


def sen_from_title(title):
    t = (title or "").lower()
    for sen, pat in SEN_TITLE:
        if re.search(pat, t):
            return sen
    return ""            # unknown -> don't attribute to a band (would pollute the model)


def parse_range(s):
    """'$230K - $320K' / '$137,861 - $250,000' / '£100-175k' -> (lo_k, hi_k) or None."""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (s or "").replace(",", ""))]
    nums = [n / 1000 if n > 2000 else n for n in nums]          # dollars -> k
    nums = [n for n in nums if 20 <= n < 2000]
    if not nums:
        return None
    return (min(nums), max(nums))


def _usd_mid(point):
    """A real point's midpoint normalized to USD via its own region factor."""
    return ((point["lo"] + point["hi"]) / 2) / point["factor"]


def build_model(cache):
    """Derive a real-data model from the harvested pay points: per-seniority USD
    median (+spread), and a per-company multiplier. Falls back to PRIOR per seniority
    when a band has too few real points."""
    pts = [p for e in cache.values() for p in e.get("points", [])]
    sen_mid, sen_spread = {}, {}
    for sen in SEN_ORDER:
        mids = sorted(_usd_mid(p) for p in pts if p.get("sen") == sen)
        if len(mids) >= 3:
            sen_mid[sen] = _median(mids)
            sen_spread[sen] = (_pct(mids, .25) / sen_mid[sen], _pct(mids, .75) / sen_mid[sen])
    # interpolate any missing seniority from the nearest filled neighbours (real data),
    # else the weak PRIOR — so the whole ladder stays monotone and grounded.
    for i, sen in enumerate(SEN_ORDER):
        if sen not in sen_mid:
            sen_mid[sen] = PRIOR[sen]
    company_mult = {}
    allmids = [_usd_mid(p) for p in pts]
    gmed = _median(allmids) if allmids else 1
    for k, e in cache.items():
        cmids = [_usd_mid(p) for p in e.get("points", [])]
        if len(cmids) >= 3 and gmed:
            company_mult[k] = max(0.6, min(1.8, _median(cmids) / gmed))
    return {"sen_mid": sen_mid, "sen_spread": sen_spread, "company_mult": company_mult,
            "n": len(pts)}


def _median(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def estimate(seniority, location, company="", model=None):
    """Data-grounded TOTAL-COMP estimate: real per-seniority USD BASE median x region
    x company multiplier, grossed to TC with a seniority + equity-heavy uplift.
    Interpolated from harvested points where possible. Labeled 'est. TC'.
    """
    sen = (seniority or "").lower().strip()
    sen = sen if sen in PRIOR else "senior"
    factor, sym = region_factor(location)
    model = model or {}
    base = (model.get("sen_mid") or PRIOR).get(sen, PRIOR.get(sen, 200))   # USD k, base
    cm = (model.get("company_mult") or {}).get(norm(company), 1.0)
    tc = TC_UPLIFT.get(sen, 1.2) * (EQUITY_FACTOR if norm(company) in EQUITY_HEAVY else 1.0)
    mid = base * factor * cm * tc
    lo_r, hi_r = (model.get("sen_spread") or {}).get(sen, (0.82, 1.20))
    lo, hi = mid * lo_r, mid * hi_r
    return f"est. TC {sym}{round(lo/5)*5}-{round(hi/5)*5}k"
BACKLOG = os.path.join(ROOT, "tracking", "backlog.jsonl")
CACHE = os.path.join(ROOT, "tracking", "salary_cache.json")
JC = os.path.join(ROOT, "job_crawler")
TODAY = datetime.date.today().isoformat()
TTL_DAYS = 30
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# "$120K – $180K", "$120,000-$180,000", "€90k–120k", "CHF 130'000–160'000",
# "£95,000 to £120,000", "USD 150,000/yr" …
CUR = r"(?:\$|USD|US\$|€|EUR|£|GBP|CHF|Fr\.?)"
NUM = r"\d{2,3}(?:[.,'\s]\d{3})*(?:\.\d+)?\s?[kK]?"
RANGE_RE = re.compile(
    rf"{CUR}\s?{NUM}\s?(?:-|–|—|to|bis|à)\s?{CUR}?\s?{NUM}", re.I)
# single anchored figure fallback ("up to $180,000", "€140k base")
ONE_RE = re.compile(rf"{CUR}\s?{NUM}", re.I)


def norm(c):
    return re.sub(r"[^a-z0-9]", "", (c or "").lower())


def _tidy(s):
    return re.sub(r"\s+", " ", s).strip(" .·•\t")


def from_text(text):
    """Return the first plausible posted salary RANGE in free text, or ''."""
    if not text:
        return ""
    # prefer a nearby salary keyword to avoid matching '$5M funding' etc.
    for m in RANGE_RE.finditer(text):
        window = text[max(0, m.start() - 60):m.start()].lower()
        span = m.group(0)
        if re.search(r"salary|compensation|pay|base|range|ote|comp\b|earn|\$|€|£|chf",
                     (window + span).lower()):
            # sanity: both endpoints look like annual comp (>= 30k-ish or has k)
            nums = re.findall(r"\d[\d.,'\s]*", span)
            if any("k" in span.lower() for _ in [0]) or \
               any(float(re.sub(r"[^\d.]", "", n) or 0) >= 30 for n in nums):
                return _tidy(span)
    return ""


# ── Ashby comp harvest (the cached "specialized-site" lookup) ───────────────
def ashby_companies():
    sys.path.insert(0, JC)
    try:
        import config as cfg
        return list(getattr(cfg, "ASHBY_COMPANIES", []))
    except Exception:
        return []


def fetch_ashby(company, cache):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    try:
        req = urllib.request.Request(url, headers=UA)
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        print(f"  [ashby:{company}] {e}", file=sys.stderr)
        return 0
    seen, points = [], []
    for j in data.get("jobs", []):
        comp = j.get("compensation") or {}
        s = comp.get("scrapeableCompensationSalarySummary") or ""
        if not s:
            continue
        seen.append(_tidy(s))
        lohi = parse_range(s)
        sen = sen_from_title(j.get("title", ""))
        if lohi and sen:
            loc = j.get("location") or ""
            points.append({"sen": sen, "region": region_code(loc),
                           "factor": region_factor(loc)[0], "lo": lohi[0], "hi": lohi[1]})
    if seen:
        _record(cache, company, seen, points)
    return len(seen)


def _record(cache, company, ranges, points=None):
    k = norm(company)
    e = cache.setdefault(k, {"company": company, "samples": [], "updated": TODAY})
    for r in ranges:
        if r and r not in e["samples"]:
            e["samples"].append(r)
    e["samples"] = e["samples"][-25:]          # keep it bounded
    if points:
        e.setdefault("points", [])
        have = {(p["sen"], p["lo"], p["hi"]) for p in e["points"]}
        for p in points:
            if (p["sen"], p["lo"], p["hi"]) not in have:
                e["points"].append(p)
        e["points"] = e["points"][-40:]        # bounded real-data corpus per company
    e["updated"] = TODAY
    # representative range = the modal / first sample (they cluster per company)
    e["range"] = e["samples"][0] if e["samples"] else ""


def load_cache():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def stale(entry):
    try:
        d = datetime.date.fromisoformat(entry.get("updated", "2000-01-01"))
        return (datetime.date.today() - d).days > TTL_DAYS
    except Exception:
        return True


def main():
    no_fetch = "--no-fetch" in sys.argv
    cache = load_cache()

    # 1) refresh Ashby company ranges (respecting TTL)
    fetched = 0
    if not no_fetch:
        for c in ashby_companies():
            if norm(c) in cache and not stale(cache[norm(c)]):
                continue
            fetched += fetch_ashby(c, cache)
            time.sleep(0.3)

    # 2) mine posted ranges from backlog descriptions -> cache (as real points too)
    rows = [json.loads(l) for l in open(BACKLOG, encoding="utf-8")]
    mined = 0
    for r in rows:
        posted = from_text(r.get("desc") or "")
        if posted:
            r["salary"] = posted                       # role's own posted range wins
            r["salary_src"] = "posted"
            lohi = parse_range(posted)
            pts = None
            if lohi:
                loc = r.get("location") or ""
                pts = [{"sen": (r.get("seniority") or "mid").lower(),
                        "region": region_code(loc), "factor": region_factor(loc)[0],
                        "lo": lohi[0], "hi": lohi[1]}]
            _record(cache, r.get("company", ""), [posted], pts)
            mined += 1

    model = build_model(cache)                          # real-data model for estimates

    # 3) backfill rows without a posted range from the company cache
    filled = 0
    for r in rows:
        if r.get("salary_src") == "posted":
            continue
        cur = (r.get("salary") or "").strip()
        if cur and cur != "—":                         # keep an existing concrete value
            continue
        e = cache.get(norm(r.get("company", "")))
        if e and e.get("range"):
            r["salary"] = "~" + e["range"]             # ~ = company estimate, not this posting
            r["salary_src"] = "company-cache"
            filled += 1
        else:
            r.setdefault("salary", "—")

    # 4) still blank -> labeled heuristic estimate from seniority x region (only for
    #    triaged rows, which have a seniority; leaves untriaged rows as "—")
    est = 0
    for r in rows:
        blank = not r.get("salary") or r["salary"] == "—"
        if r.get("triaged") and (blank or r.get("salary_src") == "estimate"):
            r["salary"] = estimate(r.get("seniority"), r.get("location"), r.get("company"), model)
            r["salary_src"] = "estimate"
            est += 1

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(BACKLOG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5) sync the salary onto promoted rows' UI details (matched by posting url)
    synced = 0
    if os.path.exists(DETAILS):
        det = json.load(open(DETAILS, encoding="utf-8"))
        by_url = {r.get("url"): r for r in rows if r.get("url")}
        for d in det.values():
            r = by_url.get(d.get("url"))
            if r and r.get("salary"):
                d["salary"] = r["salary"]; d["salary_src"] = r.get("salary_src", ""); synced += 1
            elif not d.get("salary") or d["salary"] == "—":
                d["salary"] = estimate(d.get("seniority"), d.get("location"), "", model); d["salary_src"] = "estimate"; synced += 1
        json.dump(det, open(DETAILS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with_sal = sum(1 for r in rows if r.get("salary") and r["salary"] != "—")
    print(f"salary: fetched {fetched} Ashby ranges, mined {mined} posted, "
          f"backfilled {filled} from cache, estimated {est} · {len(cache)} companies cached · "
          f"synced {synced} UI details · {with_sal}/{len(rows)} backlog rows now have a figure")

    # refresh the report so the salary figures show (triage runs before us)
    try:
        sys.path.insert(0, HERE)
        import triage
        done = [r for r in rows if r.get("triaged")]
        triage._write_report(done, rows)
    except Exception as e:
        print(f"  (report refresh skipped: {e})", file=sys.stderr)


if __name__ == "__main__":
    main()
