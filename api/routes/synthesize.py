from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from ecosynth.pipeline import Preferences

log = logging.getLogger(__name__)
router = APIRouter()


class PreferencesModel(BaseModel):
    greenness: float = Field(default=0.5, ge=0.0, le=1.0)
    steps: float = Field(default=0.3, ge=0.0, le=1.0)
    commercial: float = Field(default=0.2, ge=0.0, le=1.0)


class SynthesizeRequest(BaseModel):
    smiles: str = Field(..., description="Target molecule SMILES")
    preferences: PreferencesModel = Field(default_factory=PreferencesModel)
    pinned: Optional[list[str]] = Field(default=None, description="Intermediate SMILES to force into routes")
    blacklisted: Optional[list[str]] = Field(default=None, description="Reaction SMARTS to exclude")


class ScoreBreakdownModel(BaseModel):
    g_score: float
    atom_economy: float
    e_factor: float
    pmi: float
    chem21_score: float
    step_penalty: float
    v_score: Optional[float] = None
    c_score: Optional[float] = None
    h_score: Optional[float] = None
    route_score: Optional[float] = None
    weights: Optional[dict] = None


class RouteModel(BaseModel):
    route_id: str
    intermediates: list[str]
    n_steps: int
    product: str
    reactants: list[str]
    g_score: float
    v_score: float = 1.0
    c_score: float = 0.0
    h_score: float = 0.0
    route_score: float = 0.0
    hallucination_type: Optional[str] = None
    score_breakdown: ScoreBreakdownModel
    explanation: str
    source: str
    tree: dict
    repaired: bool = False
    reasoning_steps: list[dict] = Field(default_factory=list)


class ConstraintStateModel(BaseModel):
    solvents: list[str]
    rxn_types: list[str]
    excluded_count: int
    excluded_sample: list[str]


class SynthesizeResponse(BaseModel):
    target_smiles: str
    canonical_smiles: str
    routes: list[RouteModel]
    precedents: list[dict]
    constraint_state: Optional[ConstraintStateModel] = None
    error: Optional[str] = None


def _dominant_ht(hallucination_reports: list[dict]) -> Optional[str]:
    """Return worst HT type across all reports for a route."""
    for report in hallucination_reports:
        if report.get("severity") == "block":
            return report.get("ht_type")
    for report in hallucination_reports:
        if report.get("severity") == "warn":
            return report.get("ht_type")
    return None


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(body: SynthesizeRequest, request: Request):
    pipeline = request.app.state.pipeline
    prefs = Preferences(
        greenness=body.preferences.greenness,
        steps=body.preferences.steps,
        commercial=body.preferences.commercial,
    )

    try:
        result = pipeline.synthesize(
            target_smiles=body.smiles,
            preferences=prefs,
            pinned=body.pinned,
            blacklisted=body.blacklisted,
        )
    except Exception as e:
        log.exception("Pipeline error for %s", body.smiles)
        raise HTTPException(status_code=500, detail=str(e))

    routes_out = []
    for r in result.routes:
        bd = r.score_breakdown
        # Ensure all required fields present with defaults
        breakdown = ScoreBreakdownModel(
            g_score=bd.get("g_score", 0.0),
            atom_economy=bd.get("atom_economy", 0.0),
            e_factor=bd.get("e_factor", 0.0),
            pmi=bd.get("pmi", 0.0),
            chem21_score=bd.get("chem21_score", 0.0),
            step_penalty=bd.get("step_penalty", 0.0),
            v_score=bd.get("v_score"),
            c_score=bd.get("c_score"),
            h_score=bd.get("h_score"),
            route_score=bd.get("route_score"),
            weights=bd.get("weights"),
        )
        routes_out.append(RouteModel(
            route_id=r.route_id,
            intermediates=r.intermediates,
            n_steps=r.n_steps,
            product=r.product,
            reactants=r.reactants,
            g_score=r.g_score,
            v_score=r.v_score,
            c_score=r.c_score,
            h_score=r.h_score,
            route_score=r.route_score,
            hallucination_type=_dominant_ht(r.hallucination_reports),
            score_breakdown=breakdown,
            explanation=r.explanation,
            source=r.source,
            tree=r.tree,
            repaired=r.repaired,
            reasoning_steps=r.reasoning_steps,
        ))

    cs = result.constraint_state
    constraint_model = ConstraintStateModel(**cs) if cs else None

    return SynthesizeResponse(
        target_smiles=result.target_smiles,
        canonical_smiles=result.canonical_smiles,
        routes=routes_out,
        precedents=result.precedents,
        constraint_state=constraint_model,
        error=result.error,
    )
