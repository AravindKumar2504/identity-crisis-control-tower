"""Fool the Tower: plant your own errors with the organizers' generator, then see whether the tool finds them.

A judge picks a few errors (swaps, copies, changed clinical labels). The organizers' own data/tcga-brca/make_release.py
builds a release with exactly those changes and writes its answer key. The answer key is moved out of the release
folder, the tool compares the release with release A without it, and the result is scored against the key.
Everything is written under out/fool/ (git ignores out/); the challenge repo is only read.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import random
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
FIVE = ["clinical.tsv", "survival.tsv", "mutation_gene_level.tsv.gz", "copy_number_gistic.tsv.gz", "protein_rppa.tsv.gz"]


class _Links:
    """Stands in for shutil inside the generator: unchanged files are linked, not copied (fast, envelope-style)."""
    rmtree = staticmethod(shutil.rmtree)

    @staticmethod
    def copy(src, dst):
        os.symlink(os.path.realpath(src), dst)


def _generator(challenge: pathlib.Path):
    path = challenge / "data" / "tcga-brca" / "make_release.py"
    spec = importlib.util.spec_from_file_location("toa_make_release", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plant(challenge: pathlib.Path, changes: list[dict], seed: int | None = None,
          out_dir: pathlib.Path | None = None) -> tuple[pathlib.Path, dict]:
    """Build a release with these changes (the generator's own config format). Returns (release folder, answer key)."""
    out_dir = pathlib.Path(out_dir or REPO / "out" / "fool")
    five = out_dir / "_release_a"                       # release A's five envelope files, no RNA, linked
    five.mkdir(parents=True, exist_ok=True)
    for f in FIVE:
        if not (five / f).exists():
            os.symlink((challenge / "data" / "tcga-brca" / "raw" / f).resolve(), five / f)
    mr = _generator(challenge)
    mr.RAW, mr.OUT, mr.shutil = five, out_dir, _Links
    tries = 5 if seed is None else 1                    # a random seed can be redrawn; a given one is kept
    seed = random.randrange(10**6) if seed is None else int(seed)
    for attempt in range(tries):
        name = f"planted-{seed}"
        cfg_path = out_dir / f"{name}.config.json"
        cfg_path.write_text(json.dumps({"name": name, "seed": seed, "changes": changes}, indent=1))
        argv = sys.argv
        try:
            sys.argv = ["make_release.py", "--config", str(cfg_path)]
            with contextlib.redirect_stdout(io.StringIO()):
                mr.main()
            break
        except (Exception, SystemExit) as e:
            # The generator makes the release folder before it applies the changes, so a combination it refuses
            # would leave an empty release behind, and the screen would offer it. Remove what it left.
            shutil.rmtree(out_dir / name, ignore_errors=True)
            cfg_path.unlink(missing_ok=True)
            if isinstance(e, KeyError) and attempt < tries - 1:
                seed = random.randrange(10**6)      # Luminal A copies over Luminal A tumors drew the same sample twice
                continue
            if isinstance(e, SystemExit):
                raise RuntimeError(f"the generator stopped: {e}") from None
            raise
        finally:
            sys.argv = argv
    rel = out_dir / name
    key_path = out_dir / f"{name}.answer.json"
    (rel / "CHANGES.json").replace(key_path)            # keep the answer key out of the release the tool reads
    return rel, json.loads(key_path.read_text())


def expected(key: dict) -> set[tuple[str, str, str]]:
    """(kind, file, sample) triples a correct tool must cite: the same rule as scripts/scorecard.py."""
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


def score(challenge: pathlib.Path, rel: pathlib.Path, key: dict) -> dict:
    """Run the tool on the planted release (without the key) and score it against the key."""
    from .analyses import rerun
    from .diff import compare
    from .findings import build
    from .release import load_release
    a = load_release(challenge / "data" / "tcga-brca" / "raw", "release-A")
    b = load_release(rel)
    cmp = compare(a, b)
    results, impact = rerun(a, b, cmp.changes)
    doc = build(cmp, results, impact)
    got = {(f["kind"], e.get("file", ""), e["id"]) for f in doc["findings"] for e in f["evidence"] if e["kind"] == "sample"}
    exp = expected(key)
    rows = []
    for ch in key["changes"]:
        one = expected({"changes": [ch]})
        what = {"swap_samples": f"swap of {' and '.join(ch.get('samples', []))}",
                "replace_with_duplicates": f"{len(ch.get('duplicates', []))} copies replacing {len(ch.get('removed', []))} samples",
                "relabel_clinical": f"{len(ch.get('before', {}))} '{ch.get('column')}' labels set to '{ch.get('new_value')}'"}
        rows.append({"Planted": what.get(ch["type"], ch["type"]), "File": ch["file"],
                     "Samples to find": len(one), "Found": len(one & got)})
    return {"planted_samples": len(exp), "found": len(exp & got), "missed": sorted(exp - got),
            "false_alarms": sorted(got - exp), "verdict": doc["verdict"], "verdict_reason": doc["verdict_reason"],
            "rows": rows, "n_findings": len(doc["findings"])}
