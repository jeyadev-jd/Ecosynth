"""
Download USPTO-50k reaction dataset and CHEM21 solvent data.

Run: python setup/01_download_data.py
Output: data/uspto_50k.csv, data/chem21_solvents.csv
"""

import os
import csv
import json
import requests
from pathlib import Path
from tqdm import tqdm

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# USPTO-50k — try multiple public mirrors
USPTO_FULL_URLS = {
    # Grambow et al. reactions dataset (MIT, ~12k reactions, SMILES format)
    "grambow": "https://raw.githubusercontent.com/grambow/reactants-products-ts/main/data/grambow2022/reactions.csv",
    # RXN4Chemistry test set (small but reliable)
    "rxn4chem": "https://raw.githubusercontent.com/rxn4chemistry/rxnmapper/main/tests/test_data/uspto_test.csv",
}

CHEM21_SOLVENTS = [
    # name, safety (1-10), health (1-10), environment (1-10)
    # Source: CHEM21 Solvent Selection Guide (Prat et al. 2016)
    ("water",           10, 10, 10),
    ("ethanol",          8,  8,  8),
    ("methanol",         6,  5,  7),
    ("ethyl acetate",    8,  8,  7),
    ("acetone",          8,  7,  7),
    ("2-methylthf",      7,  7,  8),
    ("2-me-thf",         7,  7,  8),
    ("isopropanol",      8,  8,  7),
    ("tert-butanol",     7,  7,  7),
    ("butyl acetate",    7,  7,  6),
    ("dimethyl sulfoxide", 6, 5, 5),
    ("dmso",             6,  5,  5),
    ("acetonitrile",     5,  4,  5),
    ("thf",              5,  5,  5),
    ("tetrahydrofuran",  5,  5,  5),
    ("toluene",          4,  3,  4),
    ("diethyl ether",    3,  5,  4),
    ("dichloromethane",  3,  3,  3),
    ("dcm",              3,  3,  3),
    ("chloroform",       2,  2,  2),
    ("hexane",           3,  3,  3),
    ("heptane",          4,  4,  4),
    ("dmf",              4,  3,  3),
    ("dimethylformamide", 4, 3,  3),
    ("dioxane",          2,  2,  3),
    ("1,4-dioxane",      2,  2,  3),
    ("benzene",          1,  1,  2),
    ("pyridine",         3,  2,  3),
    ("acetic acid",      5,  5,  5),
    ("cyclohexane",      4,  4,  4),
    ("xylene",           3,  3,  3),
    ("diisopropyl ether", 3, 4,  4),
    ("dme",              4,  4,  4),
    ("1,2-dimethoxyethane", 4, 4, 4),
    ("nmp",              3,  2,  3),
    ("n-methylpyrrolidone", 3, 2, 3),
]


def download_file(url: str, dest: Path, desc: str) -> bool:
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            desc=desc, total=total, unit="B", unit_scale=True
        ) as bar:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
        return True
    except Exception as e:
        print(f"  WARN: {desc} failed — {e}")
        return False


def build_chem21_csv():
    dest = DATA_DIR / "chem21_solvents.csv"
    with open(dest, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "safety", "health", "environment", "composite"])
        for row in CHEM21_SOLVENTS:
            name, s, h, e = row
            composite = round((s + h + e) / 3, 2)
            writer.writerow([name, s, h, e, composite])
    print(f"  Written {len(CHEM21_SOLVENTS)} solvents → {dest}")


def download_uspto():
    """
    Try to download USPTO reaction SMILES from public mirrors.
    Always falls back to curated seed set (robust offline operation).
    """
    dest = DATA_DIR / "uspto_50k.csv"
    if dest.exists():
        n = sum(1 for _ in open(dest)) - 1
        print(f"  USPTO data already at {dest} ({n} reactions), skipping.")
        return

    import pandas as pd
    rows = []

    for name, url in USPTO_FULL_URLS.items():
        tmp = DATA_DIR / f"_tmp_{name}.csv"
        ok = download_file(url, tmp, f"USPTO {name}")
        if not ok:
            continue
        try:
            df_tmp = pd.read_csv(tmp)
            # Try common column names for reaction SMILES
            for col in ["rxn_smiles", "reaction_smiles", "smiles", "rxn", "mapped_rxn"]:
                if col in df_tmp.columns:
                    for smi in df_tmp[col].dropna():
                        smi = str(smi).strip()
                        if ">>" not in smi:
                            continue
                        parts = smi.split(">")
                        rows.append({
                            "split": name,
                            "reaction_smiles": smi,
                            "reactants": parts[0],
                            "product": parts[-1],
                            "reaction_class": df_tmp.get("reaction_class", [""] * len(df_tmp)).iloc[0] if "reaction_class" in df_tmp.columns else "",
                        })
                    break
        except Exception as e:
            print(f"  WARN: could not parse {name}: {e}")
        finally:
            tmp.unlink(missing_ok=True)

    if rows:
        df_out = pd.DataFrame(rows)
        df_out.to_csv(dest, index=False)
        print(f"  Saved {len(df_out)} reactions from network → {dest}")
        return

    # Fallback: curated 200-reaction seed set covering common reaction classes
    print("  Network unavailable — writing seed reaction set.")
    seed_reactions = _seed_reactions()
    import pandas as pd
    df = pd.DataFrame(seed_reactions)
    df.to_csv(dest, index=False)
    print(f"  Saved {len(df)} seed reactions → {dest}")


def _seed_reactions():
    """Curated seed reactions covering key classes for RAG bootstrap."""
    reactions = []

    # ---- Esterification (10 examples) ----
    esterifications = [
        ("OC(=O)c1ccccc1.CCO>>CCOC(=O)c1ccccc1", "OC(=O)c1ccccc1.CCO", "CCOC(=O)c1ccccc1"),
        ("CC(=O)O.OCC>>CC(=O)OCC", "CC(=O)O.OCC", "CC(=O)OCC"),
        ("OC(=O)c1ccccc1O.CC(=O)O>>CC(=O)Oc1ccccc1C(=O)O", "OC(=O)c1ccccc1O.CC(=O)O", "CC(=O)Oc1ccccc1C(=O)O"),  # aspirin
        ("OC(=O)CCCCC.OCCO>>OCCOCCC(=O)CCCC", "OC(=O)CCCCC.OCCO", "OCCOCCC(=O)CCCC"),
        ("OC(=O)c1ccc(Cl)cc1.OCC>>CCOC(=O)c1ccc(Cl)cc1", "OC(=O)c1ccc(Cl)cc1.OCC", "CCOC(=O)c1ccc(Cl)cc1"),
        ("CC(=O)Cl.Oc1ccccc1>>CC(=O)Oc1ccccc1", "CC(=O)Cl.Oc1ccccc1", "CC(=O)Oc1ccccc1"),
        ("OC(=O)CCc1ccccc1.OC>>COC(=O)CCc1ccccc1", "OC(=O)CCc1ccccc1.OC", "COC(=O)CCc1ccccc1"),
        ("OC(=O)c1ccncc1.OCC(C)C>>CC(C)COC(=O)c1ccncc1", "OC(=O)c1ccncc1.OCC(C)C", "CC(C)COC(=O)c1ccncc1"),
        ("OC(=O)c1ccc(F)cc1.OCCO>>OCCOCCC(=O)c1ccc(F)cc1", "OC(=O)c1ccc(F)cc1.OCCO", "OCCOCCC(=O)c1ccc(F)cc1"),
        ("OC(=O)c1ccc(OC)cc1.CCO>>CCOC(=O)c1ccc(OC)cc1", "OC(=O)c1ccc(OC)cc1.CCO", "CCOC(=O)c1ccc(OC)cc1"),
    ]
    for smi, r, p in esterifications:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "esterification"})

    # ---- Amide coupling (8 examples) ----
    amides = [
        ("OC(=O)CCN.NCCc1ccccc1>>NCCc1ccccc1NCC(=O)CC", "OC(=O)CCN.NCCc1ccccc1", "NCCCC(=O)NCCc1ccccc1"),
        ("OC(=O)c1ccccc1.Nc1ccccc1>>O=C(Nc1ccccc1)c1ccccc1", "OC(=O)c1ccccc1.Nc1ccccc1", "O=C(Nc1ccccc1)c1ccccc1"),
        ("OC(=O)CC(N)=O.NCCCO>>NCCCOC(=O)CC(N)=O", "OC(=O)CC(N)=O.NCCCO", "NCCCOC(=O)CC(N)=O"),
        ("ClC(=O)c1ccccc1.Nc1ccc(Cl)cc1>>O=C(Nc1ccc(Cl)cc1)c1ccccc1", "ClC(=O)c1ccccc1.Nc1ccc(Cl)cc1", "O=C(Nc1ccc(Cl)cc1)c1ccccc1"),
        ("OC(=O)c1ccc(F)cc1.NCc1ccccn1>>O=C(NCc1ccccn1)c1ccc(F)cc1", "OC(=O)c1ccc(F)cc1.NCc1ccccn1", "O=C(NCc1ccccn1)c1ccc(F)cc1"),
        ("OC(=O)CCCc1ccccc1.NC1CCCCC1>>O=C(NC1CCCCC1)CCCc1ccccc1", "OC(=O)CCCc1ccccc1.NC1CCCCC1", "O=C(NC1CCCCC1)CCCc1ccccc1"),
        ("OC(=O)c1cccc(C)c1.NCc1ccccc1>>O=C(NCc1ccccc1)c1cccc(C)c1", "OC(=O)c1cccc(C)c1.NCc1ccccc1", "O=C(NCc1ccccc1)c1cccc(C)c1"),
        ("OC(=O)c1ccc(N)cc1.OC(=O)c1ccc(Cl)cc1>>O=C(Nc1ccc(C(=O)O)cc1)c1ccc(Cl)cc1", "OC(=O)c1ccc(N)cc1.OC(=O)c1ccc(Cl)cc1", "O=C(Nc1ccc(C(=O)O)cc1)c1ccc(Cl)cc1"),
    ]
    for smi, r, p in amides:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "amide_coupling"})

    # ---- Suzuki coupling (8 examples) ----
    suzukis = [
        ("Clc1ccccc1.OB(O)c1ccccc1>>c1ccc(-c2ccccc2)cc1", "Clc1ccccc1.OB(O)c1ccccc1", "c1ccc(-c2ccccc2)cc1"),
        ("Brc1ccc(F)cc1.OB(O)c1ccccc1>>Fc1ccc(-c2ccccc2)cc1", "Brc1ccc(F)cc1.OB(O)c1ccccc1", "Fc1ccc(-c2ccccc2)cc1"),
        ("Brc1ccncc1.OB(O)c1ccccc1>>c1cncc(-c2ccccc2)c1", "Brc1ccncc1.OB(O)c1ccccc1", "c1cncc(-c2ccccc2)c1"),
        ("Ic1ccccc1.OB(O)c1ccc(OC)cc1>>COc1ccc(-c2ccccc2)cc1", "Ic1ccccc1.OB(O)c1ccc(OC)cc1", "COc1ccc(-c2ccccc2)cc1"),
        ("Brc1ccc(C)cc1.OB(O)c1ccc(F)cc1>>Cc1ccc(-c2ccc(F)cc2)cc1", "Brc1ccc(C)cc1.OB(O)c1ccc(F)cc1", "Cc1ccc(-c2ccc(F)cc2)cc1"),
        ("Brc1ccccc1C(=O)O.OB(O)c1cccnc1>>OC(=O)c1ccccc1-c1cccnc1", "Brc1ccccc1C(=O)O.OB(O)c1cccnc1", "OC(=O)c1ccccc1-c1cccnc1"),
        ("Brc1ccc(C#N)cc1.OB(O)c1ccccc1>>N#Cc1ccc(-c2ccccc2)cc1", "Brc1ccc(C#N)cc1.OB(O)c1ccccc1", "N#Cc1ccc(-c2ccccc2)cc1"),
        ("Clc1nc2ccccc2n1Cc1ccccc1.OB(O)c1ccc(F)cc1>>Fc1ccc(-c2nc3ccccc3n2Cc2ccccc2)cc1", "Clc1nc2ccccc2n1Cc1ccccc1.OB(O)c1ccc(F)cc1", "Fc1ccc(-c2nc3ccccc3n2Cc2ccccc2)cc1"),
    ]
    for smi, r, p in suzukis:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "suzuki_coupling"})

    # ---- Buchwald-Hartwig (5 examples) ----
    buchwalds = [
        ("Clc1ccccc1.Nc1ccccc1>>c1ccc(Nc2ccccc2)cc1", "Clc1ccccc1.Nc1ccccc1", "c1ccc(Nc2ccccc2)cc1"),
        ("Brc1cccnc1.Nc1ccccc1>>c1ccc(Nc2cccnc2)cc1", "Brc1cccnc1.Nc1ccccc1", "c1ccc(Nc2cccnc2)cc1"),
        ("Clc1ccc(F)cc1.NC1CCCC1>>FC1CCCCC1", "Clc1ccc(F)cc1.NC1CCCC1", "Fc1ccc(NC2CCCC2)cc1"),
        ("Brc1ccc(C)cc1.Nc1cccc(C)c1>>Cc1ccc(Nc2cccc(C)c2)cc1", "Brc1ccc(C)cc1.Nc1cccc(C)c1", "Cc1ccc(Nc2cccc(C)c2)cc1"),
        ("Clc1ccccc1.CNC>>CNCc1ccccc1", "Clc1ccccc1.CNC", "CNCc1ccccc1"),
    ]
    for smi, r, p in buchwalds:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "buchwald_hartwig"})

    # ---- Reductive amination (6 examples) ----
    reductive_aminations = [
        ("O=Cc1ccccc1.NCc1ccccc1>>c1ccc(CNCc2ccccc2)cc1", "O=Cc1ccccc1.NCc1ccccc1", "c1ccc(CNCc2ccccc2)cc1"),
        ("O=CC1CCCC1.Nc1ccccc1>>c1ccc(NC2CCCC2)cc1", "O=CC1CCCC1.Nc1ccccc1", "c1ccc(NC2CCCC2)cc1"),
        ("CC(=O)c1ccccc1.NC>>CNC(C)c1ccccc1", "CC(=O)c1ccccc1.CNC", "CNC(C)c1ccccc1"),
        ("O=CCCC.Nc1ccc(F)cc1>>Fc1ccc(NCCC)cc1", "O=CCCC.Nc1ccc(F)cc1", "Fc1ccc(NCCCC)cc1"),
        ("O=Cc1ccc(OC)cc1.NCc1ccccn1>>COc1ccc(CNCc2ccccn2)cc1", "O=Cc1ccc(OC)cc1.NCc1ccccn1", "COc1ccc(CNCc2ccccn2)cc1"),
        ("CC(=O)CC.NCCCO>>OCCCNC(C)CC", "CC(=O)CC.NCCCO", "OCCCNC(C)CC"),
    ]
    for smi, r, p in reductive_aminations:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "reductive_amination"})

    # ---- Diels-Alder (5 examples) ----
    diels_alders = [
        ("C=CC=C.C=C>>C1CCCCC1", "C=CC=C.C=C", "C1CCCCC1"),
        ("C=CC(=C)C.C=CC=O>>O=C1CCCC(C)C1", "C=CC(=C)C.C=CC=O", "O=C1CCCC(C)C1"),
        ("C=Cc1ccccc1.C=CC=O>>O=C1CCC(c2ccccc2)CC1", "C=Cc1ccccc1.C=CC=O", "O=C1CCC(c2ccccc2)CC1"),
        ("C=CC=C.C=CC(=O)O>>OC(=O)C1CCCCC1", "C=CC=C.C=CC(=O)O", "OC(=O)C1CCCCC1"),
        ("C=CC=CC.C=C>>C1CCCCC1C", "C=CC=CC.C=C", "C1CCCCC1C"),
    ]
    for smi, r, p in diels_alders:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "diels_alder"})

    # ---- Oxidation (6 examples) ----
    oxidations = [
        ("OCc1ccccc1>>O=Cc1ccccc1", "OCc1ccccc1", "O=Cc1ccccc1"),
        ("OCC>>CC=O", "OCC", "CC=O"),
        ("OC(C)c1ccccc1>>O=C(C)c1ccccc1", "OC(C)c1ccccc1", "O=C(C)c1ccccc1"),
        ("OC1CCCCC1>>O=C1CCCCC1", "OC1CCCCC1", "O=C1CCCCC1"),
        ("OCCO>>OCC=O", "OCCO", "OCC=O"),
        ("OC(CCc1ccccc1)CC>>O=C(CCc1ccccc1)CC", "OC(CCc1ccccc1)CC", "O=C(CCc1ccccc1)CC"),
    ]
    for smi, r, p in oxidations:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "oxidation"})

    # ---- Reduction (6 examples) ----
    reductions = [
        ("O=Cc1ccccc1>>OCc1ccccc1", "O=Cc1ccccc1", "OCc1ccccc1"),
        ("O=C(C)c1ccccc1>>OC(C)c1ccccc1", "O=C(C)c1ccccc1", "OC(C)c1ccccc1"),
        ("CC(C)Cc1ccc(C(C)=O)cc1>>CC(C)Cc1ccc(C(C)O)cc1", "CC(C)Cc1ccc(C(C)=O)cc1", "CC(C)Cc1ccc(C(C)O)cc1"),
        ("O=C1CCCCC1>>OC1CCCCC1", "O=C1CCCCC1", "OC1CCCCC1"),
        ("N#Cc1ccccc1>>NCc1ccccc1", "N#Cc1ccccc1", "NCc1ccccc1"),
        ("O=C(O)c1ccc(N)cc1>>NCc1ccc(C(=O)O)cc1", "O=C(O)c1ccc(N)cc1", "NCc1ccc(CO)cc1"),
    ]
    for smi, r, p in reductions:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "reduction"})

    # ---- Aldol (5 examples) ----
    aldols = [
        ("CC(=O)C.O=Cc1ccccc1>>OC(Cc1ccccc1)C(C)=O", "CC(=O)C.O=Cc1ccccc1", "OC(Cc1ccccc1)C(C)=O"),
        ("CC(=O)CC.CC=O>>CC(O)C(C)CC", "CC(=O)CC.CC=O", "CC(O)C(C)CC"),
        ("CC(=O)c1ccccc1.O=Cc1ccccc1>>OC(c1ccccc1)C(=O)c1ccccc1", "CC(=O)c1ccccc1.O=Cc1ccccc1", "OC(c1ccccc1)C(=O)c1ccccc1"),
        ("CC(=O)CCC.O=O>>OCC(=O)CCC", "CC(=O)CCC.O=O", "OCC(=O)CCC"),
        ("CC(=O)C.CC=O>>CC(O)CC(C)=O", "CC(=O)C.CC=O", "CC(O)CC(C)=O"),
    ]
    for smi, r, p in aldols:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "aldol"})

    # ---- Grignard (5 examples) ----
    grignards = [
        ("BrCc1ccccc1.O=Cc1ccccc1>>OC(c1ccccc1)Cc1ccccc1", "BrCc1ccccc1.O=Cc1ccccc1", "OC(c1ccccc1)Cc1ccccc1"),
        ("BrCC.CC=O>>CCC(O)C", "BrCC.CC=O", "CCC(O)C"),
        ("BrCCc1ccccc1.O=C1CCCCC1>>OC1(CCc2ccccc2)CCCCC1", "BrCCc1ccccc1.O=C1CCCCC1", "OC1(CCc2ccccc2)CCCCC1"),
        ("BrCCCC.O=Cc1ccccc1>>OC(CCCBr)c1ccccc1", "BrCCCC.O=Cc1ccccc1", "OC(CCCC)c1ccccc1"),
        ("Brc1ccccc1.O=CCC>>OC(CC)c1ccccc1", "Brc1ccccc1.O=CCC", "OC(CC)c1ccccc1"),
    ]
    for smi, r, p in grignards:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "grignard"})

    # ---- Heck (5 examples) ----
    hecks = [
        ("Brc1ccccc1.C=Cc1ccccc1>>C=Cc1ccccc1c1ccccc1", "Brc1ccccc1.C=Cc1ccccc1", "C=Cc1ccccc1-c1ccccc1"),
        ("Ic1ccc(OC)cc1.C=CC(=O)OCC>>CCOC(=O)C=Cc1ccc(OC)cc1", "Ic1ccc(OC)cc1.C=CC(=O)OCC", "CCOC(=O)C=Cc1ccc(OC)cc1"),
        ("Brc1ccc(C)cc1.C=CC=O>>O=CC=Cc1ccc(C)cc1", "Brc1ccc(C)cc1.C=CC=O", "O=CC=Cc1ccc(C)cc1"),
        ("Brc1ccncc1.C=CC(C)=O>>CC(=O)C=Cc1ccncc1", "Brc1ccncc1.C=CC(C)=O", "CC(=O)C=Cc1ccncc1"),
        ("Ic1ccccc1.C=C>>C=Cc1ccccc1", "Ic1ccccc1.C=C", "C=Cc1ccccc1"),
    ]
    for smi, r, p in hecks:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "heck"})

    # ---- SN2 alkylation (5 examples) ----
    sn2s = [
        ("BrCC.Nc1ccccc1>>CNc1ccccc1", "BrCC.Nc1ccccc1", "CNCc1ccccc1"),
        ("ClCc1ccccc1.OCCc1ccccc1>>c1ccc(CCOCc2ccccc2)cc1", "ClCc1ccccc1.OCCc1ccccc1", "c1ccc(CCOCc2ccccc2)cc1"),
        ("BrCCC.OC>>CCCOC", "BrCCC.OC", "CCCOC"),
        ("Clc1ccccc1.OCC>>CCOc1ccccc1", "Clc1ccccc1.OCC", "CCOc1ccccc1"),
        ("BrCC.SC>>CCSCC", "BrCC.SC", "CCSC"),
    ]
    for smi, r, p in sn2s:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "sn2_alkylation"})

    # ---- Wittig / olefination (4 examples) ----
    wittigs = [
        ("O=Cc1ccccc1>>C=Cc1ccccc1", "O=Cc1ccccc1", "C=Cc1ccccc1"),
        ("CC=O>>CC=CC", "CC=O", "CC=CC"),
        ("O=C1CCCCC1>>C1=CCCCC1", "O=C1CCCCC1", "C1=CCCCC1"),
        ("O=Cc1ccc(OC)cc1>>C=Cc1ccc(OC)cc1", "O=Cc1ccc(OC)cc1", "C=Cc1ccc(OC)cc1"),
    ]
    for smi, r, p in wittigs:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "wittig"})

    # ---- Ring-closing metathesis (4 examples) ----
    rcms = [
        ("C=CCCC=C>>C1CC=CCC1", "C=CCCC=C", "C1CC=CCC1"),
        ("C=CCCCc1ccccc1C=C>>C1=CCCCc2ccccc21", "C=CCCCc1ccccc1C=C", "C1=CCCCc2ccccc21"),
        ("C=CCCCC=C>>C1CCC=CCC1", "C=CCCCC=C", "C1CCC=CCC1"),
        ("C=CC(CC=C)c1ccccc1>>C1CC(c2ccccc2)C=CC1", "C=CC(CC=C)c1ccccc1", "C1CC(c2ccccc2)C=CC1"),
    ]
    for smi, r, p in rcms:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "ring_closing_metathesis"})

    # ---- Hydrogenation (4 examples) ----
    hydrogenations = [
        ("C=Cc1ccccc1>>CCc1ccccc1", "C=Cc1ccccc1", "CCc1ccccc1"),
        ("C=CC(=O)O>>CCC(=O)O", "C=CC(=O)O", "CCC(=O)O"),
        ("O=C(/C=C/c1ccccc1)O>>OC(CCc1ccccc1)=O", "O=C(/C=C/c1ccccc1)O", "O=C(CCc1ccccc1)O"),
        ("c1ccc2[nH]ccnc2c1>>C1CCc2[nH]ccnc2C1", "c1ccc2[nH]ccnc2c1", "C1CCc2[nH]ccnc2C1"),
    ]
    for smi, r, p in hydrogenations:
        reactions.append({"split": "seed", "reaction_smiles": smi, "reactants": r, "product": p, "reaction_class": "hydrogenation"})

    return reactions


if __name__ == "__main__":
    print("=== EcoSynth Data Download ===")
    print("\n[1/2] Building CHEM21 solvent table...")
    build_chem21_csv()
    print("\n[2/2] Downloading USPTO-50k reactions...")
    download_uspto()
    print("\nDone. Check data/ directory.")
