# Ecosynth

AI-assisted retrosynthesis planner that combines symbolic chemistry rules, RAG over literature/reaction data, and a green-chemistry scorer to propose, validate, and rank synthesis routes — with built-in hallucination detection and a React frontend for exploring reasoning traces.

## What it does

- **Retrosynthesis engine** (`ecosynth/`) — wraps AiZynthFinder for route search, builds a constraint graph over reaction steps, repairs broken branches, and scores routes for green-chemistry metrics (solvents, reagents).
- **Validity firewall** — checks proposed reactions against a taxonomy of known hallucination/failure modes before surfacing them.
- **RAG engine** — retrieves supporting literature/reaction precedent from a Chroma vector store (`data/chromadb/`) to ground route suggestions.
- **API** (`api/`) — FastAPI service exposing synthesis, steering, and health endpoints.
- **Frontend** (`frontend/`) — React + TypeScript UI: synthesis tree view, reasoning/constraint timelines, preference sliders, failure console.
- **Models** (`models/`) — trained green-chemistry random forest scorer.
- **Setup scripts** (`setup/`) — download reaction data (USPTO-50k), build the Chroma DB, train the green-RF and ChemBERTa models.

## Stack

Python (FastAPI, AiZynthFinder, ChromaDB, scikit-learn, transformers/ChemBERTa) + React/TypeScript/Vite frontend.

## Getting started

```bash
conda env create -f conda_env.yml
conda activate ecosynth
pip install -r requirements.txt

# one-time data/model setup
python setup/01_download_data.py
python setup/02_build_chromadb.py
python setup/03_train_green_rf.py
python setup/04_train_chemberta.py

./run.sh
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
pytest tests/
```

## Repo layout

```
api/        FastAPI app + routes (health, steer, synthesize)
ecosynth/   core pipeline: retrosynthesis, constraint graph, validity firewall, green scorer, RAG
frontend/   React/Vite UI
setup/      data download + model training scripts
models/     trained model artifacts
data/       reaction datasets, solvent/reagent tables, Chroma vector store
tests/      pytest suite
report/     project writeup (LaTeX)
```
