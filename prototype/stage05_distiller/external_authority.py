"""External authority reconciliation — plan-v3 Stage 2 (external) + spec Stage 2.

For entities the internal registers can't resolve, query public authority APIs
to propose candidates (and, ultimately, new register entries):

* **Wikidata**   — `wbsearchentities` (free, no key) — any entity type.
* **GND**        — lobid.org GND search (free, no key) — persons/orgs.
* **GeoNames**   — `searchJSON` (needs a free `GEONAMES_USERNAME`) — places.

Design mirrors `reconcile_llm.py`: **opt-in and offline-safe**. Every network
call is wrapped — a blocked egress, timeout, or bad response yields an empty
candidate list, never an exception. Stdlib only (`urllib`), so CI stays
dependency-free; parsing is split from fetching so the parsers are unit-tested
with canned JSON and never touch the network.

Enable per provider:
* Wikidata / GND work out of the box wherever outbound HTTPS is allowed.
* GeoNames activates only when ``GEONAMES_USERNAME`` is set.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

_UA = "NER4andersen/0.1 (scholarly NER; https://github.com/ogierMontanus/NER4andersen)"
_TIMEOUT = 8


@dataclass
class ExternalCandidate:
    source: str          # "wikidata" | "gnd" | "geonames"
    id: str              # provider-native id (Q-number, GND id, geonameId)
    label: str
    description: str = ""
    uri: str = ""
    extra: dict = field(default_factory=dict)


def _fetch(url: str) -> dict | None:
    """GET + JSON-decode a URL. Returns None on ANY failure (offline-safe)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# --- pure parsers (unit-tested without network) ---------------------------

def parse_wikidata(data: dict) -> list[ExternalCandidate]:
    out = []
    for hit in (data or {}).get("search", []):
        out.append(ExternalCandidate(
            source="wikidata",
            id=hit.get("id", ""),
            label=hit.get("label", "") or hit.get("match", {}).get("text", ""),
            description=hit.get("description", "") or "",
            uri=hit.get("concepturi", "") or f"https://www.wikidata.org/wiki/{hit.get('id','')}",
        ))
    return [c for c in out if c.id]


def parse_gnd(data: dict) -> list[ExternalCandidate]:
    out = []
    for m in (data or {}).get("member", []):
        gid = m.get("gndIdentifier", "")
        types = m.get("type", [])
        out.append(ExternalCandidate(
            source="gnd",
            id=gid,
            label=m.get("preferredName", ""),
            description=", ".join(t for t in types if t != "AuthorityResource"),
            uri=m.get("id", "") or (f"https://d-nb.info/gnd/{gid}" if gid else ""),
        ))
    return [c for c in out if c.id]


def parse_geonames(data: dict) -> list[ExternalCandidate]:
    out = []
    for g in (data or {}).get("geonames", []):
        gid = str(g.get("geonameId", ""))
        desc = " ".join(x for x in (g.get("fcodeName", ""), g.get("countryName", "")) if x)
        out.append(ExternalCandidate(
            source="geonames",
            id=gid,
            label=g.get("name", ""),
            description=desc,
            uri=f"https://www.geonames.org/{gid}" if gid else "",
            extra={"lat": g.get("lat"), "lng": g.get("lng"), "fcode": g.get("fcode")},
        ))
    return [c for c in out if c.id]


# --- provider searches (network) ------------------------------------------

def search_wikidata(name: str, lang: str = "da", limit: int = 5) -> list[ExternalCandidate]:
    q = urllib.parse.urlencode({
        "action": "wbsearchentities", "search": name, "language": lang,
        "uselang": lang, "format": "json", "limit": limit,
    })
    return parse_wikidata(_fetch(f"https://www.wikidata.org/w/api.php?{q}") or {})


def search_gnd(name: str, limit: int = 5) -> list[ExternalCandidate]:
    q = urllib.parse.urlencode({"q": name, "format": "json", "size": limit})
    return parse_gnd(_fetch(f"https://lobid.org/gnd/search?{q}") or {})


def search_geonames(name: str, limit: int = 5) -> list[ExternalCandidate]:
    user = os.environ.get("GEONAMES_USERNAME")
    if not user:
        return []   # GeoNames needs a (free) username — no-op without one
    q = urllib.parse.urlencode({"q": name, "maxRows": limit, "username": user})
    return parse_geonames(_fetch(f"https://secure.geonames.org/searchJSON?{q}") or {})


def propose_external(name: str, etype: str, limit: int = 5) -> list[ExternalCandidate]:
    """Aggregate external candidates appropriate to the entity type. Offline-safe."""
    cands: list[ExternalCandidate] = []
    if etype == "place":
        cands += search_geonames(name, limit)
        cands += search_wikidata(name, limit=limit)
    elif etype in ("person", "organization"):
        cands += search_gnd(name, limit)
        cands += search_wikidata(name, limit=limit)
    else:
        cands += search_wikidata(name, limit=limit)
    return cands


# --- propose a new register entry from a chosen candidate ------------------

def to_register_stub(cand: ExternalCandidate, etype: str) -> str:
    """A minimal TEI stub for a new authority record (spec deliverable C/D).

    Mirrors the shape of svNames' register entries + ``templates/*-default.xml``
    so a curator can drop it straight into persons.xml / places.xml.
    """
    if etype == "place":
        geo = ""
        if cand.extra.get("lat") and cand.extra.get("lng"):
            geo = f'\n      <location><geo>{cand.extra["lat"]} {cand.extra["lng"]}</geo></location>'
        return (
            f'<place xml:id="geo-{cand.id}">\n'
            f'   <placeName type="main">{cand.label}</placeName>{geo}\n'
            f'   <note>{cand.description}</note>\n'
            f'   <ptr type="{cand.source}" target="{cand.uri}"/>\n'
            f'</place>'
        )
    return (
        f'<person xml:id="{cand.source}-{cand.id}">\n'
        f'   <persName type="main">{cand.label}</persName>\n'
        f'   <note type="bio">{cand.description}</note>\n'
        f'   <ptr type="{cand.source}" target="{cand.uri}"/>\n'
        f'</person>'
    )
