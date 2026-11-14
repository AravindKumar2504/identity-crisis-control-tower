"""Release A label checks (Aakruti): two clinical fields that claim to record the same thing, but disagree.

  subtype_columns_disagree  PAM50Call_RNAseq vs PAM50_mRNA_nature2012 (the PAM50 subtype under two calls)
  her2_field_conflict       HER2 by immunohistochemistry vs HER2_Final_Status_nature2012 (which also uses FISH)

Every count is computed from the release passed in, so the same checks work on sealed envelopes.
Each returns Issues in the shared contract (tower/checks/__init__.py).
"""
from __future__ import annotations

from collections import Counter

from ..cards import BLANKS, card_group
from ..release import sample_type
from . import Issue, register
from .fitness import SUBTYPE_NAMES

CL = "clinical.tsv"
TCGA_2012 = ("Cancer Genome Atlas Network, Comprehensive molecular portraits of human breast tumours, Nature 2012, "
             "https://doi.org/10.1038/nature11412")
RNA, NAT = "PAM50Call_RNAseq", "PAM50_mRNA_nature2012"
IHC, FINAL = "lab_proc_her2_neu_immunohistochemistry_receptor_status", "HER2_Final_Status_nature2012"
DEFAULT_SUBTYPE_LIMIT = 0.05

# Plain names for the columns, for text a non-specialist reads: (plain name, plain name with the raw column).
# The raw column goes in brackets on its first mention in each title, next step or limitation.
COLUMN_NAMES = {
    RNA: ("the PAM50 subtype call from RNA sequencing", f"the PAM50 subtype call from RNA sequencing ({RNA})"),
    NAT: ("the PAM50 subtype call from the 2012 TCGA study",
          f"the PAM50 subtype call from the 2012 TCGA study ({NAT})"),
    IHC: ("the HER2 protein test result (IHC)", f"the HER2 protein test result (IHC; {IHC})"),
    FINAL: ("the final HER2 status from the 2012 study",
            f"the final HER2 status from the 2012 study ({FINAL}), which also uses a FISH test"),
}


def plain_name(col: str, names: dict | None = None) -> str:
    """The plain name of a column, or the raw column when it has none."""
    return (names or COLUMN_NAMES).get(col, (col, col))[0]


def named(col: str, names: dict | None = None) -> str:
    """The plain name with the raw column in brackets (for a first mention), or the raw column when it has none."""
    return (names or COLUMN_NAMES).get(col, (col, col))[1]


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _blank(v) -> bool:
    return str(v).strip() in BLANKS


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _load(release, card, name: str, columns: list[str]):
    """The clinical table and the card's group, or an 'unknown' Issue explaining why it can't be judged."""
    fields = [f"{CL}:{c}" for c in columns]
    if not release.has(CL):
        state = "unreadable" if CL in release.unreadable else "missing"
        return None, None, Issue(
            id=name, title=f"The clinical file is {state}, so this can't be checked", status="unknown",
            material=True, pre_existing=False, fields=fields,
            rule="This check can only be judged from a readable clinical.tsv.", source=TCGA_2012,
            limitation="Without the clinical file the tool can't see either field.",
            next_step="Get a release with a readable clinical file (clinical.tsv).",
            evidence_needed="A release containing clinical.tsv, matching its published fingerprint.")
    cl = release.table(CL).frame
    missing = [c for c in columns if c not in cl.columns]
    if missing:
        what = ", ".join(f"{CL}:{c}" for c in missing)
        plain = " or ".join(plain_name(c) for c in missing)
        return None, None, Issue(
            id=name, title=f"The clinical file has no column for {plain}, so this can't be checked", status="unknown",
            material=True, pre_existing=False, fields=fields, numbers={"missing_fields": missing},
            rule="This check compares two fields, so both must exist.", source=TCGA_2012,
            limitation="Without both fields the tool can't tell whether they agree.",
            next_step=f"Get a release whose clinical file includes {' and '.join(named(c) for c in missing)}.",
            evidence_needed=f"A release with {what}.")
    group = sorted(card_group(release, card))
    if not group:
        return None, None, Issue(
            id=name, title="This question's group has no samples in this release, so this can't be checked",
            status="unknown", material=True, pre_existing=False, fields=fields, numbers={"group_samples": 0},
            rule="This check needs the question's group to have samples.", source=TCGA_2012,
            limitation="The group may be empty because a file or column the group needs is missing.",
            next_step="Check that every file and column in the card's group exists and is readable.",
            evidence_needed="A release where the question's group has samples.")
    return cl, group, None


@register("subtype_columns_disagree")
def subtype_columns_disagree(release, card):
    name = "subtype_columns_disagree"
    cl, group, bad = _load(release, card, name, [RNA, NAT])
    if bad:
        return [bad]
    limits = card.get("limits") or {}
    limit = float(limits.get("subtype_disagreement", DEFAULT_SUBTYPE_LIMIT))
    limit_from = "card" if "subtype_disagreement" in limits else "default"

    both = [s for s in group if not _blank(cl.at[s, RNA]) and not _blank(cl.at[s, NAT])]
    unmapped = [s for s in both if str(cl.at[s, RNA]).strip() not in SUBTYPE_NAMES]
    compared = [s for s in both if s not in set(unmapped)]
    differ = [s for s in compared if SUBTYPE_NAMES[str(cl.at[s, RNA]).strip()] != str(cl.at[s, NAT]).strip()]
    share = len(differ) / len(compared) if compared else 0.0
    pairs = Counter(f"{cl.at[s, RNA]} vs {cl.at[s, NAT]}" for s in differ)
    numbers = {"compared": len(compared), "disagree": len(differ), "share": round(share, 4),
               "limit": limit, "limit_from": limit_from, "group_samples": len(group),
               "only_one_column_filled": sum(_blank(cl.at[s, RNA]) != _blank(cl.at[s, NAT]) for s in group),
               "unmapped_rnaseq_values": dict(Counter(str(cl.at[s, RNA]).strip() for s in unmapped)),
               "disagreeing_pairs": dict(pairs.most_common())}
    focus = (card.get("endpoint") or {}).get("focus_subtype")
    focus_txt = ""
    if focus in SUBTYPE_NAMES:
        fname = SUBTYPE_NAMES[focus]
        touch = [s for s in differ if str(cl.at[s, RNA]).strip() == focus or str(cl.at[s, NAT]).strip() == fname]
        numbers["disagreements_involving_focus_subtype"] = len(touch)
        numbers["focus_subtype"] = fname
        if touch:
            focus_txt = (f" {_plural(len(touch), 'of the disagreements involves', 'of the disagreements involve')} "
                         f"{fname}, the group this question studies, so say which column defines it.")
    pct, lim_pct = f"{share:.1%}", f"{limit:.0%}" if (limit * 100).is_integer() else f"{limit:.1%}"
    common = dict(id=name, pre_existing=True, fields=[f"{CL}:{RNA}", f"{CL}:{NAT}"], rows=differ, numbers=numbers,
                  source=TCGA_2012 + f" (the source of {NAT})",
                  rule=f"Warn if the share of tumors whose two subtype calls disagree, among tumors with both calls, is "
                       f"above {lim_pct} (limits.subtype_disagreement; {limit_from}). The RNA-seq codes are mapped "
                       "first: LumA to Luminal A, LumB to Luminal B, Basal to Basal-like, Her2 to HER2-enriched, "
                       "Normal to Normal-like.",
                  limitation=f"Only tumors with both calls can be compared ({len(compared)} of {len(group)} here). "
                             f"{cap(named(NAT))} covers only tumors in that study. Neither call is a ground truth, so "
                             "the tool can't say which one is right.")
    if share <= limit:
        return [Issue(title=f"The two subtype columns disagree for {len(differ)} of {len(compared)} tumors ({pct}), "
                            f"within the {lim_pct} limit",
                      status="pass", material=True, **common)]
    return [Issue(title=f"The two subtype columns disagree for {len(differ)} of {len(compared)} tumors ({pct}), "
                        f"above the {lim_pct} limit",
                  status="warn", material=True,
                  next_step=f"Name the subtype column used, and report the result under both {named(RNA)} and "
                            f"{named(NAT)}." + focus_txt,
                  evidence_needed="A documented reason to prefer one subtype column, or a result that holds under "
                                  "both.",
                  **common)]


def _her2_differences(cl, samples):
    both = [s for s in samples if not _blank(cl.at[s, IHC]) and not _blank(cl.at[s, FINAL])]
    differ = [s for s in both if str(cl.at[s, IHC]).strip() != str(cl.at[s, FINAL]).strip()]
    pos_neg = [s for s in differ if {str(cl.at[s, IHC]).strip(), str(cl.at[s, FINAL]).strip()}
               == {"Positive", "Negative"}]
    return both, differ, pos_neg


@register("her2_field_conflict")
def her2_field_conflict(release, card):
    name = "her2_field_conflict"
    cl, group, bad = _load(release, card, name, [IHC, FINAL])
    if bad:
        return [bad]
    both, differ, pos_neg = _her2_differences(cl, group)
    equivocal = [s for s in differ if str(cl.at[s, IHC]).strip() == "Equivocal"]
    pairs = Counter(f"IHC {cl.at[s, IHC]} vs final {cl.at[s, FINAL]}" for s in differ)
    a_both, a_differ, a_pos_neg = _her2_differences(cl, [s for s in cl.index if sample_type(s) == "01"])
    numbers = {"compared": len(both), "differ": len(differ), "group_samples": len(group),
               "ihc_equivocal_resolved": len(equivocal),
               "positive_vs_negative": len(pos_neg),
               "ihc_positive_final_negative": sum(str(cl.at[s, IHC]).strip() == "Positive" for s in pos_neg),
               "ihc_negative_final_positive": sum(str(cl.at[s, IHC]).strip() == "Negative" for s in pos_neg),
               "other_differences": len(differ) - len(equivocal) - len(pos_neg),
               "differing_pairs": dict(pairs.most_common()),
               "all_differing_samples": differ,
               "all_primary_tumors": {"compared": len(a_both), "differ": len(a_differ),
                                      "positive_vs_negative": len(a_pos_neg)}}
    common = dict(id=name, pre_existing=True, fields=[f"{CL}:{IHC}", f"{CL}:{FINAL}"], rows=pos_neg,
                  numbers=numbers,
                  source=TCGA_2012 + f" (the source of {FINAL}, which combines the protein stain with a FISH test)",
                  rule=f"Warn if any tumor is Positive in one HER2 field and Negative in the other, among tumors with "
                       "both fields filled. Differences where the protein stain was Equivocal are expected: the final "
                       "status settles those with a FISH test.",
                  limitation=f"The tool can't tell which of the two HER2 results is right for a given tumor. "
                             f"{cap(named(FINAL))}, exists only for tumors in that study. Tumors with only one of the "
                             "two results filled can't be checked.")
    if not pos_neg:
        return [Issue(title=f"No tumor is HER2-positive by one test and HER2-negative by the other ({len(differ)} of "
                            f"{len(both)} differ in other ways, such as an equivocal stain settled by FISH)",
                      status="pass", material=True, **common)]
    n = len(pos_neg)
    return [Issue(title=f"{_plural(n, 'tumor is', 'tumors are')} HER2-positive by one test and HER2-negative by the "
                        f"other ({len(differ)} of {len(both)} differ in total)",
                  status="warn", material=True,
                  next_step=f"Use {named(FINAL)}, to define HER2 status, and report the {n} conflicting "
                            f"{'tumor' if n == 1 else 'tumors'} (listed in the evidence).",
                  evidence_needed=f"A confirmed HER2 status (for example a FISH result) for the "
                                  f"{_plural(n, 'conflicting tumor', 'conflicting tumors')}.",
                  **common)]
