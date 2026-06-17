"""Rule-based classification + entity distillation for comment rows.

Baseline for plan-v3 Stage 0.5/§5, now with two improvements requested after
the vol-14 run:

* **Splitting** — a single descriptive lemma can denote *several* entities
  (e.g. "Kingos Fødeby" -> person *Thomas Kingo* + place *Slangerup*;
  "Værrebro, og Frode" -> place *Værebro* + person *Frode*). Each row yields a
  list of typed `Entity` objects.
* **Noise reduction** — the comment apparatus across volumes is dominated by
  non-entities (archaic word glosses, foreign phrases, literary references).
  A row is only a named entity when at least one entity passes positive
  evidence; otherwise it is typed `gloss` / `phrase` / `work` / `other` and
  carries no entities.

Named-entity types: place, person, mythological.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tei_comments import CommentRow, normalize

NAMED_ENTITY_TYPES = {"place", "person", "mythological"}
_TYPE_PRIORITY = {"person": 3, "place": 2, "mythological": 1}

# --- lexical cues (Danish) -------------------------------------------------

PLACE_CUES = [
    "slot", "landsby", "købstad", "byen", "halvø", "ø,", "øen", "sogn",
    "herred", "amt", "gade", "stræde", "torv", "kanal", "havn", "ladeplads",
    "flod", "bjerg", "dal", "skov", "borg", "kirke", "kloster", "provins",
    "hovedstad", "landevej", "ved ", "nord for", "syd for", "øst for",
    "vest for", "beliggende", "ligger",
]
PERSON_CUES = [
    "digteren", "salmedigteren", "forfatteren", "forfatter", "astronomen",
    "maleren", "billedhuggeren", "komponisten", "filosoffen", "teologen",
    "præsten", "biskop", "professor", "general", "officeren", "adelsmanden",
    "godsejeren", "kong ", "konge", "kongen", "dronning", "prins", "prinds",
    "kejser", "hertug", "greve", "baron", "skuespiller", "lægen",
]
MYTH_CUES = [
    "mytologi", "i græsk", "i romersk", "i nordisk", "gudinde", " gud",
    "guden", "halvgud", "nymfe", "titan", "sagnkonge",
]
PHRASE_CUES = [
    "(tysk)", "(latin)", "(fransk)", "(græsk)", "(italiensk)", "(engelsk)",
    "(spansk)", "vending", "førstelinjen", "indledningslinjen", "citat",
    "citeret", "ordsprog", "talemåde", "replik",
]
WORK_CUES = [
    "komedie", "tragedie", "skuespil", "roman", "digt", "digtet", "digtning",
    "sang", "salme", "opera", "ballet", "bog", "værk", "skrift", "epistler",
    "avis", "tidsskrift",
]

PERSON_DATE = re.compile(r"\((?:[dfDF]\.\s*)?\d{3,4}(?:\s*[-–]\s*\d{0,4})?\)")
NAME_WITH_DATE = re.compile(
    r"([A-ZÆØÅ][\wÆØÅæøåüäöéèêç.'’-]+(?:\s+(?:[a-zæøå]+\s+)?"
    r"[A-ZÆØÅ\d][\wÆØÅæøåüäöéèêç.'’-]*){0,4})"
    r"\s*\((?:[dfDF]\.\s*)?\d{3,4}"
)
# capitalised name after a place preposition: "født i Slangerup", "ved Hven"
PREP_PLACE = re.compile(
    r"\b(?:ved|i|fra|mellem|nord for|syd for|øst for|vest for|nær)\s+"
    r"([A-ZÆØÅ][\wÆØÅæøå'’-]+)"
)


@dataclass
class Entity:
    name: str
    etype: str
    evidence: str


@dataclass
class Distilled:
    row: CommentRow
    primary_type: str
    confidence: float
    entities: list[Entity] = field(default_factory=list)
    cues: list[str] = field(default_factory=list)

    # backwards-compatible accessor
    @property
    def etype(self) -> str:
        return self.primary_type

    @property
    def is_named_entity(self) -> bool:
        return any(e.etype in NAMED_ENTITY_TYPES for e in self.entities)


def _hits(text: str, cues: list[str]) -> list[str]:
    low = text.lower()
    return [c for c in cues if c in low]


def _extract_persons(definition: str) -> list[Entity]:
    out, seen = [], set()
    for m in NAME_WITH_DATE.finditer(definition):
        name = m.group(1).strip(" .,–-")
        key = normalize(name)
        if len(name) > 2 and key not in seen:
            seen.add(key)
            out.append(Entity(name, "person", "name+date"))
    return out


def _extract_places(lemma: str, definition: str,
                    place_keys: set[str]) -> list[Entity]:
    out, seen = [], set()

    def add(name, evidence):
        key = normalize(name)
        if key and key not in seen:
            seen.add(key)
            out.append(Entity(name, "place", evidence))

    if normalize(lemma) in place_keys:
        add(lemma, "lemma=knownPlace")
    for m in PREP_PLACE.finditer(definition):
        cand = m.group(1)
        if normalize(cand) in place_keys:
            add(cand, "prep+knownPlace")
    return out


def classify(row: CommentRow, place_keys: set[str]) -> Distilled:
    """Classify a row. `place_keys` = normalized known place surfaces/register."""
    lemma, defn = row.lemma, row.definition
    cues: list[str] = []

    persons = _extract_persons(defn)
    places = _extract_places(lemma, defn, place_keys)

    place_cue_hits = _hits(defn, PLACE_CUES)
    person_cue_hits = _hits(defn, PERSON_CUES)
    myth_hits = _hits(defn, MYTH_CUES)

    # If a place cue fires but no known-place name was distilled, keep the
    # leading capitalised token of the lemma as a *candidate* place
    # (reconciliation will confirm or drop it -> noise reduction downstream).
    if place_cue_hits and not places:
        head = re.match(r"([A-ZÆØÅ][\wÆØÅæøå'’-]+)", lemma)
        if head:
            places = [Entity(head.group(1), "place", "placeCue+lemmaHead")]
            cues += place_cue_hits

    entities: list[Entity] = []
    entities += persons
    entities += places

    # mythological: only when no concrete person/place and a myth cue fires
    if myth_hits and not entities:
        entities.append(Entity(lemma, "mythological", "mythCue"))
        cues += myth_hits

    # --- noise reduction: classify non-entity rows -----------------------
    strong_phrase = (
        defn.lower().startswith(tuple(c for c in PHRASE_CUES if c.startswith("(")))
        or lemma.startswith(("»", "“", '"'))
    )
    if not entities:
        if strong_phrase or _hits(defn, PHRASE_CUES):
            return Distilled(row, "phrase", 0.5, [], ["phrase"])
        if _hits(defn, WORK_CUES):
            return Distilled(row, "work", 0.4, [], ["work"])
        if len(defn) <= 60 and defn[:1].islower():
            return Distilled(row, "gloss", 0.5, [], ["short-lowercase"])
        return Distilled(row, "other", 0.3, [], [])

    # A clear quote/foreign phrase lemma is noise even if a name appears in
    # the gloss (e.g. a quotation attributed to an author).
    if strong_phrase and not any(e.evidence == "lemma=knownPlace" for e in entities):
        return Distilled(row, "phrase", 0.5, [], ["strong-phrase"])

    # primary type = highest-priority entity type present
    primary = max((e.etype for e in entities),
                  key=lambda t: _TYPE_PRIORITY.get(t, 0))
    n_ne = len(entities)
    base = {"person": 0.7, "place": 0.6, "mythological": 0.55}[primary]
    if any(e.evidence == "lemma=knownPlace" for e in entities):
        base = max(base, 0.9)
    conf = round(min(base + 0.05 * (n_ne - 1), 0.95), 2)
    cues = (["dateSig"] if persons else []) + person_cue_hits + cues
    return Distilled(row, primary, conf, entities, cues)
