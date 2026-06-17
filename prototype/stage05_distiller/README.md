# Stage 0.5 — Comments-table distiller (prototype)

A first, deliberately transparent prototype for **plan-v3 §5**: distil the
editorial comments apparatus of a svNames volume into typed authority
candidates, and validate the place output against the volume's tagged
`placeName`/`geo-*` set.

It is the **baseline** that later, context-aware reconciliation is meant to
beat — pure Danish lexical cues over each row's *lemma* + *definition*, no ML,
stdlib only.

## What it does

For each `<row xml:id="txtcmnt-…">` in
`<div type="comments">/<table rend="textcomments">`:

1. reads the `data-term` (**lemma**) and `data-definition` (**explanation**);
2. **classifies** the row — `place`, `person`, `mythological` (named entities),
   or `phrase`, `gloss`, `other` (not entities);
3. **distils** the actual entity name(s) from descriptive lemmas
   (e.g. *Kingos Fødeby* → person *Thomas Kingo*; *Tycho Brahes Øe* →
   *Tycho Brahe*);
4. emits a candidate record with **provenance** (`txtcmnt-*` id, page, file).

## Run

```bash
cd prototype/stage05_distiller
python3 distill.py --out out/vol14_candidates.json
# or point at any svNames volume:
python3 distill.py "/path/to/svNames/data/Andersen 14 - Rejseskildringer I_w_notes_Rebecca.xml"
```

Requires a local svNames checkout (the corpus XML is **not** vendored here).
The default path is the dev sibling checkout
`/home/user/svNames/data/noHiSeg_Andersen 14 - Rejseskildringer I_w_notes_Rebecca.xml`.

## Files

| File | Role |
| --- | --- |
| `tei_comments.py` | Parse the comments table + the body `placeName`/`persName` sets. |
| `classify.py` | Rule-based classifier + entity distillation. |
| `distill.py` | Entry point: candidates JSON + evaluation report. |

## Current results (volume 14)

3,109 comment rows → ~45% classified as named entities.

| type | count |
| --- | --- |
| gloss | 864 |
| place* | 697 |
| person* | 576 |
| other | 560 |
| phrase | 282 |
| mythological* | 130 |

\* counted as named entities.

**Place identification vs. the 285 tagged-place lemmas (gold = exact lemma
match against a vol-14 `placeName` surface form):**

```
TP=285  FP=412  FN=0   precision=0.41  recall=1.00  F1=0.58
```

Recall is total: every exactly-tagged place is caught. The 412 "false
positives" are the **hard cases** the plan calls out — descriptive/inflected
place lemmas not in the exact surface set (*Marienlyst → slot nord for
Helsingør*, *Stige → landsby i Lumby sogn …*) **plus** genuine
misclassifications (e.g. a few guild/custom rows). Separating those two is the
job of the next stage.

## Honest limitations (next steps)

- **Place precision is low by construction** — the broad place class mixes real
  new places with noise. Stage 2 reconciliation (geo cues, gazetteer, context
  ranking) should promote the true ones and reject the rest.
- Distillation truncates some abbreviated names (*St. Knuds Kloster* → `St`).
- Many descriptive lemmas denote **two** entities (person *and* birthplace);
  only the dominant one is currently emitted.
- The gold set here is *exact-lemma* place matches; a fuller evaluation should
  use fuzzy/inflection-aware matching against all 490 surface forms and the
  `geo-*` register.
