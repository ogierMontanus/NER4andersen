"""Re-emit the master place-name index under stricter admission rules.

Reads the per-comment STEP-2 output (out/comments-ALL-categorized.xml —
every comment individually tagged with confidence/evidence/place/lemma,
*before* placename-index.xsl's step-3 merge collapses them into rows) and
rebuilds the deduplicated index in Python, enforcing four rules that the
XSLT's grouping made hard to apply per-comment:

  1. Tivoli is a genuine homonym (Danish pleasure garden vs. the Roman hill
     town) and is split into two rows by hand, using each comment's actual
     context (work/page) to sort it into the right one.

  2. A comment is only admitted if its own PLACE — not just words that
     happen to occur in the explanation — looks like a placename: every
     token has to start uppercase, except a short whitelist of foreign
     name-linking particles (af, von, de, la, ...). This throws out
     sentence fragments, person names, opera/painting/event titles that
     upstream's step-2 categoriser had accepted purely because their
     definition mentioned a place in passing (evidence=="located" only —
     "spillede paa Det Kgl. Teater" satisfies the located-pattern without
     the definition ever defining a place). "located" evidence with no
     corroborating in-register / se-kort / head-noun / place-type signal
     is therefore rejected outright: an incidental place-mention in the
     explanation is not sufficient grounds for entry.

  3. Some `place` values are index-citation ellipses ("Abydos … Sestos") —
     the printed apparatus citing a passage by its first and last words,
     not a compound name. Each side is split out as its own candidate and
     re-run through rule 2 independently; a side that fails (e.g. the
     ellipsis spans a scene description, not two places) is dropped
     without dropping the side that passes.

  4. Where step 2 already extracted a corrected/modern spelling from the
     definition's opening ("Kalmar; se kort 1." -> place=Kalmar, lemma
     kept as Andersen's "Calmar"), that corrected form is carried straight
     through as `place`; Andersen's own spelling stays in `lemma_andersen`.
     This also cleans up merged groups where one comment's *lemma* was
     just anchor-span noise (e.g. "gammelt Sagn … Nabogaarde" anchoring a
     note that is actually about Borreby): the noisy string is dropped
     from lemma_andersen if it doesn't look like a placename in its own
     right, while the group itself is kept under the real name.

Usage:
    python reprocess_index.py \
        --categorized out/comments-ALL-categorized.xml \
        --register /home/user/svNames/data/registers/places.xml \
        --out out/2026-08-17_placenames-ALL.tsv
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field, replace

from lxml import etree

# ============================== vocabulary ==============================

# Lower-case tokens tolerated inside an otherwise-capitalised placename:
# linking particles from foreign (French/German/Italian/Spanish/Latin)
# geographic names actually attested in this corpus (Rio de Janeiro,
# Frankfurt am Main, Sierra de Gata, Mola di Gaeta, Monte Cavo's "di" ...).
PARTICLES = {
    "af", "i", "på", "de", "des", "du", "del", "della", "delle", "di", "da",
    "la", "le", "les", "el", "los", "las", "von", "van", "am", "an", "auf",
    "zu", "sur", "unter", "y", "e", "o", "of", "the", "und",
}

ELLIPSIS_RE = re.compile(r"\s*…\s*")
TOKEN_STRIP = ".,;:!?«»\"'’()[]{}"


def shape_ok(text: str) -> bool:
    """True if every word in `text` could plausibly open a proper name.

    Old Danish orthography (this edition) capitalises every noun, common
    and proper alike, so capitalisation alone cannot distinguish "Kirke"-
    the-church from "Kirke"-the-witch. What it *can* rule out cheaply is a
    lemma that is actually a clause: verbs, adjectives, pronouns, adverbs
    and conjunctions stay lower-case even under old orthography, so any
    lower-case word outside the closed-class particle list means this is
    prose, not a name.
    """
    text = re.sub(r"\([^)]*\)", " ", text)
    tokens = [t.strip(TOKEN_STRIP) for t in text.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return False
    for tok in tokens:
        if tok.isdigit():
            return False
        if tok.lower() in PARTICLES:
            continue
        if not tok[0].isupper():
            return False
    return True


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def tsv_safe(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


# ============================== register ==============================

def load_register(path: str) -> dict[str, str]:
    ns = {"t": "http://www.tei-c.org/ns/1.0"}
    reg: dict[str, str] = {}
    try:
        tree = etree.parse(path)
    except OSError:
        return reg
    for place in tree.findall(".//t:place", ns):
        gid = place.get("{http://www.w3.org/XML/1998/namespace}id") or ""
        if not gid:
            continue
        for pn in place.findall(".//t:placeName", ns):
            if pn.text:
                key = norm(re.sub(r"\([^)]*\)", "", pn.text))
                reg.setdefault(key, gid)
    return reg


# ============================== data model ==============================

@dataclass
class Comment:
    id: str
    vol: str
    page: str
    year: str
    work: str
    conf: str
    evidence: list
    place: str
    lemma: str
    variant: str
    geo: str
    definition: str


def load_comments(path: str) -> list[Comment]:
    tree = etree.parse(path)
    out = []
    for c in tree.findall("c"):
        conf = c.get("conf")
        if conf not in ("high", "medium"):
            continue
        out.append(Comment(
            id=c.get("id"), vol=c.get("vol"), page=c.get("page"),
            year=c.get("year") or "", work=c.get("work") or "",
            conf=conf, evidence=[e for e in c.get("evidence", "").split("+") if e],
            place=c.get("place"), lemma=c.get("lemma"), variant=c.get("variant"),
            geo=c.get("geo") or "", definition=c.text or "",
        ))
    return out


# ============================== rule 1: Tivoli ==============================

# Editorial call, made by reading each of the 9 comments in context (see
# session notes): 5 concern the Copenhagen pleasure garden (Carstensen,
# 1843) — including a Paris "Tivoli-Vauxhall" mention, the same genre of
# establishment rather than the Italian hill town — and 4 concern the town
# east of Rome (its waterfall, its distance from Rome, vol.15's "Vandfald
# ved Tivoli" sitting next to the Alban Hills). Hand-resolved because this
# is exactly the one-off judgement call rule/NLP signals can't make: both
# sides pass every automated check (in-register, head-noun, place-type).
TIVOLI_COPENHAGEN_IDS = {
    "txtcmnt-323-04",   # Portnøglen: "forlystelsespark ... Georg Carstensen 1843"
    "txtcmnt-273-07",   # "grundlagt af Georg Carstensen i 1843"
    "txtcmnt-138-01",   # Den nye Barselstue: "grundlagt 1843 af Georg Carstensen"
    "txtcmnt-177-01",   # Hr. Rasmussen: "grundlagt 1843 af Georg Carstensen"
    "txtcmnt-176-01",   # Skyggebilleder: "Tivoli-Vauxhall ved Paris" (same genre)
}
TIVOLI_ROME_IDS = {
    "txtcmnt-296-02",   # Improvisatoren: "by øst for Rom ved foden af Sabinerbjergene"
    "txtcmnt-261-01",   # Kun en Spillemand: "26 km øst for Rom med berømt vandfald"
    "txtcmnt-491-13",   # Rejseskildringer II: "det deilige Vandfald ved Tivoli" (next to Albanerbjergene)
    "txtcmnt-17-140-06",  # Mit Livs Eventyr: "26 km øst for Rom med berømt vandfald"
}


def split_tivoli(comments: list[Comment]):
    tivoli = [c for c in comments if norm(c.place) == "tivoli"]
    rest = [c for c in comments if norm(c.place) != "tivoli"]
    unresolved = {c.id for c in tivoli} - TIVOLI_COPENHAGEN_IDS - TIVOLI_ROME_IDS
    if unresolved:
        raise SystemExit(f"Tivoli comment(s) not in either bucket: {unresolved}")
    cph = [replace(c, place="Tivoli (København)", geo="")
           for c in tivoli if c.id in TIVOLI_COPENHAGEN_IDS]
    rome = [replace(c, place="Tivoli (Italien)")
            for c in tivoli if c.id in TIVOLI_ROME_IDS]
    return rest, cph, rome


# ============================== rules 2+3: filter / split ==============================

@dataclass
class Stats:
    dropped_located_only: int = 0
    dropped_shape: int = 0
    ellipsis_seen: int = 0
    ellipsis_split_ok: int = 0
    ellipsis_split_partial: int = 0
    ellipsis_dropped_both: int = 0


def admit(comments: list[Comment], register: dict, stats: Stats) -> list[Comment]:
    out = []
    for c in comments:
        # rule 2 (evidence half): a place-mention picked up only via the
        # generic "located" pattern (lower-case head-noun + preposition +
        # proper noun *anywhere* in the note) never establishes that the
        # comment's own lemma denotes a place — it fires just as readily
        # on "spillede paa Det Kgl. Teater" as on a real definition.
        if set(c.evidence) and set(c.evidence) == {"located"}:
            stats.dropped_located_only += 1
            continue

        if "…" in c.place:
            stats.ellipsis_seen += 1
            parts = [p.strip(" .,;") for p in ELLIPSIS_RE.split(c.place) if p.strip(" .,;")]
            valid = [p for p in parts if shape_ok(p)]
            if not valid:
                stats.ellipsis_dropped_both += 1
                continue
            if len(valid) < len(parts):
                stats.ellipsis_split_partial += 1
            else:
                stats.ellipsis_split_ok += 1
            for part in valid:
                geo = register.get(norm(part), "")
                out.append(replace(c, place=part, lemma=part, variant=part,
                                    evidence=c.evidence + ["split-ellipsis"], geo=geo))
            continue

        # rule 2 (shape half)
        if not shape_ok(c.place):
            stats.dropped_shape += 1
            continue

        out.append(c)
    return out


# ============================== aggregation (STEP 3, faithfully) ==============================

def sort_key(c: Comment):
    y = int(c.year) if c.year.isdigit() else 9999
    v = int(c.vol) if c.vol.isdigit() else 99
    p = int(c.page) if c.page.isdigit() else 99999
    return (y, v, p)


def build_rows(comments: list[Comment]) -> list[dict]:
    groups: dict[str, list[Comment]] = {}
    for c in comments:
        groups.setdefault(norm(c.place), []).append(c)

    rows = []
    for key, group in groups.items():
        group_sorted = sorted(group, key=sort_key)
        first = group_sorted[0]

        years = sorted({c.year for c in group if c.year})
        vols = sorted({c.vol for c in group if c.vol},
                      key=lambda v: int(v) if v.isdigit() else 999)

        lemmas = []
        for c in group:
            if shape_ok(c.variant) and c.lemma not in lemmas:
                lemmas.append(c.lemma)
        if not lemmas:
            lemmas = [first.place]

        expl = []
        for c in group:
            t = tsv_safe(c.definition)
            if t and t not in expl:
                expl.append(t)

        refs = [f"v{c.vol}:{c.page} ({c.year})" for c in group_sorted]

        evidence = []
        for c in group:
            for e in c.evidence:
                if e not in evidence:
                    evidence.append(e)

        rows.append({
            "place": tsv_safe(first.place),
            "lemma_andersen": " | ".join(tsv_safe(l) for l in lemmas),
            "explanation": " ¶ ".join(expl),
            "year": first.year,
            "years": " ".join(years),
            "volumes": " ".join(vols),
            "work": tsv_safe(first.work),
            "page": first.page,
            "occurrences": str(len(group)),
            "references": "; ".join(refs),
            "confidence": "high" if any(c.conf == "high" for c in group) else "medium",
            "evidence": "+".join(evidence),
            "geo_id": first.geo,
        })

    rows.sort(key=lambda r: r["place"].lower())
    return rows


COLUMNS = ["place", "lemma_andersen", "explanation", "year", "years", "volumes",
           "work", "page", "occurrences", "references", "confidence", "evidence", "geo_id"]


def write_tsv(rows: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\t".join(COLUMNS) + "\n")
        for r in rows:
            fh.write("\t".join(r[c] for c in COLUMNS) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--categorized", default="out/comments-ALL-categorized.xml")
    ap.add_argument("--register", default="/home/user/svNames/data/registers/places.xml")
    ap.add_argument("--out", default="out/2026-08-17_placenames-ALL.tsv")
    args = ap.parse_args(argv)

    register = load_register(args.register)
    comments = load_comments(args.categorized)
    print(f"comments (conf high/medium): {len(comments)}")

    rest, tivoli_cph, tivoli_rome = split_tivoli(comments)
    print(f"Tivoli: {len(tivoli_cph)} -> Tivoli (København), "
          f"{len(tivoli_rome)} -> Tivoli (Italien)")

    stats = Stats()
    admitted = admit(rest, register, stats)
    admitted += tivoli_cph + tivoli_rome

    print(f"dropped, evidence=located-only : {stats.dropped_located_only}")
    print(f"dropped, lemma not a placename : {stats.dropped_shape}")
    print(f"ellipsis lemmas seen            : {stats.ellipsis_seen}")
    print(f"  both sides kept               : {stats.ellipsis_split_ok}")
    print(f"  one side dropped              : {stats.ellipsis_split_partial}")
    print(f"  both sides dropped            : {stats.ellipsis_dropped_both}")
    print(f"admitted comments               : {len(admitted)}")

    rows = build_rows(admitted)
    print(f"index rows                      : {len(rows)}")

    write_tsv(rows, args.out)
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
