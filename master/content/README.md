# Content library (`items.tex`) — OPTIONAL pattern

This is **not wired into `master/cv.tex` by default.** For a starter kit with one
master CV, a monolithic `cv.tex` is simpler and that's what you get out of the box.
Adopt this pattern once you've accumulated several tailored `cv.tex` files that
increasingly diverge and you're tired of hand-syncing a wording fix across all of
them — that's the point where "one bullet, defined once" starts paying for itself.

## What it is

Every reusable CV bullet/skill line is defined **once**, in `items.tex`, and
referenced by id from every `cv.tex` that wants it. Fix a line here and every CV
that references it picks up the fix on its next `xelatex` build.

## Macros

```latex
\defitem{id}{\item ...body...}   % define an item (body starts with \item)
\I{id}                            % emit one item
\IL{id1,id2,id3}                  % emit several, in order (NO spaces in the list)
```

A tailored `cv.tex` inputs the library once, before `\begin{document}`:

```latex
\input{../../../master/content/items.tex}
```
(adjust the relative path to wherever your `cv.tex` actually lives — see the two
worked examples below.)

…then every `itemize` block becomes a manifest, e.g.

```latex
\begin{itemize}
\IL{skill.example.core,skill.example.tools,skill.example.leadership}
\end{itemize}
```

## ids

Dotted namespaces so they read as a rough hierarchy and could later lift into a
YAML/JSON data model without renaming anything: `skill.*`, `role.<employer>.*`,
`edu.*`, `award.*`, `pub.*`, `talk.*`, …

- **Prefabs** — canonical shared lines.
- **Variants** — a re-emphasis of a prefab for one role family, suffixed
  (e.g. `role.acme.infra` vs `role.acme.infra.platform`) so a near-duplicate
  wording doesn't fork silently.

## The one thing that stays inline

The **intro paragraph** in the profile/grey box is tailored per posting and stays
inline in each `cv.tex` — it's prose, not a bullet, and per the CV-tailoring rule
in `AI_README.md` it must never introduce a fact that isn't already in
`tracking/Profile.md`. Everything else — every `itemize` bullet — is a candidate
for the library.

## Adopting it: migrating an existing `cv.tex`

For each bullet, match it to the library:

1. **Verbatim match** → reference the id (zero content change).
2. **Near-duplicate of a prefab** (cosmetic: reorder, synonym, ± a trailing
   detail) → reference the prefab and let the small wording change ride. This is
   a deliberate normalization onto the canonical line.
3. **Genuinely different** (different facts/metrics, or a distinct framing) →
   add a new variant `\defitem` and reference it.

Then rebuild and confirm the CV still fits its fixed page count; if a collapse in
step 2 overflows, promote the collapsed line back to its own variant.

## Reviewing the library

`build_review.sh` renders every defined item, labelled with its id, into one PDF
(`master/content/review.pdf`, git-ignored) — useful for proofreading the whole
library at a glance instead of hunting through `cv.tex` files.

```bash
bash build_review.sh
```

## What's in `items.tex` here

Just 2-3 placeholder items demonstrating the macro pattern — **not real content.**
Replace them with your own bullets (or delete the file and skip this pattern
entirely) when you decide whether to adopt it.
