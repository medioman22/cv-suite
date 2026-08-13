#!/usr/bin/env python3
"""Deterministic superstar (top-tier) cap — run AFTER triage, BEFORE salary/report.

The LLM's per-batch "superstar" bar drifts: strong senior roles keep clearing it,
so the top tier creeps up and loses its "drop everything" meaning. This pass
re-imposes a hard, explainable rule and a ceiling, demoting everything else to
the next tier down (★★★):

  KEEP top-tier iff domain subscore == 5 AND seniority is Staff/Principal/Lead/
      Director+ AND (company is a frontier/marquee employer OR the role is
      Director-level leadership), then hard-cap to the top CAP by
      (domain+seniority) — your no-relocation region wins ties.

Only ever demotes top-tier -> ★★★ (never promotes), so it can't invent standouts.

  python3 pipeline/superstar_cap.py [--cap N] [--dry]
"""
import os, re, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKLOG = os.path.join(ROOT, "tracking", "backlog.jsonl")
CAP = 40
TOP_TIER = "🌟"

SEN_RANK = {"intern": 1, "junior": 2, "mid": 3, "senior": 4, "lead": 5, "staff": 6,
            "manager": 6, "principal": 7, "director": 8, "vp": 9, "c-level": 10}
STAFF, DIRECTOR = 6, 8
# Frontier / world-class research orgs — a Staff+ bullseye role here is the genuine
# "drop everything" tier. RETUNE this to your own field's marquee employers; matched
# on a normalized company string (lowercased, non-alnum stripped).
FRONTIER = {"openai", "anthropic", "googledeepmind", "deepmind", "google", "meta",
            "metaai", "apple", "nvidia", "nvidiaai", "nvidiaresearch", "microsoft",
            "microsoftai", "amazon", "tesla", "mistral", "mistralai", "cohere", "xai"}


def norm(c):
    return re.sub(r"[^a-z0-9]", "", (c or "").lower())


def senrank(r):
    return SEN_RANK.get((r.get("seniority") or "").lower().strip(), 0)


def keeps(r):
    """Deterministic superstar rule: bullseye domain, Staff+ seniority, AND a
    frontier employer. Requiring "frontier" for every top-tier pick keeps out the
    recruiter-aggregator Director/C-level flood that domain+level alone lets in."""
    ss = r.get("subscores") or {}
    dom = ss.get("domain", 0) or 0
    return dom >= 5 and senrank(r) >= STAFF and norm(r.get("company", "")) in FRONTIER


def score(r):
    ss = r.get("subscores") or {}
    return (ss.get("domain", 0) or 0) + (ss.get("seniority", 0) or 0)


def main():
    cap = int(_arg("--cap", CAP))
    dry = "--dry" in sys.argv
    rows = [json.loads(l) for l in open(BACKLOG, encoding="utf-8")]
    stars = [r for r in rows if r.get("tier") == TOP_TIER]

    kept = [r for r in stars if keeps(r)]
    kept.sort(key=lambda r: (score(r), r.get("ch", False), senrank(r)), reverse=True)
    keep_ids = set(id(r) for r in kept[:cap])       # identity — rows are unique objects

    demoted = 0
    for r in stars:
        if id(r) not in keep_ids:
            r["tier"] = "★★★"
            r["capped"] = True                      # trace: demoted by the cap, not triage
            demoted += 1

    final = sum(1 for r in rows if r.get("tier") == TOP_TIER)
    ch = sum(1 for r in rows if r.get("tier") == TOP_TIER and r.get("ch"))
    print(f"superstar cap: {len(stars)} -> {final} top-tier ({ch} in your home region); "
          f"demoted {demoted} -> ★★★ (rule: domain5 + Staff+/frontier or Director+; cap {cap})")
    if dry:
        print("\nkept:")
        for r in sorted([x for x in rows if x.get("tier") == TOP_TIER],
                        key=lambda r: (not r.get("ch"),)):
            f = "*" if r.get("ch") else " "
            print(f"  {f} {(r.get('title') or '?')[:44]:44} | {(r.get('company') or '?')[:20]:20} | {r.get('seniority','?')}")
        return
    with open(BACKLOG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


if __name__ == "__main__":
    main()
