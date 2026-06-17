"""Rule-based classifier + entity distillation for editorial-comment rows.

This is the *baseline* the plan (v3, Stage 0.5) sets out to beat with later
context-aware methods. It is deliberately transparent: Danish lexical cues over
the lemma + definition decide an entity type, and a light distillation step
pulls the actual entity name(s) out of descriptive lemmas such as
"Kingos Fødeby" (-> person *Kingo* + place *Slangerup*).

Types: place, person, mythological, work, phrase, gloss, other.
Only `place`, `person`, `mythological` count as named entities here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tei_comments import CommentRow, normalize

NAMED_ENTITY_TYPES = {"place", "person", "mythological"}

# --- lexical cues (Danish) -------------------------------------------------

PLACE_CUES = [
    "slot", "landsby", "købstad", "by ", "byen", "ø,", "øen", "halvø", "sogn",
    "herred", "amt", "gade", "stræde", "torv", "kanal", "havn", "ladeplads",
    "flod", "flod,", "å,", "bjerg", "bjerge", "dal", "skov", "borg", "kirke",
    "kloster", "residensslot", "provins", "region", "hovedstad", "landevej",
    "ved ", "nord for", "syd for", "øst for", "vest for", "beliggende",
]
PLACE_LEMMA_CUES = ["fødeby", " øe", " ø", "broe", "broen", "veien", "vej"]

PERSON_CUES = [
    "digteren", "salmedigteren", "forfatteren", "forfatter", "skrev",
    "astronomen", "maleren", "billedhuggeren", "komponisten", "filosoffen",
    "teologen", "præsten", "biskop", "professor", "general", "officeren",
    "adelsmanden", "adelsdame", "godsejeren", "kong ", "konge", "kongen",
    "dronning", "prins", "prinds", "kejser", "kejserinde", "hertug", "greve",
    "baron", "fru ", "frøken", "skuespiller", "videnskabsmanden", "lægen",
]
# A "Name (1546-1601)" / "(d. 1086)" / "(f. 1782)" date signature.
PERSON_DATE = re.compile(r"\((?:[dfDF]\.\s*)?\d{3,4}(?:\s*[-–]\s*\d{0,4})?\)")
# Leading proper-name + date, e.g. "Thomas Kingo (1634-1703)".
NAME_WITH_DATE = re.compile(
    r"([A-ZÆØÅ][\wÆØÅæøåüäöéèêç.'’-]+(?:\s+(?:[a-zæøå]+\s+)?[A-ZÆØÅ\d][\wÆØÅæøåüäöéèêç.'’-]*){0,4})"
    r"\s*\((?:[dfDF]\.\s*)?\d{3,4}"
)

MYTH_CUES = [
    "mytologi", "i græsk", "i romersk", "i nordisk", "gudinde", " gud",
    "guden", "halvgud", "nymfe", "titan", "sagnkonge", "sagn",
]
PHRASE_CUES = [
    "(tysk)", "(latin)", "(fransk)", "(græsk)", "(italiensk)", "(engelsk)",
    "(spansk)", "vending", "førstelinjen", "indledningslinjen", "citat",
    "citeret", "ordsprog", "talemåde", "replik", "jf. ", "if. ",
]


@dataclass
class Distilled:
    row: CommentRow
    etype: str
    confidence: float
    entities: list[str]          # distilled entity name(s)
    cues: list[str]              # which cues fired (for transparency)

    @property
    def is_named_entity(self) -> bool:
        return self.etype in NAMED_ENTITY_TYPES


def _hits(text: str, cues: list[str]) -> list[str]:
    low = text.lower()
    return [c for c in cues if c in low]


def _distill_person_names(definition: str) -> list[str]:
    names = []
    for m in NAME_WITH_DATE.finditer(definition):
        name = m.group(1).strip(" .,–-")
        if len(name) > 2:
            names.append(name)
    return names


def classify(row: CommentRow, place_surface_norm: set[str]) -> Distilled:
    lemma, defn = row.lemma, row.definition
    low_def = defn.lower()
    cues: list[str] = []

    # Strong signal: lemma is literally a tagged place surface form.
    lemma_is_tagged_place = normalize(lemma) in place_surface_norm

    place_hits = _hits(defn, PLACE_CUES) + [c for c in PLACE_LEMMA_CUES if c in lemma.lower()]
    person_hits = _hits(defn, PERSON_CUES)
    has_person_date = bool(PERSON_DATE.search(defn))
    myth_hits = _hits(defn, MYTH_CUES)
    phrase_hits = _hits(defn, PHRASE_CUES) or lemma.startswith(("»", "“", '"'))

    # --- decide type (priority order) ------------------------------------
    # Strong phrase signal wins first: an explicit language tag "(tysk)" etc.
    # or a quoted lemma marks a quotation/foreign phrase, not an entity, even
    # if the gloss happens to mention a "god".
    strong_phrase = (
        low_def.startswith(("(tysk)", "(latin)", "(fransk)", "(græsk)",
                            "(italiensk)", "(engelsk)", "(spansk)"))
        or lemma.startswith(("»", "“", '"'))
    )
    if strong_phrase and not lemma_is_tagged_place:
        return Distilled(row, "phrase", 0.6, [], ["strong-phrase"])

    # Mythological beats person/place (its definitions often name a "god").
    if myth_hits and not lemma_is_tagged_place:
        cues = myth_hits
        return Distilled(row, "mythological", 0.6, [lemma], cues)

    # Place: tagged-place lemma, or definition/lemma place cues without a
    # dominating person-date signature.
    place_score = len(place_hits) + (2 if lemma_is_tagged_place else 0)
    person_score = len(person_hits) + (2 if has_person_date else 0)

    if phrase_hits and place_score == 0 and person_score == 0:
        return Distilled(row, "phrase", 0.5, [], list(phrase_hits) if isinstance(phrase_hits, list) else ["phrase"])

    if place_score and place_score >= person_score:
        conf = 0.9 if lemma_is_tagged_place else 0.55 + 0.1 * min(len(place_hits), 3)
        # distilled place name: prefer the tagged lemma, else first capitalised
        # token following a "ved/i/mellem" preposition in the definition.
        entities = [lemma] if lemma_is_tagged_place else _distill_place_names(lemma, defn)
        cues = (["lemma=taggedPlace"] if lemma_is_tagged_place else []) + place_hits
        return Distilled(row, "place", round(conf, 2), entities or [lemma], cues)

    if person_score:
        conf = 0.55 + 0.1 * min(person_score, 4)
        entities = _distill_person_names(defn) or [lemma]
        cues = (["dateSig"] if has_person_date else []) + person_hits
        return Distilled(row, "person", round(min(conf, 0.95), 2), entities, cues)

    if phrase_hits:
        return Distilled(row, "phrase", 0.5, [], ["phrase"])

    # Short lowercase synonym gloss, e.g. "haver." / "første, dygtigste."
    if len(defn) <= 60 and defn[:1].islower():
        return Distilled(row, "gloss", 0.5, [], ["short-lowercase"])

    return Distilled(row, "other", 0.3, [], [])


_PREP_PLACE = re.compile(
    r"\b(?:ved|i|mellem|nord for|syd for|øst for|vest for|nær)\s+"
    r"([A-ZÆØÅ][\wÆØÅæøå'’-]+)"
)


def _distill_place_names(lemma: str, definition: str) -> list[str]:
    out = []
    m = _PREP_PLACE.search(definition)
    if m:
        out.append(m.group(1))
    # also keep a clean capitalised head of the lemma if present
    head = re.match(r"([A-ZÆØÅ][\wÆØÅæøå'’-]+)", lemma)
    if head and head.group(1) not in out:
        out.append(head.group(1))
    return out
