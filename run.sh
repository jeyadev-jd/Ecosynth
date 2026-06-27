#!/usr/bin/env bash
# EcoSynth — one-shot runner
# Usage: ./run.sh [dev|build|serve|setup|test]
set -e

MODE="${1:-serve}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

case "$MODE" in
  setup)
    echo "=== EcoSynth Setup ==="
    echo "[1/4] Downloading data..."
    python setup/01_download_data.py
    echo "[2/4] Building ChromaDB index..."
    python setup/02_build_chromadb.py
    echo "[3/4] Training green RF scorer..."
    python setup/03_train_green_rf.py
    echo "[4/4] Fine-tuning ChemBERTa validity classifier..."
    python setup/04_train_chemberta.py
    echo "Setup complete."
    ;;
  build)
    echo "=== Building frontend ==="
    cd "$ROOT/frontend"
    npm install
    npm run build
    echo "Frontend built at frontend/dist/"
    ;;
  dev)
    echo "=== Dev mode: API + frontend hot-reload ==="
    # Start API in background
    uvicorn api.main:app --reload --port 8000 &
    API_PID=$!
    trap "kill $API_PID" EXIT
    cd "$ROOT/frontend"
    npm run dev
    ;;
  serve)
    echo "=== Production serve ==="
    if [ ! -d "$ROOT/frontend/dist" ]; then
      echo "Frontend not built. Run: ./run.sh build"
      exit 1
    fi
    uvicorn api.main:app --host 0.0.0.0 --port 8000
    ;;
  test)
    echo "=== Running tests ==="
    python -m pytest tests/ -v --tb=short
    ;;
  *)
    echo "Usage: ./run.sh [setup|build|dev|serve|test]"
    exit 1
    ;;
esac
