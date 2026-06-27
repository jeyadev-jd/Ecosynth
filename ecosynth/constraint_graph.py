"""
Dynamic Constraint Propagation for EcoSynth.

Formal system: G_C^(k) = (R^(k), S^(k), T^(k), X^(k))
  R = allowed reagents (frozenset)
  S = allowed solvents (frozenset)
  T = allowed reaction-type classes (frozenset)
  X = excluded SMARTS patterns (frozenset)

Propagation φ: G_C^(k+1) = φ(G_C^(k), m_k)
  Monotone reduction: |T^(k+1)| ≤ |T^(k)| — sets only shrink, never grow.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Functional group SMARTS library — used to identify what's present in m_k
# ---------------------------------------------------------------------------
FG_SMARTS: dict[str, str] = {
    "alcohol":          "[OX2H][CX4]",
    "aldehyde":         "[CX3H1](=O)[#6]",
    "ketone":           "[CX3](=O)([#6])[#6]",
    "carboxylic_acid":  "[CX3](=O)[OX2H1]",
    "ester":            "[CX3](=O)[OX2][#6]",
    "amide":            "[CX3](=O)[NX3]",
    "amine":            "[NX3;H2,H1,H0;!$(NC=O)]",
    "thiol":            "[SH]",
    "sulfide":          "[SX2]([#6])[#6]",
    "alkene":           "[CX3]=[CX3]",
    "alkyne":           "[CX2]#[CX2]",
    "arene":            "c1ccccc1",
    "epoxide":          "[OX2r3]",
    "halide":           "[F,Cl,Br,I]",
    "nitrile":          "[CX2]#N",
    "nitro":            "[$([NX3](=O)=O),$([NX3+](=O)[O-])]",
    "anhydride":        "[CX3](=O)O[CX3]=O",
    "acyl_halide":      "[CX3](=O)[F,Cl,Br,I]",
    "boronate":         "[BX3]([OX2])[OX2]",
    "phosphate":        "[PX4](=O)([OX2])[OX2][OX2]",
    "silyl_ether":      "[SiX4][OX2][#6]",
    "diazo":            "[$([CX3]=[N+]=[N-]),$([CX3-][N+]#N)]",
    "azide":            "[$([NX1-]=[N+]=[N-]),$([NX1]#[N+][N-])]",
    "peroxide":         "[OX2][OX2]",
}

# Reaction type → required functional groups in substrate
# Propagation: if substrate has FG in key, intersect T^(k) with allowed_types
RXN_TYPE_FG_MAP: dict[str, list[str]] = {
    "acylation":         ["amine", "alcohol"],
    "alkylation":        ["amine", "alcohol", "thiol"],
    "aldol":             ["aldehyde", "ketone"],
    "amide_formation":   ["amine", "carboxylic_acid"],
    "cross_coupling":    ["arene", "halide", "boronate"],
    "cycloaddition":     ["alkene", "alkyne"],
    "epoxidation":       ["alkene"],
    "esterification":    ["alcohol", "carboxylic_acid"],
    "grignard":          ["aldehyde", "ketone", "ester"],
    "halogenation":      ["alkene", "arene"],
    "hydrogenation":     ["alkene", "alkyne", "nitro"],
    "michael":           ["alkene"],
    "oxidation":         ["alcohol", "aldehyde", "thiol", "sulfide"],
    "reduction":         ["aldehyde", "ketone", "ester", "carboxylic_acid", "nitro"],
    "retro_diels_alder": ["cycloaddition"],
    "wittig":            ["aldehyde", "ketone"],
    "buchwald_hartwig":  ["amine", "arene", "halide"],
    "suzuki":            ["arene", "boronate", "halide"],
    "heck":              ["arene", "halide", "alkene"],
    "sonogashira":       ["arene", "halide", "alkyne"],
    "negishi":           ["arene", "halide"],
    "stille":            ["arene", "halide"],
}

ALL_RXN_TYPES: frozenset[str] = frozenset(RXN_TYPE_FG_MAP.keys())

# Solvent compatibility: solvents blocked when specific FG present in substrate
# because of known side reactions
SOLVENT_FG_BLOCKS: dict[str, list[str]] = {
    "water":    ["acyl_halide", "anhydride", "diazo", "azide"],
    "alcohol":  ["acyl_halide", "anhydride"],
    "DCM":      [],  # generally compatible
    "THF":      [],
    "DMF":      ["strong_base"],
    "DMSO":     ["acid_chloride"],
    "toluene":  [],
    "acetone":  ["strong_base"],
    "hexane":   [],
    "EtOAc":    [],
    "MeCN":     [],
    "dioxane":  [],
}


@dataclass
class ConstraintState:
    """Immutable snapshot of G_C^(k) for snapshot/restore."""
    reagents:  frozenset[str]
    solvents:  frozenset[str]
    rxn_types: frozenset[str]
    excluded:  frozenset[str]  # SMARTS or canonical SMILES blacklist


class ConstraintGraph:
    """
    Mutable constraint graph; propagate() enforces monotone reduction.

    Invariant: after each call to propagate(), sets in state can only shrink.
    """

    def __init__(self, compat_csv: Path | None = None, chem21_csv: Path | None = None):
        self._compat_rules: list[dict] = []
        self._solvent_set: frozenset[str] = frozenset(SOLVENT_FG_BLOCKS.keys())

        if compat_csv and compat_csv.exists():
            with open(compat_csv) as f:
                reader = csv.DictReader(f)
                self._compat_rules = [row for row in reader]

        if chem21_csv and chem21_csv.exists():
            with open(chem21_csv) as f:
                reader = csv.DictReader(f)
                solv_names = set()
                for row in reader:
                    name = row.get("solvent", "").strip().lower()
                    if name:
                        solv_names.add(name)
            if solv_names:
                self._solvent_set = frozenset(solv_names)

        # Initial state: fully open (everything allowed)
        self._state = ConstraintState(
            reagents=frozenset(),   # empty = no restriction (all allowed)
            solvents=self._solvent_set,
            rxn_types=ALL_RXN_TYPES,
            excluded=frozenset(),
        )
        self._fg_cache: dict[str, frozenset[str]] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConstraintState:
        return self._state

    def propagate(self, intermediate_smiles: str) -> None:
        """φ(G_C^(k), m_k): update constraint state given accepted intermediate."""
        fgs = self._detect_functional_groups(intermediate_smiles)
        self._fg_cache[intermediate_smiles] = fgs

        # Update T^(k): intersect with reaction types applicable to detected FGs
        applicable_types: set[str] = set()
        for rxn_type, required_fgs in RXN_TYPE_FG_MAP.items():
            if any(fg in fgs for fg in required_fgs):
                applicable_types.add(rxn_type)
        # Monotone: only shrink T
        new_rxn_types = self._state.rxn_types & applicable_types if applicable_types else self._state.rxn_types

        # Update S^(k): remove solvents incompatible with detected FGs
        blocked_solvents: set[str] = set()
        for solvent, blocked_fgs in SOLVENT_FG_BLOCKS.items():
            if any(fg in fgs for fg in blocked_fgs):
                blocked_solvents.add(solvent)
        new_solvents = self._state.solvents - blocked_solvents

        # Update X^(k): add blacklist for known incompatible fragments
        new_excluded = set(self._state.excluded)
        for rule in self._compat_rules:
            ra, rb, sev = rule.get("reagent_a", ""), rule.get("reagent_b", ""), rule.get("severity", "warn")
            if sev == "block":
                for fg in fgs:
                    if fg in ra or fg in rb:
                        # Add the incompatible partner to excluded set as keyword
                        partner = rb if fg in ra else ra
                        new_excluded.add(f"reagent:{partner}")

        self._state = ConstraintState(
            reagents=self._state.reagents,  # R not changed by intermediate FG alone
            solvents=frozenset(new_solvents),
            rxn_types=frozenset(new_rxn_types),
            excluded=frozenset(new_excluded),
        )

    def exclude_smiles(self, smiles: str) -> None:
        """Explicitly blacklist a SMILES (used by LocalBranchRepair)."""
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            canonical = Chem.MolToSmiles(mol) if mol else smiles
        except Exception:
            canonical = smiles
        self._state = ConstraintState(
            reagents=self._state.reagents,
            solvents=self._state.solvents,
            rxn_types=self._state.rxn_types,
            excluded=self._state.excluded | {f"smiles:{canonical}"},
        )

    def query_allowed(self, smarts_or_smiles: str) -> bool:
        """Return True if this SMILES/SMARTS is not in the excluded set."""
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smarts_or_smiles)
            canonical = Chem.MolToSmiles(mol) if mol else smarts_or_smiles
        except Exception:
            canonical = smarts_or_smiles
        return f"smiles:{canonical}" not in self._state.excluded

    def query_solvent(self, solvent: str) -> bool:
        """Return True if solvent is still in S^(k)."""
        solvent_lower = solvent.lower()
        return any(solvent_lower in s.lower() or s.lower() in solvent_lower for s in self._state.solvents)

    def get_violation(self, smiles: str) -> str | None:
        """Return violation description if SMILES violates X^(k), else None."""
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            canonical = Chem.MolToSmiles(mol) if mol else smiles
        except Exception:
            canonical = smiles
        if f"smiles:{canonical}" in self._state.excluded:
            return f"SMILES blacklisted: {canonical}"
        fgs = self._detect_functional_groups(smiles)
        for excl in self._state.excluded:
            if excl.startswith("reagent:"):
                reagent = excl[len("reagent:"):]
                for fg in fgs:
                    if fg in reagent or reagent in fg:
                        return f"Reagent incompatibility: {reagent} with {fg}"
        return None

    def snapshot(self) -> ConstraintState:
        """Return immutable copy of current state for branch repair."""
        return ConstraintState(
            reagents=self._state.reagents,
            solvents=self._state.solvents,
            rxn_types=self._state.rxn_types,
            excluded=self._state.excluded,
        )

    def restore(self, snap: ConstraintState) -> None:
        """Restore to a prior snapshot (used after failed branch repair)."""
        self._state = snap

    def seed_from_context(self, context: dict) -> None:
        """
        Initialize constraints from RAG-retrieved precedent context.
        context keys: reagents, solvents, rxn_types (all lists of strings)
        """
        if "solvents" in context and context["solvents"]:
            # Intersect with current solvent set
            new_solvents = self._state.solvents & frozenset(s.lower() for s in context["solvents"])
            if new_solvents:  # only update if intersection is non-empty
                self._state = ConstraintState(
                    reagents=self._state.reagents,
                    solvents=new_solvents,
                    rxn_types=self._state.rxn_types,
                    excluded=self._state.excluded,
                )
        if "rxn_types" in context and context["rxn_types"]:
            ctx_types = frozenset(context["rxn_types"])
            new_types = self._state.rxn_types & ctx_types
            if new_types:
                self._state = ConstraintState(
                    reagents=self._state.reagents,
                    solvents=self._state.solvents,
                    rxn_types=new_types,
                    excluded=self._state.excluded,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_functional_groups(self, smiles: str) -> frozenset[str]:
        """Return set of functional group names present in SMILES."""
        if smiles in self._fg_cache:
            return self._fg_cache[smiles]
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return frozenset()
            found: set[str] = set()
            for name, smarts in FG_SMARTS.items():
                patt = Chem.MolFromSmarts(smarts)
                if patt and mol.HasSubstructMatch(patt):
                    found.add(name)
            result = frozenset(found)
            self._fg_cache[smiles] = result
            return result
        except Exception:
            return frozenset()
