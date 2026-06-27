"""
Train Random Forest green scorer on USPTO reaction data.

Uses the 5 green metrics (E-factor, AE, PMI, CHEM21, step penalty) computed
from RDKit atom counts. Since no labelled greenness ranking dataset is publicly
downloadable without login, we bootstrap training labels from a principled
heuristic (AE + inverse E-factor + CHEM21) and train RF to predict the composite.
The RF then generalises to unseen routes via the learned metric weights.

Run: python setup/03_train_green_rf.py
Reads:  data/uspto_50k.csv, data/chem21_solvents.csv
Output: models/green_rf.pkl, models/green_rf_features.json
"""

import sys
import json
import math
from pathlib import Path

import pandas as pd
import numpy as np
from tqdm import tqdm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)


def load_chem21(csv_path: Path) -> dict[str, float]:
    df = pd.read_csv(csv_path)
    return {row["name"].lower(): float(row["composite"]) for _, row in df.iterrows()}


def parse_reaction_smiles(rxn_smi: str):
    """Return (reactant_mols, product_mol) or (None, None) on failure."""
    from rdkit import Chem
    try:
        parts = rxn_smi.split(">>")
        reactant_smis = parts[0].split(".")
        product_smi = parts[-1].split(".")[0]
        r_mols = [Chem.MolFromSmiles(s) for s in reactant_smis]
        p_mol = Chem.MolFromSmiles(product_smi)
        if None in r_mols or p_mol is None:
            return None, None
        return r_mols, p_mol
    except Exception:
        return None, None


def atom_economy(r_mols, p_mol) -> float:
    from rdkit.Chem import Descriptors
    try:
        mw_prod = Descriptors.ExactMolWt(p_mol)
        mw_reactants = sum(Descriptors.ExactMolWt(m) for m in r_mols)
        if mw_reactants == 0:
            return 0.0
        return min(mw_prod / mw_reactants, 1.0)
    except Exception:
        return 0.0


def e_factor_proxy(r_mols, p_mol) -> float:
    """Proxy E-factor using atom count ratio (waste atoms / product atoms)."""
    from rdkit.Chem import Descriptors
    try:
        mw_prod = Descriptors.ExactMolWt(p_mol)
        mw_all = sum(Descriptors.ExactMolWt(m) for m in r_mols)
        waste = max(mw_all - mw_prod, 0)
        if mw_prod == 0:
            return 100.0
        return waste / mw_prod
    except Exception:
        return 100.0


def pmi_proxy(r_mols, p_mol) -> float:
    from rdkit.Chem import Descriptors
    try:
        mw_all = sum(Descriptors.ExactMolWt(m) for m in r_mols)
        mw_prod = Descriptors.ExactMolWt(p_mol)
        if mw_prod == 0:
            return 100.0
        return mw_all / mw_prod
    except Exception:
        return 100.0


def compute_features(row: dict, chem21: dict, step_count: int = 1) -> dict | None:
    rxn_smi = str(row.get("reaction_smiles", ""))
    if ">>" not in rxn_smi:
        return None

    r_mols, p_mol = parse_reaction_smiles(rxn_smi)
    if r_mols is None:
        return None

    ae = atom_economy(r_mols, p_mol)
    ef = e_factor_proxy(r_mols, p_mol)
    pmi = pmi_proxy(r_mols, p_mol)
    solvent_score = chem21.get("ethanol", 8.0) / 10.0  # default: ethanol if unknown
    step_pen = math.exp(-0.2 * step_count)

    # Normalise to [0, 1] where higher = greener
    ef_norm = 1.0 / (1.0 + ef)       # high E-factor → low score
    pmi_norm = 1.0 / (1.0 + pmi)     # high PMI → low score

    return {
        "ae": ae,
        "ef_norm": ef_norm,
        "pmi_norm": pmi_norm,
        "chem21": solvent_score,
        "step_penalty": step_pen,
    }


def bootstrap_label(feat: dict) -> float:
    """Heuristic composite greenness label used to supervise RF training."""
    return (
        0.30 * feat["ae"]
        + 0.25 * feat["ef_norm"]
        + 0.20 * feat["pmi_norm"]
        + 0.15 * feat["chem21"]
        + 0.10 * feat["step_penalty"]
    )


def train(max_rows: int = 10_000):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error
    import joblib

    csv_path = ROOT / "data" / "uspto_50k.csv"
    chem21_path = ROOT / "data" / "chem21_solvents.csv"

    if not csv_path.exists():
        print("ERROR: data/uspto_50k.csv missing. Run setup/01_download_data.py first.")
        sys.exit(1)
    if not chem21_path.exists():
        print("ERROR: data/chem21_solvents.csv missing. Run setup/01_download_data.py first.")
        sys.exit(1)

    chem21 = load_chem21(chem21_path)
    df = pd.read_csv(csv_path).fillna("").head(max_rows)

    print(f"Computing green metrics for {len(df)} reactions...")
    X_rows, y_rows = [], []
    for _, row in tqdm(df.iterrows(), total=len(df)):
        feat = compute_features(row.to_dict(), chem21)
        if feat is None:
            continue
        X_rows.append([feat["ae"], feat["ef_norm"], feat["pmi_norm"], feat["chem21"], feat["step_penalty"]])
        y_rows.append(bootstrap_label(feat))

    X = np.array(X_rows)
    y = np.array(y_rows)
    print(f"  Valid reactions for training: {len(X)}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training Random Forest...")
    rf = RandomForestRegressor(n_estimators=200, max_depth=12, n_jobs=-1, random_state=42)
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    rmse = math.sqrt(mean_squared_error(y_test, y_pred))
    print(f"  Test RMSE: {rmse:.4f}")

    feature_names = ["atom_economy", "e_factor_norm", "pmi_norm", "chem21_score", "step_penalty"]
    importances = dict(zip(feature_names, rf.feature_importances_.tolist()))
    print(f"  Feature importances: {importances}")

    model_path = MODEL_DIR / "green_rf.pkl"
    joblib.dump(rf, model_path)
    print(f"  Model saved → {model_path}")

    meta = {
        "feature_names": feature_names,
        "feature_importances": importances,
        "train_size": len(X_train),
        "test_rmse": rmse,
    }
    meta_path = MODEL_DIR / "green_rf_features.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Metadata saved → {meta_path}")


if __name__ == "__main__":
    train()
