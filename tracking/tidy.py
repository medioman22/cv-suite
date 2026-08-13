#!/usr/bin/env python3
"""Tidy the job tracker — Markdown stays the source of truth.

  python3 tracking/tidy.py            # sort + validate + export jobs.csv
  python3 tracking/tidy.py --check    # validate only, non-zero exit on problems

What it does, all NON-destructively (numbers are stable IDs, never renumbered):
  1. JOBS.md  — reorders the table rows in place: the '—' (no-number, early
                applied) rows keep their original order at the top, then every
                numbered row ascending by #. Everything outside the table body
                (title, legends, Source URLs, prose lines) is untouched.
  2. Validates every data row has exactly 8 columns and a resolvable link; prints
     a report. Duplicated #s are flagged.
  3. Exports tracking/jobs.csv (proper quoting) for spreadsheet/analysis use.
  4. INBOX.md — sorts each loose block of bare '/jobs/view/<id>/' URLs numerically.

Run this occasionally (or wire it into pipeline/daily_run.sh) once JOBS.md has
grown past the point where you can eyeball whether it's internally consistent.
"""
import csv, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.path.join(HERE, "JOBS.md")
INBOX = os.path.join(HERE, "INBOX.md")
CSVOUT = os.path.join(HERE, "jobs.csv")

SEP = re.compile(r"^\|[-\s|]+\|\s*$")          # |---|---|... separator
HEADER = re.compile(r"^\|\s*#\s*\|")            # | # | Company | ...
DATAROW = re.compile(r"^\|")


def _num_key(cell):
    """Sort key for the # column: '—'/no-int -> pin first; else first integer."""
    m = re.search(r"\d+", cell)
    return (1, int(m.group())) if m else (0, 0)


def tidy_jobs(check=False):
    lines = open(JOBS, encoding="utf-8").read().splitlines()
    # locate the ONE data table: header row, then its rows until a non-table line.
    hi = next((i for i, l in enumerate(lines) if HEADER.match(l)), None)
    if hi is None:
        print("! no table header found"); return 1
    # collect indices of data rows (contiguous run of '|' lines after the separator,
    # skipping the separator itself). Stop at the first line that isn't a table row.
    body_idx = []
    i = hi + 1
    while i < len(lines):
        l = lines[i]
        if SEP.match(l):
            i += 1; continue
        if DATAROW.match(l):
            body_idx.append(i); i += 1; continue
        break
    rows = [lines[j] for j in body_idx]
    parsed = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]

    # #s that have a posting URL in the '## Source URLs' section.
    src_txt = "\n".join(lines[next((i for i, l in enumerate(lines)
                                    if l.startswith("## Source URLs")), len(lines)):])
    # every explicit '#N' reference (URL digits have no '#', so they're ignored)…
    src_nums = {int(x) for x in re.findall(r"#(\d+)", src_txt)}
    # …plus explicit '#A-B' / '#A-#B' ranges, with a sanity cap so a stray hyphen
    # (e.g. in 'job-boards.greenhouse.io') can never blow up into a giant range.
    for a, b in re.findall(r"#(\d+)\s*-\s*#?(\d+)", src_txt):
        a, b = int(a), int(b)
        if 0 < b - a < 500:
            src_nums.update(range(a, b + 1))

    problems, nolink, seen = [], [], {}
    for r, cells in zip(rows, parsed):
        if len(cells) != 8:
            problems.append(f"  {len(cells)} cols (want 8): {r[:80]}")
            continue
        num = cells[0]
        m = re.search(r"\d+", num)
        if m:
            key = int(m.group())
            if key in seen and seen[key] != cells[1]:
                problems.append(f"  #{key} reused: {seen[key]} vs {cells[1]}")
            seen[key] = cells[1]
        has_src = bool(m) and int(m.group()) in src_nums
        if "http" not in r and "`applications/" not in r and not has_src:
            nolink.append(num)

    # stable sort: '—' rows first in original order, then numbered ascending
    order = sorted(range(len(rows)), key=lambda k: (_num_key(parsed[k][0]), k))
    for slot, k in zip(body_idx, order):
        lines[slot] = rows[k]

    if problems:
        print(f"⚠ {len(problems)} STRUCTURAL issue(s) — fix these:")
        print("\n".join(problems))
    else:
        print(f"✓ {len(rows)} rows, all 8 cols, no #-collisions")
    if nolink:
        print(f"ℹ {len(nolink)} row(s) use Google-search fallback (no stored posting URL): "
              + ", ".join(f"#{n}" for n in nolink))
    if check:
        return 1 if problems else 0

    open(JOBS, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"✓ JOBS.md table sorted ({len(rows)} rows)")

    # CSV export
    with open(CSVOUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["num", "company", "role", "location", "fit", "status", "folder", "notes"])
        for cells in sorted((c for c in parsed if len(c) == 8),
                            key=lambda c: (_num_key(c[0]),)):
            w.writerow(cells)
    print(f"✓ exported {CSVOUT}")
    return 0


def tidy_inbox():
    """Sort each maximal run of bare '/jobs/view/<id>/' URL lines by numeric id."""
    lines = open(INBOX, encoding="utf-8").read().splitlines()
    url = re.compile(r"/jobs/view/(\d+)")
    out, i, n = [], 0, 0
    while i < len(lines):
        if url.search(lines[i]) and lines[i].lstrip().startswith(("http", "-")):
            j = i
            while j < len(lines) and url.search(lines[j]) and lines[j].lstrip().startswith(("http", "-")):
                j += 1
            block = sorted(lines[i:j], key=lambda l: int(url.search(l).group(1)))
            if block != lines[i:j]:
                n += 1
            out.extend(block); i = j
        else:
            out.append(lines[i]); i += 1
    open(INBOX, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"✓ INBOX.md: {n} URL block(s) re-sorted")


if __name__ == "__main__":
    check = "--check" in sys.argv
    rc = tidy_jobs(check=check)
    if not check:
        tidy_inbox()
    sys.exit(rc)
