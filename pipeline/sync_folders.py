#!/usr/bin/env python3
"""Keep applications/ folders in sync with what JOBS.md / the dashboard show.

Every tracked row that isn't skip/closed gets its own folder under
applications/<bucket>/ (posting.md + notes.md; the master CV is copied in as a
starting point if one is found near the row's source template). Full bespoke
tailoring + a cover letter only happens later, on explicit request ("inbox"),
replacing the generic cv.tex/PDF in place.

Idempotent: rows that already resolve to a real folder on disk are left alone,
so this is safe to run after every pipeline step (wired into daily_run.sh).

  python3 pipeline/sync_folders.py
"""
import datetime, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ui"))
os.chdir(os.path.join(ROOT, "ui"))   # build_dashboard resolves paths relative to itself either way
import build_dashboard as bd   # noqa: E402  (side effect: rebuilds dashboard.html, harmless/idempotent)

JOBS = os.path.join(ROOT, "tracking", "JOBS.md")
SKIP_STATUSES = {"skip", "closed"}
APPLIED_STATUSES = {"applied", "interviewing", "interview", "rejected", "declined", "offer"}
BUCKET_BY_STARS = {4: "1_strong", 3: "1_strong", 2: "2_moderate", 1: "3_reach", 0: "3_reach"}
TODAY_TAG = datetime.date.today().strftime("%y%m%d")

_STOP = {"a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "at", "with"}


def slug(text, max_words=5, max_len=40):
    words = re.findall(r"[A-Za-z0-9]+", text)
    words = [w for w in words if w.lower() not in _STOP]
    out = "".join(w[:1].upper() + w[1:] for w in words[:max_words])
    return out[:max_len] or "Role"


def company_slug(company):
    words = re.findall(r"[A-Za-z0-9]+", company)
    return "".join(w[:1].upper() + w[1:] for w in words[:2])[:24] or "Company"


def main():
    lines = open(JOBS, encoding="utf-8").read().split("\n")
    # map row num -> line index, for the final JOBS.md rewrite
    row_line = {}
    for i, ln in enumerate(lines):
        if not ln.startswith("|"):
            continue
        cells = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(cells) < 8 or cells[0] in ("#", "") or set(cells[0]) <= set("-") or cells[1] in ("Company", ""):
            continue
        row_line[cells[0]] = i

    created, already, skipped = 0, 0, 0
    used_names = set()
    for r in bd.rows:
        num = r["num"]
        status = r["status"].strip()
        if status in SKIP_STATUSES:
            skipped += 1
            continue
        folder_rel = r["folder"]
        if folder_rel and folder_rel != "—" and os.path.isdir(os.path.join(ROOT, folder_rel)):
            already += 1
            continue

        stars = r["stars"] if r["stars"] in BUCKET_BY_STARS else 0
        core_status = status.strip().lower().split()[0] if status.strip() else ""
        bucket = "0_applied" if core_status in APPLIED_STATUSES else BUCKET_BY_STARS[stars]
        loc = r["loc"] if r["loc"] and r["loc"] != "—" else "XX"
        name = f"{TODAY_TAG}_{loc}_{company_slug(r['company'])}_{slug(r['role'])}"
        base_name, n = name, 2
        while name in used_names or os.path.isdir(os.path.join(ROOT, "applications", bucket, name)):
            name = f"{base_name}_{n}"; n += 1
        used_names.add(name)
        dest = os.path.join(ROOT, "applications", bucket, name)
        os.makedirs(dest, exist_ok=True)

        cv = r.get("cv") or {}
        src_folder = cv.get("folder")
        candidate_name = "Candidate"
        if os.path.exists(os.path.join(ROOT, "candidate.env")):
            for ln in open(os.path.join(ROOT, "candidate.env"), encoding="utf-8"):
                m = re.match(r'\s*CANDIDATE_NAME\s*=\s*"?([^"\n]+)"?', ln)
                if m:
                    candidate_name = m.group(1).strip()
        if src_folder:
            src = os.path.join(ROOT, src_folder)
            for fn in ("cv.tex", f"{candidate_name} - CV.pdf"):
                sp = os.path.join(src, fn)
                if os.path.exists(sp):
                    shutil.copy2(sp, os.path.join(dest, fn))

        tmpl_note = ""
        if cv.get("kind") == "template":
            tmpl_note = f"Generic CV copied from mapped template `{src_folder}` ({cv.get('template')}). Tailor on request."
        elif cv.get("kind") == "suggested":
            tmpl_note = f"Generic CV copied from the closest-matching template `{src_folder}` ({cv.get('name')}, keyword-inferred, not curated). Tailor on request."

        with open(os.path.join(dest, "posting.md"), "w", encoding="utf-8") as f:
            f.write(f"# {r['company']} — {r['role']}\n\n{r['location']}\n\n{r['url'] or ''}\n")
        with open(os.path.join(dest, "notes.md"), "w", encoding="utf-8") as f:
            f.write(f"# {r['company']} — {r['role']} ({r['location']})\n\n"
                     f"JOBS.md #{num}. Fit: {'★'*stars if stars else r.get('tier','')}.\n\n"
                     f"{r['notes']}\n\n{tmpl_note}\n")

        i = row_line.get(num)
        if i is not None:
            cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
            cells = cells[1:] if cells and cells[0] == "" else cells
            # re-split properly (leading/trailing pipe already stripped by .strip("|"))
            cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
            cells[6] = f"`applications/{bucket}/{name}`"
            lines[i] = "| " + " | ".join(cells) + " |"
        created += 1

    with open(JOBS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"sync_folders: created {created}, already synced {already}, skipped (skip/closed) {skipped}")


if __name__ == "__main__":
    main()
