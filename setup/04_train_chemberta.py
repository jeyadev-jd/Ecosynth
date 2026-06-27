"""
Fine-tune ChemBERTa-77M as a binary SMILES validity classifier.

Positive class (label=1): chemically valid SMILES from PubChem/USPTO
Negative class (label=0): corrupted/hallucinated SMILES

Run: python setup/04_train_chemberta.py
      (GPU recommended; CPU runs but takes ~3-4h)
Output: models/chemberta_firewall/  (HuggingFace model dir)
"""

import sys
import random
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
MODEL_DIR = ROOT / "models" / "chemberta_firewall"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "seyonec/ChemBERTa-zinc-base-v1"

CORRUPTION_STRATEGIES = [
    "swap_brackets",
    "drop_atom",
    "add_invalid_valence",
    "shuffle_fragment",
    "insert_invalid_char",
    "duplicate_ring_closure",
]


def corrupt_smiles(smi: str, rng: random.Random) -> str:
    strategy = rng.choice(CORRUPTION_STRATEGIES)
    try:
        if strategy == "swap_brackets" and "[" in smi:
            smi = smi.replace("[", "{", 1).replace("]", "}", 1)
        elif strategy == "drop_atom" and len(smi) > 4:
            idx = rng.randint(1, len(smi) - 2)
            smi = smi[:idx] + smi[idx + 1:]
        elif strategy == "add_invalid_valence":
            smi = smi.replace("C", "CCCCC", 1)[:len(smi) + 2]
        elif strategy == "shuffle_fragment" and "." in smi:
            parts = smi.split(".")
            rng.shuffle(parts)
            smi = ".".join(parts)
        elif strategy == "insert_invalid_char":
            idx = rng.randint(0, len(smi))
            smi = smi[:idx] + rng.choice(["@@@", "%%99", "**"]) + smi[idx:]
        elif strategy == "duplicate_ring_closure":
            smi = re.sub(r"(\d)", lambda m: m.group(1) + m.group(1), smi, count=1)
    except Exception:
        pass
    return smi


def collect_valid_smiles(df: pd.DataFrame, n: int, rng: random.Random) -> list[str]:
    from rdkit import Chem
    valid = []
    rows = df.sample(frac=1, random_state=42).itertuples()
    for row in rows:
        for smi_col in ["product", "reactants"]:
            smi = str(getattr(row, smi_col, "")).split(".")[0]
            if len(smi) < 4:
                continue
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                valid.append(smi)
        if len(valid) >= n:
            break
    return valid[:n]


def build_dataset(n_per_class: int = 5000):
    from rdkit import Chem

    csv_path = ROOT / "data" / "uspto_50k.csv"
    if not csv_path.exists():
        print("ERROR: data/uspto_50k.csv missing. Run setup/01_download_data.py first.")
        sys.exit(1)

    df = pd.read_csv(csv_path).fillna("")
    rng = random.Random(42)

    print(f"Collecting {n_per_class} valid SMILES...")
    valid_smiles = collect_valid_smiles(df, n_per_class, rng)
    print(f"  Got {len(valid_smiles)} valid.")

    print("Generating corrupted SMILES...")
    corrupted = []
    for smi in valid_smiles:
        bad = corrupt_smiles(smi, rng)
        # Confirm corruption actually broke it (or keep if still parses)
        if Chem.MolFromSmiles(bad) is None:
            corrupted.append(bad)
        else:
            # Try harder
            for _ in range(5):
                bad = corrupt_smiles(smi, rng)
                if Chem.MolFromSmiles(bad) is None:
                    corrupted.append(bad)
                    break

    n = min(len(valid_smiles), len(corrupted))
    texts = valid_smiles[:n] + corrupted[:n]
    labels = [1] * n + [0] * n

    combined = list(zip(texts, labels))
    rng.shuffle(combined)
    texts, labels = zip(*combined)

    print(f"  Dataset: {n} valid + {n} corrupted = {2*n} total")
    return list(texts), list(labels)


def train(n_per_class: int = 150, epochs: int = 2, batch_size: int = 8, lr: float = 2e-5):
    import torch
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        Trainer,
        TrainingArguments,
        DataCollatorWithPadding,
    )
    from torch.utils.data import Dataset

    class SMILESDataset(Dataset):
        def __init__(self, encodings, labels):
            self.encodings = encodings
            self.labels = labels

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, idx):
            item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
            item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
            return item

    texts, labels = build_dataset(n_per_class)
    split = int(0.9 * len(texts))
    train_texts, val_texts = texts[:split], texts[split:]
    train_labels, val_labels = labels[:split], labels[split:]

    print(f"\nLoading tokenizer from {BASE_MODEL}...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    print("Tokenizing...")
    train_enc = tokenizer(train_texts, truncation=True, padding=True, max_length=128)
    val_enc = tokenizer(val_texts, truncation=True, padding=True, max_length=128)

    train_ds = SMILESDataset(train_enc, train_labels)
    val_ds = SMILESDataset(val_enc, val_labels)

    print(f"Loading model {BASE_MODEL}...")
    model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=2)

    args = TrainingArguments(
        output_dir=str(MODEL_DIR / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=lr,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        logging_steps=50,
        warmup_ratio=0.1,
        report_to="none",
        use_cpu=not torch.cuda.is_available(),
    )

    def compute_metrics(eval_pred):
        logits, lab = eval_pred
        preds = np.argmax(logits, axis=-1)
        tp = ((preds == 1) & (lab == 1)).sum()
        fp = ((preds == 1) & (lab == 0)).sum()
        fn = ((preds == 0) & (lab == 1)).sum()
        precision = tp / (tp + fp + 1e-8)
        recall = tp / (tp + fn + 1e-8)
        f1 = 2 * precision * recall / (precision + recall + 1e-8)
        acc = (preds == lab).mean()
        return {"accuracy": float(acc), "f1": float(f1), "precision": float(precision), "recall": float(recall)}

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics,
    )

    print("\nTraining ChemBERTa validity classifier...")
    trainer.train()

    print(f"\nSaving model → {MODEL_DIR}")
    model.save_pretrained(str(MODEL_DIR))
    tokenizer.save_pretrained(str(MODEL_DIR))
    print("Done.")


if __name__ == "__main__":
    train()
