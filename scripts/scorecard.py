"""Score the tool against releases whose answer keys were written before the tool ran.

Each test release is a folder made by the organizers' make_release.py, holding a CHANGES.json answer key.
For every planted change the scorecard checks that the tool cites exactly the planted samples, in the right
file, under the right kind of finding, and nothing that was not planted.

Usage (from this repo, with the challenge repo next to it):
  python scripts/scorecard.py <folder with test release folders> [...more folders]
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tower.analyses import rerun  # noqa: E402
from tower.diff import compare  # noqa: E402
from tower.findings import build  # noqa: E402
from tower.release import load_release  # noqa: E402

RAW = pathlib.Path(__file__).resolve().parent.parent.parent / "oncosys-hackathon-challenge" / "data" / "tcga-brca" / "raw"


def expected(key: dict) -> set[tuple[str, str, str]]:
    """(kind, file, sample) triples a correct tool must cite."""
    out = set()
    for ch in key["changes"]:
        f = ch["file"]
        if ch["type"] == "swap_samples":
            out |= {("sample_swap", f, s) for s in ch["samples"]}
        elif ch["type"] == "replace_with_duplicates":
            out |= {("duplicate", f, d["new_id"]) for d in ch["duplicates"]}
            out |= {("membership_change", f, s) for s in ch["removed"]}
        elif ch["type"] == "relabel_clinical":
            out |= {("label_conflict", f, s) for s in ch["before"]}
    return out


def cited(doc: dict) -> set[tuple[str, str, str]]:
    return {(f["kind"], e.get("file", ""), e["id"]) for f in doc["findings"] for e in f["evidence"] if e["kind"] == "sample"}


def main(folders: list[str]) -> None:
    a = load_release(RAW, "release-A")
    rows, total_ok = [], True
    for folder in folders:
        for rel_dir in sorted(p for p in pathlib.Path(folder).iterdir() if (p / "CHANGES.json").exists()):
            key = json.loads((rel_dir / "CHANGES.json").read_text())
            t0 = time.time()
            b = load_release(rel_dir)
            cmp = compare(a, b)
            results, impact = rerun(a, b, cmp.changes)
            doc = build(cmp, results, impact)
            secs = time.time() - t0
            exp, got = expected(key), cited(doc)
            missed, extra = exp - got, got - exp
            ok = not missed and not extra
            total_ok &= ok
            rows.append((rel_dir.name, len(key["changes"]), len(exp), len(exp & got), len(missed), len(extra),
                         doc["verdict"], ", ".join(f"{x['id']} {x['status']}" for x in doc["analyses"]), f"{secs:.1f}s",
                         "PASS" if ok else "FAIL"))
            if not ok:
                print(f"{rel_dir.name}: missed {sorted(missed)[:6]} extra {sorted(extra)[:6]}")
    print(f"{'release':<14} {'changes':>7} {'expected':>8} {'found':>5} {'missed':>6} {'extra':>5}  verdict / analyses / time")
    for r in rows:
        print(f"{r[0]:<14} {r[1]:>7} {r[2]:>8} {r[3]:>5} {r[4]:>6} {r[5]:>5}  {r[6]} | {r[7]} | {r[8]}  {r[9]}")
    print("ALL PASS" if total_ok else "SOME FAILED")


if __name__ == "__main__":
    main(sys.argv[1:])
