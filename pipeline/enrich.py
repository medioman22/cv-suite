#!/usr/bin/env python3
"""Enrich backlog rows with the REAL job title + description before triage.

A LinkedIn saved-search DIGEST only gives company/location/badges — the actual
title is often dropped and the description is never there, so triage would score
on brand alone (e.g. a big-name company -> auto ★★★ for an unrelated role). This
fetches the lightweight LinkedIn guest job-posting endpoint (title, company,
location, description) and writes it back, so triage reads the actual role.

  python3 pipeline/enrich.py [--cap N]

Only enriches rows that don't yet have a description; failures are marked so they
aren't retried forever. Enriched rows are reset to untriaged so triage re-scores
them on the real content. Stdlib only.
"""
import os, re, sys, json, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKLOG = os.path.join(ROOT, "tracking", "backlog.jsonl")
CAP = 80
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def fetch_linkedin(jid):
    req = urllib.request.Request(GUEST.format(jid), headers=UA)
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    t = re.search(r"top-card-layout__title[^>]*>(.*?)<", html, re.S)
    c = (re.search(r"topcard__org-name-link[^>]*>(.*?)<", html, re.S)
         or re.search(r'topcard__flavor(?![^>]*bullet)[^>]*>(.*?)<', html, re.S))
    loc = re.search(r"topcard__flavor--bullet[^>]*>(.*?)<", html, re.S)
    d = re.search(r"show-more-less-html__markup[^>]*>(.*?)</div>", html, re.S)
    return (_clean(t.group(1)) if t else "",
            _clean(c.group(1)) if c else "",
            _clean(loc.group(1)) if loc else "",
            _clean(d.group(1))[:700] if d else "")


def _arg(flag, default):
    return type(default)(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


def main():
    cap = _arg("--cap", CAP)
    rows = [json.loads(l) for l in open(BACKLOG, encoding="utf-8")]
    todo = [r for r in rows
            if r.get("source") == "linkedin-alert" and not r.get("desc") and not r.get("enrich_failed")]
    todo = todo[:cap]
    ok = fail = 0
    for r in todo:
        try:
            title, company, location, desc = fetch_linkedin(r["id"])
            if title or desc:
                if title:
                    r["title"] = title
                if company:
                    r["company"] = company
                if location:
                    r["location"] = location
                r["desc"] = desc or "(no description)"
                r["triaged"] = False; r["tier"] = None; r["reason"] = None  # re-triage on real content
                ok += 1
            else:
                r["enrich_failed"] = True; fail += 1
        except urllib.error.HTTPError as e:
            if e.code == 429:                       # rate-limited: stop, resume next run
                print("  429 — backing off, will resume next run", file=sys.stderr); break
            r["enrich_failed"] = True; fail += 1
        except Exception:
            r["enrich_failed"] = True; fail += 1
        time.sleep(0.5)
    open(BACKLOG, "w", encoding="utf-8").write(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n")
    left = sum(1 for r in rows if r.get("source") == "linkedin-alert"
               and not r.get("desc") and not r.get("enrich_failed"))
    print(f"enriched {ok}, failed {fail}; {left} linkedin rows still un-enriched")


if __name__ == "__main__":
    main()
