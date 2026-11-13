"""Release A design checks: does the question's design let a wrong answer look right?

  leakage_columns  a model's inputs include one of the 9 clinical columns derived from the subtype or its data
  a2_robustness    A2's subtype shares under each of the two subtype columns, side by side

Every count is computed from the release passed in, so the same checks work on sealed envelopes.
Each returns Issues in the shared contract (tower/checks/__init__.py).
"""
from __future__ import annotations

from collections import Counter

from ..cards import BLANKS, card_group
from . import Issue, register
from .fitness import DERIVED_FROM, PAM50_SRC, SUBTYPE_NAMES
from .labels import NAT, RNA, TCGA_2012

CL = "clinical.tsv"
# The 9 subtype-derived clinical columns a model must not use as inputs (docs/PLAN.md, leakage_columns).
LEAKAGE_COLUMNS = [
    "PAM50Call_RNAseq", "PAM50_mRNA_nature2012", "SigClust_Intrinsic_mRNA_nature2012",
    "SigClust_Unsupervised_mRNA_nature2012", "Integrated_Clusters_no_exp__nature2012",
    "Integrated_Clusters_unsup_exp__nature2012", "Integrated_Clusters_with_PAM50__nature2012",
    "RPPA_Clusters_nature2012", "CN_Clusters_nature2012",
]
INTEGRATED_WHY = "these clusters were computed in the 2012 study by combining several of the tumor's data types"
SHARE_GAP_POINTS = 5.0


def _blank(v) -> bool:
    return str(v).strip() in BLANKS


def _why(col: str) -> str:
    return DERIVED_FROM[col][1] if col in DERIVED_FROM else INTEGRATED_WHY


@register("leakage_columns")
def leakage_columns(release, card):
    name = "leakage_columns"
    feats = [str(f).strip() for f in (card.get("features") or [])]
    if not feats:
        return [Issue(id=name, title="The card trains no model, so this check doesn't apply", status="pass",
                      material=False, pre_existing=False)]
    whole_clinical = CL in feats
    leaking = [c for c in LEAKAGE_COLUMNS if whole_clinical or c in feats or f"{CL}:{c}" in feats]
    present = None
    if release.has(CL):
        cols = set(release.table(CL).frame.columns)
        present = [c for c in LEAKAGE_COLUMNS if c in cols]
    numbers = {"features": feats, "leaking": leaking,
               "whole_clinical_file_is_a_feature": whole_clinical,
               "columns_to_keep_out": {c: _why(c) for c in LEAKAGE_COLUMNS},
               "present_in_this_release": present if present is not None else "clinical.tsv not readable here"}
    n = len(LEAKAGE_COLUMNS)
    common = dict(id=name, pre_existing=False, rows=[], numbers=numbers,
                  source=f"{TCGA_2012} (where these columns come from); {PAM50_SRC}",
                  rule=f"Block if any of the {n} clinical columns computed from the subtype, or from the data that "
                       "defines it, is a model input: the model would score well by reading the answer.",
                  limitation=f"It checks only these {n} named columns; another field that encodes the subtype would "
                             "not be caught. It judges the card's design, not the data.")
    if not leaking:
        return [Issue(title=f"None of the {n} subtype-derived clinical columns is a model input", status="pass",
                      material=True, fields=[f"{CL}:{c}" for c in LEAKAGE_COLUMNS], **common)]
    how = " (the whole clinical file is listed as a feature)" if whole_clinical else ""
    return [Issue(title=f"{len(leaking)} of the model's inputs {'is a column' if len(leaking) == 1 else 'are columns'} "
                        f"computed from the subtype it predicts{how}",
                  status="block", material=True, fields=[f"{CL}:{c}" for c in leaking],
                  next_step=f"Drop {', '.join(leaking)} from the model's features.",
                  evidence_needed="A features list with none of these columns.",
                  **common)]


@register("a2_robustness")
def a2_robustness(release, card):
    name = "a2_robustness"
    fields = [f"{CL}:{RNA}", f"{CL}:{NAT}"]

    def unknown(title, numbers=None, next_step="", evidence=""):
        return [Issue(id=name, title=title, status="unknown", material=True, pre_existing=False, fields=fields,
                      numbers=numbers or {}, rule="A2's robustness needs both subtype columns.", source=TCGA_2012,
                      limitation="Without both columns the tool can't compare the subtype mix under each.",
                      next_step=next_step, evidence_needed=evidence)]

    if not release.has(CL):
        state = "unreadable" if CL in release.unreadable else "missing"
        return unknown(f"The clinical file is {state}, so A2's robustness can't be checked",
                       next_step="Get a release with a readable clinical.tsv.",
                       evidence="A release containing clinical.tsv, matching its published fingerprint.")
    cl = release.table(CL).frame
    missing = [c for c in (RNA, NAT) if c not in cl.columns]
    if missing:
        what = ", ".join(f"{CL}:{c}" for c in missing)
        return unknown(f"The clinical file has no {what} column, so A2's robustness can't be checked",
                       numbers={"missing_fields": missing}, next_step=f"Get a release whose clinical.tsv includes {what}.",
                       evidence=f"A release with {what}.")
    group = sorted(card_group(release, card))
    both = [s for s in group if not _blank(cl.at[s, RNA]) and not _blank(cl.at[s, NAT])]
    unmapped = [s for s in both if str(cl.at[s, RNA]).strip() not in SUBTYPE_NAMES]
    unmapped_set = set(unmapped)
    compared = [s for s in both if s not in unmapped_set]
    if not compared:
        return unknown("No tumor in this group has both subtype calls, so A2's robustness can't be checked",
                       numbers={"group_samples": len(group), "compared": 0},
                       next_step="Use a release where some tumors have both subtype calls.",
                       evidence="Tumors with both subtype calls.")

    rna = {s: SUBTYPE_NAMES[str(cl.at[s, RNA]).strip()] for s in compared}
    nat = {s: str(cl.at[s, NAT]).strip() for s in compared}
    n = len(compared)
    c_rna, c_nat = Counter(rna.values()), Counter(nat.values())
    names = list(SUBTYPE_NAMES.values()) + sorted(set(c_nat) - set(SUBTYPE_NAMES.values()))
    shares = {}
    for k in names:
        a, b = 100 * c_rna[k] / n, 100 * c_nat[k] / n
        shares[k] = {f"{RNA}_count": c_rna[k], f"{RNA}_percent": round(a, 1),
                     f"{NAT}_count": c_nat[k], f"{NAT}_percent": round(b, 1),
                     "difference_points": round(a - b, 1), "_gap": abs(a - b)}
    over = [k for k in names if shares[k]["_gap"] >= SHARE_GAP_POINTS]
    top = max(names, key=lambda k: shares[k]["_gap"])
    for v in shares.values():
        v.pop("_gap")
    disagree = [s for s in compared if rna[s] != nat[s]]

    called = [s for s in group if str(cl.at[s, RNA]).strip() in SUBTYPE_NAMES]
    a2_full = Counter(SUBTYPE_NAMES[str(cl.at[s, RNA]).strip()] for s in called)
    numbers = {"compared": n, "group_samples": len(group), "disagree": len(disagree),
               "unmapped_rnaseq_values": dict(Counter(str(cl.at[s, RNA]).strip() for s in unmapped)),
               "threshold_points": SHARE_GAP_POINTS, "largest_gap": top,
               "largest_gap_points": shares[top]["difference_points"], "subtypes_over_threshold": over,
               "shares": shares,
               "a2_on_whole_group_with_rnaseq_call": {"samples": len(called),
                                                      "percent": {k: round(100 * a2_full[k] / len(called), 1)
                                                                  for k in SUBTYPE_NAMES.values()} if called else {}},
               "compared_samples": compared}
    t = shares[top]
    head = (f"{top} is {t[f'{RNA}_percent']:.1f}% of tumors under one subtype column but {t[f'{NAT}_percent']:.1f}% "
            f"under the other ({abs(t['difference_points']):.1f} points; {n} tumors with both calls)")
    common = dict(id=name, pre_existing=True, fields=fields, rows=disagree, numbers=numbers,
                  source=TCGA_2012 + f" (the source of {NAT})",
                  rule=f"Warn if any subtype's share differs by {SHARE_GAP_POINTS:g} points or more between {RNA} and "
                       f"{NAT}, among tumors with both calls. Shares are compared before rounding.",
                  limitation=f"Only tumors with both calls can be compared ({n} of {len(group)} here), and neither "
                             "column is a ground truth. The rows are the tumors whose two calls disagree, which cause "
                             "the gap.")
    if not over:
        return [Issue(title=f"A2's subtype shares agree within {SHARE_GAP_POINTS:g} points under both subtype columns "
                            f"(largest gap: {top}, {abs(t['difference_points']):.1f} points)",
                      status="pass", material=True, **common)]
    return [Issue(title=head, status="warn", material=True,
                  next_step=f"Report the subtype mix under both {RNA} and {NAT}, or say which column is used and why.",
                  evidence_needed=f"A documented reason to prefer one subtype column, or shares that agree within "
                                  f"{SHARE_GAP_POINTS:g} points.",
                  **common)]
