"""Build test releases with changes the organizers' make_release.py can't make, each with its answer written first.

Every release is built from release A, the planted change is recorded in EXPECTED.json at build time (before the
tool ever runs), and scripts/scorecard.py grades the tool against it. Unchanged cells are copied as their exact
text, like the organizers' generator.

Usage (from this repo, with the challenge repo next to it):
  python scripts/make_adversarial.py            # writes releases/x01_... to x07_... in the challenge repo
"""
from __future__ import annotations

import gzip
import json
import pathlib
import random
import shutil

import pandas as pd

CHALLENGE = pathlib.Path(__file__).resolve().parent.parent.parent / "oncosys-hackathon-challenge"
RAW = CHALLENGE / "data" / "tcga-brca" / "raw"
OUT = CHALLENGE / "data" / "tcga-brca" / "releases"
FILES = ["clinical.tsv", "survival.tsv", "mutation_gene_level.tsv.gz", "copy_number_gistic.tsv.gz", "protein_rppa.tsv.gz"]
P, C, S = "protein_rppa.tsv.gz", "clinical.tsv", "survival.tsv"
ER = "breast_carcinoma_estrogen_receptor_status"


def read(name):
    if name == C:
        return pd.read_csv(RAW / name, sep="\t", dtype=str, keep_default_na=False)
    return pd.read_csv(RAW / name, sep="\t", index_col=0, dtype=str, keep_default_na=False)


def write(df, dest, name):
    if name == C:
        df.to_csv(dest / name, sep="\t", index=False, lineterminator="\n")
    else:
        df.to_csv(dest / name, sep="\t", lineterminator="\n",
                  compression={"method": "gzip", "mtime": 0} if name.endswith(".gz") else None)


def fresh(name: str) -> pathlib.Path:
    dest = OUT / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for f in FILES:                       # envelope-style: no RNA file
        shutil.copy(RAW / f, dest / f)
    return dest


def save(dest, planted, expect, verdict):
    (dest / "EXPECTED.json").write_text(json.dumps({
        "release": dest.name, "planted": planted, "expect": sorted(expect), "verdict": verdict,
        "built_from": "release A (raw), checksums in sources.csv", "written_before_the_tool_ran": True}, indent=2))
    print(f"built {dest.name}: {planted}")


def main():
    rng = random.Random(2611)
    clinical = read(C)
    er = clinical.set_index("sampleID")[ER]
    prot = read(P)
    in_a1 = sorted(s for s in prot.columns if s[13:15] == "01" and er.get(s) in ("Positive", "Negative"))

    # x01: two samples' values quietly edited (no swap, copy or loss explains it)
    d = fresh("x01_edit_values")
    p = prot.copy()
    s1, s2 = rng.sample(in_a1, 2)
    p.loc["ERALPHA", s1] = f"{float(p.loc['ERALPHA', s1]) + 1.5:.6f}"
    p.loc["HER2", s2] = f"{float(p.loc['HER2', s2]) - 1.0:.6f}"
    write(p, d, P)
    save(d, f"ERALPHA edited for {s1}, HER2 edited for {s2}",
         [["other", P, s1], ["other", P, s2]], "Conditional")

    # x02: the ERALPHA row is gone, so A1 can't run
    d = fresh("x02_drop_eralpha")
    write(prot.drop(index="ERALPHA"), d, P)
    save(d, "ERALPHA row removed from the protein file", [], "Blocked")

    # x03: four survival outcomes flipped (no protected analysis reads survival)
    d = fresh("x03_survival_edit")
    sv = read(S)
    cand = sorted(s for s in sv.index if s[13:15] == "01" and sv.at[s, "OS"] == "0")
    picks = rng.sample(cand, 4)
    sv.loc[picks, "OS"] = "1"
    write(sv, d, S)
    save(d, f"OS flipped 0 -> 1 for {', '.join(picks)}", [["label_conflict", S, s] for s in picks], "Ready")

    # x04: one sample id renamed (its profile moves to an id that had no protein data; the old id disappears)
    d = fresh("x04_rename_id")
    old = rng.choice(in_a1)
    unused = sorted(s for s in clinical.sampleID if s[13:15] == "01" and s not in prot.columns
                    and er.get(s) in ("Positive", "Negative"))
    new = rng.choice(unused)
    write(prot.rename(columns={old: new}), d, P)
    save(d, f"protein column {old} renamed to {new}", [["other", P, new], ["other", P, old]], "Conditional")

    # x05: a truncated download (half the gzip bytes)
    d = fresh("x05_truncated_gzip")
    raw_bytes = (RAW / P).read_bytes()
    (d / P).write_bytes(raw_bytes[: len(raw_bytes) // 2])
    save(d, "protein file truncated to half its bytes", [], "Insufficient Evidence")

    # x06: the clinical file saved as commas instead of tabs
    d = fresh("x06_malformed_clinical")
    clinical.to_csv(d / C, sep=",", index=False, lineterminator="\n")
    save(d, "clinical.tsv written comma-separated", [], "Insufficient Evidence")

    # x07: an empty clinical file
    d = fresh("x07_empty_clinical")
    (d / C).write_bytes(b"")
    save(d, "clinical.tsv is empty", [], "Insufficient Evidence")


if __name__ == "__main__":
    main()
