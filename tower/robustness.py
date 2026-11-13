"""Does the conclusion still hold?

Two questions a reviewer asks about every release change:
  1. How much does THIS change move the result?  We undo that one change (put release A's data back for its
     samples) and rerun the analysis. The difference is the change's own effect.
  2. Does the research conclusion survive?  For A1 (ER-positive tumors have more ER-alpha protein than ER-negative
     ones) we resample the samples 1,000 times for a 95% range of the difference, and compare the result with and
     without every flagged sample. For A2 (the subtype mix) we report the largest shift in any subtype's share.
Numbers are computed from the same parsing and filters as the organizers' reference_analyses.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analyses import ER, PAM50, _clinical, _protein
from .release import sample_type

REPS, SEED = 1000, 7


# ------------------------------------------------------------------------------------------------ analyses on frames
def a1_frames(clin: pd.DataFrame, prot: pd.DataFrame) -> dict:
    er = clin.set_index("sampleID")[ER]
    samples = [s for s in prot.columns if sample_type(str(s)) == "01" and er.get(s) in ("Positive", "Negative")]
    vals = prot.loc["ERALPHA", samples].astype(float)
    pos = vals[[s for s in samples if er[s] == "Positive"]].to_numpy()
    neg = vals[[s for s in samples if er[s] == "Negative"]].to_numpy()
    return {"difference": float(pos.mean() - neg.mean()), "n": len(samples), "pos": pos, "neg": neg,
            "samples": samples}


def a2_frames(clin: pd.DataFrame) -> dict:
    c = clin[clin.sampleID.str[13:15] == "01"].dropna(subset=[PAM50])
    counts = c[PAM50].value_counts()
    return {"percent": {k: 100 * v / counts.sum() for k, v in counts.items()}, "n": int(counts.sum())}


def a1_range(r: dict) -> tuple[float, float]:
    """95% range of the ER+ minus ER- difference, resampling samples within each group (fixed seed)."""
    rng = np.random.default_rng(SEED)
    pos, neg = r["pos"], r["neg"]
    diffs = rng.choice(pos, (REPS, len(pos))).mean(1) - rng.choice(neg, (REPS, len(neg))).mean(1)
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


# ------------------------------------------------------------------------------------------------ undo one change
def _undo_matrix(samples, fa: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    fb = fb.copy()
    for s in samples:
        if s in fa.columns:
            fb[s] = fa[s]                 # swapped, edited, overwritten or lost: put release A's values back
        elif s in fb.columns:
            fb = fb.drop(columns=[s])     # an id that didn't exist in release A (a copy or a new sample)
    return fb


def _undo_clinical(change, ca: pd.DataFrame, cb: pd.DataFrame) -> pd.DataFrame:
    a, b = ca.set_index("sampleID"), cb.set_index("sampleID").copy()
    col = change.detail.get("column")
    for s in change.samples:
        if col is not None and s in a.index and s in b.index:
            b.loc[s, col] = a.loc[s, col]
        elif s in a.index and s not in b.index:
            b = pd.concat([b, a.loc[[s]]])
        elif s not in a.index and s in b.index:
            b = b.drop(index=s)
    return b.reset_index()


class Frames:
    """Release A and B parsed exactly like the reference analyses, loaded once."""

    def __init__(self, cmp):
        self.cmp = cmp
        self.ca, self.cb = _clinical(cmp.a), _clinical(cmp.b)
        has_p = cmp.a.has("protein_rppa.tsv.gz") and cmp.b.has("protein_rppa.tsv.gz")
        self.pa = _protein(cmp.a) if has_p else None
        self.pb = _protein(cmp.b) if has_p else None

    def undone(self, change):
        cb, pb = self.cb, self.pb
        if change.file == "clinical.tsv":
            cb = _undo_clinical(change, self.ca, self.cb)
        elif change.file == "protein_rppa.tsv.gz" and pb is not None:
            pb = _undo_matrix(change.samples, self.pa, self.pb)
        return cb, pb


def effects(cmp, changes, impact: dict) -> dict:
    """{change index: {analysis id: {now, if_undone, change, relative_pct}}} for changes that touch A1 or A2."""
    fr = Frames(cmp)
    out: dict = {}
    now_a1 = a1_frames(fr.cb, fr.pb)["difference"] if fr.pb is not None else None
    now_a2 = a2_frames(fr.cb)["percent"]
    for i, ch in enumerate(changes):
        hits = [aid for aid, (hit, _) in impact.get(i, {}).items() if hit]
        if not hits or not ch.samples:
            continue
        cb, pb = fr.undone(ch)
        res = {}
        if "A1" in hits and now_a1 is not None:
            undone = a1_frames(cb, pb)["difference"]
            res["A1"] = {"measure": "ER+ minus ER- difference", "now": round(now_a1, 3), "if_undone": round(undone, 3),
                         "change": round(now_a1 - undone, 3),
                         "relative_pct": round(abs(now_a1 - undone) / max(abs(undone), 1e-9) * 100, 2)}
        if "A2" in hits:
            undone = a2_frames(cb)["percent"]
            keys = set(undone) | set(now_a2)
            shift = max(abs(now_a2.get(k, 0) - undone.get(k, 0)) for k in keys)
            res["A2"] = {"measure": "largest subtype share shift (percentage points)", "now": None, "if_undone": None,
                         "change": round(shift, 2), "relative_pct": round(shift, 2)}
        out[i] = res
    return out


def conclusion(cmp_or_release, flagged: list[str] | None = None) -> dict:
    """Does A1's conclusion (ER+ tumors carry more ER-alpha protein than ER- tumors) hold in the new release?"""
    if hasattr(cmp_or_release, "a"):                      # a comparison
        fr = Frames(cmp_or_release)
        if fr.pb is None:
            return {}
        before, after = a1_frames(fr.ca, fr.pa), a1_frames(fr.cb, fr.pb)
        keep = [s for s in fr.pb.columns if s not in set(flagged or [])]
        without = a1_frames(fr.cb, fr.pb[keep]) if flagged else after
    else:
        rel = cmp_or_release
        if not rel.has("protein_rppa.tsv.gz"):
            return {}
        after = a1_frames(_clinical(rel), _protein(rel))
        before, without = None, after
    lo, hi = a1_range(after)
    holds = after["difference"] > 0 and lo > 0
    shift = (abs(after["difference"] - before["difference"]) / max(abs(before["difference"]), 1e-9) * 100) if before else 0.0
    reversed_ = before is not None and np.sign(before["difference"]) != np.sign(after["difference"])
    status = "reversed" if reversed_ else ("holds" if holds else "fragile")
    return {"analysis": "A1", "claim": "ER-positive primary tumors have higher mean ER-alpha protein than ER-negative ones",
            "status": status, "difference": round(after["difference"], 3), "range_95": [round(lo, 3), round(hi, 3)],
            "release_a_difference": round(before["difference"], 3) if before else None,
            "headline_shift_pct": round(shift, 2), "flagged_samples": len(flagged or []),
            "difference_without_flagged": round(without["difference"], 3), "n": after["n"]}
