"""Tests for ConstraintGraph — Dynamic Constraint Propagation."""

import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent


@pytest.fixture
def cg():
    from ecosynth.constraint_graph import ConstraintGraph
    return ConstraintGraph(
        compat_csv=ROOT / "data" / "reagent_compatibility.csv",
        chem21_csv=ROOT / "data" / "chem21_solvents.csv",
    )


class TestMonotoneReduction:
    def test_rxn_types_shrink_or_stay(self, cg):
        """Invariant: |T^(k+1)| ≤ |T^(k)|"""
        from ecosynth.constraint_graph import ALL_RXN_TYPES
        initial_count = len(cg.state.rxn_types)
        assert initial_count == len(ALL_RXN_TYPES)

        cg.propagate("CCO")  # ethanol: alcohol
        after_first = len(cg.state.rxn_types)
        assert after_first <= initial_count, "T must monotonically decrease"

        cg.propagate("CC(=O)O")  # acetic acid: carboxylic acid
        after_second = len(cg.state.rxn_types)
        assert after_second <= after_first, "T must monotonically decrease"

    def test_solvents_shrink_or_stay(self, cg):
        """S^(k) must only decrease on propagation."""
        initial_solvents = len(cg.state.solvents)
        cg.propagate("CC(=O)Cl")  # acyl chloride: blocks water, alcohol solvents
        after = len(cg.state.solvents)
        assert after <= initial_solvents


class TestSnapshotRestore:
    def test_restore_restores_exact_state(self, cg):
        snap = cg.snapshot()
        cg.propagate("CCO")
        cg.propagate("CC(=O)O")
        cg.restore(snap)
        restored = cg.state
        assert restored.rxn_types == snap.rxn_types
        assert restored.solvents == snap.solvents
        assert restored.excluded == snap.excluded

    def test_snapshot_is_immutable(self, cg):
        snap = cg.snapshot()
        cg.propagate("CCO")
        # snap should not be affected by propagation
        from ecosynth.constraint_graph import ALL_RXN_TYPES
        assert snap.rxn_types == ALL_RXN_TYPES


class TestExcludeAndQuery:
    def test_exclude_smiles_blocks_query(self, cg):
        smi = "CC(=O)Oc1ccccc1C(=O)O"  # aspirin
        assert cg.query_allowed(smi)
        cg.exclude_smiles(smi)
        assert not cg.query_allowed(smi)

    def test_get_violation_returns_message(self, cg):
        smi = "CCO"
        cg.exclude_smiles(smi)
        violation = cg.get_violation(smi)
        assert violation is not None
        assert "blacklisted" in violation.lower() or "smiles" in violation.lower()

    def test_get_violation_none_for_allowed(self, cg):
        assert cg.get_violation("CCO") is None


class TestFunctionalGroupDetection:
    def test_alcohol_detected(self, cg):
        fgs = cg._detect_functional_groups("CCO")
        assert "alcohol" in fgs

    def test_carboxylic_acid_detected(self, cg):
        fgs = cg._detect_functional_groups("CC(=O)O")
        assert "carboxylic_acid" in fgs

    def test_thiol_detected(self, cg):
        fgs = cg._detect_functional_groups("CCS")
        assert "thiol" in fgs

    def test_empty_string_returns_empty(self, cg):
        fgs = cg._detect_functional_groups("INVALID!!!!")
        assert len(fgs) == 0


class TestSeedFromContext:
    def test_seed_restricts_rxn_types(self, cg):
        from ecosynth.constraint_graph import ALL_RXN_TYPES
        initial = len(cg.state.rxn_types)
        # Seed with a small subset
        cg.seed_from_context({"rxn_types": ["oxidation", "reduction"]})
        after = len(cg.state.rxn_types)
        assert after <= initial

    def test_seed_empty_context_no_change(self, cg):
        snap = cg.snapshot()
        cg.seed_from_context({})
        assert cg.state.rxn_types == snap.rxn_types

    def test_query_solvent_present(self, cg):
        solvents = list(cg.state.solvents)
        if solvents:
            assert cg.query_solvent(solvents[0])
