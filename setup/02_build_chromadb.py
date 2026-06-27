"""
Build ChromaDB vector index from USPTO reaction data.

Run: python setup/02_build_chromadb.py
Reads:  data/uspto_50k.csv
Output: data/chromadb/  (persistent ChromaDB collection "uspto_reactions")
"""

import sys
import json
import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
CHROMA_DIR = DATA_DIR / "chromadb"


def smiles_to_fingerprint(smiles: str) -> Optional[list[float]]:
    """Morgan fingerprint (r=2, 2048-bit) as float list for ChromaDB metadata."""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
        return list(fp)
    except Exception:
        return None


def reaction_to_text(row: dict) -> str:
    parts = []
    if row.get("reaction_class"):
        parts.append(f"Reaction type: {row['reaction_class']}.")
    if row.get("reactants"):
        parts.append(f"Reactants SMILES: {row['reactants']}.")
    if row.get("product"):
        parts.append(f"Product SMILES: {row['product']}.")
    if row.get("reaction_smiles"):
        parts.append(f"Full reaction: {row['reaction_smiles']}.")
    return " ".join(parts)


def build_index(stream_batch: int = 2000):
    """Stream-encode+insert to avoid holding all embeddings in RAM."""
    csv_path = DATA_DIR / "uspto_50k.csv"
    if not csv_path.exists():
        print("ERROR: data/uspto_50k.csv not found.")
        sys.exit(1)

    import chromadb
    from sentence_transformers import SentenceTransformer

    print("Loading sentence encoder...")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")

    print("Opening ChromaDB...")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection("uspto_reactions")
    except Exception:
        pass
    collection = client.create_collection(
        name="uspto_reactions",
        metadata={"hnsw:space": "cosine"},
    )

    print("Loading USPTO data...")
    df = pd.read_csv(csv_path).fillna("")
    total = len(df)
    print(f"  {total} reactions.")

    seen_ids: set = set()
    buf_texts, buf_ids, buf_meta = [], [], []
    inserted = 0

    def flush():
        nonlocal inserted
        if not buf_texts:
            return
        embs = encoder.encode(buf_texts, batch_size=512, normalize_embeddings=True, show_progress_bar=False)
        collection.add(
            ids=buf_ids,
            documents=buf_texts,
            embeddings=[e.tolist() for e in embs],
            metadatas=buf_meta,
        )
        inserted += len(buf_texts)
        buf_texts.clear(); buf_ids.clear(); buf_meta.clear()

    for i, row in tqdm(df.iterrows(), total=total, desc="Indexing"):
        row_dict = row.to_dict()
        text = reaction_to_text(row_dict)
        if not text.strip():
            continue
        doc_id = hashlib.md5(text.encode()).hexdigest()
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        buf_texts.append(text)
        buf_ids.append(doc_id)
        buf_meta.append({
            "reaction_class": str(row_dict.get("reaction_class", "")),
            "reactants": str(row_dict.get("reactants", ""))[:500],
            "product": str(row_dict.get("product", ""))[:200],
            "reaction_smiles": str(row_dict.get("reaction_smiles", ""))[:500],
            "split": str(row_dict.get("split", "")),
            "morgan_fp_json": "",
        })
        if len(buf_texts) >= stream_batch:
            flush()

    flush()
    print(f"\nChromaDB built: {inserted} reactions indexed at {CHROMA_DIR}")


if __name__ == "__main__":
    build_index()
