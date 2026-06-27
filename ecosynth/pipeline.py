"""
EcoSynth Pipeline Orchestrator — Neuro-Symbolic Edition.

Implements Dynamic Constraint Propagation:
  G_C^(k+1) = φ(G_C^(k), m_k)
  RouteScore = αG + βV + γC + δH
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ecosynth.config import Settings
from ecosynth.rag_engine import RAGEngine
from ecosynth.validity_firewall import ValidityFirewall
from ecosynth.green_scorer import GreenScorer
from ecosynth.aizynthfinder_wrapper import AizynthWrapper
from ecosynth.constraint_graph import ConstraintGraph
from ecosynth.symbolic_engine import SymbolicEngine
from ecosynth.branch_repair import LocalBranchRepair
from ecosynth.hallucination_taxonomy import HallucinationReport
from ecosynth.mol_utils import canonicalise

log = logging.getLogger(__name__)


@dataclass
class Preferences:
    greenness: float = 0.5
    steps: float = 0.3
    commercial: float = 0.2

    def validate(self):
        total = self.greenness + self.steps + self.commercial
        if abs(total - 1.0) > 0.01:
            self.greenness /= total
            self.steps /= total
            self.commercial /= total


@dataclass
class RouteResult:
    route_id: str
    tree: dict
    intermediates: list[str]
    n_steps: int
    product: str
    reactants: list[str]
    g_score: float
    v_score: float
    c_score: float
    h_score: float
    route_score: float
    score_breakdown: dict
    explanation: str
    source: str
    hallucination_reports: list[dict] = field(default_factory=list)
    valid_intermediates: list[str] = field(default_factory=list)
    repaired: bool = False
    reasoning_steps: list[dict] = field(default_factory=list)


@dataclass
class SynthesisResult:
    target_smiles: str
    canonical_smiles: str
    routes: list[RouteResult]
    precedents: list[dict]
    constraint_state: dict = field(default_factory=dict)
    error: Optional[str] = None


class EcoSynthPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

        log.info("Initialising RAG engine...")
        self.rag = RAGEngine(
            chroma_dir=settings.chroma_dir,
            collection_name=settings.chroma_collection,
            embedding_model=settings.embedding_model,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
            ollama_timeout=settings.ollama_timeout,
            top_k=settings.rag_top_k,
        )

        log.info("Initialising validity firewall...")
        self.firewall = ValidityFirewall(
            model_path=settings.chemberta_model if settings.chemberta_model.exists() else None,
            precedent_threshold=settings.ht_precedent_threshold,
        )

        log.info("Initialising green scorer...")
        self.scorer = GreenScorer(
            chem21_csv=settings.chem21_csv,
            rf_model_path=settings.green_rf_model if settings.green_rf_model.exists() else None,
        )

        log.info("Initialising AizynthFinder wrapper...")
        self.aizynb = AizynthWrapper(
            config_path=settings.aizynthfinder_config if settings.aizynthfinder_config.exists() else None
        )

        log.info("Initialising symbolic engine...")
        self.symbolic = SymbolicEngine()

        log.info("EcoSynth pipeline ready (AizynthFinder: %s)", self.aizynb.is_available)

    def _make_constraint_graph(self) -> ConstraintGraph:
        return ConstraintGraph(
            compat_csv=self.settings.reagent_compat_csv,
            chem21_csv=self.settings.chem21_csv,
        )

    def synthesize(
        self,
        target_smiles: str,
        preferences: Optional[Preferences] = None,
        pinned: Optional[list[str]] = None,
        blacklisted: Optional[list[str]] = None,
    ) -> SynthesisResult:
        if preferences is None:
            preferences = Preferences()
        preferences.validate()

        canon = canonicalise(target_smiles)
        if canon is None:
            return SynthesisResult(
                target_smiles=target_smiles,
                canonical_smiles=target_smiles,
                routes=[],
                precedents=[],
                error=f"Invalid target SMILES: {target_smiles}",
            )

        log.info("Synthesizing: %s", canon)

        # --- Init ConstraintGraph G_C^(0) ---
        cg = self._make_constraint_graph()
        branch_repair = LocalBranchRepair(
            rag_engine=self.rag,
            max_repair_attempts=self.settings.max_branch_repair_attempts,
        )
        weights = (
            self.settings.route_score_alpha,
            self.settings.route_score_beta,
            self.settings.route_score_gamma,
            self.settings.route_score_delta,
        )

        # --- Module 1: RAG retrieval with distances ---
        precedents, chroma_distances = self.rag.retrieve_with_distances(canon)
        log.info("Retrieved %d precedents", len(precedents))

        # Seed ConstraintGraph from RAG context
        context = self.rag.build_constraint_context(precedents)
        cg.seed_from_context(context)

        # Propagate target molecule's functional groups into G_C^(0)
        cg.propagate(canon)

        # --- Module 1: Constrained LLM candidate generation ---
        constraint_list = [
            {"type": "solvents", "allowed": list(cg.state.solvents)},
            {"type": "rxn_types", "allowed": list(cg.state.rxn_types)},
        ]
        rag_candidates_raw = self.rag.generate_candidates(canon, precedents + constraint_list)
        log.info("LLM generated %d candidates", len(rag_candidates_raw))

        # Augment with reactants from top precedents (fallback when LLM weak)
        if len(rag_candidates_raw) < 2:
            for p in precedents[:5]:
                reactants_smi = p.get("reactants", "")
                for smi in reactants_smi.split("."):
                    smi = smi.strip()
                    if smi and smi != canon and len(smi) > 4:
                        rag_candidates_raw.append(smi)
            log.info("Augmented with RAG reactants → %d total candidates", len(rag_candidates_raw))

        # --- Module 2: Validity firewall with HT classification ---
        valid_candidates: list[str] = []
        for smi in rag_candidates_raw:
            # Stage 0: Symbolic engine (fastest, runs first)
            ok, reason = self.symbolic.check_valence(smi)
            if not ok:
                log.debug("Symbolic valence fail %s: %s", smi, reason)
                continue
            ok, reason = self.symbolic.enforce_constraints(smi, cg)
            if not ok:
                log.debug("Symbolic constraint fail %s: %s", smi, reason)
                continue
            # Stage 1+2+HT: Full firewall
            report = self.firewall.check(smi, constraint_graph=cg, chroma_distances=chroma_distances)
            if report.is_ok:
                valid_candidates.append(smi)
                cg.propagate(smi)  # φ(G_C^(k), m_k)
            else:
                log.debug("Firewall %s: %s [%s]", report.ht_type, report.message, smi)

        log.info("%d/%d candidates passed firewall", len(valid_candidates), len(rag_candidates_raw))

        # --- Module 4: AizynthFinder MCTS with ConstraintGraph ---
        routes_raw = self.aizynb.find_routes(
            target_smiles=canon,
            pinned=pinned,
            blacklisted=blacklisted,
            rag_candidates=valid_candidates,
            constraint_graph=cg,
        )
        log.info("AizynthFinder returned %d routes", len(routes_raw))

        if not routes_raw:
            return SynthesisResult(
                target_smiles=target_smiles,
                canonical_smiles=canon,
                routes=[],
                precedents=precedents,
                constraint_state=_cg_to_dict(cg),
                error="No routes found.",
            )

        # --- Global reasoning steps (shared across all routes) ---
        global_steps: list[dict] = []
        best_sim = (1.0 - min(chroma_distances)) if chroma_distances else 0.0
        global_steps.append(_step(1, "rag_retrieval",
            f"Retrieved {len(precedents)} precedents (best similarity {best_sim:.0%})"))
        global_steps.append(_step(2, "constraint_init",
            f"Seeded G_C^(0): {len(cg.state.rxn_types)} rxn types, {len(cg.state.solvents)} solvents"))

        # --- Module 3: Per-route scoring with G, V, C, H ---
        scored_routes = []
        for raw in routes_raw:
            route_intermediates = raw.get("intermediates", [])
            ht_reports: list[HallucinationReport] = []
            node_snap = cg.snapshot()
            route_steps: list[dict] = list(global_steps)  # copy shared prefix
            step_n = len(route_steps) + 1
            prev_rxn_count = len(cg.state.rxn_types)

            # Validate each intermediate in route under current constraint state
            repaired = False
            for node_smi in route_intermediates:
                if node_smi == canon:
                    continue
                report = self.firewall.check(node_smi, constraint_graph=cg, chroma_distances=chroma_distances)
                ht_reports.append(report)
                route_steps.append(_step(step_n, "firewall_check",
                    report.message, smiles=node_smi, severity=report.severity))
                step_n += 1
                if report.is_blocking:
                    route_steps.append(_step(step_n, "repair_triggered",
                        f"{report.ht_type or 'HT'} blocked node — initiating branch repair",
                        smiles=node_smi, severity="block"))
                    step_n += 1
                    repair_routes = branch_repair.repair(
                        target_smiles=canon,
                        failed_node_smiles=node_smi,
                        partial_route=[s for s in route_intermediates if s != node_smi],
                        ht_report=report,
                        constraint_graph=cg,
                    )
                    if repair_routes:
                        repaired = True
                        log.info("Branch repaired for %s", node_smi)
                        route_steps.append(_step(step_n, "repair_success",
                            f"Repair succeeded — new branch accepted",
                            smiles=repair_routes[0].get("product") if repair_routes else None,
                            severity="ok"))
                    else:
                        route_steps.append(_step(step_n, "repair_failed",
                            "Repair exhausted all attempts — route proceeds with warning",
                            severity="warn"))
                    step_n += 1
                    cg.restore(node_snap)
                    break
                else:
                    after_rxn_count = len(cg.state.rxn_types)
                    cg.propagate(node_smi)
                    new_rxn_count = len(cg.state.rxn_types)
                    delta = new_rxn_count - after_rxn_count
                    k = step_n - len(global_steps) - 1
                    if delta < 0:
                        route_steps.append(_step(step_n, "constraint_update",
                            f"G_C^({k}) → pruned {abs(delta)} reaction type(s) after accepting intermediate",
                            smiles=node_smi, severity="ok"))
                        step_n += 1
                    prev_rxn_count = new_rxn_count

            # Green score (G)
            route_for_scoring = {
                "reactants": raw.get("reactants", []),
                "product": raw.get("product", canon),
                "solvent": "ethanol",
                "n_steps": raw.get("n_steps", 1),
            }
            g = self.scorer.score_route(route_for_scoring)

            # Validity score (V) — use worst HT report in route
            if ht_reports:
                worst = min(ht_reports, key=lambda r: {"ok": 2, "warn": 1, "block": 0}.get(r.severity, 1))
                v = self.scorer.validity_score(worst)
            else:
                v = 1.0

            # Confidence score (C) from RAG distances
            c = self.scorer.confidence_score(chroma_distances)

            # Human preference score (H) from pinned intermediates
            h = self.scorer.human_preference_score(pinned or [], route_intermediates)

            # Formal RouteScore = αG + βV + γC + δH
            rs = self.scorer.route_score(g, v, c, h, weights)

            # Composite with user preferences (step count, commercial)
            step_score = 1.0 / (1.0 + raw.get("n_steps", 1))
            commercial_score = _commercial_proxy(raw.get("reactants", []))
            pref_score = (
                preferences.greenness * rs
                + preferences.steps * step_score
                + preferences.commercial * commercial_score
            )

            breakdown = self.scorer.score_breakdown(route_for_scoring)
            breakdown["v_score"] = round(v, 4)
            breakdown["c_score"] = round(c, 4)
            breakdown["h_score"] = round(h, 4)
            breakdown["route_score"] = round(rs, 4)
            breakdown["weights"] = {"alpha": weights[0], "beta": weights[1], "gamma": weights[2], "delta": weights[3]}

            # Annotate tree with per-node metadata
            ht_map = {r.smiles: r.to_dict() for r in ht_reports}
            route_id = raw.get("route_id", "")
            annotated_tree = _annotate_tree(raw.get("tree", {}), ht_map, c, route_id, rank=0)
            # Mark root as target
            if annotated_tree:
                annotated_tree["node_status"] = "target"

            raw["_pref_score"] = pref_score
            raw["g_score"] = g
            raw["v_score"] = v
            raw["c_score"] = c
            raw["h_score"] = h
            raw["route_score"] = rs
            raw["score_breakdown"] = breakdown
            raw["ht_reports"] = ht_reports
            raw["repaired"] = repaired
            raw["annotated_tree"] = annotated_tree
            raw["reasoning_steps"] = route_steps
            scored_routes.append(raw)

        scored_routes.sort(key=lambda r: r["_pref_score"], reverse=True)

        # --- LLM explanation for top results ---
        results: list[RouteResult] = []
        for rank_idx, raw in enumerate(scored_routes[:10]):
            explanation = self.rag.explain_route(raw, precedents)
            # Re-annotate with correct rank now that we know final ranking
            tree = raw.get("annotated_tree") or raw.get("tree", {})
            if tree:
                tree = _annotate_tree(tree, {r.smiles: r.to_dict() for r in raw.get("ht_reports", [])},
                                      raw["c_score"], raw.get("route_id", ""), rank_idx + 1)
                tree["node_status"] = "target"
            results.append(RouteResult(
                route_id=raw["route_id"],
                tree=tree,
                intermediates=raw.get("intermediates", []),
                n_steps=raw.get("n_steps", 1),
                product=raw.get("product", canon),
                reactants=raw.get("reactants", []),
                g_score=raw["g_score"],
                v_score=raw["v_score"],
                c_score=raw["c_score"],
                h_score=raw["h_score"],
                route_score=raw["route_score"],
                score_breakdown=raw["score_breakdown"],
                explanation=explanation,
                source=raw.get("source", "unknown"),
                hallucination_reports=[r.to_dict() for r in raw.get("ht_reports", [])],
                valid_intermediates=valid_candidates,
                repaired=raw.get("repaired", False),
                reasoning_steps=raw.get("reasoning_steps", []),
            ))

        return SynthesisResult(
            target_smiles=target_smiles,
            canonical_smiles=canon,
            routes=results,
            precedents=precedents,
            constraint_state=_cg_to_dict(cg),
        )


def _step(n: int, event: str, detail: str, smiles: str | None = None, severity: str | None = "ok") -> dict:
    return {"step": n, "event": event, "detail": detail, "smiles": smiles, "severity": severity}


def _annotate_tree(node: dict, ht_map: dict, c_score: float, route_id: str, rank: int) -> dict:
    """Recursively annotate tree nodes with per-node metadata for frontend rendering."""
    smi = node.get("smiles", "")
    report = ht_map.get(smi)
    annotated = {
        **node,
        "c_score": c_score,
        "ht_type": report["ht_type"] if report else None,
        "node_status": "rejected" if (report and report.get("severity") == "block") else "accepted",
        "route_id": route_id,
        "route_rank": rank,
        "children": [_annotate_tree(c, ht_map, c_score, route_id, rank) for c in node.get("children", [])],
    }
    return annotated


def _commercial_proxy(reactants: list[str]) -> float:
    """Heuristic commercial availability: short, simple SMILES → more available."""
    if not reactants:
        return 0.5
    scores = []
    for smi in reactants:
        length_score = max(0.0, 1.0 - len(smi) / 60.0)
        exotic = sum(1 for c in smi if c in {"[", "]", "@", "%"})
        exotic_score = max(0.0, 1.0 - exotic / 5.0)
        scores.append((length_score + exotic_score) / 2.0)
    return sum(scores) / len(scores)


def _cg_to_dict(cg: ConstraintGraph) -> dict:
    """Serialize ConstraintGraph state for API response."""
    state = cg.state
    return {
        "solvents": sorted(state.solvents),
        "rxn_types": sorted(state.rxn_types),
        "excluded_count": len(state.excluded),
        "excluded_sample": sorted(state.excluded)[:5],
    }
