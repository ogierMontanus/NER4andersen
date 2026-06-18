# NER4andersen — Plan v3

*Automated Authority Reconciliation and Entity Enrichment for the Andersen corpus.*

This is the third iteration of the project plan. It supersedes `plan-v2.md` after a **major
data expansion in the svNames repository** and a sharper definition of the editorial-comment
material to work from. It keeps the original specification (`plan.md`) as the governing
requirements document; `plan.md` and `plan-v2.md` remain unchanged for reference.

---

## 1. Objective & what's new in v3

NER4andersen extends svNames' named-entity workflow into a multi-stage enrichment pipeline
that:

1. harvests contextual information from **editorial notes** and **local indexes**;
2. **consolidates** it into a local authority layer with full **provenance**;
3. **reconciles** entities against internal and external authorities using *context*, not
   just labels;
4. supports **human validation and curation**;
5. produces **reusable authority data** and **reproducible evaluation reports**.

**What changed since v2 (and why this matters):**

- **Corpus: 2 → 18 volumes.** svNames now holds the whole authorship
  (`commit "volumes 1-13 and 15-18 added"`), not just the travelogues. Scope, roadmap and
  evaluation are re-based on all 18 volumes.
- **The spec's pipeline is no longer hypothetical.** v2 stated that the
  CSV/XSLT/printed-index/occurrence artifacts were "not present." They now exist in
  **`data/indexExtraction/`** as a working XSLT prototype. v3 therefore reframes the mission
  from *"build from scratch"* to **"inventory, document, and generalize the existing
  prototype."**
- **Source B is concrete.** The editorial commentary is a structured
  `div[@type='comments']/table[@rend='textcomments']` apparatus (lemma + editorial
  explanation). v3 makes its **distillation** the first hands-on experiment, tested on
  volume 14's place names.

---

## 2. svNames inventory (updated, verified on `origin/main`)

| Area | Location | Detail |
| --- | --- | --- |
| **Corpus** | `data/Andersen N - … _w_notes*.xml` | **18 volumes** — Eventyr og Historier I–III (1–3), Romaner I–III (4–6), Digte I–II (7–8), Blandinger (9), Skuespil I–IV (10–13), Rejseskildringer I–II (14–15), Selvbiografier I–III (16–18). |
| **Index-extraction** | `data/indexExtraction/` | **10 XSLT** transforms + digitized printed index + ID-assigned registry + inject/test outputs (see §3). |
| **Registry of indexed names** | `data/indexExtraction/SVindex_15_withID.xml` | **1,048** `<person>` entries keyed `xml:id="SV_14_NNNN"` — the IDs referenced by corpus `note[@type="match"]`. |
| **Person register** | `data/registers/persons.xml` | **1,053** persons, keyed by GND (`gnd-*`); name variants, gender, birth/death + place, `occupation[@ref]`, `note[@type='bio']`. |
| **Place register** | `data/registers/places.xml` | **962** places, keyed by GeoNames (`geo-*`); `location/geo`, `country`, `region`, feature-code `@type`, `ptr` → GeoNames/Wikipedia. |
| **Org / keyword registers** | `data/registers/organizations.xml`, `keywords.xml` | Present but **empty** — **out of scope** for this enrichment process (see §11 scope exclusion). |
| **Templates / gazetteer** | `data/registers/templates/` | `person-default.xml`, `place-default.xml`, 76 KB `place-types.xml` GeoNames feature-code gazetteer. |
| **NER integration** | `modules/nlp-config.xqm` | Python NER API endpoint `:8001`; maps `persName/author → PER`, `placeName/pubPlace → LOC`. |
| **Annotation write-back** | `modules/annotation-config.xqm` | Uses `@ref` as the reconciliation/reference key; defines person/place/organization/term merge-back into TEI. |

**The motivating gap:** placeNames are almost fully linked (`ref="geo-…"`), but **persNames
are essentially unlinked** — only **4 of 1,307** in vol 14 carry a `ref`. Closing this gap
corpus-wide is the headline outcome.

**Data-hygiene observations (record; do not silently "fix"):**

- The vol-15 index is ID-prefixed `SV_14_*` (volume mismatch in the IDs).
- `indexExtraction/` holds many near-duplicate experimental outputs (`new/`, `new/new/`,
  `new2/`, `*_sample`, `…Ny`, `…NyNy`).
- The index has been extracted for **persons only** so far (no place index yet).
- Curated registers cover the vol-14/15 work; vols 1–13 and 16–18 are not yet reconciled.

---

## 3. Existing pipeline walkthrough (the baseline we generalize)

`data/indexExtraction/` already implements, in XSLT, much of the spec's Stage 1–2 for
persons:

1. **Digitized printed index** — `persons_SV_15_index.xml` (+ variants): one TEI `<p>` per
   printed-index line, e.g.

   ```
   Abrahams, Nicolai Christian Levin (1798-1870), professor, oversætter.␉I 640
   ```

   = **sort-name + dates + contextual description (occupation/role/nationality) +
   volume/page occurrences**. This is the spec's **Source A** *and* the named-entity
   occurrence list in one.

2. **`SVindex2tp.xsl`** — parses each index paragraph with regexes into TEI `listPerson`
   (`persName`, `date`, contextual `note`). `SVindex2tp_xslt_2-0*.xsl` is a multi-step
   variant; `SVindex_SV2tpFormat.xsl` and `SVindex_filter-duplicates.xsl` normalise/dedupe;
   `SVpersNameMain.xsl` derives the main name form.

3. **`SVindex_xml-idPerson.xsl`** — assigns `xml:id="SV_*"` → **`SVindex_15_withID.xml`**
   (the registry of indexed names, **1,048** persons).

4. **`SVindex_injectPersons.xsl`** — builds a `vol#page → {name, date}` map and **injects /
   links index persons into the running text by page reference**, producing the injected
   text in `testdata/` and the corpus `note[@type="match"]` candidate lists.

**Limitations to overcome:** brittle regex/string parsing; persons-only; vol-15-only;
matching is page-string-based, not context-aware; no place/org/keyword handling; no external
reconciliation; no confidence scoring; no curation loop. NER4andersen generalizes and hardens
this into a robust, language-aware, multi-authority, reviewable system.

---

## 4. Conceptual model: two contextual sources

For many entities, two independent contextual sources exist.

- **Source A — Local entity index** (`data/indexExtraction/`): profession, role, nationality,
  settlement type, geographic affiliation, explanatory labels, plus volume/page occurrences.

  | Entity | Context |
  | --- | --- |
  | Udby | village near Vordingborg |
  | Abrahams, N.C.L. | professor, oversætter (1798-1870) |

- **Source B — Editorial comments table** (`div[@type='comments']/table[@rend='textcomments']`),
  plus register `note[@type='bio']`. Each `<row xml:id="txtcmnt-PPP-NN">` carries a
  `<cell type="data-term">` **lemma** and a `<cell type="data-definition">` **editorial
  explanation**:

  > **Frederiksborg** — slot ved Hillerød i Nordsjælland. Dets ældste del er opført i 1560
  > af Frederik 2. …, men hovedparten er bygget 1600-1620 under Christian 4.

  > **Winther** — collector of Danish folktales.

Both sources frequently describe the same entity; consolidating them yields richer authority
candidates than either alone.

---

## 5. Stage 0.5 — Comments-table distillation (first concrete experiment, vol 14)

The editorial comments table is the most information-dense Source B, and it requires
**distillation** before it can drive reconciliation.

**What the data looks like (vol 14, verified):** 7 `<table rend="textcomments">` blocks,
**3,109** rows of `data-term` (lemma) + `data-definition` (explanation, plain text, no inner
markup), keyed `xml:id="txtcmnt-PPP-NN"`. The `txtcmnt-*` ids appear **only inside the
comments div — never referenced from the body** — so a comment is linked to a text entity by
**lemma + page matching**, not by ID resolution.

**Why "distill further":**

- **Not all lemmas are named entities.** Examples: `»Spute dich, Schwager Kronion!«` (quote),
  `Ak Herre Jemini` (exclamation), `Morpheus` (mythological), `Aurora … Dør` (phrase).
- **Many lemmas reference an entity descriptively rather than name it.** Examples:
  `Kingos Fødeby` ("Kingo's birthplace"), `Tycho Brahes Øe`, `den baggesenske Fødeby`,
  `Værrebro, og Frode`. The real entities must be recovered from lemma **and** definition —
  e.g. *Kingos Fødeby* → person **Kingo** *and* place **Slangerup** (named in the definition).

**The experiment:**

1. Parse the 3,109 vol-14 comment rows.
2. **Classify** each lemma: NE vs non-NE, and type (place / person / org / mythological /
   work / concept).
3. For NE rows, **distill** the actual entity(ies) from lemma + definition.
4. Emit typed authority candidates with provenance (`txtcmnt-*` id + page + source file).
5. **Validate the place output against vol 14's unique placeName set.**

**Ready-made gold/test set (vol 14, verified):** the body has **1,241** `placeName`
occurrences → **370 unique `geo-*` ids** / **493 unique surface forms**; **284 comment
lemmas exactly match a placeName surface form** (the easy baseline). The remaining,
non-exact cases (possessive/descriptive lemmas, inflected Danish forms, multi-entity lemmas)
are the hard cases that prove contextual distillation beats label-only matching.

Deliverable of this stage: a small, reproducible distiller + an evaluation report
(precision/recall of NE classification and of place linking against the `geo-*` set).

---

## 6. Stage 1 — Consolidation

Generalize both `SVindex2tp.xsl`'s note-extraction **and** the Stage-0.5 comments distiller
into robust, language-aware contextual-description extraction across all 18 volumes. Then:

1. extract contextual descriptions from editorial comments (Source B);
2. extract contextual descriptions from the local index (Source A);
3. compare descriptions for the same candidate entity;
4. merge compatible descriptions; flag inconsistencies for review.

Result: a **unified authority candidate record** with per-statement provenance:

```json
{
  "label": "Udby",
  "entityType": "place",
  "settlementType": "village",
  "nearPlace": "Vordingborg",
  "sources": [
    { "type": "printed index",   "ref": "SV_14_0xxx",       "vol": 14, "page": 73 },
    { "type": "editorial note",  "ref": "txtcmnt-073-04",    "vol": 14, "page": 73 }
  ]
}
```

Every extracted statement keeps its origin (file + XPath / `SV_*` id / `txtcmnt-*` id +
vol/page).

---

## 7. Stage 2 — Context-aware reconciliation

Replace page-/string-only matching with ranked, context-aware reconciliation.

- **Internal first:** match consolidated candidates against `persons.xml` / `places.xml`
  (the `gnd-*` / `geo-*` registers) and the `SV_*` registry.
- **External authorities:** Wikidata, GND, VIAF, Library of Congress, GeoNames, national
  gazetteers, project-specific registries. Reuse svNames' existing IDs (`gnd-*`, `geo-*`,
  the `<author>` VIAF id) as a seed crosswalk (GND↔VIAF↔Wikidata, GeoNames↔Wikidata).
- **Ranking signals (not string-only):** label/alias similarity, entity-type compatibility,
  geographic compatibility, temporal compatibility (birth/death, *floruit*), and contextual
  similarity (occupation/role/nationality from the distilled description).

Enriched reconciliation queries, e.g.:

```json
{ "name": "Udby",    "type": "place",  "description": "village", "near": "Vordingborg" }
{ "name": "Winther", "type": "person", "occupation": "folklorist" }
```

Each candidate gets a **confidence score**; the architecture allows new authority providers
to be added later.

---

## 8. Stage 3 — Human curation

Automated reconciliation must always remain reviewable. Editors inspect candidates, compare
competing matches, approve/reject, create local authority records, and flag uncertain cases.

Integration targets: **OpenRefine** reconciliation workflows + reconciliation API,
annotator-style review interfaces, TEI-Publisher editorial workflows, and a lightweight web
review UI. Approved results are written back as TEI `@ref` via the contract in
`annotation-config.xqm`, so they merge cleanly into the svNames edition.

---

## 9. Repository deliverables

**A. Data model / schema** — entity labels, aliases, entity types, contextual descriptions,
provenance, authority identifiers, confidence scores, editorial decisions.

**B. Extraction pipeline** — editorial-comment extraction, index extraction (generalizing
the XSLT logic), contextual-phrase extraction, provenance tracking.

**C. Reconciliation layer** — connectors for Wikidata, OpenRefine-compatible reconciliation
services, and local authority services; pluggable for additional providers.

**D. Curation layer** — review/approval workflows and export. Outputs stay compatible with
CSV, Excel, Wikibase-style authority models, and future graph databases.

---

## 10. Proposed repo layout & stack

A Python project that **wraps and generalizes** the existing XSLT prototype (it can still
invoke Saxon for the legacy transforms during the transition), feeds svNames' `:8001` NER
endpoint, and emits `@ref` write-back. Indicative layout:

```
src/
  extract/        # comments-table distiller, index parser, contextual-phrase extraction
  consolidate/    # source-A/source-B merge + provenance
  reconcile/      # internal + external authority connectors, context-aware ranking
  curate/         # OpenRefine/web review integration, approval + @ref write-back
  model/          # shared schema (entity, statement, provenance, decision)
data/             # symlinked/imported from svNames (read-only inputs)
eval/             # gold sets + reproducible evaluation reports
notebooks/        # exploratory analysis
```

Hybrid recognition (spaCy/rule-based + the index/comment gazetteers) feeds the
linking/reconciliation core.

---

## 11. Phased roadmap (re-scoped to 18 volumes)

- **P0 — Inventory & document** the existing `indexExtraction/` pipeline and corpus.
- **P0.5 — Comments-table distillation PoC** on vol 14, validated against the placeName set
  (§5).
- **P1 — Generalize extraction & consolidation:** robust persons across all volumes; add
  places; unified candidate records with provenance (§6).
- **P2 — Context-aware multi-authority reconciliation** (§7), with confidence scoring.
- **P3 — Curation & write-back** (§8).
- **P4 — Cross-volume coreference, and cleanup** of the duplicate
  `indexExtraction/` intermediates.

> **Scope exclusion — organizations & keywords.** `organizations.xml` and
> `keywords.xml` are **out of scope for the entire present enrichment process**:
> the empty `listOrg` / keyword registers are *not* populated, `orgName` / `term`
> mentions are *not* recognised, linked, or reconciled, and no organization/keyword
> authority work (internal or external) is performed. The pipeline handles persons
> and places only. (Recorded here and in `plan.md`.)

---

## 12. Research questions & evaluation

The spec's five questions, evaluated with reproducible reports:

1. How much does contextual information improve reconciliation accuracy?
2. Which contextual features contribute most to disambiguation?
3. Can editorial-note extraction improve recall in later NER workflows?
4. How closely do editorial notes and local indexes overlap?
5. Which authority systems perform best for nineteenth-century Danish cultural entities?

**Gold sets:** vol-14's `@ref`-linked placeNames (370 `geo-*` ids / 493 surface forms) and
the `SV_*` injected person matches. **Headline metrics:** reconciliation accuracy *with vs
without* context; lemma-distillation precision/recall on the place test set; and the persName
linkage rate (baseline **4 / 1,307** in vol 14), measured corpus-wide as coverage grows.

---

## 13. Success criterion

The project succeeds when it demonstrates that contextual information harvested from editorial
notes and local indexes, consolidated into a local authority layer, achieves **measurably
better reconciliation** than label-only matching against external authority systems —
beginning with the volume-14 place-name test bed and scaling to the full 18-volume corpus.
