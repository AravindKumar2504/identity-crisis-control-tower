"""A person's review: decisions on each proposed fix and each problem, then a sign-off for the release.

Decisions go into findings.json in the shared format (`decisions`, each pointing at a repair), so a Repair Review
Desk or any other tool can read them. The original findings and analyses are never changed. The sign-off records
who approved what, when, and the fingerprints of the exact files they reviewed.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPAIR_CHOICES = ["approve", "reject", "request_more_evidence"]
ISSUE_CHOICES = ["agree", "disagree", "need more evidence"]
SIGNOFF_CHOICES = ["Approve use as stated", "Approve with the conditions listed", "Do not use", "Request more evidence"]


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def missing_decisions(findings_doc: dict | None, readiness_doc: dict, repair_dec: dict, issue_dec: dict) -> list[str]:
    """Everything a person still has to decide before the release can be signed off."""
    need = []
    if findings_doc:
        need += [r["id"] for r in findings_doc.get("repairs", []) if r["id"] not in repair_dec]
    need += [i for i in readiness_doc["review"]["required"] if not i.startswith("F") and i not in issue_dec]
    return need


def with_decisions(findings_doc: dict, repair_dec: dict, reviewer: str, role: str) -> dict:
    """A copy of findings.json with a `decisions` entry for every decided repair (shared format v0.2)."""
    doc = copy.deepcopy(findings_doc)
    doc["decisions"] = [{"repair_id": rid, "decision": d["decision"], "reason": d["reason"] or "(no reason given)",
                         "reviewer_role": role, "reviewer": reviewer, "decided_at": d["time"],
                         "original_preserved": True}
                        for rid, d in repair_dec.items()]
    return doc


def signed(readiness_doc: dict, findings_doc: dict | None, repair_dec: dict, issue_dec: dict,
           reviewer: str, role: str, decision: str, note: str) -> dict:
    """A copy of readiness.json with every review decision and the sign-off, fingerprinted."""
    doc = copy.deepcopy(readiness_doc)
    doc["review"]["items"] = (
        [{"id": rid, "type": "repair", **d, "reviewer": reviewer, "role": role} for rid, d in repair_dec.items()]
        + [{"id": iid, "type": "issue", **d, "reviewer": reviewer, "role": role} for iid, d in issue_dec.items()])
    inputs = {"release": doc["release"], "findings": _digest(findings_doc), "readiness": _digest(readiness_doc)}
    doc["review"]["signed_off"] = {"by": reviewer, "role": role, "decision": decision, "note": note, "at": now(),
                                   "verdict_at_sign_off": doc["verdict"], "inputs": inputs}
    return doc


def _digest(d: dict | None) -> str | None:
    if d is None:
        return None
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


def record_markdown(readiness_doc: dict, findings_doc: dict | None) -> str:
    """A human-readable record of the review, for the README, the demo or an email."""
    r, so = readiness_doc["review"], readiness_doc["review"]["signed_off"] or {}
    c = readiness_doc["card"]
    lines = [f"# Review record: {c['title']}", "",
             f"- Release: {readiness_doc['release']['name']}" + (f" (compared with {readiness_doc['compared_with']})"
                                                                  if readiness_doc.get("compared_with") else ""),
             f"- Tool verdict: **{readiness_doc['verdict']}**",
             f"- Signed off by: {so.get('by', '(not signed)')}, {so.get('role', '')}, at {so.get('at', '')}",
             f"- Reviewer's decision: **{so.get('decision', '(none)')}**" + (f". Note: {so['note']}" if so.get("note") else ""),
             "", "## Decisions", "", "| Item | Type | Decision | Reason |", "|---|---|---|---|"]
    for it in r["items"]:
        lines.append(f"| {it['id']} | {it['type']} | {it['decision']} | {it.get('reason', '')} |")
    lines += ["", "## Fingerprints of what was reviewed", ""]
    for f, h in (readiness_doc["release"].get("files") or {}).items():
        lines.append(f"- {f}: `{h}`")
    if so.get("inputs"):
        lines.append(f"- findings.json digest: `{so['inputs'].get('findings')}`")
        lines.append(f"- readiness.json digest: `{so['inputs'].get('readiness')}`")
    lines += ["", readiness_doc["disclaimer"]]
    return "\n".join(lines) + "\n"


class NotSaved(Exception):
    """The validator rejected the review; nothing was written."""


def write_atomic(path: pathlib.Path, text: str) -> None:
    """Write to a temporary file, then move it into place."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def validate(doc: dict, validator: pathlib.Path) -> tuple[bool | None, str]:
    """Run the organizers' validator: (True, ""), (False, its message), or (None, why) if it isn't there."""
    if not validator.exists():
        return None, "the organizers' validator wasn't found"
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "findings.reviewed.json"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        r = subprocess.run([sys.executable, str(validator), str(path)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        said = (r.stdout or r.stderr or "").replace(str(path), "findings.reviewed.json").strip()
    if r.returncode == 0:
        return True, ""
    return False, said or f"it stopped with exit code {r.returncode}"


def save(out_dir: pathlib.Path, signed_doc: dict, reviewed: dict | None, findings_doc: dict | None,
         validator: pathlib.Path) -> str:
    """Validate the reviewed findings, then write the review files. Raises NotSaved if rejected."""
    check = ""
    if reviewed is not None:
        ok, said = validate(reviewed, validator)
        if ok is False:
            raise NotSaved(f"the organizers' validator rejected findings.reviewed.json: {said}")
        check = ("Organizers' validator on findings.reviewed.json: valid" if ok
                 else f"findings.reviewed.json was not checked: {said}")
    record = record_markdown(signed_doc, findings_doc)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(out_dir / "readiness.signed.json", json.dumps(signed_doc, indent=2, default=str))
    write_atomic(out_dir / "review_record.md", record)
    if reviewed is not None:
        write_atomic(out_dir / "findings.reviewed.json", json.dumps(reviewed, indent=2))
    return check
