from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "ecosynth"})


@router.get("/ready")
async def ready(request):
    pipeline = request.app.state.pipeline
    return JSONResponse({
        "status": "ready",
        "aizynthfinder": pipeline.aizynb.is_available,
        "chemberta": pipeline.firewall.model is not None,
        "chromadb": pipeline.rag.collection is not None,
    })
