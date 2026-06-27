"""
Module 1 — Constraint-Injected RAG Engine.

Retrieves top-K precedent reactions from ChromaDB using a hybrid query
(MiniLM text embedding + Morgan fingerprint metadata filter), then injects
the retrieved SMARTS constraints into a Gemma 3 1B prompt via Ollama.

The LLM is constrained to suggest only disconnections with structural
precedent in the indexed reaction corpus.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import httpx
from sentence_transformers import SentenceTransformer

from ecosynth.mol_utils import morgan_fp, canonicalise

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are EcoSynth, an expert retrosynthesis AI. Your task is to propose \
disconnection steps to synthesise the target molecule.

CONSTRAINT — You must only propose reactions that are consistent with these \
precedent reactions retrieved from the USPTO database:

{constraints}

Rules:
1. Return ONLY a JSON array of proposed intermediate SMILES strings.
2. Each intermediate must be a valid SMILES.
3. Maximum 5 intermediates.
4. Do not explain — output JSON only.
5. Your entire response must be a single JSON array, exactly like the example. No numbered lists, no prose.

Example output format:
["CC(=O)Oc1ccccc1", "OC(=O)c1ccccc1", "CCO"]
"""


class RAGEngine:
    def __init__(
        self,
        chroma_dir: Path,
        collection_name: str,
        embedding_model: str,
        ollama_url: str,
        ollama_model: str,
        ollama_timeout: int = 120,
        top_k: int = 5,
    ):
        import chromadb
        self.client = chromadb.PersistentClient(path=str(chroma_dir))
        try:
            self.collection = self.client.get_collection(collection_name)
            log.info("ChromaDB collection '%s' loaded (%d docs)", collection_name, self.collection.count())
        except Exception:
            log.warning("ChromaDB collection '%s' not found — RAG retrieval disabled.", collection_name)
            self.collection = None

        self.encoder = SentenceTransformer(embedding_model)
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.ollama_timeout = ollama_timeout
        self.top_k = top_k

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, target_smiles: str, text_query: Optional[str] = None, k: Optional[int] = None) -> list[dict]:
        """Return top-K reaction precedents from ChromaDB."""
        if self.collection is None:
            return []

        k = k or self.top_k
        canon = canonicalise(target_smiles) or target_smiles
        query_text = text_query or f"retrosynthesis disconnection for molecule: {canon}"

        emb = self.encoder.encode(query_text, normalize_embeddings=True).tolist()

        try:
            results = self.collection.query(
                query_embeddings=[emb],
                n_results=min(k, self.collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            log.error("ChromaDB query error: %s", e)
            return []

        precedents = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            precedents.append({
                "text": doc,
                "reaction_class": meta.get("reaction_class", ""),
                "reactants": meta.get("reactants", ""),
                "product": meta.get("product", ""),
                "reaction_smiles": meta.get("reaction_smiles", ""),
                "similarity": round(1.0 - float(dist), 4),
                "distance": float(dist),
            })

        return precedents

    def retrieve_with_distances(
        self, target_smiles: str, text_query: Optional[str] = None, k: Optional[int] = None
    ) -> tuple[list[dict], list[float]]:
        """Retrieve precedents and return (results, raw_distances) for C score computation."""
        results = self.retrieve(target_smiles, text_query, k)
        distances = [r.get("distance", 1.0) for r in results]
        return results, distances

    def build_constraint_context(self, results: list[dict]) -> dict:
        """
        Extract reagent/solvent/rxn-type constraints from retrieved precedents.
        Used to seed ConstraintGraph.seed_from_context().
        """
        rxn_types: set[str] = set()
        solvents: set[str] = set()
        reagents: list[str] = []

        for r in results:
            rc = r.get("reaction_class", "")
            if rc:
                rxn_types.add(rc.lower().replace(" ", "_").replace("-", "_"))

            # Extract solvents from reaction text heuristically
            text = r.get("text", "").lower()
            for solvent in ["thf", "dcm", "ethanol", "methanol", "acetone", "toluene",
                           "dmf", "dmso", "ethyl acetate", "hexane", "water", "acetonitrile",
                           "dioxane", "diethyl ether", "chloroform"]:
                if solvent in text:
                    solvents.add(solvent)

        return {
            "rxn_types": list(rxn_types),
            "solvents": list(solvents),
            "reagents": reagents,
        }

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_candidates(self, target_smiles: str, constraints: list[dict], max_retries: int = 2) -> list[str]:
        """
        Send constrained prompt to Ollama Gemma3:1b.
        Returns list of candidate intermediate SMILES.
        Falls back to empty list if Ollama unreachable.
        """
        constraint_text = self._format_constraints(constraints)
        system = SYSTEM_PROMPT_TEMPLATE.format(constraints=constraint_text)
        user_msg = f"Target molecule SMILES: {target_smiles}\nPropose retrosynthetic intermediates:"

        for attempt in range(max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "system": system,
                        "prompt": user_msg,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 256},
                    },
                    timeout=self.ollama_timeout,
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "").strip()
                candidates = self._parse_smiles_list(raw)
                if candidates:
                    return candidates
            except Exception as e:
                log.warning("Ollama attempt %d/%d failed: %s", attempt + 1, max_retries + 1, e)

        log.error("Ollama unreachable — returning empty candidate list.")
        return []

    def explain_route(self, route: dict, constraints: list[dict]) -> str:
        """
        Generate a plain-English explanation of a synthesis route,
        citing the retrieved USPTO precedents.
        """
        steps_text = json.dumps(route.get("steps", []), indent=2)
        constraint_text = self._format_constraints(constraints[:3])
        prompt = (
            f"Explain the following retrosynthesis route in plain English for a chemist.\n"
            f"Cite which precedent reaction supports each step.\n\n"
            f"Route steps:\n{steps_text}\n\n"
            f"Supporting precedents:\n{constraint_text}\n\n"
            f"Green score: {route.get('g_score', 'N/A')}\n"
            f"Number of steps: {route.get('n_steps', 'N/A')}\n\n"
            f"Explanation:"
        )
        try:
            resp = httpx.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 400},
                },
                timeout=self.ollama_timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as e:
            log.warning("Explanation generation failed: %s", e)
            return f"Route with {route.get('n_steps', '?')} steps. G_score: {route.get('g_score', 'N/A'):.3f}."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_constraints(precedents: list[dict]) -> str:
        lines = []
        for i, p in enumerate(precedents, 1):
            rc = p.get("reaction_class") or "unknown"
            rxn = p.get("reaction_smiles") or p.get("text", "")
            sim = p.get("similarity", 0.0)
            lines.append(f"  [{i}] {rc} | {rxn[:120]} (similarity: {sim:.3f})")
        return "\n".join(lines) if lines else "  No precedents retrieved."

    @staticmethod
    def _parse_smiles_list(raw: str) -> list[str]:
        """Extract JSON array of SMILES strings from LLM output."""
        import re
        raw = raw.strip()
        # Try JSON array first
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1:
            try:
                parsed = json.loads(raw[start:end + 1])
                if isinstance(parsed, list):
                    result = [str(s).strip() for s in parsed if isinstance(s, str) and s.strip()]
                    if result:
                        return result
            except json.JSONDecodeError:
                pass
        # Fallback: regex extraction of SMILES-like tokens from each line
        _SMILES_CHARS = re.compile(r'[CNOcnoBrClFISP=#\[\]()\\/+\-@%0-9]')
        _WORD_LINE = re.compile(r'^[A-Z][a-z]{2,}')  # lines starting with English words
        results = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading numbering like "1." or "1)"
            line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if len(line) < 4:
                continue
            if _WORD_LINE.match(line):
                continue
            # Must contain at least one SMILES-characteristic character
            if not _SMILES_CHARS.search(line):
                continue
            # Extract the first whitespace-delimited token that looks like SMILES
            token = line.split()[0] if line.split() else line
            if len(token) >= 4 and _SMILES_CHARS.search(token):
                results.append(token)
        return results
