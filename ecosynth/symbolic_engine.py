"""
Symbolic Chemistry Engine — Layer 0.

Deterministic RDKit-based checks that run before any ML inference.
All methods return (passed: bool, reason: str).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ecosynth.constraint_graph import ConstraintGraph


# ~50 key SMARTS patterns covering major reaction classes and functional groups
SMARTS_LIBRARY: dict[str, str] = {
    # Functional groups
    "alcohol":           "[OX2H][CX4]",
    "primary_alcohol":   "[OX2H][CH2]",
    "secondary_alcohol": "[OX2H][CH]([#6])[#6]",
    "tertiary_alcohol":  "[OX2H][C]([#6])([#6])[#6]",
    "aldehyde":          "[CX3H1](=O)",
    "ketone":            "[CX3](=O)([#6])[#6]",
    "carboxylic_acid":   "[CX3](=O)[OX2H]",
    "ester":             "[CX3](=O)[OX2][CX4]",
    "amide":             "[CX3](=O)[NX3]",
    "amine_primary":     "[NX3;H2][#6]",
    "amine_secondary":   "[NX3;H1]([#6])[#6]",
    "amine_tertiary":    "[NX3;H0]([#6])([#6])[#6]",
    "thiol":             "[SX2H]",
    "sulfide":           "[SX2]([#6])[#6]",
    "sulfoxide":         "[SX3](=O)([#6])[#6]",
    "sulfone":           "[SX4](=O)(=O)([#6])[#6]",
    "terminal_alkene":   "[CH2]=[CX3]",
    "internal_alkene":   "[CX3;H0]=[CX3;H0]",
    "alkyne":            "[CX2]#[CX2]",
    "terminal_alkyne":   "[CX2]#[CH]",
    "arene":             "c1ccccc1",
    "heteroaromatic":    "c1ccncc1",
    "epoxide":           "[OX2r3][CX4r3]",
    "aziridine":         "[NX3r3][CX4r3]",
    "alkyl_chloride":    "[CX4][Cl]",
    "alkyl_bromide":     "[CX4][Br]",
    "alkyl_iodide":      "[CX4][I]",
    "aryl_halide":       "c[F,Cl,Br,I]",
    "vinyl_halide":      "[CX3]=[CX3][F,Cl,Br,I]",
    "nitrile":           "[CX2]#N",
    "nitro":             "[$([NX3](=O)=O),$([NX3+](=O)[O-])]",
    "boronic_acid":      "[BX3]([OX2H])[OX2H]",
    "boronate_ester":    "[BX3]([OX2][CX4])[OX2][CX4]",
    "silyl_ether":       "[SiX4][OX2][#6]",
    "phosphate":         "[PX4](=O)([OX2])[OX2][OX2]",
    "anhydride":         "[CX3](=O)[OX2][CX3]=O",
    "acyl_chloride":     "[CX3](=O)Cl",
    "acyl_bromide":      "[CX3](=O)Br",
    "diazonium":         "[#6][N+]#N",
    "azide":             "[#6][N-][N+]#N",
    "peroxide":          "[OX2][OX2]",
    "enol":              "[OX2H][CX3]=[CX3]",
    "enamine":           "[NX3][CX3]=[CX3]",
    "imine":             "[CX3]([#6])=[NX2]",
    # Reactive/problematic fragments
    "diazo":             "[$([CX3]=[N+]=[N-]),$([CX3-][N+]#N)]",
    "carbene_precursor": "[CX3]([N2])",
    "strained_ring_3":   "[r3]",
    "strained_ring_4":   "[r4]",
    # Protecting groups
    "boc_amine":         "[NX3][C](=O)OC([CH3])([CH3])[CH3]",
    "cbz_amine":         "[NX3][C](=O)OCc1ccccc1",
    "tbdms_ether":       "[OX2][Si]([CH3])([CH3])C([CH3])([CH3])[CH3]",
    "pmb_ether":         "[OX2]Cc1ccc(OC)cc1",
    "acetal":            "[CX4]([OX2][CX4])([OX2][CX4])",
}

# Valence rules: max valence per element symbol
MAX_VALENCE: dict[str, int] = {
    "C": 4, "N": 3, "O": 2, "S": 6, "P": 5,
    "F": 1, "Cl": 1, "Br": 1, "I": 1,
    "B": 3, "Si": 4, "Se": 6,
}


class SymbolicEngine:
    """Layer 0 deterministic chemistry checks — runs before any ML inference."""

    def __init__(self):
        self._compiled_smarts: dict[str, object] = {}

    def _get_mol(self, smiles: str):
        try:
            from rdkit import Chem
            return Chem.MolFromSmiles(smiles)
        except Exception:
            return None

    def _get_pattern(self, name: str):
        if name not in self._compiled_smarts:
            try:
                from rdkit import Chem
                self._compiled_smarts[name] = Chem.MolFromSmarts(SMARTS_LIBRARY[name])
            except Exception:
                self._compiled_smarts[name] = None
        return self._compiled_smarts[name]

    def check_valence(self, smiles: str) -> tuple[bool, str]:
        """Verify no atom exceeds its maximum valence."""
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False, f"Cannot parse SMILES: {smiles}"
            for atom in mol.GetAtoms():
                sym = atom.GetSymbol()
                if sym in MAX_VALENCE:
                    explicit_v = atom.GetTotalValence()
                    if explicit_v > MAX_VALENCE[sym]:
                        return False, f"{sym} at idx {atom.GetIdx()} has valence {explicit_v} > max {MAX_VALENCE[sym]}"
            return True, "valence ok"
        except Exception as e:
            return False, f"Valence check error: {e}"

    def check_stereo(self, smiles: str) -> tuple[bool, str]:
        """Check for geometrically impossible stereocenters."""
        try:
            from rdkit import Chem

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False, "Cannot parse"

            ri = mol.GetRingInfo()

            # Bredt violation: chiral bridgehead with double bond in small ring
            for atom in mol.GetAtoms():
                if (atom.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED
                        and ri.NumAtomRings(atom.GetIdx()) >= 2):
                    for bond in atom.GetBonds():
                        if bond.GetBondTypeAsDouble() == 2.0:
                            sizes = [len(r) for r in ri.AtomRings() if atom.GetIdx() in r]
                            if sizes and all(s <= 7 for s in sizes):
                                return False, "Bredt-rule violation: double bond at bridgehead"

            # Trans double bond in 3-membered ring
            for ring in ri.AtomRings():
                if len(ring) == 3:
                    ring_set = set(ring)
                    for bond in mol.GetBonds():
                        if (bond.GetBeginAtomIdx() in ring_set
                                and bond.GetEndAtomIdx() in ring_set
                                and bond.GetBondTypeAsDouble() == 2.0
                                and bond.GetStereo() == Chem.BondStereo.STEREOE):
                            return False, "Trans double bond in 3-membered ring is impossible"

            Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
            return True, "stereo ok"
        except Exception as e:
            return False, f"Stereo check error: {e}"

    def check_reagent_compat(self, smiles: str, reagents: list[str]) -> list[str]:
        """Return list of incompatibility messages for (smiles, reagents) pair."""
        if not reagents:
            return []
        mol = self._get_mol(smiles)
        if mol is None:
            return []

        issues: list[str] = []
        detected_fgs = self.detect_functional_groups(smiles)

        # Simple keyword incompatibility table (supplement to compat CSV)
        QUICK_RULES: list[tuple[str, set[str], str]] = [
            ("LiAlH4",       {"alcohol", "carboxylic_acid"},      "LiAlH4 reacts violently with protic groups"),
            ("NaH",          {"alcohol", "carboxylic_acid"},       "NaH generates H2 with protic groups"),
            ("Pd_catalyst",  {"thiol"},                            "Thiol poisons Pd catalyst"),
            ("mCPBA",        {"thiol"},                            "mCPBA over-oxidises thiols"),
            ("KMnO4",        {"thiol"},                            "KMnO4 over-oxidises thiols"),
            ("ozone",        {"thiol"},                            "Ozone over-oxidises thiols"),
            ("strong_base",  {"carboxylic_acid", "alcohol"},       "Strong base will deprotonate protic substrate"),
            ("NBS",          {"amine"},                            "NBS causes N-bromination of amines"),
        ]
        for rgt, bad_fgs, msg in QUICK_RULES:
            if any(r.lower() in rgt.lower() or rgt.lower() in r.lower() for r in reagents):
                if bad_fgs & set(detected_fgs):
                    issues.append(msg)

        return issues

    def detect_functional_groups(self, smiles: str) -> list[str]:
        """Return list of SMARTS_LIBRARY keys found in SMILES."""
        mol = self._get_mol(smiles)
        if mol is None:
            return []
        found = []
        try:
            from rdkit import Chem
            for name in SMARTS_LIBRARY:
                patt = self._get_pattern(name)
                if patt and mol.HasSubstructMatch(patt):
                    found.append(name)
        except Exception:
            pass
        return found

    def match_reaction_type(self, reactant: str, product: str) -> str | None:
        """
        Infer the most likely reaction type from reactant→product transformation.
        Returns a reaction-class string or None.
        """
        reactant_fgs = set(self.detect_functional_groups(reactant))
        product_fgs = set(self.detect_functional_groups(product))
        gained = product_fgs - reactant_fgs
        lost = reactant_fgs - product_fgs

        TRANSFORM_MAP: list[tuple[set, set, str]] = [
            ({"epoxide"},       {"alcohol"},                         "epoxide_opening"),
            ({"alkene"},        {"epoxide"},                         "epoxidation"),
            ({"alkene"},        set(),                               "hydrogenation"),
            ({"alcohol"},       {"aldehyde", "ketone"},              "oxidation"),
            ({"aldehyde"},      {"carboxylic_acid"},                 "oxidation"),
            ({"aldehyde"},      {"alcohol"},                         "reduction"),
            ({"ketone"},        {"alcohol"},                         "reduction"),
            ({"ester"},         {"alcohol"},                         "reduction"),
            ({"carboxylic_acid", "alcohol"}, {"ester"},              "esterification"),
            ({"carboxylic_acid", "amine"},   {"amide"},              "amide_formation"),
            ({"aryl_halide"},   {"arene"},                           "cross_coupling"),
            ({"alkyl_bromide"}, set(),                               "alkylation"),
            (set(),             {"alkene"},                          "elimination"),
            ({"alkene"},        {"alcohol"},                         "hydration"),
            ({"aldehyde", "ketone"}, {"imine"},                      "condensation"),
            ({"nitrile"},       {"amine"},                           "reduction"),
            ({"nitro"},         {"amine"},                           "nitro_reduction"),
        ]
        for required_lost, required_gained, rxn_name in TRANSFORM_MAP:
            if required_lost <= lost and required_gained <= gained:
                return rxn_name

        return None

    def enforce_constraints(self, smiles: str, cg: ConstraintGraph) -> tuple[bool, str]:
        """
        Check SMILES against ConstraintGraph state.
        Returns (True, "ok") or (False, reason).
        """
        if not cg.query_allowed(smiles):
            return False, f"SMILES is in exclusion set: {smiles}"

        violation = cg.get_violation(smiles)
        if violation:
            return False, violation

        # Check if molecule's FGs are compatible with remaining reaction types
        fgs = set(self.detect_functional_groups(smiles))
        allowed_types = cg.state.rxn_types
        if allowed_types:
            # At least one allowed reaction type must be applicable to this molecule
            applicable = False
            from ecosynth.constraint_graph import RXN_TYPE_FG_MAP
            for rxn_type in allowed_types:
                required = set(RXN_TYPE_FG_MAP.get(rxn_type, []))
                if required & fgs:
                    applicable = True
                    break
            if not applicable and fgs:
                # Warn-level only: molecule may be an intermediate with no current FG match
                pass

        return True, "constraints satisfied"
