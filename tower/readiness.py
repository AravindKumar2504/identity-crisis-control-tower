"""Is this release fit for the research question on a card? The verdict, its reasons, and the evidence trail.

Verdict rule over the material issues for the card (docs/CONTRACTS.md, section 3), in this order:
  any `block`                                   -> Blocked (the data can't support this use, whatever else is true)
  any `unknown`                                 -> Insufficient Evidence (the tool can't tell)
  any `warn`, or a release change touching it   -> Conditional (usable with stated conditions, after review)
  otherwise                                     -> Ready
Every verdict lists the issues and release changes that decided it, and the evidence trail behind each one:
the fields read, every sample involved, and the fingerprints of the files they came from.
"""
from __future__ import annotations

import datetime as _dt

from .analyses import ANALYSES, ER, PAM50, _clinical, _protein
from .budget import budget as error_budget
from .cards import card_fields, card_group
from .checks import Issue, run_checks
from .diff import Comparison
from .release import ROW_FILES, Release
from .robustness import a1_frames, conclusion

# What a release change can't tell anyone, by kind (the same limitations findings.json carries).
CHANGE_LIMITS = {
    "sample_swap": "Which release labels the swapped samples correctly: fingerprints prove the data moved, not where it belongs.",
    "duplicate": "Which id the copied measurements truly belong to.",
    "membership_change": "Why samples were removed or added: a redaction or withdrawn consent is legitimate, a processing loss is not.",
    "label_conflict": "Whether a changed value is a documented correction: the tool can't see the pathology or lab report behind it.",
    "missing_data": "Why values became empty or a file is missing.",
    "join_inflation": "Which of the rows that share a sample id is the real one.",
    "other": "What caused a change the tool couldn't classify.",
}
GENERAL_LIMIT = ("Anything outside the files and fields this question reads, or whether a value matches the original "
                 "pathology or lab report.")

ORDER = [("block", "Blocked"), ("unknown", "Insufficient Evidence"), ("warn", "Conditional")]


def changes_touching(card: dict, cmp: Comparison) -> list[dict]:
    """Release changes that touch what the card reads, among the samples it studies (in either release)."""
    uses = card.get("uses") or {}
    group = card_group(cmp.a, card) | card_group(cmp.b, card)
    hits = []
    for i, ch in enumerate(cmp.changes):
        if ch.file not in uses:
            continue
        col = ch.detail.get("column")
        if ch.file in ROW_FILES and col is not None and col not in uses[ch.file]:
            continue
        structural = []
        if not ch.samples and not ch.detail.get("file_missing"):
            # Rows or columns were added or removed: that matters only if the card reads one of them.
            moved = [*ch.detail.get("rows_removed", []), *ch.detail.get("rows_added", []),
                     *ch.detail.get("columns_removed", []), *ch.detail.get("columns_added", [])]
            structural = [x for x in moved if x in set(uses[ch.file] or [])]
            if not structural:
                continue
        samples = sorted(set(ch.samples) & group) if ch.samples else []
        if ch.samples and not samples:
            continue
        hits.append({"finding": f"F{i + 1}", "kind": ch.kind, "file": ch.file, "samples": samples,
                     "summary": ch.summary, "column": col, "direction": ch.detail.get("direction"),
                     "structural": structural, "file_missing": bool(ch.detail.get("file_missing"))})
    return hits


def _touch_reason(t: dict) -> str:
    if t.get("file_missing"):
        return f"Release change {t['finding']} ({t['kind']}): {t['file']}, which this question reads, is missing or unreadable."
    if t.get("structural"):
        return (f"Release change {t['finding']} ({t['kind']}) adds or removes {', '.join(t['structural'])} in "
                f"{t['file']}, which this question reads.")
    k = len(t["samples"])
    return f"Release change {t['finding']} ({t['kind']}) touches {k} sample{'' if k == 1 else 's'} this question studies."


# What a person should do about each kind of release change that touches the question, and what would settle it.
_STEPS = {
    "sample_swap": ("restore the release-A profiles of the {n} swapped sample{s}, or have the data provider confirm "
                    "which id each profile belongs to", "The provider confirms the new labels are correct."),
    "duplicate": ("exclude the {n} copied profile{s} from this analysis",
                  "The provider shows the ids are distinct specimens with their own measurements."),
    "lost": ("ask the data provider why {n} sample{s} {were} removed before using the smaller group (a redaction is "
             "legitimate, a processing loss is not)", "The provider's reason for each removal."),
    "gained": ("check where the {n} new sample{s} came from before including them", "Source records for the new samples."),
    "label_conflict": ("confirm the {n} changed '{col}' value{s} against the source records, and keep the release-A "
                       "values until they are explained", "A documented correction for each changed value."),
    "join_inflation": ("keep one row per sample id for the {n} id{s} on more than one row (ask the data provider "
                       "which row is right) before joining files", "One row per sample id, confirmed by the data provider."),
    "missing_data": ("get the missing values back from the data provider",
                     "A release where the values are present, matching its published fingerprint."),
    "other": ("look at the before and after values and decide whether to use them", "An explanation from the data provider."),
}


def _touch_step(t: dict) -> dict:
    key = t.get("direction") if t["kind"] == "membership_change" and t.get("direction") in ("lost", "gained") else t["kind"]
    text, need = _STEPS.get(key, _STEPS["other"])
    if t.get("structural"):
        text, need = (f"find out why {', '.join(t['structural'])} changed in {t['file']} before using this release",
                      "An explanation from the data provider.")
    k = len(t["samples"])
    text = text.format(n=k, col=t.get("column") or "", s="" if k == 1 else "s", were="was" if k == 1 else "were")
    return {"for": t["finding"], "step": f"{t['finding']}: {text[0].upper()}{text[1:]}.", "evidence_needed": need}


def assess(card: dict, release: Release, cmp: Comparison | None = None, results: dict | None = None,
           allow_missing: bool = False) -> dict:
    issues = run_checks(release, card, allow_missing=allow_missing)
    touching = changes_touching(card, cmp) if cmp else []
    robust = {}
    if "A1" in (card.get("analyses") or []):
        try:
            robust = conclusion(cmp if cmp else release, sorted({s for t in touching for s in t["samples"]}))
        except Exception:  # the robustness readout must never break the verdict
            robust = {}
        if robust:
            issues.append(_conclusion_issue(robust, bool(cmp)))
    material = [x for x in issues if x.material]
    eb = {}
    if set(card.get("analyses") or []) & {"A1", "A2"} and release.has("clinical.tsv"):
        try:                                     # the error budget is context; it must never break the verdict
            clin = _clinical(release)
            f1 = (a1_frames(clin, _protein(release)) if "A1" in card["analyses"] and release.has("protein_rppa.tsv.gz")
                  else None)
            c2 = (clin[clin.sampleID.str[13:15] == "01"].dropna(subset=[PAM50])[PAM50].value_counts().to_dict()
                  if "A2" in card["analyses"] else None)
            eb = error_budget(card, f1, c2, cmp, touching, clin.set_index("sampleID")[ER].to_dict() if cmp else {})
        except Exception:
            eb = {}

    verdict, deciding = "Ready", []
    for status, label in ORDER:
        hits = [x for x in material if x.status == status]
        if hits or (status == "warn" and touching):
            verdict, deciding = label, hits
            break
    reasons = [f"{x.title}." for x in deciding]
    if verdict == "Conditional" and touching:
        reasons += [_touch_reason(t) for t in touching]
    pending = [x.id for x in issues if (x.numbers or {}).get("pending") and not x.material]
    if verdict == "Ready":
        checked = [x.id for x in issues if x.status == "pass"]
        reasons = [f"Nothing material found in the checks that ran ({', '.join(checked) or 'none'})."
                   + (" No release change touches what this question reads." if cmp else "")]
    if pending:
        reasons.append(f"Not built yet, so not counted: {', '.join(pending)}.")

    files = {f: release.content_sha256.get(f) for f in (card.get("uses") or {}) if release.has(f)}
    lineage = [{"conclusion": x.title, "issue": x.id, "status": x.status, "rule": x.rule, "source": x.source,
                "fields": x.fields, "rows": x.rows, "row_count": len(x.rows), "numbers": x.numbers,
                "files": {f.split(':')[0]: files.get(f.split(':')[0]) for f in x.fields if f.split(':')[0] in files}}
               for x in issues if x.material]
    lineage += [{"conclusion": t["summary"], "finding": t["finding"], "status": "warn", "rule":
                 "A release change that touches what the question reads needs a person's review before use.",
                 "source": "findings.json (release comparison)", "fields": [f"{t['file']}:*"], "rows": t["samples"],
                 "row_count": len(t["samples"]), "files": {t["file"]: files.get(t["file"])}} for t in touching]

    analyses = {}
    for an in ANALYSES:
        if an.id in (card.get("analyses") or []):
            if results and an.id in results:
                r = results[an.id]
                analyses[an.id] = {"status": r["status"], "before": r["before"], "after": r.get("after"),
                                   "reason": r["reason"]}
            else:
                try:
                    out = an.run(release)
                    analyses[an.id] = {"status": "run", "result": {k: v for k, v in out.items() if k != "sample_ids"}}
                except Exception as e:
                    analyses[an.id] = {"status": "not_run", "reason": str(e)}

    next_steps = [{"for": x.id, "step": x.next_step, "evidence_needed": x.evidence_needed}
                  for x in deciding if x.next_step]
    if not next_steps:                        # no check named an action: say what evidence would settle it
        next_steps = [{"for": x.id, "step": "Get " + x.evidence_needed[:1].lower() + x.evidence_needed[1:],
                       "evidence_needed": x.evidence_needed} for x in deciding if x.evidence_needed]
    if verdict == "Conditional":
        next_steps += [_touch_step(t) for t in touching]
    review_items = list(dict.fromkeys([x.id for x in material if x.status != "pass"] + [t["finding"] for t in touching]))
    # What this result can't tell the user, shown under the verdict: the limits of the checks and changes behind it.
    limits = [x.limitation for x in deciding if x.limitation] + [CHANGE_LIMITS.get(t["kind"], CHANGE_LIMITS["other"])
                                                                 for t in touching]
    if robust:
        limits.append("Whether a systematic error such as a mislabelled ER test changed the result: the 95% range "
                      "covers sampling variation only.")
    limits = limits or [x.limitation for x in issues if x.material and x.limitation]
    cannot_tell = list(dict.fromkeys(limits + [GENERAL_LIMIT]))[:3]
    group_ids = sorted(card_group(release, card))
    doc = {
        "card": {k: card.get(k) for k in ("id", "title", "intended_use", "group_studied", "outcome",
                                          "acceptable_limitations", "not_acceptable", "out_of_scope")},
        "release": {"name": release.name, "files": files},
        "compared_with": cmp.a.name if cmp else None,
        "group_size": len(group_ids),
        "group_samples": group_ids,
        "cannot_tell": cannot_tell,
        "verdict": verdict,
        "reasons": reasons,
        "summary": summary(verdict, reasons, next_steps, pending),
        "issues": [x.to_dict() | {"rows": x.rows[:50], "row_count": len(x.rows)} for x in issues],
        "checked_not_material": [x.id for x in issues if not x.material and not (x.numbers or {}).get("pending")],
        "pending_checks": pending,
        "release_changes": touching,
        "robustness": robust,
        "error_budget": eb,
        "analyses": analyses,
        "next_steps": next_steps,
        "review": {"required": review_items, "items": [], "signed_off": None},
        "lineage": lineage,
        "fields_read": card_fields(card),
        "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": "Research use only. No diagnosis, treatment advice, risk score or clinical claim. "
                      "A person must review the evidence before this data is used.",
    }
    return doc


def _conclusion_issue(r: dict, compared: bool) -> Issue:
    lo, hi = r["range_95"]
    if r["status"] == "reversed":
        status, title = "block", (f"The conclusion reverses: the ER+ minus ER- difference was {r['release_a_difference']} "
                                  f"in release A and is {r['difference']} now")
    elif r["status"] == "fragile":
        status, title = "warn", (f"The conclusion is fragile: the 95% range of the ER+ minus ER- difference "
                                 f"({lo} to {hi}) includes zero")
    else:
        status = "pass"
        title = f"The conclusion holds: ER+ minus ER- difference {r['difference']} (95% range {lo} to {hi})"
        if compared:
            title += (f"; release A {r['release_a_difference']}; without the {r['flagged_samples']} flagged samples "
                      f"{r['difference_without_flagged']}")
    return Issue(id="conclusion_holds", title=title, status=status, material=True, pre_existing=False,
                 fields=["clinical.tsv:breast_carcinoma_estrogen_receptor_status", "protein_rppa.tsv.gz:ERALPHA"],
                 rows=[], numbers=r,
                 rule="Holds if the ER+ minus ER- difference is positive and its 95% range (1,000 resamples of the "
                      "samples) stays above zero; fragile if the range includes zero; reverses if its sign flips "
                      "between releases.",
                 source="Resampling of this release's samples; A1 computed as in the organizers' reference_analyses.py",
                 limitation="The range covers sampling variation only; it can't see systematic errors such as a "
                            "mislabelled ER test.",
                 next_step="" if status == "pass" else "Don't report this comparison from this release until the "
                                                       "flagged samples are resolved.",
                 evidence_needed="" if status == "pass" else "The flagged samples confirmed or restored, and the "
                                                             "comparison rerun.")


def summary(verdict: str, reasons: list[str], steps: list[dict], pending: list[str] | None = None) -> str:
    """One plain-English paragraph a non-specialist can act on. Checks that aren't built yet are named, never hidden."""
    lead = {"Ready": "Ready: the data supports this question as stated.",
            "Conditional": "Conditional: usable only with the conditions below, after a person reviews them.",
            "Blocked": "Blocked: this data can't support this question as asked.",
            "Insufficient Evidence": "Insufficient Evidence: the tool can't tell from this release."}[verdict]
    if verdict == "Ready" and pending:
        lead = "Ready on the checks that ran, but not fully checked yet."
    shown = [r for r in reasons if not r.startswith("Not built yet")]
    why = " ".join(shown[:3]) + (f" ({len(shown) - 3} more below.)" if len(shown) > 3 else "")
    pend = f" Not checked yet: {', '.join(pending)}." if pending else ""
    nxt = f" Next step: {steps[0]['step']}" if steps and steps[0]["step"] else ""
    return f"{lead} {why}{pend}{nxt} A person must review the evidence before this data is used."


def markdown(doc: dict) -> str:
    c = doc["card"]
    lines = [f"# {c['title']}", "", f"**Verdict: {doc['verdict']}**", "", doc["summary"], "",
             f"- Intended use: {c['intended_use']}", f"- Group studied: {c['group_studied']} "
             f"({doc['group_size']} samples in release {doc['release']['name']})", f"- Outcome: {c['outcome']}",
             f"- Acceptable limitations: {c['acceptable_limitations']}", "", "## Why", ""]
    lines += [f"- {r}" for r in doc["reasons"]]
    lines += ["", "## Every check", "", "| Check | Status | Matters here | Already in release A | What it found |",
              "|---|---|---|---|---|"]
    for x in doc["issues"]:
        lines.append(f"| {x['id']} | {x['status']} | {'yes' if x['material'] else 'no'} | "
                     f"{'yes' if x['pre_existing'] else 'no'} | {x['title']} |")
    if doc["release_changes"]:
        lines += ["", "## Release changes that touch this question", ""]
        lines += [f"- {t['finding']} ({t['kind']}, {t['file']}): {len(t['samples'])} sample{'' if len(t['samples']) == 1 else 's'}: {t['summary']}"
                  for t in doc["release_changes"]]
    if doc.get("error_budget"):
        eb = doc["error_budget"]
        lines += ["", "## Error budget: how wrong can the data be before the answer changes?", "",
                  f"Conclusion: {eb['conclusion']}. {eb['headline']}", ""]
        lines += [f"- Worst-case {it['error']}: survives {it['survives']}"
                  + (f"; this release made {it['this_release']}" if it["this_release"] is not None else "")
                  for it in eb["items"]]
        lines += ["", eb["method"]]
    if doc.get("cannot_tell"):
        lines += ["", "## What this can't tell you", ""] + [f"- {x}" for x in doc["cannot_tell"]]
    if doc["next_steps"]:
        lines += ["", "## Next steps", ""]
        lines += [f"- {s['step']} Evidence that would change the verdict: {s['evidence_needed']}" for s in doc["next_steps"]]
    lines += ["", "## Evidence trail", ""]
    for e in doc["lineage"]:
        lines.append(f"- **{e['conclusion']}** rule: {e['rule']} Source: {e['source']}. Fields: "
                     f"{', '.join(e['fields'])}. Samples: {e['row_count']}.")
    lines += ["", f"Review required for: {', '.join(doc['review']['required']) or 'nothing'}. Signed off: no.", "",
              doc["disclaimer"]]
    return "\n".join(lines) + "\n"
