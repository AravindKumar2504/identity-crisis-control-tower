"""Command line: compare two releases, or open a sealed envelope and compare its release with release A.

  python -m tower compare <release A folder> <release B folder> [--out findings.json]
  python -m tower envelope <number> <four words> [--challenge <challenge repo folder>]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

from .analyses import rerun
from .diff import compare
from .findings import build
from .release import load_release

REPO = pathlib.Path(__file__).resolve().parent.parent


def find_challenge(given: str | None) -> pathlib.Path:
    for c in [given, os.environ.get("ONCOSYS_CHALLENGE"), REPO.parent / "oncosys-hackathon-challenge"]:
        if c and (pathlib.Path(c) / "envelopes" / "unseal.py").exists():
            return pathlib.Path(c).resolve()
    sys.exit("Can't find the challenge repo. Clone https://github.com/disleveK/oncosys-hackathon-challenge next to "
             "this repo, or pass --challenge <folder>.")


def run_compare(dir_a, dir_b, out: pathlib.Path, analyses=None, name_a=None, name_b=None,
                challenge: pathlib.Path | None = None, quiet=False) -> dict:
    t0 = time.time()
    a = load_release(dir_a, name_a)
    b = load_release(dir_b, name_b)
    cmp = compare(a, b)
    results, impact = rerun(a, b, cmp.changes, analyses)
    doc = build(cmp, results, impact, selected=analyses)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))
    (out.parent / "report.md").write_text(plain_report(doc))
    elapsed = time.time() - t0
    if not quiet:
        print_summary(doc, out, elapsed)
    if challenge:
        validate(out, challenge)
    return doc


def validate(path: pathlib.Path, challenge: pathlib.Path) -> bool:
    v = challenge / "format" / "validate.py"
    if not v.exists():
        return False
    r = subprocess.run([sys.executable, str(v), str(path)], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip())
    return r.returncode == 0


def print_summary(doc: dict, out: pathlib.Path, elapsed: float) -> None:
    print(f"\nVerdict: {doc['verdict']}. {doc['verdict_reason']}")
    for f in doc["findings"]:
        n = sum(1 for e in f["evidence"] if e["kind"] == "sample")
        aff = ", ".join(f["affects_analyses"]) or "none"
        print(f"  {f['id']} {f['kind']:<17} {f['severity']:<6} {n:>3} sample(s)  affects: {aff}")
    for a in doc["analyses"]:
        b, af = a.get("before") or {}, a.get("after") or {}
        if a["id"] == "A1" and af:
            print(f"  {a['id']} {a['status']}: difference {b.get('difference')} -> {af.get('difference')}, "
                  f"n {b.get('n_samples')} -> {af.get('n_samples')}")
        elif a["id"] == "A2" and af:
            print(f"  {a['id']} {a['status']}: n {b.get('n_samples')} -> {af.get('n_samples')}")
        else:
            print(f"  {a['id']} {a['status']}: {a.get('reason', '')}")
    for n in doc.get("notes", []):
        print(f"  note: {n}")
    print(f"Wrote {out} and {out.parent / 'report.md'} in {elapsed:.1f} s")


def plain_report(doc: dict) -> str:
    lines = [f"# Release check: {doc['data']['releases'][1]['name']} against {doc['data']['releases'][0]['name']}", "",
             f"**Question:** {doc['question']}", "", f"**Verdict: {doc['verdict']}.** {doc['verdict_reason']}", "",
             "Research use only. This report makes no clinical claim. A person must review every finding.", "",
             "## What changed", ""]
    if not doc["findings"]:
        lines.append("Nothing changed in the files the tool compared.")
    for f in doc["findings"]:
        lines += [f"### {f['id']} · {f['kind']} · severity {f['severity']} · confidence {f['confidence']}", "",
                  f["summary"], "", f"Affects: {', '.join(f['affects_analyses']) or 'no protected analysis'}. "
                  f"{f.get('impact_reasons', '')}", "", f"Limitation: {f['limitation']}", "", "Evidence:"]
        lines += [f"- {e['kind']} `{e['id']}` ({e.get('file', '')}, release {e.get('release', '')}): {e.get('note', '')}"
                  for e in f["evidence"]]
        lines.append("")
    lines += ["## Analyses", ""]
    for a in doc["analyses"]:
        lines += [f"- **{a['id']}** ({a['title']}): {a['status']}. {a.get('reason', '')}",
                  f"  - before: `{json.dumps(a.get('before'))}`"]
        if a.get("after") is not None:
            lines.append(f"  - after: `{json.dumps(a.get('after'))}`")
    lines += ["", "## Proposed fixes (each needs a person's approval)", ""]
    lines += [f"- {r['id']} {r['action']} for {', '.join(r['addresses'])}: {r['justification']}" for r in doc["repairs"]]
    if doc.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {n}" for n in doc["notes"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tower", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare", help="compare two release folders")
    c.add_argument("release_a"), c.add_argument("release_b")
    c.add_argument("--out", default="out/findings.json")
    c.add_argument("--analyses", help="comma-separated, e.g. A1 or A1,A2 (default: all)")
    c.add_argument("--challenge", help="challenge repo folder, to run the organizers' validator")
    e = sub.add_parser("envelope", help="open a sealed envelope and check its release against release A")
    e.add_argument("number"), e.add_argument("words", nargs="+")
    e.add_argument("--challenge"), e.add_argument("--out-dir", default="out")
    e.add_argument("--analyses")
    args = p.parse_args(argv)
    sel = args.analyses.split(",") if getattr(args, "analyses", None) else None

    if args.cmd == "compare":
        ch = find_challenge(args.challenge) if args.challenge else None
        run_compare(args.release_a, args.release_b, pathlib.Path(args.out), sel, challenge=ch)
        return

    challenge = find_challenge(args.challenge)
    t0 = time.time()
    r = subprocess.run([sys.executable, "envelopes/unseal.py", args.number, *args.words], cwd=challenge)
    if r.returncode != 0:
        sys.exit("Unsealing failed (see the message above). Check the envelope number and the four words.")
    name = "practice" if args.number.lower() == "practice" else f"E{int(args.number.upper().lstrip('E')):02d}"
    release_b = challenge / "envelopes" / "opened" / name / "release"
    print(f"Unsealed in {time.time() - t0:.1f} s; comparing envelope {name}'s release with release A")
    run_compare(challenge / "data" / "tcga-brca" / "raw", release_b,
                pathlib.Path(args.out_dir) / name / "findings.json", sel, name_a="release-A", name_b=name,
                challenge=challenge)
    print(f"Total time from unseal to findings: {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
