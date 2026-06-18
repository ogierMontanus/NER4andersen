"""Curation export — plan-v3 §9 Deliverable D / spec Stage 3.

Turn the distiller's candidate records (the JSON written by `distill.py`) into
formats a curator can act on:

* **CSV** — one row per entity mention (flat, opens in Excel / OpenRefine).
* **OpenRefine reconciliation candidates** — JSONL, one object per mention, with
  `candidates` in the OpenRefine recon-result shape
  (`{id, name, score, match}`), ready to seed a reconciliation column.
* **QuickStatements** — a Wikibase-style stub for mentions whose external
  candidate is a Wikidata Q-id (Label + described-at-URL), for round-tripping
  curated links into a Wikibase.

Pure functions over the candidate list (stdlib only) — unit-tested, no network.
"""

from __future__ import annotations

import argparse
import csv
import json

CSV_COLUMNS = [
    "ref", "page", "file", "lemma", "entityType", "isNamedEntity",
    "entityName", "entityKind", "internalId", "method", "externalCandidates",
    "definition",
]


def _primary_entity(rec: dict) -> dict | None:
    ents = rec.get("distilledEntities") or []
    return ents[0] if ents else None


def _internal_id(rec: dict) -> tuple[str, str]:
    """Return (id, method) from whichever reconciliation fired, else ('', '')."""
    pr = rec.get("personReconciliation")
    if pr and pr.get("gndIds"):
        return pr["gndIds"][0], pr.get("method", "")
    rc = rec.get("reconciliation")
    if rc and rc.get("geoIds"):
        return rc["geoIds"][0], rc.get("method", "")
    return "", ""


def to_rows(candidates: list[dict]) -> list[dict]:
    """Flat one-mention-per-row dicts for CSV / OpenRefine."""
    rows = []
    for rec in candidates:
        ent = _primary_entity(rec)
        internal_id, method = _internal_id(rec)
        ext = rec.get("externalCandidates") or []
        prov = rec.get("provenance", {})
        rows.append({
            "ref": prov.get("ref", ""),
            "page": prov.get("page", ""),
            "file": prov.get("file", ""),
            "lemma": rec.get("label", ""),
            "entityType": rec.get("entityType", ""),
            "isNamedEntity": rec.get("isNamedEntity", False),
            "entityName": ent["name"] if ent else "",
            "entityKind": ent["type"] if ent else "",
            "internalId": internal_id,
            "method": method,
            "externalCandidates": "; ".join(
                f"{c['source']}:{c['id']}" for c in ext
            ),
            "definition": rec.get("definition", ""),
        })
    return rows


def write_csv(candidates: list[dict], path: str) -> None:
    rows = to_rows(candidates)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def to_openrefine(candidates: list[dict]) -> list[dict]:
    """One recon object per *named-entity* mention, candidates in OpenRefine shape.

    Internal matches are emitted as a confirmed candidate (score 100, match
    true); external proposals as unconfirmed candidates for the curator to pick.
    """
    out = []
    for rec in candidates:
        if not rec.get("isNamedEntity"):
            continue
        ent = _primary_entity(rec)
        if not ent:
            continue
        cands = []
        internal_id, _ = _internal_id(rec)
        if internal_id:
            cands.append({"id": internal_id, "name": ent["name"],
                          "score": 100, "match": True})
        for c in rec.get("externalCandidates") or []:
            cands.append({"id": f"{c['source']}:{c['id']}",
                          "name": c.get("label", ""), "score": 50, "match": False})
        out.append({
            "ref": rec.get("provenance", {}).get("ref", ""),
            "cell": ent["name"],
            "type": ent["type"],
            "candidates": cands,
        })
    return out


def write_openrefine(candidates: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for obj in to_openrefine(candidates):
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def to_quickstatements(candidates: list[dict]) -> list[str]:
    """QuickStatements V1 lines for mentions linked to a Wikidata Q-id."""
    lines = []
    for rec in candidates:
        for c in rec.get("externalCandidates") or []:
            if c.get("source") == "wikidata" and c.get("id", "").startswith("Q"):
                label = (_primary_entity(rec) or {}).get("name", "")
                lines.append(f'{c["id"]}\tLda\t"{label}"')
                if c.get("uri"):
                    lines.append(f'{c["id"]}\tS854\t"{c["uri"]}"')
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates", help="candidates JSON written by distill.py")
    ap.add_argument("--csv", default="out/curation.csv")
    ap.add_argument("--openrefine", default="out/curation.openrefine.jsonl")
    ap.add_argument("--quickstatements", default="")
    args = ap.parse_args(argv)

    with open(args.candidates, encoding="utf-8") as fh:
        candidates = json.load(fh)

    if args.csv:
        write_csv(candidates, args.csv)
        print(f"CSV            -> {args.csv} ({len(candidates)} rows)")
    if args.openrefine:
        write_openrefine(candidates, args.openrefine)
        print(f"OpenRefine     -> {args.openrefine}")
    if args.quickstatements:
        with open(args.quickstatements, "w", encoding="utf-8") as fh:
            fh.write("\n".join(to_quickstatements(candidates)) + "\n")
        print(f"QuickStatements-> {args.quickstatements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
