"""The analyses a new release must not silently break, each declaring exactly what it reads.

A1 and A2 reproduce the organizers' data/tcga-brca/reference_analyses.py number for number (same parsing,
same filters, same rounding), so before-and-after results can be compared with theirs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .diff import Change
from .release import Release, sample_type

ER = "breast_carcinoma_estrogen_receptor_status"
PAM50 = "PAM50Call_RNAseq"


def _clinical(rel: Release) -> pd.DataFrame:
    return pd.read_csv(rel.path / "clinical.tsv", sep="\t", low_memory=False)


def _protein(rel: Release) -> pd.DataFrame:
    return pd.read_csv(rel.path / "protein_rppa.tsv.gz", sep="\t", index_col=0)


def run_a1(rel: Release) -> dict:
    clinical, protein = _clinical(rel), _protein(rel)
    er = clinical.set_index("sampleID")[ER]
    samples = [s for s in protein.columns if sample_type(str(s)) == "01" and er.get(s) in ("Positive", "Negative")]
    if "ERALPHA" not in protein.index or not samples:
        raise ValueError("A1 cannot run: the ERALPHA row or the ER-labelled primary tumors are missing")
    vals = protein.loc["ERALPHA", samples]
    groups = {k: vals[[s for s in samples if er[s] == k]] for k in ("Positive", "Negative")}
    return {"n_samples": len(samples), "sample_ids": sorted(samples),
            "n_positive": int(groups["Positive"].size), "n_negative": int(groups["Negative"].size),
            "mean_positive": round(float(groups["Positive"].mean()), 3),
            "mean_negative": round(float(groups["Negative"].mean()), 3),
            "difference": round(float(groups["Positive"].mean() - groups["Negative"].mean()), 3)}


def run_a2(rel: Release) -> dict:
    clinical = _clinical(rel)
    c = clinical[clinical.sampleID.str[13:15] == "01"].dropna(subset=[PAM50])
    counts = c[PAM50].value_counts().sort_index()
    if counts.sum() == 0:
        raise ValueError("A2 cannot run: no primary tumor has a subtype call")
    return {"n_samples": int(counts.sum()), "sample_ids": sorted(c.sampleID),
            "counts": {k: int(v) for k, v in counts.items()},
            "percent": {k: round(100 * v / counts.sum(), 1) for k, v in counts.items()}}


@dataclass
class Analysis:
    id: str
    title: str
    reads: dict[str, list[str]]          # file -> clinical columns (row files) or matrix rows it reads
    run: Callable[[Release], dict]

    def can_run(self, rel: Release) -> bool:
        return all(rel.has(f) for f in self.reads)


ANALYSES = [
    Analysis("A1", "ER-alpha protein by clinical ER status (primary tumors)",
             {"clinical.tsv": [ER], "protein_rppa.tsv.gz": ["ERALPHA"]}, run_a1),
    Analysis("A2", "PAM50 subtype mix of primary tumors",
             {"clinical.tsv": [PAM50]}, run_a2),
]


def touches(change: Change, an: Analysis, pop_a: set[str], pop_b: set[str], a: Release, b: Release) -> tuple[bool, str]:
    """Does this change touch something the analysis reads? Returns (affected, reason in plain words)."""
    if change.file not in an.reads:
        return False, f"{an.id} does not read {change.file}"
    if change.detail.get("file_missing"):
        return True, f"{an.id} reads {change.file}, which is missing"
    col = change.detail.get("column")
    if col is not None and col not in an.reads[change.file]:
        return False, f"{an.id} does not read the '{col}' column"
    if change.kind == "other" and not change.samples:
        lost_rows = set(change.detail.get("rows_removed", [])) | set(change.detail.get("columns_removed", []))
        if lost_rows & set(an.reads[change.file]):
            return True, f"{an.id} reads {', '.join(sorted(lost_rows & set(an.reads[change.file])))}, which was removed"
        return False, f"{an.id} does not read the rows or columns that changed"
    hit = sorted(set(change.samples) & (pop_a | pop_b))
    if not hit:
        # A gained or relabelled primary tumor can enter the analysis without being in either population yet.
        return False, f"none of these samples is in {an.id}'s group of samples in either release"
    edits_only = "edited" in change.detail or "blanked" in change.detail   # renames and moves always touch A1's samples
    if change.kind in ("missing_data", "other") and change.file == "protein_rppa.tsv.gz" and edits_only:
        pa, pb = _protein(a), _protein(b)
        moved = [s for s in hit if s in pa.columns and s in pb.columns and "ERALPHA" in pa.index
                 and "ERALPHA" in pb.index and str(pa.at["ERALPHA", s]) != str(pb.at["ERALPHA", s])]
        if not moved:
            return False, f"the changed values are not in the ERALPHA row that {an.id} reads"
    return True, f"{len(hit)} of these samples are in {an.id}'s group of samples"


def rerun(a: Release, b: Release, changes: list[Change], selected: list[str] | None = None):
    """Run each analysis on release A; rerun on release B only if a change touches it.

    Returns (results, impact) where results[id] = {status, before, after, reason} and
    impact[change index] = {analysis id: (affected, reason)}.
    """
    results, impact = {}, {i: {} for i in range(len(changes))}
    for an in ANALYSES:
        if selected and an.id not in selected:
            continue
        try:
            before = an.run(a)
        except Exception as e:  # release A itself cannot support it
            results[an.id] = {"status": "not_rerun", "before": None, "after": None,
                              "reason": f"could not run on release {a.name}: {e}", "title": an.title}
            continue
        pop_a = set(before["sample_ids"])
        if not an.can_run(b):
            missing = [f + (" (unreadable)" if f in b.unreadable else "") for f in an.reads if not b.has(f)]
            for i, ch in enumerate(changes):
                impact[i][an.id] = touches(ch, an, pop_a, set(), a, b)
            results[an.id] = {"status": "not_rerun", "before": _public(before), "after": None,
                              "reason": f"release {b.name} has no {', '.join(missing)}", "title": an.title,
                              "blocked": True}
            continue
        # Population in B is needed to judge samples that enter the analysis; it is cheap to compute.
        try:
            after = an.run(b)
            pop_b = set(after["sample_ids"])
        except Exception as e:
            after, pop_b = None, set()
            results[an.id] = {"status": "not_rerun", "before": _public(before), "after": None,
                              "reason": f"could not run on release {b.name}: {e}", "title": an.title, "blocked": True}
        hits = []
        for i, ch in enumerate(changes):
            impact[i][an.id] = touches(ch, an, pop_a, pop_b, a, b)
            if impact[i][an.id][0]:
                hits.append(i)
        if an.id in results:                       # could not run on B
            continue
        if not hits:
            results[an.id] = {"status": "not_rerun", "before": _public(before), "after": None, "title": an.title,
                              "reason": f"no change touches what {an.id} reads, so it was left alone"}
            continue
        same = _public(before) == _public(after) and before["sample_ids"] == after["sample_ids"]
        results[an.id] = {"status": "unchanged" if same else "changed", "before": _public(before),
                          "after": _public(after), "title": an.title,
                          "reason": f"rerun because {len(hits)} finding(s) touch what {an.id} reads",
                          "entered": sorted(pop_b - pop_a), "left": sorted(pop_a - pop_b)}
    return results, impact


def _public(r: dict | None) -> dict | None:
    if r is None:
        return None
    return {k: v for k, v in r.items() if k != "sample_ids"}
