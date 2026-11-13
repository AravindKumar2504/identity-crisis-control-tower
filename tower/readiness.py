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

from .analyses import ANALYSES
from .cards import card_fields, card_group
from .checks import Issue, run_checks
from .diff import Comparison
from .release import ROW_FILES, Release

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
        samples = sorted(set(ch.samples) & group) if ch.samples else []
        if ch.samples and not samples:
            continue
        hits.append({"finding": f"F{i + 1}", "kind": ch.kind, "file": ch.file, "samples": samples or ch.samples,
                     "summary": ch.summary})
    return hits


def assess(card: dict, release: Release, cmp: Comparison | None = None, results: dict | None = None,
           allow_missing: bool = False) -> dict:
    issues = run_checks(release, card, allow_missing=allow_missing)
    material = [x for x in issues if x.material]
    touching = changes_touching(card, cmp) if cmp else []

    verdict, deciding = "Ready", []
    for status, label in ORDER:
        hits = [x for x in material if x.status == status]
        if hits or (status == "warn" and touching):
            verdict, deciding = label, hits
            break
    reasons = [f"{x.title}." for x in deciding]
    if verdict == "Conditional" and touching:
        reasons += [f"Release change {t['finding']} ({t['kind']}) touches {len(t['samples'])} sample(s) this "
                    f"question studies." for t in touching]
    pending = [x.id for x in issues if x.status == "unknown" and not x.material]
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
                  for x in deciding if x.next_step or x.evidence_needed]
    review_items = [x.id for x in material if x.status != "pass"] + [t["finding"] for t in touching]
    doc = {
        "card": {k: card.get(k) for k in ("id", "title", "intended_use", "group_studied", "outcome",
                                          "acceptable_limitations", "not_acceptable", "out_of_scope")},
        "release": {"name": release.name, "files": files},
        "compared_with": cmp.a.name if cmp else None,
        "group_size": len(card_group(release, card)),
        "verdict": verdict,
        "reasons": reasons,
        "summary": summary(verdict, reasons, next_steps),
        "issues": [x.to_dict() | {"rows": x.rows[:50], "row_count": len(x.rows)} for x in issues],
        "checked_not_material": [x.id for x in issues if not x.material],
        "release_changes": touching,
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


def summary(verdict: str, reasons: list[str], steps: list[dict]) -> str:
    """One plain-English paragraph a non-specialist can act on."""
    lead = {"Ready": "Ready: the data supports this question as stated.",
            "Conditional": "Conditional: usable only with the conditions below, after a person reviews them.",
            "Blocked": "Blocked: this data can't support this question as asked.",
            "Insufficient Evidence": "Insufficient Evidence: the tool can't tell from this release."}[verdict]
    why = " ".join(reasons[:2])
    nxt = f" Next step: {steps[0]['step']}" if steps and steps[0]["step"] else ""
    return f"{lead} {why}{nxt} A person must review the evidence before this data is used."


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
        lines += [f"- {t['finding']} ({t['kind']}, {t['file']}): {len(t['samples'])} sample(s): {t['summary']}"
                  for t in doc["release_changes"]]
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
