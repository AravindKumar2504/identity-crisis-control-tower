"""Error budget: how wrong can the data be before the research answer changes?

The tool already says whether a conclusion still holds. The error budget says how much damage it can take, counted in
the same kinds of error the release comparison detects, and how much of that budget a release used.

  A1 (ER-positive tumors carry more ER-alpha protein than ER-negative ones)
    swaps    profiles traded between an ER-positive and an ER-negative tumor, worst case first (the highest
             ER-positive value traded with the lowest ER-negative value)
    labels   wrong ER labels, worst case first (whichever single relabel hurts the answer most, at every step)
    copies   copied profiles, worst case first (the most damaging profile copied into the other group)
    Each count is how many such errors the answer survives before its 95% range touches zero.
  A2 (the most common subtype in the subtype mix)
    labels   tumors of the most common subtype relabelled as the runner-up, until it is no longer the most common

"Worst case" means an adversary chooses which samples to corrupt; real errors land at random and do less harm, so
the budget is a floor. The 95% range uses the normal approximation (difference minus 1.96 standard errors) so it can
be recomputed at every step; for the release itself the screen also shows the 1,000-resample range.
"""
from __future__ import annotations

import numpy as np

from .analyses import ER, PAM50

CAP = 2000
METHOD = ("Worst case: at every step the tool picks the error that hurts the answer most, so real, random errors would "
          "need many more. Counted until the 95% range of the ER-positive minus ER-negative difference touches zero "
          "(A1), or until the most common subtype loses its lead (A2).")


def _lower(p: np.ndarray, n: np.ndarray) -> float:
    d = p.mean() - n.mean()
    return float(d - 1.96 * np.sqrt(p.var(ddof=1) / len(p) + n.var(ddof=1) / len(n)))


def a1_swaps(pos, neg) -> int:
    p, n = np.sort(np.asarray(pos, float))[::-1], np.sort(np.asarray(neg, float))
    for k in range(min(len(p), len(n), CAP) + 1):
        pk, nk = np.concatenate([p[k:], n[:k]]), np.concatenate([n[k:], p[:k]])
        if _lower(pk, nk) <= 0:
            return k
    return min(len(p), len(n))


def a1_labels(pos, neg) -> int:
    p, n = list(np.sort(np.asarray(pos, float))[::-1]), list(np.sort(np.asarray(neg, float)))
    for k in range(CAP):
        if len(p) < 3 or len(n) < 3 or _lower(np.array(p), np.array(n)) <= 0:
            return k
        move_p = _lower(np.array(p[1:]), np.array(n + [p[0]]))         # highest ER+ value relabelled ER-
        move_n = _lower(np.array(p + [n[0]]), np.array(n[1:]))         # lowest ER- value relabelled ER+
        if move_p <= move_n:
            n.append(p.pop(0))
        else:
            p.append(n.pop(0))
        p.sort(reverse=True)
        n.sort()
    return CAP


def a1_copies(pos, neg) -> int:
    p, n = np.asarray(pos, float), np.asarray(neg, float)
    low, high = n.min(), p.max()
    for k in range(CAP):
        if _lower(p, n) <= 0:
            return k
        into_p = _lower(np.append(p, low), n)                          # the lowest ER- profile copied into ER+
        into_n = _lower(p, np.append(n, high))                         # the highest ER+ profile copied into ER-
        if into_p <= into_n:
            p = np.append(p, low)
        else:
            n = np.append(n, high)
    return CAP


def a2_lead(counts: dict) -> tuple[str, str, int]:
    top = sorted(counts.items(), key=lambda kv: -kv[1])
    if len(top) < 2:
        return (top[0][0] if top else ""), "", 0
    return top[0][0], top[1][0], (top[0][1] - top[1][1]) // 2 + 1


def _used(cmp, touching: list[dict], er_b: dict) -> dict:
    """How many errors of each budgeted kind this release made, among the question's samples."""
    used = {"swaps": 0, "labels": 0, "copies": 0, "subtype_labels": 0}
    for t in touching:
        ch = cmp.changes[int(t["finding"][1:]) - 1]
        if t["kind"] == "sample_swap":
            pairs = ch.detail.get("pairs") or []
            cross = {tuple(sorted(pq)) for pq in pairs if er_b.get(pq[0]) and er_b.get(pq[1]) and er_b[pq[0]] != er_b[pq[1]]}
            used["swaps"] += len(cross)
        elif t["kind"] == "duplicate":
            used["copies"] += len(t["samples"])
        elif t["kind"] == "label_conflict" and ch.detail.get("column") == ER:
            used["labels"] += len(t["samples"])
        elif t["kind"] == "label_conflict" and ch.detail.get("column") == PAM50:
            used["subtype_labels"] += len(t["samples"])
    return used


def budget(card: dict, frames_a1: dict | None, a2_counts: dict | None, cmp=None, touching=None, er_b=None) -> dict:
    """The error budget for a card that protects A1 or A2, and how much of it this release used."""
    analyses = card.get("analyses") or []
    used = _used(cmp, touching or [], er_b or {}) if cmp is not None else None
    items = []
    if "A1" in analyses and frames_a1 and len(frames_a1["pos"]) > 2 and len(frames_a1["neg"]) > 2:
        pos, neg = frames_a1["pos"], frames_a1["neg"]
        conclusion = "ER-positive primary tumors carry more ER-alpha protein than ER-negative ones"
        items = [{"error": "swaps between ER groups", "survives": a1_swaps(pos, neg),
                  "this_release": used["swaps"] if used else None},
                 {"error": "wrong ER labels", "survives": a1_labels(pos, neg),
                  "this_release": used["labels"] if used else None},
                 {"error": "copied profiles", "survives": a1_copies(pos, neg),
                  "this_release": used["copies"] if used else None}]
        analysis = "A1"
    elif "A2" in analyses and a2_counts:
        lead, runner, need = a2_lead(a2_counts)
        conclusion = f"{lead} is the most common subtype ({a2_counts.get(lead, 0)} tumors)"
        items = [{"error": f"{lead} tumors relabelled {runner}", "survives": need,
                  "this_release": used["subtype_labels"] if used else None}]
        analysis = "A2"
    else:
        return {}
    spent = [(it["this_release"] / it["survives"], it) for it in items if it["this_release"] and it["survives"]]
    if used is None:
        headline = "The answer survives " + ", ".join(f"{it['survives']} worst-case {it['error']}" for it in items) + "."
    elif not spent:
        headline = (f"This release used none of the error budget: the answer survives {items[0]['survives']} "
                    f"worst-case {items[0]['error']}.")
    else:
        share, it = max(spent, key=lambda x: x[0])
        pct = f"{100 * share:.0f}%" if share >= 0.01 else "under 1%"
        headline = (f"This release used {it['this_release']} of the {it['survives']} worst-case {it['error']} the answer "
                    f"can take ({pct}).")
    return {"analysis": analysis, "conclusion": conclusion, "items": items, "headline": headline, "method": METHOD}
