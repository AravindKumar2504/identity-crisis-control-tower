"""Turn a comparison into findings.json (shared format v0.2), the file the organizers' checker reads.

It holds only what changed between the two releases: one finding per change, every affected sample cited as
evidence, never an unchanged sample. Problems that were already in release A belong in the readiness report.
Severity follows the organizers' rule: how much the change could alter the research answer, with the reason.
"""
from __future__ import annotations

from .analyses import ANALYSES
from .diff import Comparison

LIMITS = {
    "sample_swap": "Fingerprints prove the profiles moved between ids; they cannot say which release labels them "
                   "correctly. A person should confirm against the source before trusting either.",
    "duplicate": "Identical profiles under two ids are almost never real biology; the tool cannot tell which id the "
                 "measurements truly belong to.",
    "membership_change": "The tool sees that samples are missing or new, not why; a removal can be a legitimate "
                         "redaction.",
    "label_conflict": "A changed value can be a legitimate correction; the tool cannot see the pathology report "
                      "behind it.",
    "missing_data": "The tool sees values become empty, not why they were withdrawn.",
    "other": "The tool could not classify this change, so it reports it without guessing its cause.",
}


def headline_shift(aid: str, res: dict) -> float:
    """How far the headline number moved: A1 relative change in the difference, A2 largest subtype shift (pp)."""
    b, a = res.get("before"), res.get("after")
    if not b or not a:
        return 0.0
    if aid == "A1":
        return abs(a["difference"] - b["difference"]) / max(abs(b["difference"]), 1e-9) * 100
    if aid == "A2":
        keys = set(b["percent"]) | set(a["percent"])
        return max(abs(a["percent"].get(k, 0) - b["percent"].get(k, 0)) for k in keys)
    return 0.0


def _er(rel, ids):
    if not rel.has("clinical.tsv"):
        return {}
    cl = rel.table("clinical.tsv").frame
    col = "breast_carcinoma_estrogen_receptor_status"
    return {s: (cl.at[s, col] if s in cl.index and col in cl.columns else "") for s in ids}


def severity(ch, affected: list[str], results: dict, a) -> tuple[str, str]:
    if not affected:
        where = f"the '{ch.detail['column']}' column" if ch.detail.get("column") else ch.file
        return "low", f"No protected analysis reads {where}, so this cannot move A1 or A2; it is still wrong data."
    if ch.detail.get("file_missing") or any(results.get(x, {}).get("blocked") for x in affected):
        return "high", f"{', '.join(affected)} cannot be checked against this release."
    moved = {x: headline_shift(x, results.get(x, {})) for x in affected}
    big = [x for x, v in moved.items() if (x == "A1" and v >= 0.5) or (x == "A2" and v >= 0.5)]
    if ch.kind == "sample_swap":
        ers = _er(a, ch.samples)
        groups = {v for v in ers.values() if v}
        if len(groups) > 1:
            return "high", ("The swapped samples sit in different ER groups (" + ", ".join(f"{s} {ers[s]}" for s in ch.samples)
                            + "), so A1 now compares the wrong protein values in each group.")
        return "medium", ("The swapped samples are in the same ER group, so A1's group means hold, but every "
                          "per-sample result for these samples is wrong.")
    if ch.kind == "duplicate":
        return "high", (f"Copied profiles are counted twice in {', '.join(affected)}, which inflates a group "
                        "with measurements that belong to other samples.")
    if big:
        return "high", f"The headline result of {', '.join(big)} moves by half a percent or more."
    return "medium", f"It changes which samples {', '.join(affected)} uses, but the headline result moves by less than half a percent."


def repairs_for(fid: str, ch) -> list[dict]:
    t = ch.samples
    if ch.kind == "sample_swap":
        return [{"action": "restore_from_previous_release", "targets": t,
                 "justification": "Each sample's release-A profile is known exactly from its fingerprint; restoring "
                                  "puts every profile back under its own id. Evidence to reconsider: the data "
                                  "provider confirms the new labels are correct."}]
    if ch.kind == "duplicate":
        return [{"action": "exclude", "targets": t,
                 "justification": "These ids carry copies of other samples' measurements; excluding them removes the "
                                  "double counting. Evidence to reconsider: the provider shows the ids are distinct "
                                  "specimens with their own measurements."}]
    if ch.kind == "membership_change" and ch.detail.get("direction") == "lost":
        return [{"action": "flag_for_review", "targets": t,
                 "justification": "Ask the provider why these samples were removed; a redaction is legitimate, a "
                                  "processing loss is not."},
                {"action": "restore_from_previous_release", "targets": t,
                 "justification": "Until the removal is explained, analyses can keep the release-A measurements so the "
                                  "affected group does not shrink silently."}]
    if ch.kind == "label_conflict":
        return [{"action": "flag_for_review", "targets": t,
                 "justification": f"Confirm the new '{ch.detail.get('column')}' values against the source record; "
                                  "if they are not documented corrections, keep the release-A values."}]
    if ch.kind == "missing_data":
        return [{"action": "restore_from_previous_release", "targets": t or [ch.file],
                 "justification": "The values existed in release A; restore them until the provider explains the "
                                  "withdrawal."}]
    return [{"action": "flag_for_review", "targets": t or [ch.file],
             "justification": "The change could not be classified, so a person must look at the before and after "
                              "values."}]


def build(cmp: Comparison, results: dict, impact: dict, team: str = "Identity_Crisis",
          question: str | None = None, selected: list[str] | None = None) -> dict:
    a, b = cmp.a, cmp.b
    names = {"A": a.name, "B": b.name}
    ids = [x.id for x in ANALYSES if not selected or x.id in selected]
    question = question or (f"Did release {b.name} change anything that affects analyses "
                            + " and ".join(f"{x.id} ({x.title})" for x in ANALYSES if x.id in ids) + "?")
    findings, repairs = [], []
    for i, ch in enumerate(cmp.changes):
        fid = f"F{i + 1}"
        affected = [x for x in ids if impact.get(i, {}).get(x, (False, ""))[0]]
        not_aff = [x for x in ids if x not in affected]
        sev, why = severity(ch, affected, results, a)
        ev = [{"kind": "sample", "id": s, "release": names.get(ch.evidence_release.get(s, "B"), b.name),
               "file": ch.file, "note": ch.notes.get(s, "")} for s in ch.samples]
        if "A1" in affected and ch.file == "protein_rppa.tsv.gz":
            ev.append({"kind": "protein", "id": "ERALPHA", "release": b.name, "file": ch.file,
                       "note": "the protein row A1 reads"})
        if not ev:
            ev.append({"kind": "file", "id": ch.file, "release": b.name if b.has(ch.file) else a.name,
                       "note": "file-level change"})
        reasons = "; ".join(f"{x}: {impact[i][x][1]}" for x in ids if x in impact.get(i, {}))
        findings.append({"id": fid, "kind": ch.kind, "summary": f"{ch.summary} Why it matters: {why}",
                         "severity": sev, "confidence": ch.confidence, "evidence": ev,
                         "affects_analyses": affected, "not_affected_analyses": not_aff,
                         "limitation": LIMITS.get(ch.kind, LIMITS["other"]), "needs_human_review": True,
                         "impact_reasons": reasons, "detail": _jsonable(ch.detail)})
        for r in repairs_for(fid, ch):
            targets = [{"kind": "sample", "id": t, "release": names.get(ch.evidence_release.get(t, "B"), b.name),
                        "file": ch.file} if t in ch.samples else {"kind": "file", "id": t}
                       for t in r["targets"]]
            repairs.append({"id": f"R{len(repairs) + 1}", **r, "targets": targets, "addresses": [fid]})

    analyses = []
    for x in ids:
        r = results.get(x)
        if not r:
            continue
        item = {"id": x, "status": r["status"], "before": r["before"] or {}, "title": r["title"], "reason": r["reason"]}
        if r.get("after") is not None:
            item["after"] = r["after"]
        if r.get("entered") or r.get("left"):
            item["samples_entered"], item["samples_left"] = r.get("entered", []), r.get("left", [])
        analyses.append(item)

    verdict, verdict_reason = decide(cmp, results, findings, ids)
    return {
        "format_version": "0.2",
        "producer": {"team": team, "product": "Cohort Control Tower", "track": "cohort-firewall"},
        "data": {"dataset": "TCGA-BRCA (UCSC Xena hub, event frozen release)",
                 "releases": [{"name": a.name, "files": [{"file": f, "sha256": a.file_sha256[f], "hash_of": "file"}
                                                         for f in a.files]},
                              {"name": b.name, "files": [{"file": f, "sha256": b.content_sha256[f], "hash_of": "content"}
                                                         for f in b.files]}]},
        "question": question,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "notes": cmp.notes,
        "findings": findings,
        "analyses": analyses,
        "repairs": repairs,
    }


def decide(cmp, results, findings, ids) -> tuple[str, str]:
    needed = {f for an in ANALYSES if an.id in ids for f in an.reads}
    missing = sorted(f for f in needed if not cmp.b.has(f))
    if missing:
        return "Insufficient Evidence", f"Release {cmp.b.name} has no {', '.join(missing)}, which the question needs."
    blocked = [x for x in ids if results.get(x, {}).get("blocked")]
    if blocked:
        return "Blocked", f"{', '.join(blocked)} cannot be rerun on release {cmp.b.name}."
    touched = [f for f in findings if f["affects_analyses"]]
    if touched:
        moved = [x for x in ids if results.get(x, {}).get("status") == "changed"]
        return "Conditional", (f"{len(touched)} finding(s) touch what the question reads"
                               + (f"; {', '.join(moved)} changed when rerun" if moved else "; reruns show no change")
                               + ". A person must review the findings before this release is used.")
    if findings:
        return "Ready", (f"{len(findings)} change(s) found, but none touches what the question reads; they are "
                         "listed at low severity.")
    return "Ready", "Nothing that the question reads changed between the releases."


def _jsonable(d):
    if isinstance(d, dict):
        return {str(k): _jsonable(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_jsonable(v) for v in d]
    if isinstance(d, (str, int, float, bool)) or d is None:
        return d
    return str(d)
