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


def _comments_region(text: str) -> str:
    idx = text.find('<div type="comments">')
    return text[idx:] if idx != -1 else ""


def load_volume(path: str) -> Vol:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    comments = _comments_region(text)
    body = text[: text.find('<div type="comments">')] if comments else text

    vol = Vol(path=path)

    for rid, row_body in _ROW.findall(comments):
        term = _TERM.search(row_body)
        defn = _DEFN.search(row_body)
        if not term or not defn:
            continue
        page = int(rid.split("-")[1])
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
