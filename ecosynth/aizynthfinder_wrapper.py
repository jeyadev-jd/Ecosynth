"""
Module 4 — AizynthFinder MCTS Wrapper.

Wraps AstraZeneca AizynthFinder for multi-step retrosynthesis planning.
Supports pinned intermediates and blacklisted reaction SMARTS patterns.

If AizynthFinder is not installed or config is missing, returns a fallback
single-step route derived from the RAG candidates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ecosynth.constraint_graph import ConstraintGraph
    from ecosynth.branch_repair import LocalBranchRepair

log = logging.getLogger(__name__)


def _route_tree_to_dict(node, depth: int = 0) -> dict:
    """Recursively convert AizynthFinder RouteCollection node to plain dict."""
    result = {
        "smiles": getattr(node, "smiles", ""),
        "type": getattr(node, "type", "mol"),
        "depth": depth,
        "children": [],
    }
    children = getattr(node, "children", []) or []
    for child in children:
        result["children"].append(_route_tree_to_dict(child, depth + 1))
    return result


def _count_steps(node_dict: dict) -> int:
    """Count reaction steps in a route tree."""
    count = 1 if node_dict.get("type") == "reaction" else 0
    for child in node_dict.get("children", []):
        count += _count_steps(child)
    return count


def _extract_intermediates(node_dict: dict) -> list[str]:
    """Collect all intermediate mol SMILES in a route."""
    mols = []
    if node_dict.get("type") != "reaction" and node_dict.get("smiles"):
        mols.append(node_dict["smiles"])
    for child in node_dict.get("children", []):
        mols.extend(_extract_intermediates(child))
    return mols


class AizynthWrapper:
    def __init__(self, config_path: Optional[Path] = None):
        self._available = False
        self._finder = None

        if config_path is None or not config_path.exists():
            log.warning(
                "AizynthFinder config not found at %s — single-step fallback active.",
                config_path,
            )
            return

        try:
            from aizynthfinder.aizynthfinder import AiZynthFinder
            self._finder = AiZynthFinder(configfile=str(config_path))
            self._available = True
            log.info("AizynthFinder loaded from %s", config_path)
        except ImportError:
            log.warning("aizynthfinder not installed — single-step fallback active.")
        except Exception as e:
            log.error("AizynthFinder init error: %s — fallback active.", e)

    @property
    def is_available(self) -> bool:
        return self._available

    def find_routes(
        self,
        target_smiles: str,
        pinned: Optional[list[str]] = None,
        blacklisted: Optional[list[str]] = None,
        rag_candidates: Optional[list[str]] = None,
        constraint_graph: Optional[ConstraintGraph] = None,
    ) -> list[dict]:
        """
        Run MCTS retrosynthesis for target_smiles.

        Args:
            target_smiles:     SMILES of the target molecule.
            pinned:            SMILES of intermediates that must appear in routes.
            blacklisted:       Reaction SMARTS strings to exclude.
            rag_candidates:    Fallback candidates from RAG (used if MCTS unavailable).
            constraint_graph:  Active ConstraintGraph; filters routes against G_C^(k).

        Returns:
            List of route dicts, each with keys:
              route_id, tree, steps, intermediates, n_steps, reactants, product
        """
        # Merge ConstraintGraph exclusions into blacklisted
        effective_blacklisted = list(blacklisted or [])
        if constraint_graph is not None:
            for excl in constraint_graph.state.excluded:
                if excl.startswith("smiles:"):
                    effective_blacklisted.append(excl[len("smiles:"):])

        if self._available:
            routes = self._mcts_routes(target_smiles, pinned, effective_blacklisted)
        else:
            routes = self._fallback_routes(target_smiles, rag_candidates or [])

        # Filter routes against ConstraintGraph
        if constraint_graph is not None:
            routes = self._filter_routes(routes, constraint_graph)

        return routes

    def _filter_routes(self, routes: list[dict], cg: ConstraintGraph) -> list[dict]:
        """Remove routes containing blacklisted intermediates."""
        filtered = []
        for route in routes:
            intermediates = route.get("intermediates", [])
            if all(cg.query_allowed(smi) for smi in intermediates):
                filtered.append(route)
            else:
                log.debug("Route %s filtered by ConstraintGraph", route.get("route_id"))
        return filtered if filtered else routes[:1]  # keep at least one

    def _mcts_routes(
        self,
        target_smiles: str,
        pinned: Optional[list[str]],
        blacklisted: Optional[list[str]],
    ) -> list[dict]:
        finder = self._finder
        finder.target_smiles = target_smiles
        finder.config.iteration_limit = 100
        finder.config.time_limit = 60

        # Apply blacklist if supported by installed version
        if blacklisted:
            try:
                for smarts in blacklisted:
                    finder.config.filter_policy.blacklist.add(smarts)
            except AttributeError:
                log.debug("Blacklisting not supported in this AizynthFinder version.")

        finder.tree_search()
        finder.build_routes()

        routes = []
        for i, route in enumerate(finder.routes):
            try:
                tree = _route_tree_to_dict(route.reaction_tree)
                intermediates = _extract_intermediates(tree)

                # Skip routes that don't contain pinned intermediates
                if pinned:
                    if not all(p in intermediates for p in pinned):
                        continue

                n_steps = _count_steps(tree)
                routes.append({
                    "route_id": f"route_{i}",
                    "tree": tree,
                    "intermediates": intermediates,
                    "n_steps": n_steps,
                    "product": target_smiles,
                    "reactants": intermediates[-3:] if intermediates else [],
                    "source": "aizynthfinder",
                })
            except Exception as e:
                log.debug("Route %d parse error: %s", i, e)

        log.info("AizynthFinder returned %d routes for %s", len(routes), target_smiles)
        return routes

    def _fallback_routes(self, target_smiles: str, rag_candidates: list[str]) -> list[dict]:
        """Single-step fallback using RAG candidates as direct precursors."""
        if not rag_candidates:
            return [{
                "route_id": "route_0_fallback",
                "tree": {"smiles": target_smiles, "type": "mol", "depth": 0, "children": []},
                "intermediates": [target_smiles],
                "n_steps": 1,
                "product": target_smiles,
                "reactants": [target_smiles],
                "source": "fallback_no_candidates",
            }]

        routes = []
        for i, candidate in enumerate(rag_candidates[:5]):
            routes.append({
                "route_id": f"route_{i}_fallback",
                "tree": {
                    "smiles": target_smiles,
                    "type": "mol",
                    "depth": 0,
                    "children": [{
                        "smiles": "rag_step",
                        "type": "reaction",
                        "depth": 1,
                        "children": [{"smiles": candidate, "type": "mol", "depth": 2, "children": []}],
                    }],
                },
                "intermediates": [target_smiles, candidate],
                "n_steps": 1,
                "product": target_smiles,
                "reactants": [candidate],
                "source": "rag_fallback",
            })
        return routes
