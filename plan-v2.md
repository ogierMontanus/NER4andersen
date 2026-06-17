# Plan: Flesh out `plan.md` in NER4andersen

## Context

`NER4andersen` is an empty repo (only `.gitattributes`). It is meant to hold the
**named-entity reconciliation & enrichment** workbench for the **svNames** project — a
TEI Publisher / eXist-db edition of Hans Christian Andersen's travel writings
(*Rejseskildringer I & II*). The user supplied an authoritative specification
("Repository Specification: Automated Authority Reconciliation and Entity Enrichment") and
asked to **flesh out `plan.md`**, **drawing in data from svNames, especially the `data`
subfolder**. So the deliverable is a single, well-structured `plan.md` that turns that
spec into an actionable plan *grounded in the concrete svNames data*, not a from-scratch
design and not project code.

### What the spec asks for (summary)
A multi-stage workflow that: (1) harvests contextual info from **editorial notes** and
**local indexes**; (2) **consolidates** it into a local authority layer with **provenance**;
(3) performs **context-aware reconciliation** against external authorities (Wikidata, GND,
VIAF, Library of Congress, GeoNames, gazetteers); (4) supports **human curation**
(OpenRefine etc.); (5) emits reusable authority data + reproducible evaluation reports.
Headline success criterion: contextual info yields **measurably better reconciliation than
label-only matching**.

### How svNames data grounds each stage (verified)
From `/home/user/svNames`:
- **Source texts / editorial notes** (`data/*.xml`): `noHiSeg_Andersen 14 - Rejseskildringer I…`
  (~2.1 MB; **1,307 `<persName>`**, **1,366 `<placeName>`**, **688 `<note>`**) and
  `commentHiSegAndersen_15-Rejseskildringer_II…` (~2.7 MB). Text I holds **553
  `<note type="match">`** elements that already list candidate index entries as
  `<person corresp="#SV_14_NNNN"><persName type="main">…</persName><date>…</date></person>`
  — i.e. the spec's "registry of indexed names" (the `SV_14_*` **printed index**) and the
  editorial-note→index matching are *partially materialized in the data already*. This is
  the primary Source A (local index) + Source B (editorial note) harvesting target.
- **Local authority records** (`data/registers/`): `persons.xml` — **1,053** persons keyed
  by GND (`xml:id="gnd-…"`) with name variants, gender, birth/death + place, `occupation[@ref]`,
  and `note[@type='bio']` (the spec's "Winther, folklorist" style context). `places.xml` —
  **962** places keyed by GeoNames (`xml:id="geo-…"`) with `location/geo`, `country`,
  `region`, feature-code `@type` (e.g. `P.PPL`), and `ptr` to GeoNames + Wikipedia (the
  spec's "Udby, village near Vordingborg" style context). `organizations.xml` and
  `keywords.xml` exist but are **empty** (enrichment targets). `templates/` provides
  `person-default.xml`, `place-default.xml`, and a 76 KB `place-types.xml` GeoNames gazetteer.
- **Existing pipeline integration points** (`modules/`): `nlp-config.xqm` (Python NER API
  endpoint `:8001`; `persName/author → PER`, `placeName/pubPlace → LOC`) and
  `annotation-config.xqm` (uses `@ref` as the reconciliation/reference key; defines
  person/place/organization/term annotation merge-back into TEI).
- **The motivating gap (verified):** placeNames are almost fully linked (`ref="geo-…"`,
  ~1,366/1,366) but **persNames are essentially unlinked — only 4 of 1,307** carry a `ref`.
  Reconciliation/enrichment is precisely what closes this gap.

> Note: the spec also lists CSV / Excel / PowerQuery / XSLT / AWK / lookup-table inputs.
> **None are present** in the current svNames or NER4andersen checkouts — `plan.md` will
> treat "inventory & document existing pipeline artifacts" as Phase 0 and note these as
> expected-but-not-yet-in-repo, to be located/imported.

## Deliverable

One file: **`/home/user/NER4andersen/plan.md`**, committed and pushed to branch
`claude/ner4andersen-plan-svnames-rjqwqn`. No other files; no project code in this task.

## Proposed structure & content of `plan.md`

Written so a collaborator can act without re-reading the spec or svNames. Mirrors the
spec's own ordering, with svNames specifics woven in:

1. **Objective** — Restate the 5 goals; frame NER4andersen as practical research
   infrastructure feeding linked `@ref` annotations + authority data back to svNames.

2. **Relationship to svNames & existing inputs** — Concrete inventory table (paths +
   verified counts above): corpus files, the `SV_14_*` printed-index / `note[@type='match']`
   occurrence lists, the registers, and the integration points (`nlp-config.xqm`,
   `annotation-config.xqm`). Flag the persName linking gap (4/1,307) as the headline target.
   List Phase-0 artifacts-to-locate (CSV/Excel/PowerQuery/XSLT/AWK/lookup tables) as
   not-yet-in-repo.

3. **Conceptual model: two contextual sources** — Source A = local entity index
   (profession, role, nationality, settlement type, geographic affiliation), mapped to
   `persons.xml`/`places.xml` fields and the printed index. Source B = editorial notes,
   mapped to the corpus `<note>`/`note[@type='match']` and register `note[@type='bio']`.
   Use the spec's "Udby = village near Vordingborg" and "Winther = folklorist" examples,
   tied to real `placeName`/`persName` entries.

4. **Stage 1 — Consolidation** — Extract contextual descriptions from notes and indexes,
   compare, merge compatible, flag inconsistencies; emit a **unified authority candidate
   record** (the spec's JSON shape: `label`, `entityType`, `settlementType`, `nearPlace`,
   `sources[]`) with **provenance preserved per statement** (source file + XPath/index id).

5. **Stage 2 — Automated context-aware reconciliation** — Targets: Wikidata, GND, VIAF,
   Library of Congress, GeoNames, national gazetteers, project registries. Candidate
   ranking beyond string match: label/alias similarity, entity-type compatibility,
   geographic + temporal compatibility, contextual similarity. Enriched query shape per
   spec; output confidence scores. Reuse svNames' existing IDs (GND in `persons.xml`,
   GeoNames in `places.xml`, VIAF on `<author>`) as gold/seed crosswalk.

6. **Stage 3 — Human curation** — Reviewable workflows; integrate OpenRefine reconciliation
   API, annotator-style review, TEI-Publisher editorial workflow, lightweight web review.
   Editors inspect/compare/approve/reject candidates, create local records, flag uncertain
   cases. Approved results write back as TEI `@ref` via `annotation-config.xqm`.

7. **Repository deliverables** — (A) **Data model/schema**: labels, aliases, types,
   contextual descriptions, provenance, authority IDs, confidence, editorial decisions.
   (B) **Extraction pipeline**: editorial-note, index, contextual-phrase extraction +
   provenance. (C) **Reconciliation layer**: Wikidata + OpenRefine-compatible + local
   connectors, pluggable for new providers. (D) **Curation layer**: review/approval/export,
   compatible with CSV, Excel, Wikibase-style models, future graph DBs.

8. **Proposed repo layout & stack** — Pluggable Python project (extraction modules,
   reconciliation connectors, curation/export, eval); how it relates to svNames' `:8001`
   NER endpoint and `@ref` write-back contract. Keep "hybrid" recognition (spaCy/rule +
   gazetteer) feeding the linking/reconciliation core, per earlier direction.

9. **Phased roadmap** — Phase 0 inventory & document existing pipeline/artifacts →
   Phase 1 consolidation + provenance → Phase 2 context-aware reconciliation → Phase 3
   curation & write-back → Phase 4 orgs/keywords enrichment & reuse for downstream NER.

10. **Research questions & evaluation** — The spec's five questions (context→accuracy gain;
    most useful features; notes→recall; note/index overlap; best authority for C19 Danish
    cultural entities). Use the `@ref`-linked placeNames + the `SV_14_*` index matches as a
    gold set; produce **reproducible evaluation reports**. Headline metric: reconciliation
    accuracy *with* vs *without* context, and persName linkage rate (baseline 4/1,307).

11. **Success criterion** — Restate: consolidated local authority layer from notes + indexes
    yields measurably better reconciliation than label-only matching.

## Files

- Create: `/home/user/NER4andersen/plan.md` (only new file).
- Read-only grounding (no edits): svNames `data/registers/*.xml`, `data/taxonomy.xml`, the
  two `data/*.xml` corpus files (notes + `SV_14_*` index matches), `data/registers/templates/*`,
  `modules/nlp-config.xqm`, `modules/annotation-config.xqm`.

## Verification

- `plan.md` renders as valid Markdown (headings, inventory table, the JSON examples in
  fenced blocks, ordered lists) and covers every spec section + success criterion.
- Cross-check every cited figure against svNames: 1,053 persons, 962 places, 1,307 persName
  / 1,366 placeName / 688 notes / 553 `note[@type='match']` in Text I, 4 linked persName,
  empty orgs/keywords.
- Confirm referenced paths/identifiers exist and are correct (`SV_14_*` index refs,
  `nlp-config.xqm` endpoint + type map, `annotation-config.xqm` `@ref` key, register IDs
  `gnd-*`/`geo-*`, `<author>` VIAF).
- Commit on `claude/ner4andersen-plan-svnames-rjqwqn` with a descriptive message and
  `git push -u origin claude/ner4andersen-plan-svnames-rjqwqn` (retry w/ backoff on network
  errors). No PR unless requested.