"""Sub-series Navneregister (name-index) parser — plan-v3 Source A.

Each sub-series of the 18-volume edition ends, in its final volume, with a
cumulative printed **Navneregister** (`<head type="major">Navneregister</head>`
+ `<p>` entries). Each entry is

    Surname, Given (dates), contextual description.  <vol-refs>

where the references use **Roman numerals relative to the sub-series**
(`I 640`, `III 594; IV 649`). This parser locates those sections, parses the
entries, and resolves every Roman numeral to an **absolute volume number**.

**Mapping — aligned with svNames `data/indexExtraction/`.** The canonical XSLT
pipeline (`SVindex2tp_xslt_2-0_step-2.xsl`, `SVindex_xml-idPerson.xsl`) resolves a
reference as:

    absolute_vol = base + roman − 1

where `base` is the sub-series' **first** absolute volume, declared as
`teiHeader/volumeNumber` in the extracted index files (e.g. `<volumeNumber>14`
for Rejseskildringer → I=14, II=15). This parser uses the same formula: it reads
`teiHeader/volumeNumber` as the base when present, and otherwise derives the base
from the edition's own volume titles (`Andersen N - <series> <roman>`) — which
reproduces the same value (Skuespil→10, Rejseskildringer→14, Selvbiografier→16).

Named-entity indexes only (Navneregister) — the Eventyr/Digte "Register" /
"Titelregister" are *title* indexes and are deliberately skipped, consistent
with the persons/places-only scope.

> svnames-index repo: the canonical sub-series→volume mapping is maintained
> there; it was not reachable from this session, so the base is taken from
> `teiHeader/volumeNumber` / derived from titles per the formula above. They
> agree on the present corpus.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from dataclasses import dataclass, field

from tei_comments import normalize, strip_markup

_ROMAN_UNITS = [
    ("M", 1000), ("CM", 900), ("D", 500), ("CD", 400), ("C", 100), ("XC", 90),
    ("L", 50), ("XL", 40), ("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1),
]
_ROMAN_RE = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_HEAD = re.compile(r'<head type="major">\s*Navneregister\s*</head>', re.I)
_NEXT_MAJOR = re.compile(r'<head type="major">')
_P = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)
_DATE_PAREN = re.compile(r"\(([^)]*\d{3,}[^)]*)\)")
# first sub-series volume marker in a ref tail: a Roman numeral followed by a page
_REF_START = re.compile(r"(?:^|[\s.,;])(VI{0,3}|IV|I{1,3})\s+\d")
_TEIHEADER = re.compile(r"<teiHeader\b.*?</teiHeader>", re.S)
_VOLNUM = re.compile(r"<volumeNumber>\s*([^<]+?)\s*</volumeNumber>")


@dataclass
class IndexEntry:
    name: str                       # lead/sort form as printed
    dates: str = ""
    description: str = ""
    occurrences: list[dict] = field(default_factory=list)   # [{vol, page}]
    see_also: str = ""
    series: str = ""
    source_volume: int = 0


def roman_to_int(s: str) -> int | None:
    """Standard subtractive Roman → int (mirrors XSLT `roman50-to-arabic`)."""
    t = s.strip().upper()
    if not t or not _ROMAN_RE.match(t):
        return None
    total, i = 0, 0
    for sym, val in _ROMAN_UNITS:
        while t[i:i + len(sym)] == sym:
            total += val
            i += len(sym)
    return total if i == len(t) else None


def build_series_map(data_dir: str) -> tuple[dict[str, dict[int, int]], dict[int, str]]:
    """Derive {series: {roman_index: abs_vol}} and {abs_vol: series} from titles."""
    series_map: dict[str, dict[int, int]] = {}
    vol_series: dict[int, str] = {}
    for p in glob.glob(os.path.join(data_dir, "Andersen [0-9]* - *_w_notes*.xml")):
        m = re.search(r"Andersen (\d+) - (.+?)_w_notes", os.path.basename(p))
        if not m:
            continue
        vol = int(m.group(1))
        title = m.group(2).strip()
        rm = re.search(r"\s(VI{0,3}|IV|I{1,3})$", title)
        roman = roman_to_int(rm.group(1)) if rm else 1
        series = title[: rm.start()].strip() if rm else title
        series_map.setdefault(series, {})[roman] = vol
        vol_series[vol] = series
    return series_map, vol_series


def _teiheader_base(text: str) -> int | None:
    """Base volume from teiHeader/volumeNumber (arabic or roman), per the XSLT."""
    hdr = _TEIHEADER.search(text)
    if not hdr:
        return None
    vm = _VOLNUM.search(hdr.group(0))
    if not vm:
        return None
    raw = vm.group(1).strip()
    return int(raw) if raw.isdigit() else roman_to_int(raw)


def _parse_refs(tail: str, base: int | None) -> list[dict]:
    """Tokenise a ref tail into [{vol, page}] via `base + roman - 1`."""
    if base is None:
        return []
    occ, current = [], None
    for tok in re.split(r"[,;]\s*|\s+", tail):
        tok = tok.strip(" .")
        if not tok:
            continue
        r = roman_to_int(tok)
        if r is not None:
            current = base + r - 1
        elif tok.isdigit() and current is not None:
            occ.append({"vol": current, "page": int(tok)})
    return occ


def parse_entry(raw: str, series: str, base: int | None, source_vol: int) -> IndexEntry | None:
    entry = re.sub(r"\s+", " ", strip_markup(raw)).strip()
    if not entry:
        return None
    # alphabet section header (single letter, incl. Æ/Ø/Å) or short heading
    if len(entry) <= 2 and entry == entry.upper():
        return None

    # cross-reference: "X, se Y" (no own references)
    see = re.match(r"^(.*?),\s+se\s+(.+)$", entry)
    if see and not _REF_START.search(entry):
        return IndexEntry(name=see.group(1).strip(), see_also=see.group(2).strip(),
                          series=series, source_volume=source_vol)

    dm = _DATE_PAREN.search(entry)
    if dm:
        name = entry[: dm.start()].strip(" ,.")
        dates = dm.group(1).strip()
        after = entry[dm.end():]
    else:
        name, dates, after = entry, "", entry

    rs = _REF_START.search(after)
    if rs:
        description = after[: rs.start()].strip(" ,.;")
        occ = _parse_refs(after[rs.start():], base)
    else:
        description, occ = (after if not dm else after.strip(" ,.;")), []

    # drop the preamble / non-entries: no name evidence, no refs, no see-ref
    if not occ and not dates and (len(name) < 3 or " " not in name.strip()):
        if not dm:
            return None
    return IndexEntry(name=name, dates=dates, description=description.strip(" ,.;"),
                      occurrences=occ, series=series, source_volume=source_vol)


def parse_volume(path: str, series_map, vol_series) -> list[IndexEntry]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    h = _HEAD.search(text)
    if not h:
        return []
    nxt = _NEXT_MAJOR.search(text, h.end())
    segment = text[h.end(): nxt.start() if nxt else len(text)]

    m = re.search(r"Andersen (\d+)", os.path.basename(path))
    source_vol = int(m.group(1)) if m else 0
    series = vol_series.get(source_vol, "")
    # base = teiHeader/volumeNumber if present, else the series' first volume
    base = _teiheader_base(text) or min(series_map.get(series, {1: 0}).values())

    entries = []
    for raw in _P.findall(segment):
        e = parse_entry(raw, series, base, source_vol)
        if e:
            entries.append(e)
    return entries


def parse_corpus(data_dir: str) -> dict[str, list[IndexEntry]]:
    """Return {series: entries} for every sub-series whose register is present."""
    series_map, vol_series = build_series_map(data_dir)
    out: dict[str, list[IndexEntry]] = {}
    for p in sorted(glob.glob(os.path.join(data_dir, "Andersen [0-9]* - *_w_notes*.xml"))):
        entries = parse_volume(p, series_map, vol_series)
        if entries:
            out[vol_series.get(int(re.search(r'Andersen (\d+)', p).group(1)), p)] = entries
    return out


def to_authority_index(entries: list[IndexEntry]) -> dict[str, set[str]]:
    """Map normalized name (+ flipped 'Surname, Given') -> {synthetic id}.

    Lets the reconciler treat the parsed Navneregister as an extra person
    authority. Ids are stable within a run: ``svidx-<vol>-<n>``.
    """
    index: dict[str, set[str]] = {}
    for n, e in enumerate(entries):
        if e.see_also or not e.name:
            continue
        eid = f"svidx-{e.source_volume}-{n:04d}"
        keys = {normalize(e.name)}
        if "," in e.name:
            sur, _, given = e.name.partition(",")
            keys.add(normalize(f"{given.strip()} {sur.strip()}"))
        for k in keys:
            if k:
                index.setdefault(k, set()).add(eid)
    return index


def build_index_authority(data_dir: str) -> dict[str, set[str]]:
    """Parse every sub-series Navneregister and return a name -> {svidx-*} map.

    Convenience wrapper used to fold the printed name indexes into the person
    register as a default authority source. Returns {} if no register is present.
    """
    entries = [e for es in parse_corpus(data_dir).values() for e in es]
    return to_authority_index(entries)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="/home/user/svNames/data")
    ap.add_argument("--out", default="", help="write parsed entries as JSON")
    args = ap.parse_args(argv)

    by_series = parse_corpus(args.data)
    series_map, vol_series = build_series_map(args.data)

    print("Sub-series → absolute volumes (derived from titles):")
    for s, m in sorted(series_map.items(), key=lambda kv: min(kv[1].values())):
        cov = ", ".join(str(v) for _, v in sorted(m.items()))
        print(f"   {s:24s} vols {cov}")
    print("-" * 60)
    print("Navneregister sections parsed:")
    total = 0
    for series, entries in by_series.items():
        occ = sum(len(e.occurrences) for e in entries)
        refs_vols = sorted({o['vol'] for e in entries for o in e.occurrences})
        total += len(entries)
        print(f"   {series:24s} {len(entries):5d} entries · {occ} occurrences · "
              f"covers vols {refs_vols}")
    print(f"   {'TOTAL':24s} {total:5d} entries")

    if args.out:
        payload = {s: [e.__dict__ for e in es] for s, es in by_series.items()}
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
