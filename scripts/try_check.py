"""Try one check: run it for every card that lists it, on release A and on the practice envelope, and print its Issues.

It also flags contract problems (docs/CONTRACTS.md section 2) so they are caught before a pull request.

Usage (from this repo, with the challenge repo next to it):
  python scripts/try_check.py survival_redacted
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from tower.cards import list_cards  # noqa: E402
from tower.checks import CHECKS, LOAD_ERRORS, load_all  # noqa: E402
from tower.release import load_release  # noqa: E402

CH = REPO.parent / "oncosys-hackathon-challenge"
STATUSES = {"pass", "warn", "block", "unknown"}


def problems(x, name: str) -> list[str]:
    out = []
    if not str(x.id).startswith(name):
        out.append(f"id '{x.id}' should be '{name}' or start with '{name}_'")
    if x.status not in STATUSES:
        out.append(f"status '{x.status}' must be one of {sorted(STATUSES)}")
    if not isinstance(x.material, bool):
        out.append("material must be True or False")
    if x.status in ("warn", "block"):
        for f in ("rule", "source", "next_step", "evidence_needed"):
            if not getattr(x, f):
                out.append(f"a {x.status} needs '{f}'")
        if not x.numbers:
            out.append("put the counts behind the result in 'numbers'")
    if any(":" not in f for f in x.fields):
        out.append("each field should read 'file:column', for example 'clinical.tsv:PAM50Call_RNAseq'")
    return out


def main(name: str) -> None:
    load_all()
    for mod, err in LOAD_ERRORS.items():
        print(f"A check file failed to load: tower/checks/{mod}.py: {err}")
    fn = CHECKS.get(name)
    if fn is None:
        sys.exit(f"No check named '{name}' is registered. Put @register(\"{name}\") above your function in a file in "
                 "tower/checks/, with exactly the name the cards use.")
    cards = [c for c in list_cards() if name in (c.get("checks") or [])]
    print(f"{name}: listed on {', '.join(c['id'] for c in cards) or 'no card'}")
    releases = [("release A", load_release(CH / "data" / "tcga-brca" / "raw", "release-A"))]
    practice = CH / "envelopes" / "opened" / "practice" / "release"
    if practice.exists():
        releases.append(("practice envelope", load_release(practice)))
    bad = 0
    for label, rel in releases:
        print(f"\n== {label}")
        for c in cards:
            try:
                issues = fn(rel, c)
            except Exception as e:
                bad += 1
                print(f"  {c['id']}: CRASHED: {type(e).__name__}: {e}")
                continue
            for x in issues:
                print(f"  {c['id']}: {x.status}{' (material)' if x.material else ''} | {x.id} | {x.title}")
                print(f"      numbers: {json.dumps(x.numbers, default=str)[:300]}")
                print(f"      rows: {len(x.rows)} sample ids | fields: {', '.join(x.fields)}")
                if x.status != "pass":
                    print(f"      next step: {x.next_step}")
                for p in problems(x, name):
                    bad += 1
                    print(f"      CONTRACT PROBLEM: {p}")
    print("\nNo contract problems." if not bad else f"\n{bad} problem(s) to fix before your pull request.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "endpoint_suitability")
