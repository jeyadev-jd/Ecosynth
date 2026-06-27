"""RDKit helpers — SMILES parsing, fingerprints, sanitisation."""

from typing import Optional
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors


def parse_smiles(smiles: str) -> Optional[Chem.Mol]:
    """Return sanitised RDKit Mol or None."""
    if not smiles or not smiles.strip():
        return None
    try:
        mol = Chem.MolFromSmiles(smiles.strip())
        if mol is not None:
            Chem.SanitizeMol(mol)
        return mol
    except Exception:
        return None


def morgan_fp(smiles: str, radius: int = 2, n_bits: int = 2048) -> Optional[list[int]]:
    """Return Morgan fingerprint as int list, or None on parse failure."""
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=n_bits)
    return list(fp)


def mol_weight(smiles: str) -> float:
    mol = parse_smiles(smiles)
    if mol is None:
        return 0.0
    return Descriptors.ExactMolWt(mol)


def atom_count(smiles: str) -> int:
    mol = parse_smiles(smiles)
    if mol is None:
        return 0
    return mol.GetNumAtoms()


def smiles_to_inchi(smiles: str) -> Optional[str]:
    from rdkit.Chem.inchi import MolToInchi
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    try:
        return MolToInchi(mol)
    except Exception:
        return None


def canonicalise(smiles: str) -> Optional[str]:
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)
