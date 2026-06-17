"""Optional LLM-assisted entity linking — plan-v3 Stage 2, hybrid path.

The rule-based reconciler (`reconcile.py`) links many place candidates to the
internal register by exact / inflection / token / fuzzy match. This module
handles the *hard cases* it can't: it asks Claude to pick the correct authority
id from a shortlist, using the entity's editorial definition as context.

It is **strictly optional and free by default**:

* No ``ANTHROPIC_API_KEY`` in the environment  → `llm_available()` is False and
  `llm_link()` returns ``None`` (the caller keeps the rule-based result).
* `anthropic` SDK not installed                → same graceful no-op.

So the pipeline — and CI — runs with zero API dependency; the LLM path activates
only when a key is present *and* the SDK is installed. Default model is the cheap
``claude-haiku-4-5``; override with ``NER4ANDERSEN_LLM_MODEL``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

DEFAULT_MODEL = os.environ.get("NER4ANDERSEN_LLM_MODEL", "claude-haiku-4-5")

_SYSTEM = (
    "You are an authority-control assistant for a scholarly edition of Hans "
    "Christian Andersen's travel writings (19th-century Danish). Given an entity "
    "mention, its editorial gloss, and a shortlist of candidate authority records, "
    "decide which candidate denotes the SAME real-world entity. Use dates, "
    "occupation, and geography in the gloss to disambiguate. If none of the "
    "candidates is clearly the same entity, return null — do not guess."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "authority_id": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["authority_id", "confidence", "rationale"],
    "additionalProperties": False,
}


@dataclass
class LLMLink:
    authority_id: str | None
    confidence: float
    rationale: str
    source: str = "llm"


def llm_available() -> bool:
    """True only when both an API key and the anthropic SDK are present."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def llm_link(
    name: str,
    definition: str,
    candidates: list[tuple[str, str]],
    *,
    model: str = DEFAULT_MODEL,
) -> LLMLink | None:
    """Pick the authority id for `name` from `candidates` [(id, display_name)].

    Returns an `LLMLink`, or ``None`` when the LLM path is unavailable (no key /
    no SDK) or when there are no candidates to choose from — in every no-op case
    the caller should fall back to its rule-based result.
    """
    if not candidates or not llm_available():
        return None

    import anthropic

    shortlist = "\n".join(f"- {cid}: {disp}" for cid, disp in candidates)
    user = (
        f"Entity mention: {name}\n"
        f"Editorial gloss: {definition}\n\n"
        f"Candidate authority records:\n{shortlist}\n\n"
        "Return the id of the matching candidate, or null."
    )

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=[{"type": "text", "text": _SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(text)

    valid_ids = {cid for cid, _ in candidates}
    aid = data.get("authority_id")
    if aid is not None and aid not in valid_ids:
        aid = None  # never accept an id the model invented
    return LLMLink(
        authority_id=aid,
        confidence=float(data.get("confidence", 0.0)),
        rationale=str(data.get("rationale", "")),
    )
