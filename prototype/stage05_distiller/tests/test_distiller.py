"""Unit tests for the Stage 0.5 distiller. Stdlib unittest, no corpus needed."""

import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))   # make the modules importable

from tei_comments import (  # noqa: E402
    load_volume,
    load_place_register,
    load_person_register,
    normalize,
)
from classify import classify  # noqa: E402
from reconcile import (  # noqa: E402
    reconcile_place,
    reconcile_person,
    reconcile_entity_name,
    candidate_shortlist,
)
import reconcile_llm  # noqa: E402
import external_authority as ext  # noqa: E402
import export  # noqa: E402

VOL = os.path.join(HERE, "fixtures", "mini_volume.xml")
REG = os.path.join(HERE, "fixtures", "mini_places.xml")
PERSONS = os.path.join(HERE, "fixtures", "mini_persons.xml")


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.vol = load_volume(VOL)

    def test_only_textcomments_rows_ingested(self):
        # 5 textcomments rows; deviation + register rows excluded
        self.assertEqual(len(self.vol.rows), 5)
        ids = {r.rid for r in self.vol.rows}
        self.assertIn("txtcmnt-048-01", ids)
        self.assertNotIn("txtcmnt-048-06", ids)   # deviation row

    def test_body_placenames_exclude_apparatus_and_register(self):
        # geo-1 (Slangerup) and geo-2 (Roskilde) occur in running text only.
        self.assertEqual(set(self.vol.place_refs), {"geo-1", "geo-2"})
        self.assertIn(normalize("Roskilde"), self.vol.place_surface_norm)

    def test_page_derived_from_id(self):
        self.assertEqual(self.vol.rows[0].page, 48)


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.vol = load_volume(VOL)
        self.reg = load_place_register(REG)
        self.keys = set(self.vol.place_surface_norm) | set(self.reg)
        self.by_id = {
            r.rid: classify(r, self.keys) for r in self.vol.rows
        }

    def test_split_person_and_place(self):
        d = self.by_id["txtcmnt-048-01"]   # "Kingos Fødeby"
        types = {e.etype for e in d.entities}
        names = {e.name for e in d.entities}
        self.assertIn("person", types)
        self.assertIn("place", types)
        self.assertIn("Thomas Kingo", names)
        self.assertIn("Slangerup", names)

    def test_place_lemma(self):
        d = self.by_id["txtcmnt-048-02"]   # "Frederiksborg" / slot ved Hillerød
        self.assertTrue(any(e.etype == "place" for e in d.entities))

    def test_mythological(self):
        d = self.by_id["txtcmnt-048-03"]   # Morpheus
        self.assertEqual(d.primary_type, "mythological")

    def test_phrase_is_noise(self):
        d = self.by_id["txtcmnt-048-04"]   # German quote
        self.assertFalse(d.is_named_entity)
        self.assertEqual(d.primary_type, "phrase")

    def test_gloss_is_noise(self):
        d = self.by_id["txtcmnt-048-05"]   # "konstigt" -> word gloss
        self.assertFalse(d.is_named_entity)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.reg = load_place_register(REG)

    def test_exact(self):
        geo, method = reconcile_entity_name("Slangerup", self.reg)
        self.assertEqual(geo, ["geo-1"])
        self.assertEqual(method, "exact")

    def test_inflection(self):
        # genitive / definite forms collapse to the register key
        geo, method = reconcile_entity_name("Roskildes", self.reg)
        self.assertEqual(geo, ["geo-2"])
        self.assertEqual(method, "infl")

    def test_no_false_link(self):
        geo, method = reconcile_entity_name("Paris", self.reg)
        self.assertIsNone(geo)

    def test_reconcile_place_from_split_entity(self):
        vol = load_volume(VOL)
        keys = set(vol.place_surface_norm) | set(self.reg)
        d = classify(vol.rows[0], keys)   # Kingos Fødeby -> place Slangerup
        m = reconcile_place(d, self.reg)
        self.assertIsNotNone(m)
        self.assertIn("geo-1", m.geo_ids)


class PersonReconcileTests(unittest.TestCase):
    def setUp(self):
        self.persons = load_person_register(PERSONS)

    def test_indexes_gnd_and_sv_ids(self):
        # both id schemes are accepted as authority keys
        all_ids = set()
        for ids in self.persons.values():
            all_ids |= ids
        self.assertIn("gnd-118777157", all_ids)
        self.assertIn("SV_14_0134", all_ids)

    def test_flipped_sort_name_indexed(self):
        # "Brahe, Tycho" must also be reachable as "Tycho Brahe"
        self.assertIn(normalize("Tycho Brahe"), self.persons)

    def test_reconcile_person_from_split_entity(self):
        # "Kingos Fødeby" distils to person "Thomas Kingo" -> gnd id
        vol = load_volume(VOL)
        keys = set(vol.place_surface_norm)
        d = classify(vol.rows[0], keys)
        m = reconcile_person(d, self.persons)
        self.assertIsNotNone(m)
        self.assertIn("gnd-118777157", m.gnd_ids)


class LLMOptionalTests(unittest.TestCase):
    """The LLM path must be a graceful no-op without a key — keeps CI free."""

    def setUp(self):
        self.reg = load_place_register(REG)

    def test_unavailable_without_key(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            self.assertFalse(reconcile_llm.llm_available())
            # no key -> link returns None regardless of candidates
            link = reconcile_llm.llm_link(
                "Slangerup", "a village", [("geo-1", "slangerup")]
            )
            self.assertIsNone(link)
        finally:
            if old is not None:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_link_none_when_no_candidates(self):
        link = reconcile_llm.llm_link("Nowhere", "a place", [])
        self.assertIsNone(link)

    def test_shortlist_blocks_to_plausible_candidates(self):
        # "Roskilds" (inflected) should surface the Roskilde register entry
        cands = candidate_shortlist("Roskilds", self.reg)
        ids = {cid for cid, _ in cands}
        self.assertIn("geo-2", ids)


class ExternalAuthorityTests(unittest.TestCase):
    """Parsers are tested with canned JSON — never touch the network."""

    def test_parse_wikidata(self):
        data = {"search": [
            {"id": "Q1748", "label": "København",
             "description": "Denmarks hovedstad", "concepturi": "http://x/Q1748"},
            {"id": "", "label": "junk"},  # dropped (no id)
        ]}
        cands = ext.parse_wikidata(data)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].id, "Q1748")
        self.assertEqual(cands[0].source, "wikidata")

    def test_parse_gnd(self):
        data = {"member": [
            {"gndIdentifier": "118562347", "preferredName": "Kingo, Thomas",
             "type": ["DifferentiatedPerson", "AuthorityResource"],
             "id": "https://d-nb.info/gnd/118562347"},
        ]}
        cands = ext.parse_gnd(data)
        self.assertEqual(cands[0].id, "118562347")
        self.assertIn("DifferentiatedPerson", cands[0].description)

    def test_parse_geonames(self):
        data = {"geonames": [
            {"geonameId": 2614481, "name": "Roskilde", "countryName": "Denmark",
             "fcodeName": "seat of a first-order admin division",
             "lat": "55.64", "lng": "12.08", "fcode": "PPLA"},
        ]}
        cands = ext.parse_geonames(data)
        self.assertEqual(cands[0].id, "2614481")
        self.assertEqual(cands[0].extra["fcode"], "PPLA")

    def test_geonames_noop_without_username(self):
        old = os.environ.pop("GEONAMES_USERNAME", None)
        try:
            self.assertEqual(ext.search_geonames("Roskilde"), [])
        finally:
            if old is not None:
                os.environ["GEONAMES_USERNAME"] = old

    def test_fetch_offline_safe(self):
        # unreachable host -> None, never raises
        self.assertIsNone(ext._fetch("https://invalid.invalid.example/x"))

    def test_register_stub_place(self):
        c = ext.ExternalCandidate("geonames", "2614481", "Roskilde",
                                   "PPLA Denmark", "https://geonames.org/2614481",
                                   {"lat": "55.64", "lng": "12.08"})
        stub = ext.to_register_stub(c, "place")
        self.assertIn('xml:id="geo-2614481"', stub)
        self.assertIn("<geo>55.64 12.08</geo>", stub)


class ExportTests(unittest.TestCase):
    CANDS = [
        {  # internally linked person
            "label": "Kingos Fødeby", "entityType": "person",
            "isNamedEntity": True,
            "distilledEntities": [{"name": "Thomas Kingo", "type": "person"}],
            "definition": "salmedigteren ...",
            "provenance": {"ref": "txtcmnt-048-01", "page": 48, "file": "v14.xml"},
            "personReconciliation": {"gndIds": ["SV_14_0514"], "method": "exact"},
        },
        {  # unlinked place with an external Wikidata candidate
            "label": "Udby", "entityType": "place", "isNamedEntity": True,
            "distilledEntities": [{"name": "Udby", "type": "place"}],
            "definition": "landsby ved Vordingborg",
            "provenance": {"ref": "txtcmnt-050-02", "page": 50, "file": "v14.xml"},
            "externalCandidates": [
                {"source": "wikidata", "id": "Q123", "label": "Udby",
                 "description": "village", "uri": "http://wd/Q123"},
            ],
        },
        {  # non-entity noise — excluded from OpenRefine output
            "label": "konstigt", "entityType": "gloss", "isNamedEntity": False,
            "distilledEntities": [], "definition": "kunstigt",
            "provenance": {"ref": "txtcmnt-050-03", "page": 50, "file": "v14.xml"},
        },
    ]

    def test_rows_flatten_one_per_mention(self):
        rows = export.to_rows(self.CANDS)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["internalId"], "SV_14_0514")
        self.assertEqual(rows[1]["externalCandidates"], "wikidata:Q123")

    def test_openrefine_excludes_noise_and_shapes_candidates(self):
        objs = export.to_openrefine(self.CANDS)
        self.assertEqual(len(objs), 2)            # the gloss row dropped
        person = objs[0]
        self.assertTrue(person["candidates"][0]["match"])
        self.assertEqual(person["candidates"][0]["score"], 100)
        place = objs[1]
        self.assertFalse(place["candidates"][0]["match"])  # external = unconfirmed

    def test_quickstatements_for_wikidata(self):
        qs = export.to_quickstatements(self.CANDS)
        self.assertTrue(any(line.startswith("Q123\tLda") for line in qs))


if __name__ == "__main__":
    unittest.main()
