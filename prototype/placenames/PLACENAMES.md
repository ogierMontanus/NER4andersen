# Extracting place names from an ANDERSEN volume

A two-stage XSLT pipeline that turns the editorial commentary of a svNames
volume into a **deduplicated place-name index with a year column**. Written and
validated against *Andersen 15 – Rejseskildringer II*, then run across all 18
volumes.

```
volume .xml ──▶ extract-comments.xsl ──▶ comments.xml ──▶ placename-index.xsl ──┬─▶ …categorized.xml   (review)
                (all comments + page                                            └─▶ …placenames.tsv    (the index)
                 + work + year)
```

---

## 1. Run it

Saxon is required (XSLT 3.0 — `xsl:for-each-group`, `fn:sort`, higher-order
functions). Saxon-HE plus its resolver dependency:

```bash
cd /tmp
curl -sSO https://repo1.maven.org/maven2/net/sf/saxon/Saxon-HE/12.4/Saxon-HE-12.4.jar
curl -sSO https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/5.2.2/xmlresolver-5.2.2.jar
curl -sSO https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/5.2.2/xmlresolver-5.2.2-data.jar
export CP=/tmp/Saxon-HE-12.4.jar:/tmp/xmlresolver-5.2.2.jar:/tmp/xmlresolver-5.2.2-data.jar
```

```bash
# STEP 1 — every comment, with page / work / year
java -cp "$CP" net.sf.saxon.Transform \
  -s:"$SV/data/Andersen 15 - Rejseskildringer II_w_notes_rebecca_2024-06-06_comments.xml" \
  -xsl:extract-comments.xsl -o:out/comments-vol15.xml

# STEPS 2+3 — categorise, then index (deduplicated, with year)
java -cp "$CP" net.sf.saxon.Transform \
  -s:out/comments-vol15.xml -xsl:placename-index.xsl \
  -o:out/placenames-vol15.tsv \
  categorized=comments-vol15-categorized.xml \
  register=$SV/data/registers/places.xml
```

> ⚠️ `categorized` is resolved **relative to `-o:`**, so pass a bare filename
> (it lands beside the TSV) or an absolute path. `out/x.xml` would land in
> `out/out/x.xml`.

To do another volume, change only the `-s:` path. Nothing else is volume-specific.

---

## 2. What the volumes actually look like

Three encoding facts cost real debugging time. Check them first on a new volume.

### 2.1 A comment exists twice

| where | shape |
| --- | --- |
| printed apparatus (end of volume) | `<table rend="textcomments">` → `<row xml:id="txtcmnt-012-01">` with `<cell type="data-term">` (lemma) + `<cell type="data-definition">` (explanation) |
| injected into the running text | `<seg target="txtcmnt-012-01"><data-term>…</data-term><data-definition>…</data-definition>…</seg>` |

The apparatus is **authoritative and complete** (across all 18 volumes the
extractor found *no* inline-only comment). The inline `seg` is what tells you
which *work* a comment sits in, and therefore its year. Vol 8 writes the inline
copy as XML comments (`<!--DATA-TERM: …-->`) instead of elements — harmless,
because the apparatus is what we read.

### 2.2 `row` is not always a child of `table`

Volumes 8–13 wrap every row in an extra untyped `<cell>`:

```xml
<table rend="textcomments">
  <cell type="page">45</cell>
  <cell><row xml:id="txtcmnt-045-01"> … </row></cell>
```

So the selector must use the **descendant** axis. `table/row` silently returns
zero comments for six volumes:

```xpath
//table[@rend='textcomments']//row[cell[@type='data-term'] or cell[@type='data-definition']]
```

For the same reason the page is taken from **`@xml:id`**, which survives every
nesting; the `<cell type="page">` is only a fallback.

But the id itself comes in **two schemes**:

| scheme | example | volumes |
| --- | --- | --- |
| `txtcmnt-PAGE-SEQ` | `txtcmnt-045-01` → p. 45 | 1–16 |
| `txtcmnt-VOL-PAGE-SEQ` | `txtcmnt-17-013-01` → p. 13 | 17–18 |

Taking “the first number after `txtcmnt-`” silently yields the *volume* as the
page for vols 17–18 — every comment in vol 17 comes out as page 17. In both
schemes the page is the **second-to-last numeric part**, so that is what
`f:page-from-id()` returns.

### 2.3 Two different places to find the year

This is the whole basis of the `year` column — it is read from file metadata,
never guessed.

| layout | where the date lives | volumes |
| --- | --- | --- |
| source block is a **child** of the work | `div[@type='work']/div[@type='source']/sourceDate` | 15 (minor pieces), 16–18 |
| the three major travel books | `div[@type='work']/front//docImprint` | 14, 15 |
| source block **wraps** a booklet, works are its children | `div[@type='work']/ancestor::div[@type='source']/sourceDate` | 1–3 (tales), 7 |

```xml
<!-- Rejseskildringer: source INSIDE work -->
<div type="work"><div type="source"><sourceTitle>Dagbladet</sourceTitle><sourceDate>1857</sourceDate></div>

<!-- Eventyr: source WRAPS the works -->
<div type="source"><sourceTitle>Eventyr, fortalte for Børn. Første Hefte</sourceTitle><sourceDate>1835</sourceDate>
   <div type="work"><head type="main">Fyrtøiet</head>…
```

`f:year()` tries all of them in order. Missing the ancestor case leaves ~85 % of
a tale volume undated.

---

## 3. Deciding what is a place (step 2)

Danish editorial prose, so the signals are lexical. Five are computed
independently and recorded in `@evidence`, so any decision can be audited:

| signal | meaning |
| --- | --- |
| `in-register` | lemma matches `data/registers/places.xml` |
| `se-kort` | the note carries a map cross-reference (“se kort 2”). In this edition **only places are mapped** — a very strong signal, and it catches notes with no descriptive prose at all (`Leksand :: se kort 2.`) |
| `head-noun` | the definition *opens* with a geographic head-noun — it predicates a place: “by i Indien”, “landskab i Sverige”, “karteuserkloster fra 1516” |
| `located` | a **lower-case** head-noun + spatial preposition + proper noun (“flod … gennem Rom”) |
| `place-type` | a geographic word occurs anywhere near the start (weak) |

`head-noun` is the discriminating one. It separates a real place note from a
vocabulary gloss that merely *contains* a geographic word — “kvindelig
forstander for et **nonnekloster**” (an abbess) or “det at gå op til alteret i en
**kirke**” (communion) are correctly rejected because the geographic word is
buried after a preposition rather than heading the definition.

**Match whole words, never substrings.** Three real bugs this prevents:

| naive substring | wrongly matches | 
| --- | --- |
| `å` | **p**å, udr**å**be |
| `elv` | s**elv** |
| `dal` (compound tail) | the surname Vi**dal** |

XPath regex has **no `\b`**, so boundaries are written `(^|[^\p{L}\p{N}])`.
The compound rule in `located` additionally requires `\p{Ll}+` so that a proper
name ending in a type ("Vidal", "Bangsbo") cannot masquerade as one.

**Person veto.** Parenthesised life-dates in the opening — `(1796-1868), svensk
forfatter` — mark the note as a person and demote it, unless the lemma is in the
register. This is what keeps *Alfons Henriques* and *Ana Carlota Xavier Vidal*
out of a place index.

### Confidence

| tier | rule | vol 15 |
| --- | --- | ---: |
| `high` | `in-register` \| `se-kort` \| `head-noun` | 247 |
| `medium` | `located` | 48 |
| `low` | only a generic geographic word, or a person note that mentions somewhere | 153 |
| — | no place signal at all | 2 178 |

The index takes **high + medium**. `low` is deliberately kept in the categorised
XML as the **review bucket** — it holds genuine misses (e.g. *Coimbra*, whose
note opens “200 km nord for Lissabon…” with no head-noun) next to true
negatives. Read it; do not ship it unreviewed.

---

## 4. The index (step 3)

Deduplicated with `xsl:for-each-group` on a normalised key (parentheses and
punctuation stripped, case folded, so `Halland(s)` → `halland`).

| column | notes |
| --- | --- |
| `place` | headword. If the note opens with a modern normalised spelling (`Calmar` → “**Kalmar**; se kort 1.”) that becomes the headword |
| `lemma_andersen` | **Andersen’s own spelling(s)**, taken verbatim from the `seg`/`data-term` lemma — inflection markers and all (`Fahlun(s)`, `Skaane`, `Bajonne`). Multiple spellings are joined with ` \| ` |
| `explanation` | **the editorial explanation(s)** — the `data-definition` prose. When several notes merge into one row they are joined with ` ¶ ` |
| `year` | **year of the reference** — the publication year of the work the comment sits in, from `docImprint`/`sourceDate`. Earliest, when a place recurs |
| `years` | every distinct year, when a place is referenced in more than one work |
| `volumes` | every volume the place occurs in (only interesting for a merged index) |
| `work`, `page` | of the **main entry** — the earliest reference, ordered by year, then volume, then page |
| `occurrences` | how many comments were merged into the row |
| `references` | every occurrence as `v<vol>:<page> (<year>)`, earliest first — the accumulated citation list |
| `confidence`, `evidence` | for review |
| `geo_id` | `geo-…` if the name is in `places.xml` |

Every field is passed through `f:tsv()`, which flattens tabs and newlines, so the
explanation prose can never break the column structure.

Vol 15: **2 626 comments → 295 place notes → 286 unique places.**

```
place    lemma_andersen      explanation                                      year  years      n
Bayonne  Bayonne | Bajonne   fransk by ved grænsen til Spanien. ¶ Bayonne,    1863  1863 1868  2
                             by ved Golfe de Gascogne ca. 25 km fra …
Falun    Fahlun(s) | Fahlun  Falun; se kort 1-2.                              1851  1851       2
Kalmar   Calmar              Kalmar; se kort 1.                               1851  1851       1
Skåne    Skaane              Skåne; det sydligste landskab i Sverige.         1851  1851       1
```

*Bayonne* is commented once in **I Spanien** (1863) and again in **Et Besøg i
Portugal** (1868); the two notes collapse to one row, the earlier year leads,
both of Andersen’s spellings are kept, and both editorial explanations are
carried through. The headword is the modern form, so the index sorts and
deduplicates on *Kalmar* / *Skåne* while still recording that Andersen wrote
*Calmar* / *Skaane*.

---

## 4b. Merging several volumes into one index

Pass extra `comments.xml` files in `sources` (semicolon-separated). The index is
then built over the union: a place already present keeps its **single main
entry** and simply accumulates the new occurrences, years, volumes and
spellings — it is not duplicated.

```bash
java -cp "$CP" net.sf.saxon.Transform \
  -s:out/comments-vol15.xml -xsl:placename-index.xsl \
  -o:out/placenames-vol15-18.tsv \
  sources="out/comments-vol16.xml;out/comments-vol17.xml;out/comments-vol18.xml" \
  categorized=comments-vol15-18-categorized.xml
```

### The whole edition

```bash
SRC=$(for n in $(seq 2 18); do printf "out/comments-vol%s.xml;" $n; done | sed 's/;$//')
java -Xmx2g -cp "$CP" net.sf.saxon.Transform \
  -s:out/comments-vol1.xml -xsl:placename-index.xsl \
  -o:out/placenames-ALL.tsv sources="$SRC" categorized=comments-ALL-categorized.xml
```

All 18 volumes — 30 571 comments, 1 671 place notes (1 159 high + 512 medium),
1 407 more held back for review:

| | per-volume rows | master index |
| --- | ---: | ---: |
| all 18 volumes | 1 583 | **1 365** |

**218 places are shared between volumes** and collapse into one entry each; 147
of them span more than one volume. Takes ~17 s.

Volumes 15–18 alone (Rejseskildringer II + Selvbiografier I–III):

| | vol 15 | vol 16 | vol 17 | vol 18 | merged |
| --- | ---: | ---: | ---: | ---: | ---: |
| comments | 2 626 | 2 204 | 2 303 | 2 086 | 9 219 |
| place notes (high+med) | 295 | 94 | 142 | 95 | 626 |
| **index rows** | 286 | 87 | 138 | 91 | **570** |

602 per-volume rows collapse to 570 — 30 places shared. A fully merged example:

```
place          Pompeji
lemma_andersen Pompeji(s) | Pompeji
years          1846 1855 1860 1868 1869
volumes        15 16 17 18
work           Mit eget Eventyr uden Digtning     page 213     occurrences 6
references     v16:213 (1846); v17:66 (1855); v17:153 (1855);
               v15:187 (1860); v15:456 (1868); v18:218 (1869)
explanation    antik romersk by, begravet ved Vesuvs udbrud i 79 e.Kr. ¶ den
               romerske by syd for Napoli, der blev ødelagt … ved Vesuvs udbrud 79
```

The main entry is the **earliest** reference (1846, vol 16, p. 213), while
`references` preserves every later occurrence with its own volume, page and year.

> ⚠️ **Homonyms merge.** Deduplication is by name, so two different places that
> share one collapse into a single row. In the full-edition index *Tivoli* merges
> the Copenhagen pleasure garden (“forlystelsespark anlagt … i 1843”) with the
> town east of Rome (“by øst for Rom ved foden af Sabinerbjergene”) — 9
> occurrences across 8 volumes. The `explanation` column makes this visible,
> because the conflicting definitions sit side by side separated by ` ¶ `. Splitting
> them is an editorial decision, so the pipeline does not guess — but `homonym_eval.py`
> (§4c) finds the candidates for you and can ask an LLM to adjudicate them.

---

## 4c. Finding homonym candidates — `homonym_eval.py`

Scanning 150 merged rows by eye for cases like Tivoli does not scale. Two-stage
triage instead, over the merged `explanation` column (split on ` ¶ `):

**Stage A — rule/NLP divergence estimate, always free, stdlib-only.** For every
pair of merged notes on a row it scores disagreement from four signals:
token Jaccard overlap, fuzzy string similarity (`rapidfuzz` if installed, else
`difflib`), whether the two notes' geographic head-nouns disagree (`kirke` vs.
`domkirke`, weighted heaviest — this is what actually catches Tivoli:
*forlystelsespark* vs. *by*), and how little proper-noun context the notes
share. The worst pair's weighted score is the row's divergence (0–1); rows
≥ 0.35 are flagged and printed worst-first.

```bash
python homonym_eval.py out/placenames-ALL.tsv
```

Against the full-edition index (1 365 rows, 150 with merged notes) this flags
108 rows. Tivoli comes out at 0.94 with `heads=forlystelsespark/by`; the top of
the list is dominated by genuine head-noun clashes (`Fredensborg` slot/by,
`Kirken` domkirke/kirke, `Portici` teater/forstad — an opera title colliding
with the town).

**Stage B — optional LLM adjudication (haiku).** For flagged rows, ask a cheap
model to read the actual notes and decide `one_place` / `multiple_places` /
`unclear`, with a rationale and (if split) which notes go with which place.
Same opt-in-only pattern as `reconcile_llm.py`: no-ops with a clear message if
`ANTHROPIC_API_KEY` is unset or `anthropic` isn't installed, never errors.

```bash
pip install -r requirements-llm.txt   # optional: rapidfuzz, anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python homonym_eval.py out/placenames-ALL.tsv --llm --out out/homonym-candidates.json
```

`--dry-run` prints the prompts without calling the API; `--limit N` caps how
many rows go to the LLM; `--threshold` adjusts the Stage-A cutoff (default
0.35); `--out` writes flagged rows + signals + verdicts as JSON for review.

---

## 4d. Stricter re-emission — `reprocess_index.py`

`placename-index.xsl`'s step-3 merge only ever looks at the *definition* text
when deciding whether a comment is a place; it never checks whether the
comment's own lemma actually looks like one. That lets three kinds of noise
into the index: a comment whose definition merely *mentions* a place in
passing ("spillede paa Det Kgl. Teater" satisfies the `located` pattern —
lower-case common noun + preposition + proper noun — without ever defining
one), a person or title picked up because a place word occurs somewhere in
its gloss, and an apparatus lemma that is really an index-citation ellipsis
("Abydos … Sestos") rather than a name.

`reprocess_index.py` re-derives the index from the **per-comment** step-2
output (`out/comments-ALL-categorized.xml` — every comment individually
tagged, before step-3's grouping erases which lemma came from which note)
and admits a comment only if:

* its evidence is not `located` alone — an incidental place-mention in the
  explanation is not sufficient grounds for entry, only a defining
  head-noun, an in-register match, or an explicit map cross-reference is;
* its own lemma looks like a name — every word has to start uppercase,
  except a short whitelist of foreign name-linking particles (`af`, `von`,
  `de`, `la`, `di`, …). Old Danish orthography capitalises *every* noun, so
  this can't tell "Kirke"-the-church from "Kirke"-the-witch, but it reliably
  throws out clauses: verbs, adjectives, pronouns and adverbs stay
  lower-case regardless of orthography, so a lemma carrying one is prose,
  not a name.

An ellipsis lemma is split on `…` and each side is re-run through the same
check independently, so "Abydos … Sestos" (both genuine — "antikke græske
byer på hhv. den asiatiske og den europæiske side af Dardanellerne") becomes
two rows, while a side that fails (a scene description, not a place) is
dropped without dropping the side that passes. **Tivoli** — the running
example of a homonym merge — is split by hand into `Tivoli (København)` and
`Tivoli (Italien)`, sorted by reading each of the 9 underlying comments in
its own work/page context (Carstensen/1843 → Copenhagen; "26 km øst for Rom"
/ the waterfall beside Albanerbjergene → the Roman town). Where step 2
already extracted a corrected spelling from the definition's opening
("Kalmar; se kort 1." for lemma "Calmar"), that stays the index headword —
this was already load-bearing for volumes 4b/4c merge and is preserved as-is.

```bash
python reprocess_index.py \
  --categorized out/comments-ALL-categorized.xml \
  --register /home/user/svNames/data/registers/places.xml \
  --out out/2026-08-17_placenames-ALL.tsv
```

Against the full-edition index (1,671 high/medium comments):

| | comments | rows |
| --- | ---: | ---: |
| unfiltered (`placenames-ALL.tsv`) | 1 671 | 1 365 |
| `located`-only evidence, dropped | −207 | |
| lemma isn't a placename, dropped | −164 | |
| ellipsis lemmas: both sides kept / one side / both dropped | 33 / 22 / 6 | |
| Tivoli, split by hand | 9 → 2 rows | |
| **stricter (`2026-08-17_placenames-ALL.tsv`)** | **1 326 admitted** | **1 041** |

**Known trade-off.** This trades recall for precision on purpose: some real
places only ever got `located` evidence because their type-word isn't in
`$TYPES`/`$COMP` (a landmark building, "curia hostilia"; a cliff, "Lorelei";
a mountain massif, "Olympen") and are dropped along with the actual noise.
And capitalisation alone can't catch every non-place: a capitalised person
or title with no lower-case word in it ("Cecrops", a mythological king)
still gets through. Both are visible, on request, by diffing against
`placenames-ALL.tsv` — nothing is silently discarded, everything dropped is
still sitting in `comments-ALL-categorized.xml`.

---

## 5. Coverage across the 18 volumes

Run as-is, no per-volume tuning:

| vol | title | comments | dated | index rows |
| ---: | --- | ---: | ---: | ---: |
| 1–3 | Eventyr og Historier I–III | 3 437 | 100 / 92 / 100 % | 7 / 38 / 33 |
| 4–6 | Romaner I–III | 3 892 | 100 % | 104 / 64 / 24 |
| 7–8 | Digte I–II | 3 905 | 92 % / **3 %** | 39 / 84 |
| 9 | Blandinger | 2 212 | 98 % | 59 |
| 10–13 | Skuespil I–IV | 4 797 | 100 / 98 / 69 / 100 % | 14 / 27 / 29 / 22 |
| 14–15 | Rejseskildringer I–II | 5 735 | 100 % | 437 / 286 |
| 16–18 | Selvbiografier I–III | 6 593 | 100 % | 87 / 138 / 91 |
| | **total** | **30 571** | **91 %** | **1 583 → 1 365 merged** |

The travel writing dominates, as expected: vols 14–15 alone supply 723 of the
1 583 per-volume rows, because those are the volumes whose commentary is
systematically topographic (and the only ones with map cross-references).

### Known gaps

* **Vol 8 (Digte II) — 3 % dated.** Not a bug: the file has 227 work divs but
  **no `<sourceDate>` and no `<div type="source">`**, so there is no per-poem date
  to read. Either accept blank years or supply a date list out of band.
* **Vols 2, 7, 12** — partial; some works sit outside any dated source block.
* Lowercase headwords (`det blaa Taarn`, `stora Kopparberget`, `ørk`) are mostly
  genuine Andersen descriptive place phrases — worth eyeballing, not worth
  filtering automatically.

---

## 6. Tuning for a new volume

Everything volume-specific is a stylesheet parameter or one of two word lists:

* `$TYPES` — geographic head-nouns, with Danish definite/plural forms. Add
  regional vocabulary as you meet it (`kilde`, `gods`, `bydel`, `residensslot`
  were added while working through vol 15).
* `$COMP` — heads allowed as the *tail* of a compound (`havneby`, `domkirke`,
  `Atlanterhavet`). Keep this list short and unambiguous: every entry you add is
  a chance for a surname to collide with it.
* `head-window` (default 80) — how far into a definition a head-noun still counts.
* `register` — the authority file used for `in-register` / `geo_id`.

Sanity checks after running a new volume:

1. `count` in `comments.xml` is non-zero and close to the number of
   `<cell type="data-term">` in the source (if it is 0, suspect the `//row` nesting);
2. `year=""` is rare — if it is common, the volume uses a date layout not in §2.3;
3. sample 15 rows of the index and 10 of the `low` bucket before publishing.
