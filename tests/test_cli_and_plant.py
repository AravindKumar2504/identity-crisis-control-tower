"""Tests for the command line and Fool the Tower's file handling."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import synth  # noqa: E402
from synth import ER, P  # noqa: E402
from tower import plant  # noqa: E402
from tower.cli import main  # noqa: E402

CHALLENGE = REPO.parent / "oncosys-hackathon-challenge"
RAW = CHALLENGE / "data" / "tcga-brca" / "raw"


def run(argv: list[str]) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(argv)
    return out.getvalue()


class CommandLine(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        fr = synth.frames()
        self.a = synth.write(self.tmp / "release-A", fr)
        pos, neg = synth.a1_samples(fr)
        changed = synth.copy(fr)
        changed[P] = changed[P].rename(columns={pos[0]: neg[0], neg[0]: pos[0]})[list(fr[P].columns)]
        self.b = synth.write(self.tmp / "release-B", changed)
        self.swapped = {pos[0], neg[0]}
        self.challenge = self.tmp / "challenge"
        (self.challenge / "envelopes").mkdir(parents=True)
        (self.challenge / "envelopes" / "unseal.py").write_text("", encoding="utf-8")

    def test_compare(self):
        out = self.tmp / "out" / "findings.json"
        text = run(["compare", str(self.a), str(self.b), "--out", str(out)])
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["verdict"], "Conditional")
        self.assertEqual({e["id"] for e in doc["findings"][0]["evidence"] if e["kind"] == "sample"}, self.swapped)
        self.assertIn("F1 sample_swap", text)
        report = (out.parent / "report.md").read_text(encoding="utf-8")
        self.assertIn("F1", report)

    def test_compare_one_analysis(self):
        out = self.tmp / "out" / "findings.json"
        run(["compare", str(self.a), str(self.b), "--out", str(out), "--analyses", "A2"])
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(([a["id"] for a in doc["analyses"]], doc["verdict"]), (["A2"], "Ready"))

    def test_check_with_and_without_a_comparison(self):
        out = self.tmp / "readiness"
        run(["check", "--card", "er-alpha-by-er", "--release", str(self.b), "--against", str(self.a),
             "--challenge", str(self.challenge), "--out-dir", str(out)])
        doc = json.loads((out / "er-alpha-by-er.json").read_text(encoding="utf-8"))
        self.assertEqual((doc["verdict"], doc["compared_with"]), ("Conditional", "release-A"))
        self.assertTrue((out / "er-alpha-by-er.md").exists())

    def test_cards(self):
        self.assertEqual(len(run(["cards"]).strip().splitlines()), 8)

    def test_wrong_input_is_a_message_not_a_traceback(self):
        for argv, expect in (
                (["compare", str(self.a), str(self.tmp / "nowhere")], "release folder not found"),
                (["check", "--card", "no-such-card", "--release", str(self.b), "--challenge", str(self.challenge)],
                 "no card 'no-such-card'")):
            with self.subTest(argv=argv[0]):
                with self.assertRaises(SystemExit) as stop:
                    run(argv)
                self.assertIn(expect, str(stop.exception.code))
        (self.tmp / "empty").mkdir()
        with self.assertRaises(SystemExit) as stop:
            run(["compare", str(self.a), str(self.tmp / "empty")])
        self.assertIn("no TCGA-BRCA files found", str(stop.exception.code))


class Links(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.src = self.tmp / "src.txt"
        self.src.write_text("data", encoding="utf-8")

    def test_copies_where_links_are_refused(self):
        with mock.patch.object(plant.os, "symlink", side_effect=OSError("a required privilege is not held")):
            plant._link(self.src, self.tmp / "dst.txt")
        dst = self.tmp / "dst.txt"
        self.assertFalse(dst.is_symlink())
        self.assertEqual(dst.read_text(encoding="utf-8"), "data")

    def test_links_where_it_can(self):
        try:
            plant._link(self.src, self.tmp / "dst.txt")
        except OSError:
            self.skipTest("this system can't link or copy here")
        self.assertEqual((self.tmp / "dst.txt").read_text(encoding="utf-8"), "data")


@unittest.skipUnless(RAW.is_dir() and (CHALLENGE / "data" / "tcga-brca" / "make_release.py").exists(),
                     "needs the challenge repo and release A next to this repo")
class FoolTheTower(unittest.TestCase):
    def test_planted_errors_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            changes = [{"type": "swap_samples", "file": P, "count": 1, "opposite_er": True},
                       {"type": "relabel_clinical", "file": "clinical.tsv", "column": ER, "new_value": "Negative",
                        "count": 3}]
            rel, key = plant.plant(CHALLENGE, changes, seed=4242, out_dir=pathlib.Path(tmp))
            self.assertFalse((rel / "CHANGES.json").exists())
            res = plant.score(CHALLENGE, rel, key)
            self.assertEqual((res["found"], res["missed"], res["false_alarms"]), (res["planted_samples"], [], []))


if __name__ == "__main__":
    unittest.main()
