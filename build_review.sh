#!/usr/bin/env bash
# Build a proofreading PDF of the content library (OPTIONAL — see
# master/content/README.md): every item in master/content/items.tex rendered
# exactly as it appears on a CV, labelled with its id, grouped by section.
# Output: master/content/review.pdf (git-ignored, regenerate anytime).
#
#   bash build_review.sh
#
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
CONTENT="$REPO/master/content"
ITEMS="$CONTENT/items.tex"
# master/cv.tex supplies the shared preamble (fonts/colors/macros) so items
# render exactly as they will on a real CV.
SRC="$REPO/master/cv.tex"

python3 - "$SRC" "$ITEMS" "$CONTENT/review.tex" <<'PY'
import re, sys
SRC, ITEMS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

pre = []
for ln in open(SRC):
    if ln.startswith(r"\begin{document}"):
        break
    if "items.tex" in ln or ln.startswith("% ── CONTENT LIBRARY") or "graphicspath" in ln:
        continue
    pre.append(ln.rstrip("\n"))
preamble = "\n".join(pre)

nitems = sum(1 for l in open(ITEMS) if l.lstrip().startswith(r"\defitem"))

body = []
for ln in open(ITEMS):
    s = ln.rstrip("\n")
    m = re.match(r"\\defitem\{([^}]+)\}", s)
    if m:
        body.append(r"\showitem{%s}" % m.group(1)); continue
    c = re.match(r"^%\s*[─═]{2,}\s*(.*?)\s*[─═]{2,}\s*$", s)
    if c and c.group(1):
        body.append(r"\reviewhead{%s}" % c.group(1).replace("&", r"\&")); continue

doc = preamble + r"""
\graphicspath{{../../assets/}}
\newcommand{\reviewhead}[1]{\vspace{7pt}{\color{ruleline}\avenirdemibold\fontsize{12}{14}\selectfont #1}\par\vspace{3pt}}
\newcommand{\showitem}[1]{\noindent{\ttfamily\scriptsize\color{linkcolor}#1}\begin{itemize}[leftmargin=1.6em,itemsep=0pt,topsep=0pt,parsep=0pt]\I{#1}\end{itemize}\vspace{1pt}}
\setlength{\parindent}{0pt}
\input{items.tex}
\begin{document}
{\avenirdemibold\fontsize{16}{18}\selectfont Content library review \textemdash\ items.tex}\par
{\color{dategrey}\small Each entry: id (blue) then the rendered bullet. """ + str(nitems) + r""" items.}\\[8pt]
""" + "\n".join(body) + "\n\\end{document}\n"

open(OUT, "w").write(doc)
print(f"wrote {OUT} ({nitems} items)")
PY

( cd "$CONTENT" && xelatex -interaction=nonstopmode review.tex >review_build.log 2>&1 )
grep -o "Output written on review.pdf ([0-9]* pages)" "$CONTENT/review_build.log" \
  && echo "-> $CONTENT/review.pdf"
