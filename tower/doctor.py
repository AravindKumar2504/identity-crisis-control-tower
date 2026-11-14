"""python -m tower doctor: is this machine ready for the sealed envelope?

Checks Python and the packages, finds the challenge repo, verifies release A against its published checksums and
counts the sealed envelopes. Then it opens the public practice envelope and checks the tool's findings.json end to
end: the organizers' validator, the same samples and kinds as their reference output, the same A1 result, and the
time taken. --full also runs the scorecard on the test releases. Exit code 0 means ready, 1 means something to fix.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
PRACTICE_CODE = ["orange", "meadow", "pilot", "lantern"]      # the public practice code (envelopes/README.md)
PACKAGES = [("pandas", "pandas"), ("numpy", "numpy"), ("jsonschema", "jsonschema"), ("yaml", "pyyaml"),
            ("cryptography", "cryptography"), ("streamlit", "streamlit"), ("altair", "altair")]
INSTALL = "pip install -r requirements.txt"


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def line(self, ok: bool, text: str, fix: str = "") -> bool:
        print(f"  {'✓' if ok else '✗'} {text}")
        if not ok:
            self.problems.append(text)
            if fix:
                print(f"      fix: {fix}")
        return ok

    def end(self) -> int:
        if self.problems:
            n = len(self.problems)
            print(f"\nNot ready: fix the {n} {'item' if n == 1 else 'items'} marked ✗ before the demo.")
            return 1
        print("\nReady for the sealed envelope.")
        return 0


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_challenge(given: str | None) -> pathlib.Path | None:
    for c in [given, os.environ.get("ONCOSYS_CHALLENGE"), REPO.parent / "oncosys-hackathon-challenge"]:
        if c and (pathlib.Path(c) / "envelopes" / "unseal.py").exists():
            return pathlib.Path(c).resolve()
    return None


def _cited(doc: dict) -> set[tuple[str, str]]:
    return {(f["kind"], e["id"]) for f in doc["findings"] for e in f["evidence"] if e["kind"] == "sample"}


def _a1(doc: dict):
    a1 = next((a for a in doc["analyses"] if a["id"] == "A1"), {})
    return a1.get("status"), (a1.get("after") or {}).get("difference")


def run(challenge_arg: str | None = None, full: bool = False) -> int:
    r = Report()
    print("Is this machine ready for the sealed envelope?\n\nSoftware")
    v = sys.version_info
    r.line(v >= (3, 11), f"Python {v.major}.{v.minor}.{v.micro}", "Install Python 3.11 or newer.")
    for mod, name in PACKAGES:
        try:
            m = importlib.import_module(mod)
            r.line(True, f"{name} {getattr(m, '__version__', '')}".strip())
        except Exception:
            r.line(False, f"{name} is not installed", INSTALL)

    print("\nThe challenge repo and release A")
    ch = _find_challenge(challenge_arg)
    if not r.line(ch is not None, f"challenge repo at {ch}" if ch else "the challenge repo wasn't found",
                  "Clone https://github.com/disleveK/oncosys-hackathon-challenge next to this repo, "
                  "or pass --challenge <folder>."):
        return r.end()
    for rel in ("envelopes/unseal.py", "format/validate.py", "data/tcga-brca/reference_analyses.py"):
        r.line((ch / rel).exists(), f"{rel} is there", "Run git pull in the challenge repo.")
    raw, sources = ch / "data" / "tcga-brca" / "raw", ch / "data" / "tcga-brca" / "sources.csv"
    expected = ({row["file"]: row["sha256"] for row in csv.DictReader(open(sources, encoding="utf-8"))}
                if sources.exists() else {})
    if not r.line(bool(expected), "sources.csv lists release A's published checksums", "Run git pull in the challenge repo."):
        return r.end()
    for f, h in expected.items():
        ok = (raw / f).exists() and _sha256(raw / f) == h
        r.line(ok, f"release A {f} matches its published checksum" if ok
               else f"release A {f} is missing or doesn't match its published checksum",
               "From the challenge repo, run: python data/tcga-brca/fetch.py")
    sealed = list((ch / "envelopes" / "sealed").glob("*.sealed"))
    r.line(bool(sealed), f"{len(sealed)} sealed envelopes on disk (git pull the challenge repo on Saturday morning anyway)",
           "Run git pull in the challenge repo.")

    print("\nThe practice envelope, end to end")
    t0 = time.time()
    u = subprocess.run([sys.executable, "envelopes/unseal.py", "practice", *PRACTICE_CODE], cwd=ch,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})   # unseal.py prints a check mark; Windows pipes use cp1252
    if not r.line(u.returncode == 0, "the practice envelope opens", (u.stderr or u.stdout).strip()[-300:]):
        return r.end()
    from .cli import run_compare
    out = REPO / "out" / "doctor" / "practice" / "findings.json"
    doc = run_compare(raw, ch / "envelopes" / "opened" / "practice" / "release", out, name_a="release-A",
                      name_b="practice", quiet=True)
    secs = time.time() - t0
    val = subprocess.run([sys.executable, str(ch / "format" / "validate.py"), str(out)], capture_output=True, text=True)
    r.line(val.returncode == 0, "findings.json passes the organizers' validator", (val.stdout or val.stderr).strip()[-300:])
    ref_path = ch / "format" / "examples" / "control-tower-practice-B.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        mine, theirs = _cited(doc), _cited(ref)
        r.line(mine == theirs, f"cites the same {len(theirs)} samples, under the same kinds, as the organizers' reference"
               if mine == theirs else f"cites different samples from the organizers' reference: missing "
               f"{sorted(theirs - mine)[:3]}, extra {sorted(mine - theirs)[:3]}")
        r.line(_a1(doc) == _a1(ref), f"A1 matches the reference: {_a1(doc)[0]}, difference {_a1(doc)[1]}"
               if _a1(doc) == _a1(ref) else f"A1 differs from the reference: ours {_a1(doc)}, theirs {_a1(ref)}")
    r.line(secs < 60, f"unseal to findings.json in {secs:.1f} s (the organizers ask for under a minute)")

    if full:
        print("\nScorecard (test releases)")
        rel = ch / "data" / "tcga-brca" / "releases"
        if r.line(rel.exists() and any(rel.iterdir()), "the test releases are built", "See the README: Reproduce the scorecard."):
            s = subprocess.run([sys.executable, str(REPO / "scripts" / "scorecard.py"), str(rel)],
                               capture_output=True, text=True)
            last = [x for x in s.stdout.splitlines() if "releases pass" in x]
            r.line("ALL PASS" in s.stdout, last[0] if last else "the scorecard didn't finish", (s.stderr or "")[-300:])
    return r.end()
