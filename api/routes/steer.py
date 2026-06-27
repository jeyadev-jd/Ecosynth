"""
Human-in-the-loop steering endpoint.

Accepts pin/reject actions on route nodes and re-runs the pipeline
with the updated constraint set.
"""

import logging
from typing import Literal, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from ecosynth.pipeline import Preferences

log = logging.getLogger(__name__)
router = APIRouter()


class SteerRequest(BaseModel):
    target_smiles: str
    action: Literal["pin", "reject"]
    smiles: str = Field(..., description="Intermediate SMILES to pin or reject")
    current_pinned: list[str] = Field(default_factory=list)
    current_blacklisted: list[str] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)


class SteerResponse(BaseModel):
    target_smiles: str
    canonical_smiles: str
    routes: list[dict]
    precedents: list[dict]
    applied_action: str
    pinned: list[str]
    blacklisted: list[str]
    error: Optional[str] = None


@router.post("/steer", response_model=SteerResponse)
async def steer(body: SteerRequest, request: Request):
    pipeline = request.app.state.pipeline

    pinned = list(body.current_pinned)
    blacklisted = list(body.current_blacklisted)

    if body.action == "pin":
        if body.smiles not in pinned:
            pinned.append(body.smiles)
        applied = f"Pinned intermediate: {body.smiles}"
    elif body.action == "reject":
        # Blacklist this SMILES as a product (removes paths through it)
        if body.smiles not in blacklisted:
            blacklisted.append(body.smiles)
        applied = f"Rejected intermediate: {body.smiles}"
    else:
        raise HTTPException(status_code=400, detail="action must be 'pin' or 'reject'")

    prefs_raw = body.preferences or {}
    prefs = Preferences(
        greenness=float(prefs_raw.get("greenness", 0.5)),
        steps=float(prefs_raw.get("steps", 0.3)),
        commercial=float(prefs_raw.get("commercial", 0.2)),
    )

    try:
        result = pipeline.synthesize(
            target_smiles=body.target_smiles,
            preferences=prefs,
            pinned=pinned or None,
            blacklisted=blacklisted or None,
        )
    except Exception as e:
        log.exception("Steer pipeline error")
        raise HTTPException(status_code=500, detail=str(e))

    routes_out = []
    for r in result.routes:
        routes_out.append({
            "route_id": r.route_id,
            "intermediates": r.intermediates,
            "n_steps": r.n_steps,
            "product": r.product,
            "reactants": r.reactants,
            "g_score": r.g_score,
            "score_breakdown": r.score_breakdown,
            "explanation": r.explanation,
            "source": r.source,
            "tree": r.tree,
        })

    return SteerResponse(
        target_smiles=result.target_smiles,
        canonical_smiles=result.canonical_smiles,
        routes=routes_out,
        precedents=result.precedents,
        applied_action=applied,
        pinned=pinned,
        blacklisted=blacklisted,
        error=result.error,
    )
