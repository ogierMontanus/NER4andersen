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

from tei_comments import load_volume, normalize
from classify import classify, NAMED_ENTITY_TYPES

DEFAULT_VOL = (
    "/home/user/svNames/data/"
    "noHiSeg_Andersen 14 - Rejseskildringer I_w_notes_Rebecca.xml"
)


def run(vol_path: str, out_path: str | None) -> int:
    vol = load_volume(vol_path)
    if not vol.rows:
        print(f"No comment rows found in {vol_path}", file=sys.stderr)
        return 2

    distilled = [classify(r, vol.place_surface_norm) for r in vol.rows]

    # --- candidate records (the spec's unified shape, provenance kept) ----
    candidates = []
    for d in distilled:
        candidates.append(
            {
                "label": d.row.lemma,
                "entityType": d.etype,
                "isNamedEntity": d.is_named_entity,
                "confidence": d.confidence,
                "distilledEntities": d.entities,
                "cues": d.cues,
                "definition": d.row.definition,
                "provenance": {
                    "source": "editorial-comment",
                    "ref": d.row.rid,
                    "page": d.row.page,
                    "file": os.path.basename(vol_path),
                },
            }
        )

    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(candidates, fh, ensure_ascii=False, indent=2)

    _report(vol, distilled, out_path)
    return 0


def _report(vol, distilled, out_path):
    counts = Counter(d.etype for d in distilled)
    ne = sum(1 for d in distilled if d.is_named_entity)

    # Gold place set: rows whose lemma exactly matches a tagged placeName
    # surface form (the 284-row baseline in volume 14).
    gold_place_rows = {
        d.row.rid for d in distilled if normalize(d.row.lemma) in vol.place_surface_norm
    }
    pred_place_rows = {d.row.rid for d in distilled if d.etype == "place"}

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
    print("Place identification vs. tagged-place lemmas (gold = exact match):")
    print(f"   gold place rows : {len(gold_place_rows)}")
    print(f"   predicted place : {len(pred_place_rows)}")
    print(f"   TP={tp}  FP={fp}  FN={fn}")
    print(f"   precision={prec:.3f}  recall={rec:.3f}  F1={f1:.3f}")
    print(f"   (FP = place-typed rows beyond the exact set: candidate new / "
          f"inflected places — the hard cases)")
    if out_path:
        print("-" * 64)
        print(f"candidates written to: {out_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("volume", nargs="?", default=DEFAULT_VOL,
                    help="path to a svNames TEI volume xml")
    ap.add_argument("--out", default="out/candidates.json",
                    help="output JSON path ('' to skip writing)")
    args = ap.parse_args(argv)
    return run(args.volume, args.out or None)


if __name__ == "__main__":
    raise SystemExit(main())
