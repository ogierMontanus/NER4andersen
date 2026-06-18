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
| `external_authority.py` | **Optional** Wikidata/GND/GeoNames connectors (offline-safe). |
| `distill.py` | Entry point: candidate JSON + evaluation report (one volume). |
| `corpus_eval.py` | Run all 18 volumes → consolidated Markdown report (`eval/`). |
| `export.py` | Curation export: CSV + OpenRefine JSONL + QuickStatements. |
| `register_index.py` | Parse the sub-series **Navneregister** name indexes (`eval/`). |
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

### External authorities (`--external`)

For entities still unlinked after internal reconciliation, `--external` proposes
candidates from public authority APIs and attaches them as `externalCandidates`
in the output (and can emit a TEI register stub via
`external_authority.to_register_stub`):

| Provider | Entity types | Key needed |
| --- | --- | --- |
| **Wikidata** (`wbsearchentities`) | any | none |
| **GND** (lobid.org) | person / org | none |
| **GeoNames** (`searchJSON`) | place | free `GEONAMES_USERNAME` |

It is **opt-in, bounded (`--external-max`, default 25), and offline-safe** —
stdlib `urllib` only, and every call is wrapped so a blocked egress, timeout, or
bad response yields *no* candidates rather than an error (the connector reports
"network blocked … offline-safe"). It needs an environment whose **network
policy permits these hosts** — configure that per
<https://code.claude.com/docs/en/claude-code-on-the-web>. Parsers are split from
fetching and unit-tested with canned JSON, so CI never makes a network call.

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

**All 18 volumes** (`corpus_eval.py`, snapshot in `eval/corpus_report.md`):

- **30,553** comment rows · **24%** named-entity · **1,287** person mentions and
  **926** place mentions linked to the internal registers.
- Person linkage is highest on the travelogues (vol 14 **84%**, vol 15 **78%**)
  where the editorial apparatus is densest; place recall is 1.00 on vol 14 (the
  only volume with injected `geo-*` placeName tags).

```bash
python3 corpus_eval.py --data /path/to/svNames/data --out eval/corpus_report.md
```

### Sub-series name indexes (`register_index.py`)

Each sub-series ends, in its final volume, with a cumulative printed
**Navneregister** (`<head type="major">Navneregister</head>` + `<p>` entries:
*name (dates), description. vol-refs*). This parser extracts them and resolves
each Roman-numeral reference to an **absolute volume**, using the same formula as
svNames' `data/indexExtraction/` XSLT pipeline:

```
absolute_vol = base + roman − 1
```

where `base` is the sub-series' first volume — read from `teiHeader/volumeNumber`
when present (e.g. `<volumeNumber>14` for Rejseskildringer in the extracted index
files), otherwise derived from the edition's volume titles (they agree). Example:
*Abrahamson … III 594; IV 649* (Skuespil, base 10) → **vol 12 p594, vol 13 p649**.

```bash
python3 register_index.py --data /path/to/svNames/data --out eval/navneregister.json
```

Coverage in the current corpus (`eval/navneregister.json`):

| Sub-series | Source vol | Covers vols | Entries |
| --- | ---: | --- | ---: |
| Skuespil | 13 | 10–13 | 695 |
| Rejseskildringer | 15 | 14–15 | 1,073 |
| Selvbiografier | 18 | 16–18 | 1,828 |

**Only `Navneregister` (name) indexes** are parsed; the Eventyr/Digte
"Register" / "Titelregister" are *title* indexes (out of scope). **Romaner**:
the edition's print has a Romaner index, but it is **not yet encoded** in the
working vol-6 file (no `Navneregister` section) — the parser will pick it up
automatically once it is added. The `svnames-index` repo (the canonical
sub-series→volume mapping) was not reachable from this session; the base-volume
formula above reproduces it.

### Curation export (`export.py`)

Turns a `distill.py` candidates JSON into curator-ready formats (spec
Deliverable D / Stage 3):

```bash
python3 distill.py --out out/vol14.json
python3 export.py out/vol14.json --csv out/curation.csv \
    --openrefine out/curation.openrefine.jsonl
```

- **CSV** — one row per mention (ref, page, lemma, entity, internal id, method,
  external candidates, definition); opens in Excel / OpenRefine.
- **OpenRefine** — JSONL of named-entity mentions with `candidates` in the
  reconciliation-result shape (`{id, name, score, match}`): internal matches are
  confirmed (score 100), external proposals unconfirmed for the curator to pick.
- **QuickStatements** — Wikibase-style stubs for mentions with a Wikidata Q-id.

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
