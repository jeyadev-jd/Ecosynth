"""
Hallucination Taxonomy for EcoSynth.

HT-01  VALENCE_VIOLATION       — atom exceeds allowed valence (RDKit parse fail)
HT-02  STEREO_IMPOSSIBLE       — stereochemistry geometrically infeasible
HT-03  NO_PRECEDENT            — no ChromaDB precedent above similarity threshold
HT-04  REAGENT_INCOMPATIBILITY — known chemical incompatibility in reagent table
HT-05  CONSTRAINT_VIOLATION    — violates active ConstraintGraph state G_C^(k)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ecosynth.constraint_graph import ConstraintGraph


class HallucinationType(str, Enum):
    HT01_VALENCE_VIOLATION       = "HT-01"
    HT02_STEREO_IMPOSSIBLE       = "HT-02"
    HT03_NO_PRECEDENT            = "HT-03"
    HT04_REAGENT_INCOMPATIBILITY = "HT-04"
    HT05_CONSTRAINT_VIOLATION    = "HT-05"


@dataclass
class HallucinationReport:
    smiles: str
    ht_type: HallucinationType | None
    message: str
    severity: str  # "ok" | "warn" | "block"
    details: dict = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return self.severity in ("ok", "warn")

    @property
    def is_blocking(self) -> bool:
        return self.severity == "block"

    def to_dict(self) -> dict:
        return {
            "smiles": self.smiles,
            "ht_type": self.ht_type.value if self.ht_type else None,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


def _ok(smiles: str) -> HallucinationReport:
    return HallucinationReport(smiles=smiles, ht_type=None, message="ok", severity="ok")


class HallucinationClassifier:
    """Classify SMILES against the five hallucination types."""

    def __init__(self, precedent_threshold: float = 0.3):
        self.precedent_threshold = precedent_threshold

    def classify(
        self,
        smiles: str,
        constraint_graph: ConstraintGraph | None = None,
        chroma_distances: list[float] | None = None,
        reagents_in_route: list[str] | None = None,
    ) -> HallucinationReport:
        """Run all checks in priority order; return first blocking hit, worst warn, or ok."""
        worst_warn: HallucinationReport | None = None

        for report in [
            self._check_ht01(smiles),
            self._check_ht02(smiles),
            self._check_ht03(smiles, chroma_distances),
            self._check_ht04(smiles, reagents_in_route or []),
        ]:
            if report.is_blocking:
                return report
            if report.severity == "warn":
                worst_warn = report

        if constraint_graph is not None:
            report = self._check_ht05(smiles, constraint_graph)
            if report.is_blocking:
                return report
            if report.severity == "warn":
                worst_warn = report

        return worst_warn if worst_warn is not None else _ok(smiles)

    def _check_ht01(self, smiles: str) -> HallucinationReport:
        """HT-01: RDKit valence check."""
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return HallucinationReport(
                    smiles=smiles,
                    ht_type=HallucinationType.HT01_VALENCE_VIOLATION,
                    message="RDKit parse failed — likely valence violation",
                    severity="block",
                )
            # Explicit sanitization to catch subtler valence errors
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                return HallucinationReport(
                    smiles=smiles,
                    ht_type=HallucinationType.HT01_VALENCE_VIOLATION,
                    message=f"Sanitization failed: {e}",
                    severity="block",
                )
        except Exception as e:
            return HallucinationReport(
                smiles=smiles,
                ht_type=HallucinationType.HT01_VALENCE_VIOLATION,
                message=f"RDKit error: {e}",
                severity="block",
            )
        return _ok(smiles)

    def _check_ht02(self, smiles: str) -> HallucinationReport:
        """HT-02: Stereo feasibility via RDKit CIPRank and ring-strain heuristics."""
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem, rdMolDescriptors

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return _ok(smiles)

            # Check for impossible stereocenters (e.g. bridgehead in Bredt-violating position)
            ri = mol.GetRingInfo()
            for atom in mol.GetAtoms():
                if atom.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED:
                    # Bridgehead double-bond (Bredt) check: atom in two rings, has double bond
                    if ri.NumAtomRings(atom.GetIdx()) >= 2:
                        for bond in atom.GetBonds():
                            if bond.GetBondTypeAsDouble() == 2.0:
                                ring_sizes = [len(r) for r in ri.AtomRings() if atom.GetIdx() in r]
                                if all(s <= 7 for s in ring_sizes):
                                    return HallucinationReport(
                                        smiles=smiles,
                                        ht_type=HallucinationType.HT02_STEREO_IMPOSSIBLE,
                                        message="Bredt-rule violation: double bond at bridgehead of small ring",
                                        severity="block",
                                    )

            # Check for conflicting stereo descriptors (E/Z on non-double bond, etc.)
            try:
                Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
            except Exception as e:
                return HallucinationReport(
                    smiles=smiles,
                    ht_type=HallucinationType.HT02_STEREO_IMPOSSIBLE,
                    message=f"Stereo assignment failed: {e}",
                    severity="block",
                )

            # Three-membered ring with trans double bond is impossible
            for ring in ri.AtomRings():
                if len(ring) == 3:
                    ring_set = set(ring)
                    for bond in mol.GetBonds():
                        if (bond.GetBeginAtomIdx() in ring_set and
                                bond.GetEndAtomIdx() in ring_set and
                                bond.GetBondTypeAsDouble() == 2.0 and
                                bond.GetStereo() in (Chem.BondStereo.STEREOE,)):
                            return HallucinationReport(
                                smiles=smiles,
                                ht_type=HallucinationType.HT02_STEREO_IMPOSSIBLE,
                                message="Trans double bond in 3-membered ring is geometrically impossible",
                                severity="block",
                            )
        except Exception:
            pass
        return _ok(smiles)

    def _check_ht03(self, smiles: str, chroma_distances: list[float] | None) -> HallucinationReport:
        """HT-03: No precedent in reaction database."""
        if chroma_distances is None:
            return _ok(smiles)
        if len(chroma_distances) == 0:
            return HallucinationReport(
                smiles=smiles,
                ht_type=HallucinationType.HT03_NO_PRECEDENT,
                message="No precedent reactions found in database",
                severity="block",
                details={"distances": []},
            )
        best = min(chroma_distances)
        if best > self.precedent_threshold:
            return HallucinationReport(
                smiles=smiles,
                ht_type=HallucinationType.HT03_NO_PRECEDENT,
                message=f"Nearest precedent distance {best:.3f} exceeds threshold {self.precedent_threshold}",
                severity="warn",
                details={"best_distance": best, "threshold": self.precedent_threshold},
            )
        return _ok(smiles)

    def _check_ht04(self, smiles: str, reagents_in_route: list[str]) -> HallucinationReport:
        """HT-04: Reagent incompatibility lookup (lightweight keyword matching)."""
        if not reagents_in_route:
            return _ok(smiles)
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return _ok(smiles)
            # Detect key functional groups via SMARTS
            FG_SMARTS = {
                "thiol": "[SH]",
                "protic": "[OH,NH]",
                "amine": "[NH2,NH,NR2]",
            }
            detected_fgs = set()
            for name, pat in FG_SMARTS.items():
                patt = Chem.MolFromSmarts(pat)
                if patt and mol.HasSubstructMatch(patt):
                    detected_fgs.add(name)

            INCOMPATIBLE_PAIRS = {
                ("oxidant", "thiol"): ("block", "Over-oxidation of thiol"),
                ("mCPBA", "thiol"): ("block", "Over-oxidation of thiol"),
                ("KMnO4", "thiol"): ("block", "Over-oxidation of thiol"),
                ("Pd_catalyst", "thiol"): ("block", "Catalyst poisoning"),
                ("strong_base", "protic"): ("block", "Deprotonation of substrate"),
            }
            for (rgt, fg), (sev, msg) in INCOMPATIBLE_PAIRS.items():
                if rgt in reagents_in_route and fg in detected_fgs:
                    return HallucinationReport(
                        smiles=smiles,
                        ht_type=HallucinationType.HT04_REAGENT_INCOMPATIBILITY,
                        message=msg,
                        severity=sev,
                        details={"reagent": rgt, "functional_group": fg},
                    )
        except Exception:
            pass
        return _ok(smiles)

    def _check_ht05(self, smiles: str, constraint_graph: ConstraintGraph) -> HallucinationReport:
        """HT-05: ConstraintGraph violation check."""
        violation = constraint_graph.get_violation(smiles)
        if violation:
            return HallucinationReport(
                smiles=smiles,
                ht_type=HallucinationType.HT05_CONSTRAINT_VIOLATION,
                message=f"Violates active constraint: {violation}",
                severity="block",
                details={"constraint": violation},
            )
        return _ok(smiles)
