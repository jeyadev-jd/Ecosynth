"""EcoSynth FastAPI application — Neuro-Symbolic Edition."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ecosynth.config import settings
from ecosynth.pipeline import EcoSynthPipeline, _cg_to_dict
from ecosynth.constraint_graph import ConstraintGraph
from api.routes import health, synthesize, steer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting EcoSynth pipeline...")
    app.state.pipeline = EcoSynthPipeline(settings)
    log.info("Pipeline ready.")
    yield
    log.info("EcoSynth shutdown.")


app = FastAPI(
    title="EcoSynth",
    description="Neuro-Symbolic Green Retrosynthesis — Dynamic Constraint Propagation + RouteScore",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(health.router, tags=["health"])
app.include_router(synthesize.router, prefix="/api", tags=["synthesis"])
app.include_router(steer.router, prefix="/api", tags=["steering"])

# ------------------------------------------------------------------
# Neuro-symbolic endpoints
# ------------------------------------------------------------------

class WeightsRequest(BaseModel):
    alpha: float = 0.4   # G weight
    beta:  float = 0.3   # V weight
    gamma: float = 0.2   # C weight
    delta: float = 0.1   # H weight


@app.post("/api/weights", tags=["neuro-symbolic"])
async def update_weights(body: WeightsRequest):
    """Update RouteScore weights α,β,γ,δ for this session."""
    total = body.alpha + body.beta + body.gamma + body.delta
    if abs(total - 1.0) > 0.05:
        raise HTTPException(status_code=400, detail=f"Weights must sum to ~1.0 (got {total:.3f})")
    settings.route_score_alpha = body.alpha
    settings.route_score_beta  = body.beta
    settings.route_score_gamma = body.gamma
    settings.route_score_delta = body.delta
    return {"status": "ok", "weights": {"alpha": body.alpha, "beta": body.beta, "gamma": body.gamma, "delta": body.delta}}


@app.get("/api/constraint-graph", tags=["neuro-symbolic"])
async def get_constraint_graph():
    """
    Return a fresh ConstraintGraph state (seeded from config paths only).
    Per-synthesis constraint state is returned inline in /api/synthesize responses.
    """
    cg = ConstraintGraph(
        compat_csv=settings.reagent_compat_csv,
        chem21_csv=settings.chem21_csv,
    )
    return _cg_to_dict(cg)


@app.get("/api/weights", tags=["neuro-symbolic"])
async def get_weights():
    """Return current RouteScore weights."""
    return {
        "alpha": settings.route_score_alpha,
        "beta":  settings.route_score_beta,
        "gamma": settings.route_score_gamma,
        "delta": settings.route_score_delta,
    }


# Serve built frontend (after `npm run build`)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file = FRONTEND_DIST / full_path
        if file.exists() and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
