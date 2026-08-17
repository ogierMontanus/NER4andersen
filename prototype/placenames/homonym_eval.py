"""Homonym detection for the merged place-name index.

The index deduplicates by name, so two different places that share a name
collapse into one row — *Tivoli* merges the Copenhagen pleasure garden with the
town east of Rome. Their editorial explanations then sit side by side in the
`explanation` column, separated by ` ¶ `, which is exactly the evidence needed
to spot the problem.

Two stages, cheap first:

  STAGE A — rule/NLP divergence (free, deterministic, always runs)
      Score how much the merged explanations disagree, using four complementary
      signals. Only rows above a threshold go any further.

  STAGE B — LLM adjudication (optional, only on what stage A flags)
      Ask a small model whether the notes describe one place or several, and to
      name the distinct places. Free no-op unless ANTHROPIC_API_KEY *and* the
      anthropic SDK are present, exactly like reconcile_llm.py.

Stage A on the full-edition index flags a few dozen rows out of 1 365, so the
LLM only ever sees the hard remainder.

Usage:
    python3 homonym_eval.py out/placenames-ALL.tsv                 # stage A only
    python3 homonym_eval.py out/placenames-ALL.tsv --llm           # + adjudicate
    python3 homonym_eval.py out/placenames-ALL.tsv --llm --dry-run # show prompts
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from itertools import combinations

# ---------------------------------------------------------------- stage A ---

# Optional: rapidfuzz gives a better token_set ratio. difflib is the fallback so
# the tool, and CI, need no third-party package.
try:
    from rapidfuzz import fuzz as _fuzz

    def _ratio(a: str, b: str) -> float:
        return _fuzz.token_set_ratio(a, b) / 100.0

    FUZZ_BACKEND = "rapidfuzz"
except ImportError:  # pragma: no cover - exercised only without rapidfuzz
    import difflib

    def _ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    FUZZ_BACKEND = "difflib"

# geographic head-nouns — kept in step with $TYPES in placename-index.xsl
TYPES = """by byen byer byerne købstad hovedstad landsby landsbyen flække provins
provinsen landskab landskabet region regionen amt herred sogn distrikt ø øen øer
øerne halvø holm flod floden elv å åen sund sundet fjord bugt hav havet sø søen
kanal vig stræde strædet bjerg bjerget bjerge bjergene bjergkæde bakke dal dalen
klippe plateau vulkan skov hede slette ørken gade gaden torv plads allé bro havn
havnen kaj promenade slot slottet borg borgen palads paladset kloster klosteret
klostret kirke kirken domkirke katedral tårn fæstning citadel ruin ruiner ruinerne
kilde gods herregård hovedgård forstad bydel kvarter residensslot kongerige
republik koloni hertugdømme grevskab næs odde kyst vandfald forlystelseshave
forlystelsespark park have teater universitet museum""".split()
TYPESET = set(TYPES)

# Danish function words — dropped before comparing content
STOP = set("""og i på ved til fra af den det de en et som der er var blev til med
for om han hun hans hendes sin sit deres men eller ikke har havde kan kunne skal
skulle vil ville nu da så her der hvor hvis mere meget lille store gamle nye
efter under over mellem ca jf se dvs bl.a m.fl osv samt hvor hvad""".split())

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def content_tokens(s: str) -> set[str]:
    return {t for t in (w.lower() for w in _WORD.findall(s)) if t not in STOP and len(t) > 2}


def head_noun(s: str) -> str | None:
    """First geographic head-noun — what the note says the thing *is*."""
    for w in (w.lower() for w in _WORD.findall(s)):
        if w in TYPESET:
            return w
        # compounds: havneby, klosterkirke, forlystelsespark
        for t in ("by", "kirke", "kloster", "bjerg", "havn", "gade", "slot",
                  "borg", "flod", "dal", "park", "have", "hav"):
            if len(w) > len(t) + 2 and w.endswith(t):
                return t
    return None


def proper_nouns(s: str) -> set[str]:
    """Capitalised words that are not sentence-initial — place/person context."""
    out = set()
    for sent in re.split(r"[.;¶]\s*", s):
        words = _WORD.findall(sent)
        for w in words[1:]:
            if w[:1].isupper() and len(w) > 2:
                out.add(_fold(w))
    return out


@dataclass
class Pair:
    a: int
    b: int
    divergence: float
    signals: dict = field(default_factory=dict)


def compare(a: str, b: str) -> Pair:
    ta, tb = content_tokens(a), content_tokens(b)
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 1.0
    fuz = _ratio(a, b)
    ha, hb = head_noun(a), head_noun(b)
    head_disagree = 1.0 if (ha and hb and ha != hb) else 0.0
    pa, pb = proper_nouns(a), proper_nouns(b)
    prop = len(pa & pb) / len(pa | pb) if (pa | pb) else 1.0

    # Divergence: lexical distance, plus the two domain signals that actually
    # separate a homonym from a paraphrase — the notes call it a different KIND
    # of thing, and they anchor it to different named contexts.
    score = (0.30 * (1 - jac)
             + 0.20 * (1 - fuz)
             + 0.30 * head_disagree
             + 0.20 * (1 - prop))
    return Pair(0, 0, round(score, 3), {
        "jaccard": round(jac, 3), "fuzz": round(fuz, 3),
        "head_a": ha, "head_b": hb, "head_disagree": bool(head_disagree),
        "proper_overlap": round(prop, 3),
    })


def row_divergence(notes: list[str]) -> Pair:
    """Worst disagreeing pair in a row — one bad pair is enough to suspect a homonym."""
    worst = Pair(0, 0, 0.0, {})
    for i, j in combinations(range(len(notes)), 2):
        p = compare(notes[i], notes[j])
        if p.divergence > worst.divergence:
            p.a, p.b = i, j
            worst = p
    return worst


def split_notes(explanation: str) -> list[str]:
    return [n.strip() for n in explanation.split("¶") if n.strip()]


def stage_a(rows: list[dict], threshold: float) -> list[dict]:
    out = []
    for r in rows:
        notes = split_notes(r["explanation"])
        if len(notes) < 2:
            continue
        p = row_divergence(notes)
        r = dict(r, _notes=notes, _divergence=p.divergence, _signals=p.signals,
                 _worst=(p.a, p.b))
        if p.divergence >= threshold:
            out.append(r)
    out.sort(key=lambda r: -r["_divergence"])
    return out


# ---------------------------------------------------------------- stage B ---

DEFAULT_MODEL = os.environ.get("NER4ANDERSEN_LLM_MODEL", "claude-haiku-4-5")

SYSTEM = (
    "You audit a place-name index built from a 19th-century Danish scholarly "
    "edition of Hans Christian Andersen. Index rows are deduplicated by name, so "
    "a single row may wrongly merge two different real places that share a name "
    "(e.g. Tivoli: the Copenhagen pleasure garden vs. the town east of Rome).\n"
    "Given one headword and the editorial notes merged under it, decide whether "
    "the notes describe ONE place or SEVERAL DIFFERENT places. Notes that "
    "paraphrase each other, or describe different aspects/periods of the same "
    "place, are ONE place. Answer only from the notes; do not use outside "
    "knowledge to invent distinctions. The notes are in Danish."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["one_place", "multiple_places", "unclear"]},
        "distinct_places": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "note_indices": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["label", "note_indices"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["verdict", "distinct_places", "confidence", "rationale"],
    "additionalProperties": False,
}


def llm_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def build_prompt(row: dict) -> str:
    notes = "\n".join(f"[{i}] {n}" for i, n in enumerate(row["_notes"]))
    return (f"Headword: {row['place']}\n"
            f"Andersen's spelling(s): {row['lemma_andersen']}\n"
            f"Volumes: {row['volumes']}   Years: {row['years']}\n\n"
            f"Editorial notes merged under this headword:\n{notes}\n\n"
            "One place or several?")


def llm_adjudicate(row: dict, model: str = DEFAULT_MODEL) -> dict | None:
    """Ask the model to adjudicate one flagged row. None when the LLM is off."""
    if not llm_available():
        return None
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_prompt(row)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


# -------------------------------------------------------------------- cli ---

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tsv", nargs="?", default="out/placenames-ALL.tsv")
    ap.add_argument("--threshold", type=float, default=0.35,
                    help="stage-A divergence at which a row is flagged (default 0.35)")
    ap.add_argument("--llm", action="store_true",
                    help="adjudicate flagged rows with an LLM (no-op without a key)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true",
                    help="with --llm, print the prompts instead of calling the API")
    ap.add_argument("--limit", type=int, default=0, help="cap LLM calls")
    ap.add_argument("--out", default="", help="write flagged rows + verdicts as JSON")
    args = ap.parse_args(argv)

    with open(args.tsv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    multi = [r for r in rows if len(split_notes(r["explanation"])) > 1]
    flagged = stage_a(rows, args.threshold)

    print(f"index rows                 : {len(rows)}")
    print(f"rows with >1 merged note   : {len(multi)}")
    print(f"flagged (divergence >= {args.threshold}) : {len(flagged)}"
          f"   [fuzz backend: {FUZZ_BACKEND}]")
    print("-" * 78)
    for r in flagged[:25]:
        s = r["_signals"]
        head = f"{s['head_a']}/{s['head_b']}" if s["head_disagree"] else (s["head_a"] or "-")
        print(f"  {r['_divergence']:.2f}  {r['place'][:24]:<25} vols={r['volumes'][:16]:<17}"
              f" heads={head}")

    results = []
    if args.llm:
        todo = flagged[: args.limit] if args.limit else flagged
        if args.dry_run:
            print("\n" + "=" * 78)
            print(f"DRY RUN — {len(todo)} prompt(s); model={args.model}")
            for r in todo[:2]:
                print("-" * 78)
                print(build_prompt(r))
        elif not llm_available():
            print("\nLLM adjudication skipped: set ANTHROPIC_API_KEY and install "
                  "`anthropic` (pip install -r requirements-llm.txt) to enable it.")
        else:
            print(f"\nadjudicating {len(todo)} row(s) with {args.model} …")
            for r in todo:
                v = llm_adjudicate(r, args.model)
                results.append({"place": r["place"], "divergence": r["_divergence"],
                                "verdict": v})
                if v:
                    print(f"  {r['place'][:26]:<27} {v['verdict']:<16} "
                          f"conf={v.get('confidence')}  {v.get('rationale','')[:60]}")

    if args.out:
        payload = [{k: v for k, v in r.items() if not k.startswith("_")}
                   | {"divergence": r["_divergence"], "signals": r["_signals"],
                      "notes": r["_notes"]} for r in flagged]
        by_place = {x["place"]: x["verdict"] for x in results}
        for p in payload:
            if p["place"] in by_place:
                p["llm_verdict"] = by_place[p["place"]]
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
