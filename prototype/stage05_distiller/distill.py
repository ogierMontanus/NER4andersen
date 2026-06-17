"""Stage 0.5 prototype entry point.

Parse a volume's editorial comments table, distil each row into a typed
authority candidate with provenance, write JSON, and evaluate the place-typed
output against the volume's unique placeName / geo-* set.

Usage:
    python distill.py /path/to/svNames/data/<volume>.xml [--out out/vol14.json]

Default volume path resolves to the sibling svNames checkout used in
development.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from tei_comments import load_volume, load_place_register, normalize
from classify import classify, NAMED_ENTITY_TYPES
from reconcile import reconcile_place, candidate_shortlist
from reconcile_llm import llm_available, llm_link

DEFAULT_VOL = (
    "/home/user/svNames/data/"
    "noHiSeg_Andersen 14 - Rejseskildringer I_w_notes_Rebecca.xml"
)
DEFAULT_REGISTER = "/home/user/svNames/data/registers/places.xml"


def run(vol_path: str, out_path: str | None, register_path: str | None,
        use_llm: bool = False) -> int:
    vol = load_volume(vol_path)
    if not vol.rows:
        print(f"No comment rows found in {vol_path}", file=sys.stderr)
        return 2

    register = None
    if register_path and os.path.exists(register_path):
        register = load_place_register(register_path)

    # Known places that anchor classification = body placeName surfaces
    # (running text) plus the internal register's names.
    place_keys = set(vol.place_surface_norm)
    if register:
        place_keys |= set(register.keys())

    distilled = [classify(r, place_keys) for r in vol.rows]

    place_matches: dict[str, object] = {}
    llm_links: dict[str, object] = {}
    # LLM path is opt-in AND gated on a key + SDK being present (else no-op).
    llm_on = use_llm and register is not None and llm_available()
    if register:
        for d in distilled:
            if not any(e.etype == "place" for e in d.entities):
                continue
            m = reconcile_place(d, register)
            if m:
                place_matches[d.row.rid] = m
            elif llm_on:
                # hard case: rule-based found nothing — ask the LLM to pick
                pname = next(e.name for e in d.entities if e.etype == "place")
                shortlist = candidate_shortlist(pname, register)
                link = llm_link(pname, d.row.definition, shortlist)
                if link and link.authority_id:
                    llm_links[d.row.rid] = link

    # --- candidate records (the spec's unified shape, provenance kept) ----
    candidates = []
    for d in distilled:
        rec = {
            "label": d.row.lemma,
            "entityType": d.etype,
            "isNamedEntity": d.is_named_entity,
            "confidence": d.confidence,
            "distilledEntities": [
                {"name": e.name, "type": e.etype, "evidence": e.evidence}
                for e in d.entities
            ],
            "cues": d.cues,
            "definition": d.row.definition,
            "provenance": {
                "source": "editorial-comment",
                "ref": d.row.rid,
                "page": d.row.page,
                "file": os.path.basename(vol_path),
            },
        }
        m = place_matches.get(d.row.rid)
        if m is not None:
            rec["reconciliation"] = {
                "authority": "svNames/places.xml",
                "matchedName": m.entity_name,
                "geoIds": m.geo_ids,
                "method": m.method,
            }
        link = llm_links.get(d.row.rid)
        if link is not None:
            rec["reconciliation"] = {
                "authority": "svNames/places.xml",
                "geoIds": [link.authority_id],
                "method": "llm",
                "confidence": link.confidence,
                "rationale": link.rationale,
            }
        candidates.append(rec)

    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(candidates, fh, ensure_ascii=False, indent=2)

    _report(vol, distilled, out_path, register, place_matches, llm_links, llm_on)
    return 0


def _report(vol, distilled, out_path, register, place_matches,
            llm_links=None, llm_on=False):
    counts = Counter(d.etype for d in distilled)
    ne = sum(1 for d in distilled if d.is_named_entity)

    # Gold place set: rows whose lemma exactly matches a tagged placeName
    # surface form (the 284-row baseline in volume 14).
    gold_place_rows = {
        d.row.rid for d in distilled if normalize(d.row.lemma) in vol.place_surface_norm
    }
    # with splitting, a row "predicts place" if any distilled entity is a place
    pred_place_rows = {
        d.row.rid for d in distilled
        if any(e.etype == "place" for e in d.entities)
    }

    tp = len(gold_place_rows & pred_place_rows)
    fp = len(pred_place_rows - gold_place_rows)
    fn = len(gold_place_rows - pred_place_rows)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    print("=" * 64)
    print(f"Stage 0.5 distillation — {os.path.basename(vol.path)}")
    print("=" * 64)
    print(f"comment rows                 : {len(distilled)}")
    print(f"unique placeName geo-ids     : {len(vol.place_refs)}")
    print(f"unique placeName surfaces    : {len(vol.place_surface_norm)}")
    print(f"named-entity rows (distilled): {ne} "
          f"({100*ne/len(distilled):.1f}%)")
    print("type distribution:")
    for t, c in counts.most_common():
        flag = "  *NE" if t in NAMED_ENTITY_TYPES else ""
        print(f"   {t:14s} {c:5d}{flag}")
    print("-" * 64)
    if gold_place_rows:
        print("Place identification vs. tagged-place lemmas (gold = exact match):")
        print(f"   gold place rows : {len(gold_place_rows)}")
        print(f"   predicted place : {len(pred_place_rows)}")
        print(f"   TP={tp}  FP={fp}  FN={fn}")
        print(f"   precision={prec:.3f}  recall={rec:.3f}  F1={f1:.3f}")
        print("   (FP = rows with a place entity beyond the exact set: candidate "
              "new / inflected places — confirmed by reconciliation below)")
    else:
        print("No tagged placeNames in this volume — place P/R metric N/A "
              f"(rows with a place candidate: {len(pred_place_rows)}; "
              "reconciliation still applies).")

    if register is not None:
        pred_place = [d for d in distilled
                      if any(e.etype == "place" for e in d.entities)]
        linked = set(place_matches)
        hard_linked = len(linked - gold_place_rows)
        print("-" * 64)
        print("Internal reconciliation vs. svNames places.xml register:")
        print(f"   register place-name keys : {len(register)}")
        print(f"   place rows linked to geo : {len(linked)} / {len(pred_place)} "
              f"({100*len(linked)/max(len(pred_place),1):.1f}%)")
        print(f"   of those, hard-case rows promoted (not in exact set): "
              f"{hard_linked}")
        if llm_on:
            print(f"   LLM-linked hard cases (rule-based found nothing): "
                  f"{len(llm_links or {})}")
        elif llm_links is not None:
            print("   LLM linking: off (no ANTHROPIC_API_KEY/SDK, or --llm not set)")
    if out_path:
        print("-" * 64)
        print(f"candidates written to: {out_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("volume", nargs="?", default=DEFAULT_VOL,
                    help="path to a svNames TEI volume xml")
    ap.add_argument("--out", default="out/candidates.json",
                    help="output JSON path ('' to skip writing)")
    ap.add_argument("--register", default=DEFAULT_REGISTER,
                    help="path to svNames places.xml ('' to skip reconciliation)")
    ap.add_argument("--llm", action="store_true",
                    help="enable optional LLM linking for hard cases "
                         "(no-op unless ANTHROPIC_API_KEY + anthropic SDK present)")
    args = ap.parse_args(argv)
    return run(args.volume, args.out or None, args.register or None,
               use_llm=args.llm)


if __name__ == "__main__":
    raise SystemExit(main())
