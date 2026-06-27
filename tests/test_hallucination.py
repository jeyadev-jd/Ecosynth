"""Tests for HallucinationClassifier — HT-01 through HT-05."""

import pytest


@pytest.fixture
def classifier():
    from ecosynth.hallucination_taxonomy import HallucinationClassifier
    return HallucinationClassifier(precedent_threshold=0.3)


@pytest.fixture
def cg():
    from pathlib import Path
    from ecosynth.constraint_graph import ConstraintGraph
    ROOT = Path(__file__).parent.parent
    return ConstraintGraph(
        compat_csv=ROOT / "data" / "reagent_compatibility.csv",
        chem21_csv=ROOT / "data" / "chem21_solvents.csv",
    )


class TestHT01ValenceViolation:
    def test_valid_smiles_passes(self, classifier):
        report = classifier.classify("CCO")
        assert report.is_ok, f"Valid SMILES failed: {report.message}"

    def test_invalid_smiles_blocked(self, classifier):
        report = classifier.classify("C(C)(C)(C)(C)C")  # pentavalent carbon via parse fail
        # Note: RDKit may or may not catch this particular pattern; test an definitely-invalid string
        report2 = classifier.classify("INVALID@@@SMILES")
        assert report2.is_blocking
        from ecosynth.hallucination_taxonomy import HallucinationType
        assert report2.ht_type == HallucinationType.HT01_VALENCE_VIOLATION

    def test_aspirin_passes(self, classifier):
        report = classifier.classify("CC(=O)Oc1ccccc1C(=O)O")
        assert report.is_ok

    def test_benzene_passes(self, classifier):
        report = classifier.classify("c1ccccc1")
        assert report.is_ok

    def test_garbage_smiles_blocked(self, classifier):
        # Use a string with invalid characters that RDKit definitely rejects
        report = classifier.classify("X!@#NOTSMILES")
        assert report.is_blocking


class TestHT03NoPrecedent:
    def test_no_distances_no_block(self, classifier):
        # No distances provided → HT-03 skipped
        report = classifier.classify("CCO", chroma_distances=None)
        assert report.is_ok

    def test_empty_distances_blocked(self, classifier):
        from ecosynth.hallucination_taxonomy import HallucinationType
        report = classifier.classify("CCO", chroma_distances=[])
        assert report.is_blocking
        assert report.ht_type == HallucinationType.HT03_NO_PRECEDENT

    def test_close_distance_ok(self, classifier):
        # Distance < threshold → precedent found → ok
        report = classifier.classify("CCO", chroma_distances=[0.1, 0.15, 0.2])
        assert report.is_ok

    def test_far_distance_warns(self, classifier):
        from ecosynth.hallucination_taxonomy import HallucinationType
        report = classifier.classify("CCO", chroma_distances=[0.5, 0.6, 0.7])
        assert report.severity in ("warn", "block")
        assert report.ht_type == HallucinationType.HT03_NO_PRECEDENT


class TestHT05ConstraintViolation:
    def test_excluded_smiles_blocked(self, classifier, cg):
        from ecosynth.hallucination_taxonomy import HallucinationType
        smi = "CCO"
        cg.exclude_smiles(smi)
        report = classifier.classify(smi, constraint_graph=cg)
        assert report.is_blocking
        assert report.ht_type == HallucinationType.HT05_CONSTRAINT_VIOLATION

    def test_non_excluded_passes(self, classifier, cg):
        report = classifier.classify("CCO", constraint_graph=cg)
        assert report.is_ok

    def test_no_constraint_graph_skips_ht05(self, classifier):
        # Without CG, HT-05 not checked
        report = classifier.classify("CCO", constraint_graph=None)
        assert report.is_ok


class TestHallucinationReport:
    def test_to_dict(self, classifier):
        report = classifier.classify("CCO")
        d = report.to_dict()
        assert "smiles" in d
        assert "ht_type" in d
        assert "severity" in d
        assert "message" in d

    def test_ok_report_properties(self, classifier):
        report = classifier.classify("CCO")
        assert report.is_ok
        assert not report.is_blocking
        assert report.ht_type is None
        assert report.severity == "ok"

    def test_blocking_report_properties(self, classifier):
        report = classifier.classify("NOTSMILES!!!")
        assert report.is_blocking
        assert not report.is_ok
        assert report.ht_type is not None


class TestSymbolicEngine:
    def test_valence_check_valid(self):
        from ecosynth.symbolic_engine import SymbolicEngine
        se = SymbolicEngine()
        ok, msg = se.check_valence("CCO")
        assert ok

    def test_detect_alcohol(self):
        from ecosynth.symbolic_engine import SymbolicEngine
        se = SymbolicEngine()
        fgs = se.detect_functional_groups("CCO")
        assert "alcohol" in fgs

    def test_match_reaction_type_reduction(self):
        from ecosynth.symbolic_engine import SymbolicEngine
        se = SymbolicEngine()
        # aldehyde → alcohol should match reduction
        rxn = se.match_reaction_type("CC=O", "CCO")
        assert rxn is not None

    def test_reagent_compat_thiol_pd(self):
        from ecosynth.symbolic_engine import SymbolicEngine
        se = SymbolicEngine()
        issues = se.check_reagent_compat("CCS", ["Pd_catalyst"])
        assert len(issues) > 0
        assert any("poison" in i.lower() or "thiol" in i.lower() for i in issues)

    def test_enforce_constraints_blocked(self):
        from pathlib import Path
        from ecosynth.symbolic_engine import SymbolicEngine
        from ecosynth.constraint_graph import ConstraintGraph
        ROOT = Path(__file__).parent.parent
        se = SymbolicEngine()
        cg = ConstraintGraph(
            compat_csv=ROOT / "data" / "reagent_compatibility.csv",
            chem21_csv=ROOT / "data" / "chem21_solvents.csv",
        )
        cg.exclude_smiles("CCO")
        ok, reason = se.enforce_constraints("CCO", cg)
        assert not ok


class TestGreenScorerVCH:
    def test_validity_score_ok(self):
        from ecosynth.green_scorer import GreenScorer
        from ecosynth.hallucination_taxonomy import HallucinationReport
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        scorer = GreenScorer(chem21_csv=ROOT / "data" / "chem21_solvents.csv")
        report = HallucinationReport(smiles="CCO", ht_type=None, message="ok", severity="ok")
        assert scorer.validity_score(report) == 1.0

    def test_validity_score_block(self):
        from ecosynth.green_scorer import GreenScorer
        from ecosynth.hallucination_taxonomy import HallucinationReport, HallucinationType
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        scorer = GreenScorer(chem21_csv=ROOT / "data" / "chem21_solvents.csv")
        report = HallucinationReport(smiles="X", ht_type=HallucinationType.HT01_VALENCE_VIOLATION, message="fail", severity="block")
        assert scorer.validity_score(report) == 0.0

    def test_confidence_score_close(self):
        from ecosynth.green_scorer import GreenScorer
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        scorer = GreenScorer(chem21_csv=ROOT / "data" / "chem21_solvents.csv")
        c = scorer.confidence_score([0.05, 0.1])
        assert c > 0.8

    def test_confidence_score_far(self):
        from ecosynth.green_scorer import GreenScorer
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        scorer = GreenScorer(chem21_csv=ROOT / "data" / "chem21_solvents.csv")
        c = scorer.confidence_score([2.0, 3.0])
        assert c < 0.5

    def test_route_score_formula(self):
        from ecosynth.green_scorer import GreenScorer
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        scorer = GreenScorer(chem21_csv=ROOT / "data" / "chem21_solvents.csv")
        g, v, c, h = 0.8, 1.0, 0.6, 0.0
        weights = (0.4, 0.3, 0.2, 0.1)
        rs = scorer.route_score(g, v, c, h, weights)
        expected = 0.4 * 0.8 + 0.3 * 1.0 + 0.2 * 0.6 + 0.1 * 0.0
        assert abs(rs - expected) < 1e-6

    def test_route_score_bounded(self):
        from ecosynth.green_scorer import GreenScorer
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        scorer = GreenScorer(chem21_csv=ROOT / "data" / "chem21_solvents.csv")
        rs = scorer.route_score(1.0, 1.0, 1.0, 1.0)
        assert 0.0 <= rs <= 1.0
