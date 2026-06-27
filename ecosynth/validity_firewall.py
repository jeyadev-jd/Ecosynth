"""
Module 2 — SMILES Validity Firewall.

Two-stage filter:
  Stage 1 (deterministic):  RDKit Chem.MolFromSmiles() — syntax check
  Stage 2 (learned):        ChemBERTa-77M binary classifier — chemical plausibility

If ChemBERTa model is not yet trained, falls back to Stage 1 only.

Returns HallucinationReport (not bare bool) when constraint_graph is provided.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ecosynth.mol_utils import parse_smiles
from ecosynth.hallucination_taxonomy import (
    HallucinationClassifier,
    HallucinationReport,
    HallucinationType,
    _ok,
)

if TYPE_CHECKING:
    from ecosynth.constraint_graph import ConstraintGraph

log = logging.getLogger(__name__)


class ValidityFirewall:
    def __init__(self, model_path: Optional[Path] = None, precedent_threshold: float = 0.3):
        self.tokenizer = None
        self.model = None
        self._classifier = HallucinationClassifier(precedent_threshold=precedent_threshold)

        if model_path and model_path.exists():
            try:
                from transformers import AutoTokenizer, AutoModelForSequenceClassification
                import torch
                self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
                self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
                self.model.eval()
                self._torch = torch
                log.info("ChemBERTa firewall loaded from %s", model_path)
            except Exception as e:
                log.warning("ChemBERTa load failed (%s) — using Stage 1 only.", e)
        else:
            log.info("No ChemBERTa model found — Stage 1 only (RDKit).")

    def check(
        self,
        smiles: str,
        constraint_graph: Optional[ConstraintGraph] = None,
        chroma_distances: Optional[list[float]] = None,
        reagents_in_route: Optional[list[str]] = None,
    ) -> HallucinationReport:
        """
        Returns HallucinationReport.
        severity="ok" on pass; "warn" or "block" on failure.
        """
        # Stage 1: deterministic RDKit parse (HT-01)
        mol = parse_smiles(smiles)
        if mol is None:
            from ecosynth.hallucination_taxonomy import HallucinationReport as HR, HallucinationType as HT
            return HR(
                smiles=smiles,
                ht_type=HT.HT01_VALENCE_VIOLATION,
                message="RDKit parse failed",
                severity="block",
            )

        # Stage 2: learned ChemBERTa classifier
        if self.model is not None:
            try:
                inputs = self.tokenizer(
                    smiles,
                    return_tensors="pt",
                    truncation=True,
                    max_length=128,
                    padding=True,
                )
                with self._torch.no_grad():
                    logits = self.model(**inputs).logits
                pred = int(logits.argmax(dim=-1).item())
                if pred == 0:
                    from ecosynth.hallucination_taxonomy import HallucinationReport as HR, HallucinationType as HT
                    return HR(
                        smiles=smiles,
                        ht_type=HT.HT01_VALENCE_VIOLATION,
                        message="ChemBERTa: chemically implausible",
                        severity="block",
                    )
            except Exception as e:
                log.debug("ChemBERTa inference error: %s", e)

        # Full HT classification (HT-02 through HT-05)
        report = self._classifier.classify(
            smiles=smiles,
            constraint_graph=constraint_graph,
            chroma_distances=chroma_distances,
            reagents_in_route=reagents_in_route,
        )
        return report

    def check_simple(self, smiles: str) -> tuple[bool, str]:
        """Legacy API: returns (is_valid, reason) for backward compatibility."""
        report = self.check(smiles)
        return report.is_ok, report.message

    def filter_batch(
        self,
        smiles_list: list[str],
        constraint_graph: Optional[ConstraintGraph] = None,
    ) -> list[tuple[str, HallucinationReport]]:
        """Check a list of SMILES. Returns [(smiles, HallucinationReport), ...]."""
        return [(smi, self.check(smi, constraint_graph=constraint_graph)) for smi in smiles_list]
