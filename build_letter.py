#!/usr/bin/env python3
"""Build a cover-letter PDF from a folder's message_to_hiring_team.md.

  python3 build_letter.py applications/1_strong/260714_CH_Acme_ML_Engineer   # one
  python3 build_letter.py all                                               # every folder with a letter .md

Reads message_to_hiring_team.md, converts it to LaTeX, injects it into
master/letter.tex, and renders "<Your Name> - Cover Letter.pdf" (name from
candidate.env) into the same folder (US-letter, one page, CV letterhead).
Stdlib + xelatex only.
"""
import os, re, sys, subprocess, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
TPL = os.path.join(ROOT, "master", "letter.tex")
SRC = "message_to_hiring_team.md"


def candidate_name():
    env = os.path.join(ROOT, "candidate.env")
    if os.path.exists(env):
        for ln in open(env, encoding="utf-8"):
            m = re.match(r'\s*CANDIDATE_NAME\s*=\s*"?([^"\n]+)"?', ln)
            if m:
                return m.group(1).strip()
    return "Candidate"


OUT = f"{candidate_name()} - Cover Letter.pdf"

_ESC = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _esc(s):
    return "".join(_ESC.get(c, c) for c in s)


def md_to_tex(md):
    """Return (title, body_tex). Title = first '# ' heading; body = the rest,
    blank-line-separated paragraphs, with **bold** honored."""
    lines = md.splitlines()
    title = ""
    body_lines = []
    for ln in lines:
        if not title and ln.startswith("# "):
            title = ln[2:].strip()
            continue
        body_lines.append(ln)
    # split into paragraphs on blank lines
    paras, cur = [], []
    for ln in body_lines:
        if ln.strip():
            cur.append(ln.rstrip())
        elif cur:
            paras.append(" ".join(cur)); cur = []
    if cur:
        paras.append(" ".join(cur))

    def conv(p):
        # protect ** bold ** spans, escape the rest, then re-apply \textbf
        out, i = [], 0
        for m in re.finditer(r"\*\*(.+?)\*\*", p):
            out.append(_esc(p[i:m.start()]))
            out.append(r"\textbf{" + _esc(m.group(1)) + "}")
            i = m.end()
        out.append(_esc(p[i:]))
        return "".join(out)

    body = "\n\n".join(conv(p) for p in paras)
    return _esc(title), body


def build_one(folder):
    md_path = os.path.join(folder, SRC)
    if not os.path.exists(md_path):
        print(f"no {SRC} in {folder}", file=sys.stderr); return False
    title, body = md_to_tex(open(md_path, encoding="utf-8").read())
    tex = open(TPL, encoding="utf-8").read().replace("__TITLE__", title).replace("__BODY__", body)
    with tempfile.TemporaryDirectory() as tmp:
        tf = os.path.join(tmp, "letter.tex")
        open(tf, "w", encoding="utf-8").write(tex)
        r = subprocess.run(["xelatex", "-interaction=nonstopmode", "letter.tex"],
                           cwd=tmp, capture_output=True, text=True)
        pdf = os.path.join(tmp, "letter.pdf")
        if not os.path.exists(pdf):
            print(f"FAIL {folder}\n{r.stdout[-1500:]}", file=sys.stderr); return False
        shutil.copyfile(pdf, os.path.join(folder, OUT))
    pages = "?"
    m = re.search(r"Output written on letter.pdf \((\d+) page", r.stdout)
    if m:
        pages = m.group(1)
    print(f"[{pages}p] {os.path.relpath(folder, ROOT)}/{OUT}")
    return True


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "all":
        for base, _, files in os.walk(os.path.join(ROOT, "applications")):
            if SRC in files:
                build_one(base)
    elif arg:
        build_one(arg.rstrip("/"))
    else:
        sys.exit("usage: build_letter.py <folder>|all")


if __name__ == "__main__":
    main()
