"""
Local Branch Repair for EcoSynth.

On hallucination detected at node f in a synthesis route:
  1. Snapshot G_C^(k) before f
  2. Blacklist failed SMILES in ConstraintGraph
  3. Re-generate subtree from parent of f (via RAG + pipeline)
  4. If all repair attempts fail: restore snapshot, return []
  5. Accumulate session-level blacklist across all repair calls
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ecosynth.constraint_graph import ConstraintGraph, ConstraintState
    from ecosynth.hallucination_taxonomy import HallucinationReport

logger = logging.getLogger(__name__)


@dataclass
class RepairRecord:
    target_smiles: str
    failed_node: str
    ht_type: str | None
    attempts: int
    success: bool
    repaired_route: list[dict] = field(default_factory=list)


class LocalBranchRepair:
    """
    Selective subtree invalidation and re-generation.

    Does NOT restart the full pipeline — only re-generates from
    the parent of the failed node downward.
    """

    def __init__(self, rag_engine: Any = None, max_repair_attempts: int = 3):
        self._rag = rag_engine
        self.max_repair_attempts = max_repair_attempts
        self._session_blacklist: set[str] = set()
        self._repair_log: list[RepairRecord] = []

    @property
    def session_blacklist(self) -> frozenset[str]:
        return frozenset(self._session_blacklist)

    def repair(
        self,
        target_smiles: str,
        failed_node_smiles: str,
        partial_route: list[str],
        ht_report: HallucinationReport,
        constraint_graph: ConstraintGraph,
    ) -> list[dict]:
        """
        Attempt local repair after hallucination at failed_node_smiles.

        Returns list of alternative route dicts, or [] if repair fails.
        """
        snap: ConstraintState = constraint_graph.snapshot()
        self._session_blacklist.add(failed_node_smiles)
        constraint_graph.exclude_smiles(failed_node_smiles)

        logger.info(
            "Branch repair: failed=%s ht=%s attempt up to %d",
            failed_node_smiles,
            ht_report.ht_type,
            self.max_repair_attempts,
        )

        parent_smiles = partial_route[-1] if partial_route else target_smiles
        repaired: list[dict] = []

        for attempt in range(1, self.max_repair_attempts + 1):
            candidates = self._generate_alternatives(
                target_smiles=target_smiles,
                parent_smiles=parent_smiles,
                constraint_graph=constraint_graph,
                exclude=self._session_blacklist,
            )
            if candidates:
                repaired = [
                    {
                        "smiles": c,
                        "route": partial_route + [c],
                        "repaired": True,
                        "repair_attempt": attempt,
                        "replaced_node": failed_node_smiles,
                    }
                    for c in candidates
                ]
                logger.info("Repair succeeded on attempt %d: %d candidates", attempt, len(candidates))
                break
            logger.info("Repair attempt %d: no valid candidates", attempt)

        if not repaired:
            logger.warning("All %d repair attempts failed; restoring snapshot", self.max_repair_attempts)
            constraint_graph.restore(snap)

        self._repair_log.append(RepairRecord(
            target_smiles=target_smiles,
            failed_node=failed_node_smiles,
            ht_type=ht_report.ht_type.value if ht_report.ht_type else None,
            attempts=self.max_repair_attempts if not repaired else len(repaired),
            success=bool(repaired),
            repaired_route=repaired,
        ))

        return repaired

    def _generate_alternatives(
        self,
        target_smiles: str,
        parent_smiles: str,
        constraint_graph: ConstraintGraph,
        exclude: set[str],
    ) -> list[str]:
        """
        Generate alternative SMILES candidates for the subtree rooted at parent_smiles.
        Falls back to RDKit fragmentation if RAG engine unavailable.
        """
        if self._rag is not None:
            try:
                candidates = self._rag.generate_candidates(
                    target_smiles=parent_smiles,
                    constraints=[
                        {"type": "exclude", "smiles": list(exclude)},
                        {"type": "solvents", "allowed": list(constraint_graph.state.solvents)},
                        {"type": "rxn_types", "allowed": list(constraint_graph.state.rxn_types)},
                    ],
                    max_retries=2,
                )
                valid = [c for c in candidates if c not in exclude and constraint_graph.query_allowed(c)]
                return valid
            except Exception as e:
                logger.warning("RAG generation failed during repair: %s", e)

        # Fallback: RDKit-based fragment generation
        return self._rdkit_fallback(parent_smiles, exclude, constraint_graph)

    def _rdkit_fallback(
        self,
        parent_smiles: str,
        exclude: set[str],
        constraint_graph: ConstraintGraph,
    ) -> list[str]:
        """Generate simple single-bond-cleavage fragments as repair candidates."""
        try:
            from rdkit import Chem
            from rdkit.Chem import BRICS

            mol = Chem.MolFromSmiles(parent_smiles)
            if mol is None:
                return []

            frags = set()
            # BRICS decomposition gives chemically meaningful fragments
            brics_frags = BRICS.BRICSDecompose(mol)
            for frag in brics_frags:
                # Strip BRICS dummy atoms
                cleaned = frag.replace("[3H]", "").replace("[4H]", "").replace("[5H]", "").replace("[6H]", "")
                cleaned = cleaned.replace("[7H]", "").replace("[8H]", "").replace("[9H]", "").replace("[10H]", "")
                cleaned = cleaned.strip(".")
                if len(cleaned) >= 4:
                    frag_mol = Chem.MolFromSmiles(cleaned)
                    if frag_mol:
                        canonical = Chem.MolToSmiles(frag_mol)
                        if canonical not in exclude and constraint_graph.query_allowed(canonical):
                            frags.add(canonical)

            return list(frags)[:5]
        except Exception as e:
            logger.warning("RDKit fallback repair failed: %s", e)
            return []

    def get_repair_log(self) -> list[dict]:
        return [
            {
                "target": r.target_smiles,
                "failed_node": r.failed_node,
                "ht_type": r.ht_type,
                "attempts": r.attempts,
                "success": r.success,
            }
            for r in self._repair_log
        ]

    def reset_session(self) -> None:
        """Clear session blacklist and repair log (call between independent synthesis requests)."""
        self._session_blacklist.clear()
        self._repair_log.clear()
