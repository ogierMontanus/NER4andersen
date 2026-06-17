"""TEI parsing helpers for the Stage 0.5 comments-table distiller.

The svNames corpus files are large TEI documents with ``xml:space="preserve"``
and heavy inline markup, so we parse the two regions we care about with
targeted regexes rather than building a full DOM:

* the editorial comments apparatus
  (``<div type="comments">/<table rend="textcomments">``), and
* the ``<placeName ref="geo-*">`` occurrences in the running text.

Both have proven stable across volume 14; the same helpers generalise to the
other volumes that share the encoding.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_ROW = re.compile(r'<row xml:id="(txtcmnt-[0-9-]+)">(.*?)</row>', re.S)
_TERM = re.compile(r'<cell type="data-term">(.*?)</cell>', re.S)
_DEFN = re.compile(r'<cell type="data-definition">(.*?)</cell>', re.S)
_PLACE = re.compile(r'<placeName ref="(geo-[0-9]+)">([^<]*)</placeName>')
_PERSON = re.compile(r'<persName\b[^>]*>([^<]*)</persName>')

# Place register: <place xml:id="geo-..."> ... <placeName ...>Name</placeName>
_REG_PLACE = re.compile(r'<place\b[^>]*xml:id="(geo-[0-9]+)"[^>]*>(.*?)</place>', re.S)
_REG_PNAME = re.compile(r"<placeName[^>]*>([^<]*)</placeName>")


def strip_markup(fragment: str) -> str:
    """Remove inline tags and collapse whitespace."""
    return _WS.sub(" ", _TAG.sub("", fragment)).strip()


def normalize(text: str) -> str:
    """Case/diacritic-insensitive key for matching surface forms."""
    text = strip_markup(text).lower().strip(" .,;:!?«»“”\"'…")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS.sub(" ", text).strip()


@dataclass
class CommentRow:
    rid: str          # e.g. txtcmnt-048-01
    page: int         # derived from the id (048 -> 48)
    lemma: str        # data-term, markup stripped
    definition: str   # data-definition, markup stripped


@dataclass
class Vol:
    path: str
    rows: list[CommentRow] = field(default_factory=list)
    place_refs: dict[str, set[str]] = field(default_factory=dict)   # geo-id -> surface forms
    place_surface_norm: set[str] = field(default_factory=set)
    person_surface_norm: set[str] = field(default_factory=set)


# Tables/sections that are NOT running text and must be stripped before we
# read body placeName/persName occurrences:
#   * textcomments  — the editorial apparatus (its own pipeline below)
#   * textdeviations — text-critical variants (position/deviation cells)
#   * any trailing name/title register ("Navneregister", "Titelregister")
_COMMENTS_TABLE = re.compile(r'<table rend="textcomments">.*?</table>', re.S)
_DEVIATION_TABLE = re.compile(r'<table rend="textdeviations">.*?</table>', re.S)
_REGISTER_DIV = re.compile(
    r'<div type="(?:names?register|navneregister|titelregister|registre?)"[^>]*>.*?</div>',
    re.S | re.I,
)


def _non_running_text(text: str) -> str:
    """Strip apparatus + registers so only running text remains."""
    text = _COMMENTS_TABLE.sub(" ", text)
    text = _DEVIATION_TABLE.sub(" ", text)
    text = _REGISTER_DIV.sub(" ", text)
    return text


def _comment_rows(text: str) -> list[tuple[str, str]]:
    """All textcomments rows anywhere in the document (across work-comments).

    Volumes beyond 14/15 scatter many ``<table rend="textcomments">`` inside
    ``<div type="work-comments">`` blocks, so we collect rows from every such
    table rather than a single trailing ``<div type="comments">``. Deviation
    and register rows are excluded because they lack data-term/data-definition.
    """
    rows = []
    for table in _COMMENTS_TABLE.findall(text):
        rows.extend(_ROW.findall(table))
    return rows


def load_volume(path: str) -> Vol:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    body = _non_running_text(text)

    vol = Vol(path=path)

    for rid, row_body in _comment_rows(text):
        term = _TERM.search(row_body)
        defn = _DEFN.search(row_body)
        if not term or not defn:
            continue
        # row id is txtcmnt-PPP-NN; page may be absent in some encodings
        parts = rid.split("-")
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        vol.rows.append(
            CommentRow(
                rid=rid,
                page=page,
                lemma=strip_markup(term.group(1)),
                definition=strip_markup(defn.group(1)),
            )
        )

    for geo, surface in _PLACE.findall(body):
        surf = strip_markup(surface)
        if not surf:
            continue
        vol.place_refs.setdefault(geo, set()).add(surf)
        vol.place_surface_norm.add(normalize(surf))

    for surface in _PERSON.findall(body):
        surf = normalize(surface)
        if surf:
            vol.person_surface_norm.add(surf)

    return vol


def load_place_register(path: str) -> dict[str, set[str]]:
    """Map normalized place name -> set of geo-* ids from a TEI place register.

    Used to reconcile distilled place candidates against svNames'
    ``data/registers/places.xml`` (the internal authority file).
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    index: dict[str, set[str]] = {}
    for geo, body in _REG_PLACE.findall(text):
        for name in _REG_PNAME.findall(body):
            key = normalize(name)
            if key:
                index.setdefault(key, set()).add(geo)
    return index
