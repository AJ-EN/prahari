"""Tests for the plate grammar, constrained decoder, and confusion matcher."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prahari.common import plate_grammar as g


class TestParse:
    def test_modern_standard(self):
        p = g.parse("GJ 01 AB 1234")
        assert p.valid and p.state_code == "GJ" and p.district == 1
        assert p.district_name == "Ahmedabad" and p.series == "AB"

    def test_normalisation_strips_separators(self):
        for s in ["GJ-01-AB-1234", "gj01ab1234", "GJ 01 AB 1234", "GJ.01.AB.1234"]:
            assert g.parse(s).plate == "GJ01AB1234"

    def test_bad_state_code_rejected(self):
        p = g.parse("XX01AB1234")
        assert not p.valid and "not a valid state code" in p.reasons[0]

    def test_district_out_of_range_rejected(self):
        # Gujarat issues GJ-01..GJ-39; GJ-77 cannot exist.
        p = g.parse("GJ77AB1234")
        assert not p.valid and "out of range" in p.reasons[0]

    def test_bh_series(self):
        p = g.parse("22BH1234AA")
        assert p.valid and p.state_code == "BH"

    def test_garbage_rejected(self):
        assert not g.parse("HELLO").valid
        assert not g.parse("").valid


class TestConfusionDistance:
    def test_identical_is_zero(self):
        assert g.confusion_distance("GJ01AB1234", "GJ01AB1234") == 0.0

    def test_known_confusion_is_cheap(self):
        # O/0 is the single most common OCR confusion on plates.
        assert g.confusion_distance("GJ01ABO234", "GJ01AB0234") < 0.15

    def test_unrelated_substitution_is_expensive(self):
        # W and 3 are not confusable by any real OCR engine.
        assert g.confusion_distance("GJ01ABW234", "GJ01AB3234") >= 1.0

    def test_symmetric(self):
        a, b = "GJ01AB1234", "GJ01AB1Z34"
        assert g.confusion_distance(a, b) == g.confusion_distance(b, a)


class TestConstrainedDecode:
    def test_repairs_a_realistic_misread(self):
        # 6->G, 8->B, I->1: all well-attested confusions.
        cands = g.constrained_decode("6J01A8I234")
        assert cands and cands[0].plate == "GJ01AB1234"

    def test_every_candidate_is_grammatically_valid(self):
        for raw in ["6J01A8I234", "GJ0IAB1Z34", "GJ27TU9O12", "22BH1Z34AA"]:
            for c in g.constrained_decode(raw):
                assert g.is_valid(c.plate), f"{c.plate} from {raw} is not valid"

    def test_refuses_to_invent_a_plate_from_nothing(self):
        # 'W' has no attested OCR confusion with any other letter, and 'WJ' is
        # not a state code, so nothing valid is reachable. The decoder must
        # return nothing rather than hallucinate a plausible-looking plate.
        assert g.constrained_decode("WJ01AB1234") == []

    def test_zero_to_G_is_repaired(self):
        # 0/G is a real confusion on plates (both closed round glyphs), so
        # '0J05AB1234' SHOULD resolve to a Gujarat plate. This documents
        # intended behaviour, not a bug.
        cands = g.constrained_decode("0J05AB1234")
        assert cands and cands[0].plate == "GJ05AB1234"

    def test_edits_are_explainable(self):
        c = g.constrained_decode("GJ27TU9O12")[0]
        assert c.edits and "O->0" in c.edits[0]
        assert "corrected" in c.explain()


class TestWatchlistMatching:
    WL = {
        "GJ01AB1234": {"type": "stolen_vehicle"},
        "GJ18BC5678": {"type": "wanted_person"},
        "MH12XY9999": {"type": "blacklisted"},
    }

    def test_exact_match_scores_perfectly(self):
        hits = g.match_watchlist("GJ18BC5678", self.WL)
        assert hits[0].exact and hits[0].score == 1.0
        assert g.should_alert(hits[0])

    def test_single_misread_still_alerts(self):
        # This is the case naive `WHERE plate = ?` loses silently.
        hits = g.match_watchlist("GJ01AB1Z34", self.WL)
        assert hits[0].watchlist_plate == "GJ01AB1234"
        assert g.should_alert(hits[0])

    def test_heavy_misread_lands_in_review_not_silence(self):
        hits = g.match_watchlist("6J01A8I234", self.WL)
        assert hits and hits[0].watchlist_plate == "GJ01AB1234"
        # Found, but correctly not confident enough to auto-alert.
        assert not g.should_alert(hits[0])

    def test_unrelated_plate_raises_no_alert(self):
        hits = g.match_watchlist("RJ14ZZ0001", self.WL)
        assert not any(g.should_alert(h) for h in hits)

    def test_accepts_bare_list_watchlist(self):
        hits = g.match_watchlist("GJ01AB1234", ["GJ01AB1234", "MH12XY9999"])
        assert hits[0].exact
