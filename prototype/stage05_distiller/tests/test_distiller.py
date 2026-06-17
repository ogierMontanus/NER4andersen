"""Unit tests for the Stage 0.5 distiller. Stdlib unittest, no corpus needed."""

import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))   # make the modules importable

from tei_comments import load_volume, load_place_register, normalize  # noqa: E402
from classify import classify  # noqa: E402
from reconcile import reconcile_place, reconcile_entity_name  # noqa: E402

VOL = os.path.join(HERE, "fixtures", "mini_volume.xml")
REG = os.path.join(HERE, "fixtures", "mini_places.xml")


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


if __name__ == "__main__":
    unittest.main()
