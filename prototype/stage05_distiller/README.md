# Stage 0.5 — Comments-table distiller (prototype)

A transparent, stdlib-only baseline for **plan-v3 §5**: distil the editorial
comments apparatus of any svNames volume into typed authority candidates, split
multi-entity lemmas, reduce non-entity noise, and reconcile place candidates
against the internal `places.xml` register.

It is the **baseline** later context-aware reconciliation must beat — Danish
lexical cues over each row's *lemma* + *definition*, no ML.

## What it does

For each `<row xml:id="txtcmnt-…">` in a `<table rend="textcomments">`
(anywhere in the document — volumes scatter many of these inside
`<div type="work-comments">`):

1. reads `data-term` (**lemma**) + `data-definition` (**explanation**);
2. **classifies + splits** into a list of typed `Entity` objects —
   `place` / `person` / `mythological` (named entities), e.g.
   *Kingos Fødeby* → person **Thomas Kingo** + place **Slangerup**;
3. **reduces noise** — rows with no entity evidence become
   `phrase` / `work` / `gloss` / `other` (not entities);
4. **reconciles** place entities to svNames `places.xml`
   (exact / inflection / token / fuzzy match → `geo-*` ids);
5. emits a candidate record with **provenance** (`txtcmnt-*` id, page, file).

### Robustness to other volumes (important)

Volumes 3, 5, … 18 are **not** simple like volume 14. The parser is built to
cope:

- **Only `textcomments` rows are ingested.** `<table rend="textdeviations">`
  (text-critical variants, `position`/`deviation` cells) and trailing
  **name/title registers** (`Navneregister`, `Titelregister`, TOC rows) are
  excluded — they lack `data-term`/`data-definition`, and register `<div>`s are
  stripped explicitly.
- **Body `placeName`/`persName` are read from running text only** — apparatus
  and register tables are removed first, so comment/register names are never
  mistaken for text occurrences.
- Most volumes (fairy tales, novels, poems) have **no body NER tags at all**;
  the place P/R metric is then reported as N/A, but reconciliation against the
  register still produces linked place candidates.

## Run

```bash
cd prototype/stage05_distiller
python3 distill.py --out out/vol14.json
# any volume + the internal place register:
python3 distill.py "/path/to/svNames/data/Andersen 3 - Eventyr og Historier III_w_notes.xml" \
    --register "/path/to/svNames/data/registers/places.xml"
```

The corpus XML is **not** vendored; supply a local svNames checkout. Defaults
point at the dev sibling checkout under `/home/user/svNames`.

## Files

| File | Role |
| --- | --- |
| `tei_comments.py` | Parse comments rows, body name sets, and the place register. |
| `classify.py` | Rule-based classifier + entity splitting + noise reduction. |
| `reconcile.py` | Inflection-/fuzzy-aware place ↔ `geo-*` reconciliation + LLM candidate shortlisting. |
| `reconcile_llm.py` | **Optional** LLM linking for hard cases (no-op without a key). |
| `distill.py` | Entry point: candidate JSON + evaluation report. |
| `tests/` | Stdlib `unittest` + tiny TEI fixtures (run in CI, no corpus). |

### Optional LLM linking (`--llm`)

The hybrid Stage-2 path (plan-v3 §7): when the rule-based reconciler finds **no**
register match for a place candidate, `--llm` asks Claude to pick the right
`geo-*` id from a cheap candidate shortlist, using the editorial gloss as context.

It is **free and inert by default** — `reconcile_llm.llm_available()` is False
unless both `ANTHROPIC_API_KEY` *and* the `anthropic` SDK are present, so the
distiller, CI, and a plain `--llm` run all stay zero-cost and fall back to the
rule-based result. To actually enable it:

```bash
pip install -r requirements-llm.txt
export ANTHROPIC_API_KEY=sk-ant-...        # a *funded API* account (not a Pro plan)
python3 distill.py --llm
```

Default model is `claude-haiku-4-5` (override with `NER4ANDERSEN_LLM_MODEL`);
the shared instruction is prompt-cached, so a full-corpus run costs cents.

## Results

**Volume 14** (3,109 rows, tagged placeNames):

- ~40% rows classified as named entities (down from 47% before noise reduction).
- Place identification vs. the 285 exact-lemma gold places: **recall 1.00**.
- Reconciliation links **301 / 818** place-candidate rows to `places.xml`,
  promoting **165** descriptive/inflected hard-case places (e.g.
  *Marienlyst → Helsingør*, *Stige → Lumby*). The unreconciled remainder is the
  candidate/noise pool the next stage prunes.
- **Person reconciliation** links **443 / 526** person-candidate rows (84%) to
  `persons.xml` (`gnd-*` / `SV_*` ids), e.g. *Kingos Fødeby → Thomas Kingo*,
  *Kongen → Frederik 6.* This directly attacks the headline gap: only **4 / 1,307**
  `persName` tags in the source vol-14 text carry a `ref`. (The register mixes
  GND authority ids with the `SV_*` printed-index ids — both are accepted.)

**Volume 3** (Eventyr, no body NER tags, has a Navneregister):

- Only **27%** of rows are named entities — heavy gloss/phrase/work noise is
  correctly demoted; **zero** register/TOC rows leak into the candidates.

Run `distill.py` on any volume to reproduce these reports.

## Known limitations / next steps

- Place precision in the *raw* class is low by design; reconciliation is the
  filter. A confidence threshold + register-confirmation should gate what
  reaches curation.
- Splitting occasionally over-generates (a stray capitalised token typed as a
  place) or mis-types legendary kings as `mythological`; orthographic drift
  between inline tags and the register (*Roeskilde* vs *Roskilde*) costs some
  links.
- The `places.xml` register de-duplicates to ~388 name keys / 390 `geo-*` ids;
  a cleaned register and a `persons.xml` reconciler are natural follow-ups, as
  is using the volume **Navneregister** sections as gazetteers.
