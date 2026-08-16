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

Volumes 15–18 (Rejseskildringer II + Selvbiografier I–III):

| | vol 15 | vol 16 | vol 17 | vol 18 | merged |
| --- | ---: | ---: | ---: | ---: | ---: |
| comments | 2 626 | 2 204 | 2 303 | 2 086 | 9 219 |
| place notes (high+med) | 295 | 94 | 142 | 95 | 626 |
| **index rows** | 286 | 87 | 138 | 91 | **570** |

602 per-volume rows collapse to 570 — **30 places are shared between volumes**
and merge into one entry each. The fullest example:

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

---

## 5. Coverage across the 18 volumes

Run as-is, no per-volume tuning:

| vol | title | comments | dated |
| ---: | --- | ---: | ---: |
| 1–3 | Eventyr og Historier I–III | 3 437 | 100 / 92 / 100 % |
| 4–6 | Romaner I–III | 3 892 | 100 % |
| 7–8 | Digte I–II | 3 905 | 92 % / **3 %** |
| 9 | Blandinger | 2 212 | 98 % |
| 10–13 | Skuespil I–IV | 4 797 | 100 / 98 / 69 / 100 % |
| 14–15 | Rejseskildringer I–II | 5 735 | 100 % |
| 16–18 | Selvbiografier I–III | 6 593 | 100 % |
| | **total** | **30 571** | **91 %** |

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
