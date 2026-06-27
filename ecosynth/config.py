"""Central configuration via Pydantic Settings. Override with .env or env vars."""

from pathlib import Path
from pydantic_settings import BaseSettings


ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    # Paths
    data_dir: Path = ROOT / "data"
    models_dir: Path = ROOT / "models"
    chroma_dir: Path = ROOT / "data" / "chromadb"
    chem21_csv: Path = ROOT / "data" / "chem21_solvents.csv"
    green_rf_model: Path = ROOT / "models" / "green_rf.pkl"
    chemberta_model: Path = ROOT / "models" / "chemberta_firewall"
    aizynthfinder_config: Path = ROOT / "data" / "aizynthfinder_config.yml"

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_collection: str = "uspto_reactions"
    rag_top_k: int = 5

    # LLM (Ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:1b"
    ollama_timeout: int = 120

    # AizynthFinder
    aizynthfinder_time_limit: int = 60
    aizynthfinder_max_transforms: int = 4
    aizynthfinder_iterations: int = 100

    # Neuro-symbolic components
    reagent_compat_csv: Path = ROOT / "data" / "reagent_compatibility.csv"

    # RouteScore weights: αG + βV + γC + δH
    route_score_alpha: float = 0.4   # G: greenness
    route_score_beta:  float = 0.3   # V: validity
    route_score_gamma: float = 0.2   # C: confidence (RAG precedent)
    route_score_delta: float = 0.1   # H: human preference

    # HT-03 threshold: ChromaDB distance above this = no precedent warning
    ht_precedent_threshold: float = 0.3

    # Branch repair
    max_branch_repair_attempts: int = 3

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    class Config:
        env_file = ROOT / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
