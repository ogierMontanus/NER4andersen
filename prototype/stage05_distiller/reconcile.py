"""Internal reconciliation of distilled place entities (plan-v3 Stage 2 start).

Links place entities to the svNames place register (`places.xml`) and, by doing
so, *promotes the true places out of the noisy place class* and *drops* the
ones that match nothing. Matching is now inflection-aware:

* `exact`  — name normalizes to a register key;
* `infl`   — after stripping Danish genitive `-s` and definite suffixes
             (`-en/-et/-erne/-ene`) the name matches a register key;
* `token`  — a capitalised token of the name matches a register key.

Edit-distance fuzziness is deliberately kept to a cheap (≤1) check to avoid
false links; richer linking is a later increment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tei_comments import normalize

_SUFFIXES = ("erne", "ene", "en", "et", "s")


def _inflection_variants(key: str) -> set[str]:
    out = {key}
    for suf in _SUFFIXES:
        if key.endswith(suf) and len(key) - len(suf) >= 3:
            out.add(key[: -len(suf)])
    return out


def _edit_distance_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    # find first mismatch
    i = 0
    while i < min(la, lb) and a[i] == b[i]:
        i += 1
    if la == lb:
        return a[i + 1:] == b[i + 1:]          # substitution
    if la > lb:
        return a[i + 1:] == b[i:]              # deletion from a
    return a[i:] == b[i + 1:]                  # insertion into a


@dataclass
class PlaceMatch:
    rid: str
    entity_name: str
    geo_ids: list[str]
    method: str          # exact | infl | token | fuzzy


@dataclass
class PersonMatch:
    rid: str
    entity_name: str
    gnd_ids: list[str]
    method: str          # exact | infl | token | fuzzy


def reconcile_entity_name(name: str, register: dict[str, set[str]]):
    key = normalize(name)
    if not key:
        return None, None
    if key in register:
        return sorted(register[key]), "exact"
    for v in _inflection_variants(key):
        if v in register:
            return sorted(register[v]), "infl"
    for token in re.split(r"[\s,]+", name):
        if token[:1].isupper():
            tkey = normalize(token)
            for v in _inflection_variants(tkey):
                if v in register:
                    return sorted(register[v]), "token"
    # cheap fuzzy: edit distance 1 against register keys of similar length
    for rk in register:
        if abs(len(rk) - len(key)) <= 1 and _edit_distance_le1(key, rk):
            return sorted(register[rk]), "fuzzy"
    return None, None


def reconcile_place(distilled, register: dict[str, set[str]]) -> PlaceMatch | None:
    """Best register match across a row's place entities (and lemma fallback)."""
    names = [e.name for e in distilled.entities if e.etype == "place"]
    names.append(distilled.row.lemma)
    for name in names:
        geo_ids, method = reconcile_entity_name(name, register)
        if geo_ids:
            return PlaceMatch(distilled.row.rid, name, geo_ids, method)
    return None


def reconcile_person(distilled, register: dict[str, set[str]]) -> PersonMatch | None:
    """Best register match across a row's person entities (gnd-* ids)."""
    for e in distilled.entities:
        if e.etype != "person":
            continue
        gnd_ids, method = reconcile_entity_name(e.name, register)
        if gnd_ids:
            return PersonMatch(distilled.row.rid, e.name, gnd_ids, method)
    return None


def candidate_shortlist(
    name: str, register: dict[str, set[str]], limit: int = 15
) -> list[tuple[str, str]]:
    """Register candidates sharing a token/prefix with `name`, for the LLM.

    `register` maps normalized key -> set of authority ids. Returns
    (authority_id, display_name) pairs — cheap blocking so the LLM ranks a small,
    plausible set rather than the whole register. Excludes exact matches (those
    are already handled by the rule-based path).
    """
    key = normalize(name)
    tokens = {t for t in re.split(r"[\s,]+", key) if len(t) >= 3}
    out: list[tuple[str, str]] = []
    for rkey, ids in register.items():
        if rkey == key or not ids:
            continue
        rtokens = set(re.split(r"[\s,]+", rkey))
        prefix = len(key) >= 4 and (rkey.startswith(key[:4]) or key.startswith(rkey[:4]))
        if (tokens & rtokens) or prefix:
            out.append((sorted(ids)[0], rkey))
        if len(out) >= limit:
            break
    return out

