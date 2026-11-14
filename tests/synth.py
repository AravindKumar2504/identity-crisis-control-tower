"""Small made-up releases in the event's file layout, for tests."""
from __future__ import annotations

import pathlib
import random

import pandas as pd

ER = "breast_carcinoma_estrogen_receptor_status"
PAM, NAT = "PAM50Call_RNAseq", "PAM50_mRNA_nature2012"
IHC, FINAL = "lab_proc_her2_neu_immunohistochemistry_receptor_status", "HER2_Final_Status_nature2012"
C, S = "clinical.tsv", "survival.tsv"
P, CN, MU = "protein_rppa.tsv.gz", "copy_number_gistic.tsv.gz", "mutation_gene_level.tsv.gz"
SUBTYPES = {"LumA": "Luminal A", "LumB": "Luminal B", "Basal": "Basal-like", "Her2": "HER2-enriched",
            "Normal": "Normal-like"}
SITES = ["A1", "B2", "C3", "D4"]


def sid(i: int, kind: str = "01") -> str:
    return f"TCGA-{SITES[i % len(SITES)]}-{i:04d}-{kind}"


def frames(n: int = 40, seed: int = 7) -> dict[str, pd.DataFrame]:
    """n primary tumors and 4 normals; the last 6 tumors have no protein data."""
    rng = random.Random(seed)
    tumors = [sid(i) for i in range(n)]
    normals = [sid(i, "11") for i in range(4)]
    codes = list(SUBTYPES)
    clinical = []
    for i, s in enumerate(tumors):
        er = "Negative" if i % 4 == 3 else "Positive"
        sub = codes[i % 5]
        clinical.append({"sampleID": s, ER: er, PAM: sub, NAT: SUBTYPES[sub] if i % 2 == 0 else "",
                         IHC: "Positive" if i % 5 == 3 else "Negative",
                         FINAL: "Positive" if i % 5 == 3 else "Negative"})
    clinical += [{"sampleID": s, ER: "", PAM: "", NAT: "", IHC: "", FINAL: ""} for s in normals]
    survival = []
    for i, s in enumerate(tumors + normals):
        t = str(200 + 37 * i)
        dead = "1" if i % 6 == 0 else "0"
        survival.append({"sample": s, "_PATIENT": s[:12], "OS": dead, "OS.time": t, "DSS": dead, "DSS.time": t,
                         "DFI": "0", "DFI.time": t, "PFI": dead, "PFI.time": t, "Redaction": ""})
    with_protein = tumors[:-6] + normals[:2]
    er_of = {r["sampleID"]: r[ER] for r in clinical}
    proteins = ["ERALPHA", "HER2", "PR"] + [f"PROT{i:02d}" for i in range(9)]
    prot = {}
    for s in with_protein:
        era = (2.0 if er_of[s] == "Positive" else -1.0 if er_of[s] == "Negative" else 0.5) + rng.uniform(-0.6, 0.6)
        prot[s] = [f"{era:.6f}"] + [f"{rng.uniform(-2, 2):.6f}" for _ in proteins[1:]]
    genes = [f"GENE{i:02d}" for i in range(12)]
    return {
        C: pd.DataFrame(clinical),
        S: pd.DataFrame(survival).set_index("sample"),
        P: pd.DataFrame(prot, index=pd.Index(proteins, name="sample")),
        CN: pd.DataFrame({s: [str(rng.choice([-2, -1, 0, 1, 2])) for _ in genes] for s in tumors + normals},
                         index=pd.Index(genes, name="Gene Symbol")),
        MU: pd.DataFrame({s: [str(rng.choice([0, 0, 0, 1])) for _ in genes] for s in tumors},
                         index=pd.Index(genes, name="sample")),
    }


def write(folder: pathlib.Path, fr: dict[str, pd.DataFrame], skip: tuple[str, ...] = ()) -> pathlib.Path:
    """Write the frames as a release folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in fr.items():
        if name in skip:
            continue
        if name == C:
            df.to_csv(folder / name, sep="\t", index=False, lineterminator="\n")
        else:
            df.to_csv(folder / name, sep="\t", lineterminator="\n",
                      compression={"method": "gzip", "mtime": 0} if name.endswith(".gz") else None)
    return folder


def copy(fr: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {k: v.copy() for k, v in fr.items()}


def a1_samples(fr: dict[str, pd.DataFrame]) -> tuple[list[str], list[str]]:
    """Tumors with protein data, by ER status: (positive, negative)."""
    er = fr[C].set_index("sampleID")[ER]
    have = [s for s in fr[P].columns if s[13:15] == "01"]
    return [s for s in have if er[s] == "Positive"], [s for s in have if er[s] == "Negative"]
