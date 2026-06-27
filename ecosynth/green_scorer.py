"""
Module 3 — Unified Multi-Criteria Green Scorer.

Computes 5 green metrics per reaction route and fuses them via a trained
Random Forest regressor into a single G_score ∈ [0, 1].

Also computes V, C, H scores for the formal composite:
  RouteScore = αG + βV + γC + δH

Metrics:
  m1  E-factor           (waste mass / product mass)     — lower is greener
  m2  Atom Economy       (MW product / sum MW reactants) — higher is greener
  m3  PMI                (total mass in / mass product)  — lower is greener
  m4  CHEM21 Solvent     composite score from guide      — higher is greener
  m5  Step Count Penalty exp(-0.2 * n_steps)             — higher is greener
"""

import math
import csv
import logging
from pathlib import Path
from typing import Optional

from rdkit.Chem import Descriptors

from ecosynth.mol_utils import parse_smiles

log = logging.getLogger(__name__)


class GreenScorer:
    FEATURE_NAMES = ["atom_economy", "e_factor_norm", "pmi_norm", "chem21_score", "step_penalty"]

    def __init__(self, chem21_csv: Path, rf_model_path: Optional[Path] = None):
        self.chem21 = self._load_chem21(chem21_csv)
        self.rf = None
        if rf_model_path and rf_model_path.exists():
            import joblib
            self.rf = joblib.load(rf_model_path)
            log.info("Green RF model loaded from %s", rf_model_path)
        else:
            log.warning("No RF model found — using heuristic weights.")

    # ------------------------------------------------------------------
    # Individual metrics
    # ------------------------------------------------------------------

    def atom_economy(self, reactant_smiles: list[str], product_smiles: str) -> float:
        try:
            p_mol = parse_smiles(product_smiles)
            r_mols = [parse_smiles(s) for s in reactant_smiles]
            if p_mol is None or None in r_mols:
                return 0.0
            mw_prod = Descriptors.ExactMolWt(p_mol)
            mw_all = sum(Descriptors.ExactMolWt(m) for m in r_mols)
            if mw_all == 0:
                return 0.0
            return min(mw_prod / mw_all, 1.0)
        except Exception as e:
            log.debug("atom_economy error: %s", e)
            return 0.0

    def e_factor(self, reactant_smiles: list[str], product_smiles: str) -> float:
        """Mass of waste / mass of product. Lower = greener."""
        try:
            p_mol = parse_smiles(product_smiles)
            r_mols = [parse_smiles(s) for s in reactant_smiles]
            if p_mol is None or None in r_mols:
                return 100.0
            mw_prod = Descriptors.ExactMolWt(p_mol)
            mw_all = sum(Descriptors.ExactMolWt(m) for m in r_mols)
            waste = max(mw_all - mw_prod, 0.0)
            return waste / mw_prod if mw_prod > 0 else 100.0
        except Exception as e:
            log.debug("e_factor error: %s", e)
            return 100.0

    def pmi(self, reactant_smiles: list[str], product_smiles: str) -> float:
        """Process Mass Intensity: total mass in / product mass. Lower = greener."""
        try:
            p_mol = parse_smiles(product_smiles)
            r_mols = [parse_smiles(s) for s in reactant_smiles]
            if p_mol is None or None in r_mols:
                return 100.0
            mw_prod = Descriptors.ExactMolWt(p_mol)
            mw_all = sum(Descriptors.ExactMolWt(m) for m in r_mols)
            return mw_all / mw_prod if mw_prod > 0 else 100.0
        except Exception as e:
            log.debug("pmi error: %s", e)
            return 100.0

    def chem21_score(self, solvent: str) -> float:
        """CHEM21 composite [0-1]. Falls back to 0.5 (unknown solvent)."""
        key = solvent.strip().lower()
        raw = self.chem21.get(key, 5.0)
        return raw / 10.0

    def step_penalty(self, n_steps: int) -> float:
        return math.exp(-0.2 * max(n_steps, 1))

    # ------------------------------------------------------------------
    # Route scoring
    # ------------------------------------------------------------------

    def score_route(self, route: dict) -> float:
        """
        Compute G_score for a route dict.

        Expected route keys (all optional with sensible defaults):
          reactants: list[str]  — SMILES of reactants
          product:   str        — SMILES of final product
          solvent:   str        — solvent name
          n_steps:   int        — number of synthetic steps
        """
        reactants = route.get("reactants", [])
        product = route.get("product", "")
        solvent = route.get("solvent", "ethanol")
        n_steps = int(route.get("n_steps", 1))

        if isinstance(reactants, str):
            reactants = reactants.split(".")

        ae = self.atom_economy(reactants, product)
        ef = self.e_factor(reactants, product)
        pmi_val = self.pmi(reactants, product)
        c21 = self.chem21_score(solvent)
        sp = self.step_penalty(n_steps)

        ef_norm = 1.0 / (1.0 + ef)
        pmi_norm = 1.0 / (1.0 + pmi_val)

        features = [[ae, ef_norm, pmi_norm, c21, sp]]

        if self.rf is not None:
            score = float(self.rf.predict(features)[0])
        else:
            # Heuristic fallback weights
            score = (
                0.30 * ae
                + 0.25 * ef_norm
                + 0.20 * pmi_norm
                + 0.15 * c21
                + 0.10 * sp
            )

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # V, C, H score components for formal RouteScore
    # ------------------------------------------------------------------

    def validity_score(self, ht_report) -> float:
        """V score from HallucinationReport: 1.0=ok, 0.5=warn, 0.0=block."""
        severity = getattr(ht_report, "severity", "ok")
        if severity == "ok":
            return 1.0
        if severity == "warn":
            return 0.5
        return 0.0

    def confidence_score(self, chroma_distances: list[float] | None) -> float:
        """C score: similarity to nearest precedent in [0,1]. 1=close precedent."""
        if not chroma_distances:
            return 0.0
        best = min(chroma_distances)
        # ChromaDB L2 distance: 0=identical, larger=further
        # Convert: C = exp(-best) capped at 1
        return min(1.0, math.exp(-best))

    def human_preference_score(self, pinned: list[str], route_smiles: list[str]) -> float:
        """H score: fraction of route nodes that were pinned by user."""
        if not pinned or not route_smiles:
            return 0.0
        pinned_set = set(pinned)
        matched = sum(1 for s in route_smiles if s in pinned_set)
        return matched / len(route_smiles)

    def route_score(
        self,
        g: float,
        v: float,
        c: float,
        h: float,
        weights: tuple[float, float, float, float] = (0.4, 0.3, 0.2, 0.1),
    ) -> float:
        """Formal RouteScore = αG + βV + γC + δH, all components in [0,1]."""
        alpha, beta, gamma, delta = weights
        score = alpha * g + beta * v + gamma * c + delta * h
        return max(0.0, min(1.0, score))

    def score_breakdown(self, route: dict) -> dict:
        """Return all raw metric values alongside G_score for display."""
        reactants = route.get("reactants", [])
        product = route.get("product", "")
        solvent = route.get("solvent", "ethanol")
        n_steps = int(route.get("n_steps", 1))
        if isinstance(reactants, str):
            reactants = reactants.split(".")

        ae = self.atom_economy(reactants, product)
        ef = self.e_factor(reactants, product)
        pmi_val = self.pmi(reactants, product)
        c21 = self.chem21_score(solvent)
        sp = self.step_penalty(n_steps)

        return {
            "g_score": self.score_route(route),
            "atom_economy": round(ae, 4),
            "e_factor": round(ef, 4),
            "pmi": round(pmi_val, 4),
            "chem21_score": round(c21, 4),
            "step_penalty": round(sp, 4),
            # V, C, H populated by pipeline after full classification
            "v_score": None,
            "c_score": None,
            "h_score": None,
            "route_score": None,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_chem21(csv_path: Path) -> dict[str, float]:
        result: dict[str, float] = {}
        if not csv_path.exists():
            log.warning("CHEM21 CSV not found at %s", csv_path)
            return result
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip().lower()
                composite = float(row.get("composite", 5.0))
                result[name] = composite
        return result
