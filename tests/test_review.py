"""Tests for saving a sign-off (tower/review.py)."""
from __future__ import annotations

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
from synth import P  # noqa: E402
from tower import review  # noqa: E402
from tower.analyses import rerun  # noqa: E402
from tower.cards import load_card  # noqa: E402
from tower.diff import compare  # noqa: E402
from tower.findings import build  # noqa: E402
from tower.readiness import assess  # noqa: E402
from tower.release import load_release  # noqa: E402

REAL_VALIDATOR = REPO.parent / "oncosys-hackathon-challenge" / "format" / "validate.py"
# stand-ins for the organizers' validator
PASSES = "import sys\nprint('valid  ', sys.argv[1])\n"
REJECTS = "import sys\nprint('INVALID', sys.argv[1])\nprint('   - decisions: unknown repair')\nsys.exit(1)\n"
SAYS_VALID_BUT_FAILS = "import sys\nprint('valid  ', sys.argv[1])\nsys.exit(1)\n"
NAME = "Zo\u00eb \u0141ukasz \u674e \U0001F44D"


class SignOff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(cls._tmp.name)
        fr = synth.frames()
        a = load_release(synth.write(tmp / "release-A", fr))
        pos, neg = synth.a1_samples(fr)
        changed = synth.copy(fr)
        changed[P] = changed[P].rename(columns={pos[0]: neg[0], neg[0]: pos[0]})[list(fr[P].columns)]
        b = load_release(synth.write(tmp / "release-B", changed))
        cmp = compare(a, b)
        results, impact = rerun(a, b, cmp.changes)
        cls.findings = build(cmp, results, impact)
        cls.ready = assess(load_card("er-alpha-by-er"), b, cmp, results)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.dir = pathlib.Path(self._dir.name)
        decisions = {r["id"]: {"decision": "approve", "reason": f"checked by {NAME}", "time": review.now()}
                     for r in self.findings["repairs"]}
        self.reviewed = review.with_decisions(self.findings, decisions, NAME, "research data engineer")
        self.signed = review.signed(self.ready, self.findings, decisions, {}, NAME, "research data engineer",
                                    "Approve with the conditions listed", f"note from {NAME}")

    def validator(self, body: str) -> pathlib.Path:
        path = self.dir / "validate.py"
        path.write_text(body, encoding="utf-8")
        return path

    def save(self, validator: pathlib.Path) -> str:
        return review.save(self.dir / "out", self.signed, self.reviewed, self.reviewed, validator)

    def test_saved_when_the_validator_passes(self):
        check = self.save(self.validator(PASSES))
        self.assertEqual(check, "Organizers' validator on findings.reviewed.json: valid")
        out = self.dir / "out"
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["findings.reviewed.json", "readiness.signed.json", "review_record.md"])
        self.assertIn(NAME, (out / "review_record.md").read_text(encoding="utf-8"))
        signed = json.loads((out / "readiness.signed.json").read_text(encoding="utf-8"))
        self.assertEqual(signed["review"]["signed_off"]["by"], NAME)
        self.assertEqual(json.loads((out / "findings.reviewed.json").read_text(encoding="utf-8"))["decisions"][0]["reviewer"], NAME)

    def test_nothing_is_saved_when_the_validator_rejects(self):
        for label, body in (("rejects", REJECTS), ("prints valid but exits 1", SAYS_VALID_BUT_FAILS)):
            with self.subTest(label):
                with self.assertRaises(review.NotSaved) as stop:
                    self.save(self.validator(body))
                self.assertIn("validator rejected findings.reviewed.json", str(stop.exception))
                self.assertFalse((self.dir / "out").exists())
        self.assertIn("unknown repair", review.validate(self.reviewed, self.validator(REJECTS))[1])

    def test_no_validator_to_ask(self):
        check = self.save(self.dir / "no-such-validate.py")
        self.assertIn("was not checked", check)
        self.assertTrue((self.dir / "out" / "findings.reviewed.json").exists())

    def test_release_a_alone_has_no_findings_to_check(self):
        check = review.save(self.dir / "out", self.signed, None, None, self.validator(REJECTS))
        self.assertEqual(check, "")
        self.assertEqual(sorted(p.name for p in (self.dir / "out").iterdir()), ["readiness.signed.json", "review_record.md"])

    def test_a_failed_write_leaves_no_partial_file(self):
        target = self.dir / "record.md"
        with mock.patch.object(review.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                review.write_atomic(target, "text")
        self.assertEqual([p.name for p in self.dir.iterdir()], [])
        review.write_atomic(target, NAME)
        self.assertEqual(target.read_text(encoding="utf-8"), NAME)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["record.md"])

    @unittest.skipUnless(REAL_VALIDATOR.exists(), "needs the challenge repo next to this repo")
    def test_the_organizers_validator_accepts_the_reviewed_findings(self):
        self.assertEqual(review.validate(self.reviewed, REAL_VALIDATOR), (True, ""))
        broken = {**self.reviewed, "decisions": [{"repair_id": "R999", "decision": "approve", "reason": "x",
                                                  "reviewer_role": "y"}]}
        ok, said = review.validate(broken, REAL_VALIDATOR)
        self.assertFalse(ok)
        self.assertIn("unknown repair 'R999'", said)


if __name__ == "__main__":
    unittest.main()
