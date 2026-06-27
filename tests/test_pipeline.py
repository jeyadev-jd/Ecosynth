"""
Integration test for EcoSynth pipeline.

Runs the full pipeline on aspirin (SMILES: CC(=O)Oc1ccccc1C(=O)O).
Requires no Ollama/AizynthFinder — tests the fallback paths.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ecosynth.config import settings
from ecosynth.pipeline import EcoSynthPipeline, Preferences
from ecosynth.mol_utils import parse_smiles, canonicalise, morgan_fp, mol_weight


ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


# ---------- mol_utils ----------

def test_parse_smiles_valid():
    mol = parse_smiles(ASPIRIN)
    assert mol is not None


def test_parse_smiles_invalid():
    mol = parse_smiles("GARBAGE@@@")
    assert mol is None


def test_canonicalise():
    c = canonicalise("c1ccccc1")
    assert c is not None
    assert "c" in c.lower() or "C" in c


def test_morgan_fp_length():
    fp = morgan_fp(ASPIRIN)
    assert fp is not None
    assert len(fp) == 2048


def test_mol_weight():
    mw = mol_weight(ASPIRIN)
    assert 170 < mw < 200, f"Aspirin MW should be ~180, got {mw:.1f}"


# ---------- Pipeline (fallback mode, no Ollama / AizynthFinder) ----------

@pytest.fixture(scope="module")
def pipeline():
    return EcoSynthPipeline(settings)


def test_pipeline_invalid_smiles(pipeline):
    result = pipeline.synthesize("GARBAGE@@@")
    assert result.error is not None
    assert len(result.routes) == 0


def test_pipeline_returns_result(pipeline):
    result = pipeline.synthesize(ASPIRIN)
    # Even in fallback mode (no Ollama, no AizynthFinder) should return structure
    assert result.target_smiles == ASPIRIN
    assert result.canonical_smiles is not None
    # Routes may be empty if Ollama is down — that's acceptable in CI
    assert isinstance(result.routes, list)


def test_pipeline_gscore_in_range(pipeline):
    result = pipeline.synthesize(ASPIRIN)
    for route in result.routes:
        assert 0.0 <= route.g_score <= 1.0, f"G_score out of range: {route.g_score}"


def test_pipeline_routes_have_required_fields(pipeline):
    result = pipeline.synthesize(ASPIRIN)
    for route in result.routes:
        assert route.route_id
        assert isinstance(route.n_steps, int)
        assert isinstance(route.intermediates, list)
        assert isinstance(route.score_breakdown, dict)
        assert "g_score" in route.score_breakdown


def test_pipeline_preferences_accepted(pipeline):
    prefs = Preferences(greenness=0.8, steps=0.1, commercial=0.1)
    result = pipeline.synthesize(ASPIRIN, preferences=prefs)
    assert result.target_smiles == ASPIRIN


def test_pipeline_steerable(pipeline):
    result = pipeline.synthesize(ASPIRIN)
    if not result.routes:
        pytest.skip("No routes returned (Ollama/AizynthFinder not available).")
    first_route = result.routes[0]
    if not first_route.intermediates:
        pytest.skip("No intermediates in first route.")
    pin_smi = first_route.intermediates[0]
    result2 = pipeline.synthesize(ASPIRIN, pinned=[pin_smi])
    assert result2.target_smiles == ASPIRIN
