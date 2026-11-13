"""Release A coverage checks: how much of the question's group has no value in a field the question needs.

  subtype_missing  share of the card's base group with no PAM50 subtype call (PAM50Call_RNAseq)
  missing_values   for each clinical field the card reads, share of the card's base group with no value
                   (one Issue per field, id missing_values_<column>)

Both count over card_base_group: the card's own group already drops the blanks, so blanks counted inside it are zero.
Every count is computed from the release passed in, so the same checks work on sealed envelopes.
Each returns Issues in the shared contract (tower/checks/__init__.py).
"""
from __future__ import annotations

from collections import Counter

from ..cards import BLANKS, card_base_group
from . import Issue, register

CL = "clinical.tsv"
SUBTYPE = "PAM50Call_RNAseq"
DEFAULT_MISSING_LIMIT = 0.10


def _blank(v) -> bool:
    return str(v).strip() in BLANKS


def _pct(x: float) -> str:
    return f"{x:.0%}" if round(x * 100, 6).is_integer() else f"{x:.1%}"


def _limit(card) -> tuple[float, str]:
    limits = card.get("limits") or {}
    if "missing_fraction" in limits:
        return float(limits["missing_fraction"]), "card"
    return DEFAULT_MISSING_LIMIT, "default"


def _source(card) -> str:
    accept = str(card.get("acceptable_limitations") or "").strip()
    return ("The card's limits.missing_fraction" + (f" and its acceptable limitations: \"{accept}\"" if accept else ""))


def _unknown(issue_id, title, fields, card, numbers=None, next_step="", evidence=""):
    return Issue(id=issue_id, title=title, status="unknown", material=True, pre_existing=False, fields=fields,
                 numbers=numbers or {}, rule="Missing values can only be counted from a readable field.",
                 source=_source(card),
                 limitation="Without the field the tool can't tell how many tumors lack a value.",
                 next_step=next_step, evidence_needed=evidence)


def _base(release, card, issue_id, fields):
    """The clinical table and the card's base group, or an 'unknown' Issue explaining why it can't be judged."""
    if not release.has(CL):
        state = "unreadable" if CL in release.unreadable else "missing"
        return None, None, _unknown(issue_id, f"The clinical file is {state}, so missing values can't be counted",
                                    fields, card, next_step="Get a release with a readable clinical.tsv.",
                                    evidence="A release containing clinical.tsv, matching its published fingerprint.")
    cl = release.table(CL).frame
    base = sorted(card_base_group(release, card))
    if not base:
        need = [f for f in ((card.get("group") or {}).get("in_files") or []) if not release.has(f)]
        if need:
            what = ", ".join(need)
            return None, None, _unknown(issue_id, f"This question's group needs {what}, which this release doesn't "
                                        "include, so missing values can't be counted", fields, card,
                                        numbers={"base_group_samples": 0, "missing_files": need},
                                        next_step=f"Get a release that includes {what}.",
                                        evidence=f"A release containing {what}.")
        return None, None, _unknown(issue_id, "This question's group has no samples in this release, so missing "
                                    "values can't be counted", fields, card, numbers={"base_group_samples": 0},
                                    next_step="Check that every file in the card's group exists and is readable.",
                                    evidence="A release where the question's group has samples.")
    return cl, base, None


def _count(cl, base, col):
    blank = [s for s in base if _blank(cl.at[s, col])]
    blank_set = set(blank)
    filled = Counter(str(cl.at[s, col]).strip() for s in base if s not in blank_set)
    kinds = Counter(str(cl.at[s, col]).strip() for s in blank)
    return blank, filled, kinds


@register("subtype_missing")
def subtype_missing(release, card):
    name = "subtype_missing"
    fields = [f"{CL}:{SUBTYPE}"]
    cl, base, bad = _base(release, card, name, fields)
    if bad:
        return [bad]
    if SUBTYPE not in cl.columns:
        return [_unknown(name, f"The clinical file has no {SUBTYPE} column, so missing subtype calls can't be counted",
                         fields, card, numbers={"missing_fields": [SUBTYPE]},
                         next_step=f"Get a release whose clinical.tsv includes {SUBTYPE}.",
                         evidence=f"A release with {CL}:{SUBTYPE}.")]
    limit, limit_from = _limit(card)
    blank, filled, kinds = _count(cl, base, SUBTYPE)
    share = len(blank) / len(base)
    numbers = {"blank": len(blank), "base_group_samples": len(base), "share": round(share, 4), "limit": limit,
               "limit_from": limit_from, "blank_values_seen": dict(kinds), "filled_subtypes": dict(filled.most_common())}
    head = f"{len(blank)} of {len(base)} primary tumors ({_pct(share)}) have no PAM50 subtype call"
    common = dict(id=name, pre_existing=True, fields=fields, rows=blank, numbers=numbers, source=_source(card),
                  rule=f"Warn if the share of the question's base group (before the not-blank filter) with a blank "
                       f"{SUBTYPE} is above {_pct(limit)} (limits.missing_fraction; {limit_from}).",
                  limitation="The data doesn't say why a subtype call is missing (for example no RNA sample, or one "
                             "that failed quality control), so the tool can't tell whether the missing tumors differ "
                             "from the rest.")
    if share <= limit:
        return [Issue(title=f"{head}, within the {_pct(limit)} limit", status="pass", material=False, **common)]
    return [Issue(title=f"{head}, above the {_pct(limit)} limit", status="warn", material=True,
                  next_step=f"Report the subtype mix together with the {_pct(share)} of tumors that have no subtype "
                            "call, and don't treat the missing tumors as missing at random.",
                  evidence_needed="Subtype calls for the missing tumors, or a documented reason they are missing that "
                                  "shows it is unrelated to subtype.",
                  **common)]


@register("missing_values")
def missing_values(release, card):
    name = "missing_values"
    cols = list((card.get("uses") or {}).get(CL) or [])
    if not cols:
        return [Issue(id=name, title="The question reads no clinical fields, so this check doesn't apply",
                      status="pass", material=False, pre_existing=False)]
    cl, base, bad = _base(release, card, name, [f"{CL}:{c}" for c in cols])
    if bad:
        return [bad]
    limit, limit_from = _limit(card)
    allowed_by_card = (card.get("group") or {}).get("values") or {}
    out = []
    for col in cols:
        iid, fields = f"{name}_{col}", [f"{CL}:{col}"]
        if col not in cl.columns:
            out.append(_unknown(iid, f"The clinical file has no {col} column, so its missing values can't be counted",
                                fields, card, numbers={"missing_fields": [col]},
                                next_step=f"Get a release whose clinical.tsv includes {col}.",
                                evidence=f"A release with {CL}:{col}."))
            continue
        blank, filled, kinds = _count(cl, base, col)
        share = len(blank) / len(base)
        numbers = {"field": col, "blank": len(blank), "base_group_samples": len(base), "share": round(share, 4),
                   "limit": limit, "limit_from": limit_from, "blank_values_seen": dict(kinds),
                   "filled_values": dict(filled.most_common())}
        if col in allowed_by_card:
            allowed = {str(v) for v in allowed_by_card[col]}
            unused = {v: n for v, n in filled.items() if v not in allowed}
            numbers["values_the_card_uses"] = sorted(allowed)
            numbers["filled_but_not_a_value_the_card_uses"] = sum(unused.values())
            numbers["filled_but_not_used_values"] = unused
        head = f"{col} is blank for {len(blank)} of {len(base)} tumors ({_pct(share)})"
        common = dict(id=iid, pre_existing=True, fields=fields, rows=blank, numbers=numbers, source=_source(card),
                      rule=f"Warn if the share of the question's base group (before its value filters) with a blank "
                           f"{col} is above {_pct(limit)} (limits.missing_fraction; {limit_from}).",
                      limitation="The data doesn't say why a value is missing, so the tool can't tell whether the "
                                 "tumors without one differ from the rest. Values that are filled but unusable (for "
                                 "example Indeterminate) are counted in the numbers, not as blank.")
        if share <= limit:
            out.append(Issue(title=f"{head}, within the {_pct(limit)} limit", status="pass", material=False, **common))
            continue
        out.append(Issue(title=f"{head}, above the {_pct(limit)} limit", status="warn", material=True,
                         next_step=f"Report that {len(blank)} tumors ({_pct(share)}) have no {col}, and don't assume "
                                   "they resemble the tumors that have one.",
                         evidence_needed=f"Values of {col} for the blank tumors, or a documented reason for the gaps "
                                         "that shows they are unrelated to the outcome.",
                         **common))
    return out
