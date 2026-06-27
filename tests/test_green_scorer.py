"""Tests for the unified green scoring module."""

import sys
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ecosynth.green_scorer import GreenScorer

DATA_DIR = Path(__file__).parent.parent / "data"
CHEM21_CSV = DATA_DIR / "chem21_solvents.csv"


@pytest.fixture(scope="module")
def scorer():
    return GreenScorer(chem21_csv=CHEM21_CSV, rf_model_path=None)


# ---------- Atom Economy ----------

def test_atom_economy_esterification(scorer):
    # Aspirin synthesis: salicylic acid + acetic anhydride -> aspirin + acetic acid
    # AE: MW(aspirin=180) / (MW(salicylic=138) + MW(acetic_anhydride=102)) = ~75%
    ae = scorer.atom_economy(
        ["OC(=O)c1ccccc1O", "CC(=O)OC(C)=O"],
        "CC(=O)Oc1ccccc1C(=O)O"
    )
    assert 0.6 < ae < 0.9, f"Esterification AE should be ~75%, got {ae:.3f}"


def test_atom_economy_perfect(scorer):
    # Diels-Alder: all atoms incorporated into product — AE near 1.0
    ae = scorer.atom_economy(["C=CC=C", "C=C"], "C1CCCCC1")
    assert ae > 0.8, f"Diels-Alder AE should be high, got {ae:.3f}"


def test_atom_economy_invalid(scorer):
    ae = scorer.atom_economy(["INVALID@@@"], "CC")
    assert ae == 0.0


# ---------- E-Factor ----------

def test_e_factor_low_for_atom_efficient(scorer):
    ef = scorer.e_factor(["C=CC=C", "C=C"], "C1CCCCC1")
    assert ef < 0.5, f"Low-waste reaction should have low E-factor, got {ef:.3f}"


def test_e_factor_invalid(scorer):
    ef = scorer.e_factor(["GARBAGE"], "CC")
    assert ef == 100.0


# ---------- PMI ----------

def test_pmi_greater_than_one(scorer):
    pmi = scorer.pmi(["OC(=O)c1ccccc1O", "CC(=O)OC(C)=O"], "CC(=O)Oc1ccccc1C(=O)O")
    assert pmi >= 1.0, "PMI must be >= 1 (conservation of mass)"


def test_pmi_invalid(scorer):
    pmi = scorer.pmi(["GARBAGE"], "CC")
    assert pmi == 100.0


# ---------- CHEM21 ----------

def test_chem21_water_top(scorer):
    if not CHEM21_CSV.exists():
        pytest.skip("CHEM21 CSV not yet downloaded.")
    score = scorer.chem21_score("water")
    assert score >= 0.9, f"Water should score near 1.0, got {score:.3f}"


def test_chem21_benzene_low(scorer):
    if not CHEM21_CSV.exists():
        pytest.skip("CHEM21 CSV not yet downloaded.")
    score = scorer.chem21_score("benzene")
    assert score < 0.3, f"Benzene should score low, got {score:.3f}"


def test_chem21_unknown_fallback(scorer):
    score = scorer.chem21_score("some_unknown_solvent_xyz")
    assert 0.0 <= score <= 1.0


# ---------- Step Penalty ----------

def test_step_penalty_decreasing(scorer):
    scores = [scorer.step_penalty(n) for n in range(1, 8)]
    for i in range(len(scores) - 1):
        assert scores[i] > scores[i + 1], "Step penalty must decrease with more steps"


def test_step_penalty_one_step(scorer):
    sp = scorer.step_penalty(1)
    expected = math.exp(-0.2)
    assert abs(sp - expected) < 1e-6


# ---------- G_score ----------

def test_gscore_in_range(scorer):
    route = {
        "reactants": ["OC(=O)c1ccccc1O", "CC(=O)OC(C)=O"],
        "product": "CC(=O)Oc1ccccc1C(=O)O",
        "solvent": "ethanol",
        "n_steps": 2,
    }
    g = scorer.score_route(route)
    assert 0.0 <= g <= 1.0, f"G_score must be in [0,1], got {g}"


def test_gscore_greener_beats_wasteful(scorer):
    green_route = {
        "reactants": ["C=CC=C", "C=C"],
        "product": "C1CCCCC1",
        "solvent": "water",
        "n_steps": 1,
    }
    wasteful_route = {
        "reactants": ["c1ccccc1", "CCCCCCCCCCc1ccccc1"],
        "product": "CC",
        "solvent": "benzene",
        "n_steps": 6,
    }
    g_green = scorer.score_route(green_route)
    g_waste = scorer.score_route(wasteful_route)
    assert g_green > g_waste, f"Green route ({g_green:.3f}) should beat wasteful ({g_waste:.3f})"


def test_score_breakdown_keys(scorer):
    route = {
        "reactants": ["CCO", "CC(=O)O"],
        "product": "CC(=O)OCC",
        "solvent": "ethyl acetate",
        "n_steps": 1,
    }
    bd = scorer.score_breakdown(route)
    for key in ["g_score", "atom_economy", "e_factor", "pmi", "chem21_score", "step_penalty"]:
        assert key in bd, f"Missing key: {key}"
