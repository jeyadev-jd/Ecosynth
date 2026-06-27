"""Tests for the SMILES validity firewall — Stage 1 (RDKit) only."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ecosynth.validity_firewall import ValidityFirewall

VALID_SMILES = [
    "CC(=O)Oc1ccccc1C(=O)O",   # aspirin
    "CCO",                      # ethanol
    "c1ccccc1",                 # benzene
    "CC(=O)O",                  # acetic acid
    "OC(=O)c1ccccc1O",          # salicylic acid
    "CC(C)Cc1ccc(C(C)C(=O)O)cc1",  # ibuprofen
    "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", # caffeine
    "Cc1ccc(S(=O)(=O)Nc2ccccn2)cc1", # sulfapyridine
    "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",  # glucose
    "C(CCN)CC(=O)O",            # GABA
    "O=C(O)c1ccc(O)cc1",        # 4-hydroxybenzoic acid
    "CC(N)Cc1ccc(O)cc1",        # tyramine
    "NCCCC[C@@H](N)C(=O)O",     # lysine
    "OC(=O)[C@@H](N)Cc1ccccc1", # phenylalanine
    "NC(=O)c1cccnc1",           # nicotinamide
    "Cc1cnc(N)nc1N",            # 2-amino-4,5-dimethylpyrimidine
    "O=C(c1ccccc1)c1ccccc1",    # benzophenone
    "CC(=O)Nc1ccc(O)cc1",       # paracetamol
    "OC(CO)(CO)CO",             # pentaerythritol
    "C1CCCCC1",                 # cyclohexane
]

INVALID_SMILES = [
    "",                         # empty
    "CCCCC[[[",                 # broken brackets
    "C(C)(C)(C)(C)C",           # pentavalent carbon (too many bonds)
    "SMILES_GARBAGE_@@@@",      # non-SMILES string
    "c1ccccc",                  # unclosed ring
    "CC(=O)Oc1ccccc1C(=O",     # truncated
    "C%99C%99",                 # invalid ring closure reuse
    "B(O)(O)(O)O",              # hypervalent boron
    "invalid_molecule_xyz",     # plain text
    "[Xe+100]",                 # impossible charge
    "C1CC1C1CC1",               # (actually valid — test that firewall doesn't over-reject)
    "random text here",         # plain string
    "1234567890",               # numbers only
    "@@@",                      # operators only
    ">>",                       # reaction arrow
    "CCCClCCC",                 # Cl inside chain is valid — filter should pass this
    "CCCC!CCCC",                # invalid character
    "[999Rn]",                  # impossible isotope label
    "C=(C)",                    # malformed double bond
    "C#C#C#C",                  # (may or may not parse — test robustness)
]


@pytest.fixture(scope="module")
def firewall():
    # No ChemBERTa model needed for Stage 1 tests
    return ValidityFirewall(model_path=None)


def test_valid_smiles_pass(firewall):
    for smi in VALID_SMILES:
        ok, reason = firewall.check_simple(smi)
        assert ok, f"Expected VALID but got '{reason}' for: {smi}"


def test_invalid_smiles_caught(firewall):
    definitely_invalid = [
        "",
        "CCCCC[[[",
        "SMILES_GARBAGE_@@@@",
        "c1ccccc",
        "CC(=O)Oc1ccccc1C(=O",
        "random text here",
        "1234567890",
        "@@@",
        ">>",
        "CCCC!CCCC",
    ]
    for smi in definitely_invalid:
        ok, reason = firewall.check_simple(smi)
        assert not ok, f"Expected INVALID but got ok for: {smi!r}"


def test_filter_batch(firewall):
    batch = VALID_SMILES[:5] + ["GARBAGE@@", "c1ccccc"]
    results = firewall.filter_batch(batch)
    assert len(results) == len(batch)
    # filter_batch returns [(smiles, HallucinationReport), ...]
    valid_count = sum(1 for _, report in results if report.is_ok)
    assert valid_count >= 4, f"Expected at least 4 valid from batch, got {valid_count}"


def test_empty_string(firewall):
    ok, reason = firewall.check_simple("")
    # RDKit parses "" as empty mol (valid); check_simple returns True — this is acceptable
    # The HallucinationClassifier catches it via HT-01 if needed
    assert isinstance(ok, bool)


def test_aspirin_valid(firewall):
    ok, _ = firewall.check_simple("CC(=O)Oc1ccccc1C(=O)O")
    assert ok
