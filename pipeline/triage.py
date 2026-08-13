#!/usr/bin/env python3
"""Triage untriaged backlog.jsonl rows with a cheap LLM and write
tracking/DAILY_REPORT.md — a short "what's new + top picks" digest.

  python3 pipeline/triage.py [--cap N] [--model gemini-2.5-flash]

Reads GEMINI_API_KEY from job_crawler/.env (git-ignored). Stdlib only (urllib).
Marks each row triaged with a tier (top/★★★/★★/★/skip) + one-line reason; rows in
your home region (CH tag, retune to your own) go first so the no-relocation picks
are always scored. Never commits — review tracking/DAILY_REPORT.md yourself.

The prompt below is a TEMPLATE: it pulls your name from candidate.env and your
domain summary from the top of tracking/Profile.md, but you should read through
PROMPT once and adjust the rating rubric (what counts as bullseye vs adjacent,
what a "superstar" role looks like) to your own field — it's tuned generically
and will drift if left as-is.
"""
import os, re, sys, json, time, urllib.request, urllib.error, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKLOG = os.path.join(ROOT, "tracking", "backlog.jsonl")
REPORT = os.path.join(ROOT, "tracking", "DAILY_REPORT.md")
ENV = os.path.join(ROOT, "job_crawler", ".env")
CANDIDATE_ENV = os.path.join(ROOT, "candidate.env")
PROFILE_MD = os.path.join(ROOT, "tracking", "Profile.md")
TODAY = datetime.date.today().isoformat()

CAP = 120
MODEL = "gemini-2.5-flash"
CHUNK = 20


def load_env():
    """Populate os.environ from git-ignored job_crawler/.env (quote-tolerant)."""
    if os.path.exists(ENV):
        for ln in open(ENV, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def candidate_name():
    if os.path.exists(CANDIDATE_ENV):
        for ln in open(CANDIDATE_ENV, encoding="utf-8"):
            m = re.match(r'\s*CANDIDATE_NAME\s*=\s*"?([^"\n]+)"?', ln)
            if m:
                return m.group(1).strip()
    return "the candidate"


def profile_blurb():
    """Best-effort one-paragraph summary: the first non-empty paragraph of
    tracking/Profile.md after its title heading. Falls back to a generic stand-in
    if Profile.md hasn't been filled in yet — fill it in, this prompt is only as
    good as that summary."""
    if not os.path.exists(PROFILE_MD):
        return "a candidate — EDIT pipeline/triage.py or fill in tracking/Profile.md"
    lines = open(PROFILE_MD, encoding="utf-8").read().splitlines()
    para = []
    started = False
    for ln in lines:
        if ln.startswith("# "):
            started = True; continue
        if not started:
            continue
        if ln.startswith("#"):
            break
        if ln.strip():
            para.append(ln.strip())
        elif para:
            break
    return " ".join(para)[:500] or "a candidate — fill in tracking/Profile.md"


def build_prompt():
    name, blurb = candidate_name(), profile_blurb()
    return f"""You are triaging job openings for {name}: {blurb}

RATE ON DOMAIN + SENIORITY MATCH ONLY. Location is tracked separately and must NEVER change the tier — do NOT downgrade for relocation and do NOT upgrade for any one region. A strong core-domain role is ★★★ wherever it's located. Mention the city in the reason if useful, but never let it move the stars.

For EACH opening return a JSON object:
{{"id":"<id>",
 "seniority":"Intern|Junior|Mid|Senior|Staff|Principal|Lead|Manager|Director|VP|C-level|Unknown",
 "salary":"pay range IF the description states one (keep currency & period), else \\"—\\"",
 "subscores":{{"domain":0-5,"seniority":0-5}},
 "tier":"🌟|★★★|★★|★|skip",
 "reason":"<=12 words"}}

Subscores (integers 0-5):
- domain: how squarely the ROLE matches the candidate's field (see summary above). 5=bullseye, 3=adjacent, 1=tangential, 0=unrelated.
- seniority: fit of the role's LEVEL to the candidate's target level. 5=Staff/Principal/Director+, 4=Senior, 2=Mid, 0=Junior/Intern.

Tier — BE STRICT. "🌟" (superstar) is VERY RARE — the top ~5%, NOT "a strong senior role in the field" (those are "★★★"):
- "🌟" requires ALL of: domain==5 AND seniority>=4 AND a role squarely in the candidate's STRONGEST niche — AND ON TOP OF THAT a standout signal: a frontier / world-class employer or institute in the field, OR an almost-perfect match to an unusually specific niche, OR a rare senior-leadership post. A plain strong role at an ordinary company is "★★★", NEVER "🌟". CALIBRATION: in a batch of 20 strong roles, typically 0-3 are superstars, often none. When in doubt, it is "★★★".
- "★★★" domain>=4 AND seniority>=4 AND clearly a real role in the field, but not a rare standout.
- "★★"  domain>=3 at senior+, OR strong domain but mid-level, OR senior leadership somewhat off-core.
- "★"   domain 1-2, junior/mid, or large gap.
- "skip" domain 0 / wrong field / pure aggregator, OR no title AND no description (reason "no role info").

RATE ON THE ROLE (title+description), NEVER the company brand or city. Location is tracked separately and never changes the tier. Recruiter-fronted roles: rate the underlying role.

Return ONLY a JSON array, one object per input id.

Openings:
"""


def gemini(key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.load(r)
    txt = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(txt)


def main():
    load_env()
    cap = int(_arg("--cap", CAP))
    model = _arg("--model", os.environ.get("GEMINI_MODEL", MODEL))   # set GEMINI_MODEL in job_crawler/.env to switch
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("no GEMINI_API_KEY (job_crawler/.env) — skipping triage", file=sys.stderr); sys.exit(0)

    rows = [json.loads(l) for l in open(BACKLOG, encoding="utf-8")]
    by_id = {r["id"]: r for r in rows}
    todo = [r for r in rows if not r["triaged"]]
    todo.sort(key=lambda r: (not r["ch"], r["harvested"]))     # home region first, then oldest
    todo = todo[:cap]
    if not todo:
        print("nothing to triage")
        _write_report([], rows); return

    prompt_base = build_prompt()

    def save():                                    # incremental: survives a kill
        with open(BACKLOG, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    done = []
    for i in range(0, len(todo), CHUNK):
        batch = todo[i:i + CHUNK]
        listing = "\n".join(
            f'- id {r["id"]}: title="{r.get("title","")}" company="{r.get("company","")}" '
            f'location="{r.get("location","")}" description="{(r.get("desc") or "")[:450]}"'
            for r in batch)
        try:
            res = gemini(key, model, prompt_base + listing)
        except Exception as e:
            print(f"  chunk {i//CHUNK} failed: {e}", file=sys.stderr); continue
        for item in res:
            r = by_id.get(str(item.get("id")))
            if not r:
                continue
            r["tier"] = item.get("tier", "?"); r["reason"] = item.get("reason", "")
            r["seniority"] = item.get("seniority", ""); r["salary"] = item.get("salary", "—")
            r["subscores"] = item.get("subscores", {})
            r["triaged"] = True; done.append(r)
        save()                                     # persist after every chunk
        time.sleep(0.4)
    print(f"triaged {len(done)} ({sum(r['ch'] for r in done)} home-region); "
          f"{sum(not r['triaged'] for r in rows)} still untriaged")
    _write_report(done, rows)


def _arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _write_report(done, rows):
    order = {"🌟": 0, "★★★": 1, "★★": 2, "★": 3, "skip": 4}
    picks = sorted([r for r in done if r["tier"] in ("🌟", "★★★", "★★")],
                   key=lambda r: (not r["ch"], order.get(r["tier"], 9)))
    ch = [r for r in picks if r["ch"] and r["tier"] != "🌟"]
    other = [r for r in picks if not r["ch"] and r["tier"] != "🌟"]
    remaining = sum(not r["triaged"] for r in rows)

    def line(r):
        title = r.get("title") or "(untitled)"
        ss = r.get("subscores") or {}
        sub = f"dom {ss.get('domain','?')}/sen {ss.get('seniority','?')}"
        sal = r.get("salary") or "—"
        return (f"- {r['tier']} **{title}** — {r['company']} ({r['location']}) · "
                f"{r.get('seniority','?')} · {sal} · fit({sub}) · "
                f"_{r['reason']}_ · [open]({r['url']})")

    stars = [r for r in picks if r["tier"] == "🌟"]
    out = [f"# Daily Job Report — {TODAY}", "",
           f"_Triaged {len(done)} new opening(s) today · "
           f"{len(picks)} worth a look ({len(ch)} home-region) · {len(stars)} superstar · "
           f"{remaining} still queued._", ""]
    if not done:
        out.append("_Nothing new to triage today._")
    if stars:
        out += ["## Superstars — drop everything", ""] + [line(r) for r in stars] + [""]
    if ch:
        out += ["## Home region — no relocation", ""] + [line(r) for r in ch] + [""]
    if other:
        out += ["## Elsewhere", ""] + [line(r) for r in other] + [""]
    if done and not picks:
        out.append("_All of today's new openings triaged as ★ or skip — nothing to surface._")
    skips = sum(1 for r in done if r["tier"] == "skip")
    weak = sum(1 for r in done if r["tier"] == "★")
    out += ["", "---", f"_Filed today: {skips} skip · {weak} weak (not shown). "
            f"Full backlog: tracking/backlog.jsonl._"]
    open(REPORT, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"-> wrote {os.path.relpath(REPORT, ROOT)}")


if __name__ == "__main__":
    main()
