"""Tests for the coverage, design, bias and question checks, the verdict rule and the cards (no download)."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import synth  # noqa: E402
from synth import C, ER, FINAL, IHC, NAT, P, PAM, S  # noqa: E402
from tower import questions  # noqa: E402
from tower.analyses import rerun  # noqa: E402
from tower.cards import REQUIRED, list_cards, load_card  # noqa: E402
from tower.checks import CHECKS, Issue, load_all, run_checks  # noqa: E402
from tower.checks.bias import site_shift  # noqa: E402
from tower.checks.coverage import missing_values, subtype_missing  # noqa: E402
from tower.checks.design import LEAKAGE_COLUMNS, a2_robustness, leakage_columns  # noqa: E402
from tower.checks.fitness import (endpoint_suitability, inputs_present, label_derivation,  # noqa: E402
                                  outcome_available)
from tower.diff import compare  # noqa: E402
from tower.readiness import assess, markdown  # noqa: E402
from tower.release import load_release  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.fr = synth.frames()
        self.n = 0

    def release(self, fr=None, skip=(), name=None):
        self.n += 1
        return load_release(synth.write(self.tmp / (name or f"r{self.n}"), fr if fr is not None else self.fr, skip))

    def check(self, fn, release, card) -> list[Issue]:
        issues = fn(release, card)
        self.assertTrue(issues)
        for x in issues:
            self.assertIsInstance(x, Issue)
            self.assertTrue(x.title.strip())
            self.assertNotIn("nan", x.title.lower().split())
            self.assertTrue(all(":" in f for f in x.fields), x.fields)
            self.assertEqual(len(x.rows), len(set(x.rows)))
            if x.status in ("warn", "block"):
                for attr in ("rule", "source", "next_step", "evidence_needed"):
                    self.assertTrue(getattr(x, attr), f"{x.id}: a {x.status} needs {attr}")
                self.assertTrue(x.numbers)
            json.dumps(x.to_dict(), allow_nan=False)
        return issues

    def one(self, fn, release, card) -> Issue:
        issues = self.check(fn, release, card)
        self.assertEqual(len(issues), 1)
        return issues[0]


class Coverage(Base):
    def test_subtype_missing(self):
        card = load_card("subtype-mix")
        x = self.one(subtype_missing, self.release(), card)
        self.assertEqual((x.status, x.material, x.numbers["blank"], x.numbers["base_group_samples"]), ("pass", False, 0, 40))
        fr = synth.copy(self.fr)
        blank = list(fr[C].sampleID[:5])
        fr[C].loc[fr[C].sampleID.isin(blank), PAM] = ""
        x = self.one(subtype_missing, self.release(fr), card)
        self.assertEqual((x.status, x.material, sorted(x.rows)), ("warn", True, sorted(blank)))      # 5 of 40 is over 10%
        fr[C] = fr[C].drop(columns=[PAM])
        self.assertEqual(self.one(subtype_missing, self.release(fr), card).status, "unknown")
        self.assertEqual(self.one(subtype_missing, self.release(skip=(C,)), card).status, "unknown")

    def test_missing_values_one_issue_per_field(self):
        card = load_card("her2-positive-protein")
        issues = self.check(missing_values, self.release(), card)
        self.assertEqual([x.id for x in issues], [f"missing_values_{IHC}", f"missing_values_{FINAL}"])
        self.assertEqual({(x.status, x.material) for x in issues}, {("pass", False)})

    def test_missing_values_counts_the_base_group(self):
        card = load_card("er-alpha-by-er")
        pos, _ = synth.a1_samples(self.fr)
        fr = synth.copy(self.fr)
        fr[C].loc[fr[C].sampleID.isin(pos[:4]), ER] = ""
        x = self.one(missing_values, self.release(fr), card)
        self.assertEqual((x.status, x.numbers["blank"], x.numbers["base_group_samples"]), ("warn", 4, 34))
        self.assertEqual(sorted(x.rows), sorted(pos[:4]))

    def test_missing_values_edge_cases(self):
        rel = self.release()
        x = self.one(missing_values, rel, {"id": "t", "uses": {P: ["HER2"]}})
        self.assertEqual((x.status, x.material), ("pass", False))
        x = self.one(missing_values, rel, {"id": "t", "uses": {C: ["no_such_column"]}, "group": {"sample_type": "01"}})
        self.assertEqual((x.status, x.id), ("unknown", "missing_values_no_such_column"))
        esr1 = load_card("esr1-expression-vs-er")      # needs the RNA file
        self.assertEqual(self.one(missing_values, rel, esr1).status, "unknown")


class Design(Base):
    def test_leakage_columns(self):
        rel = self.release()
        x = self.one(leakage_columns, rel, load_card("subtype-classifier-rna"))
        self.assertEqual((x.status, x.material, len(x.numbers["columns_to_keep_out"])), ("pass", True, 9))
        for feats, n in (([C], 9), ([NAT, "rna_hiseq.tsv.gz"], 1), ([f"{C}:{PAM}"], 1)):
            with self.subTest(features=feats):
                x = self.one(leakage_columns, rel, {"id": "t", "features": feats})
                self.assertEqual((x.status, len(x.numbers["leaking"])), ("block", n))
        x = self.one(leakage_columns, rel, {"id": "t"})
        self.assertEqual((x.status, x.material), ("pass", False))
        self.assertEqual(len(LEAKAGE_COLUMNS), 9)

    def test_a2_robustness(self):
        card = load_card("subtype-mix")
        x = self.one(a2_robustness, self.release(), card)
        self.assertEqual((x.status, x.numbers["compared"], x.numbers["disagree"]), ("pass", 20, 0))
        fr = synth.copy(self.fr)
        both = fr[C][(fr[C][PAM] == "LumA") & (fr[C][NAT] != "")].sampleID[:2]
        fr[C].loc[fr[C].sampleID.isin(both), NAT] = "Luminal B"
        x = self.one(a2_robustness, self.release(fr), card)
        self.assertEqual((x.status, sorted(x.rows)), ("warn", sorted(both)))      # Luminal A: 20% vs 10% of 20
        self.assertEqual(x.numbers["largest_gap_points"], 10.0)
        fr[C] = fr[C].drop(columns=[NAT])
        self.assertEqual(self.one(a2_robustness, self.release(fr), card).status, "unknown")


class Bias(Base):
    def test_site_shift(self):
        card = load_card("er-alpha-by-er")
        rel = self.release()
        x = self.one(site_shift, rel, card)
        self.assertEqual(x.status, "pass")
        self.assertAlmostEqual(x.numbers["total_variation_distance"], 0.029, places=3)
        strict = {**card, "limits": {"site_shift_tvd": 0.01}}
        x = self.one(site_shift, rel, strict)
        self.assertEqual((x.status, len(x.rows)), ("warn", 34))
        self.assertEqual(self.one(site_shift, self.release(skip=(P,)), card).status, "unknown")
        self.assertEqual(self.one(site_shift, self.release(skip=(C,)), card).status, "unknown")


class Fitness(Base):
    def test_endpoint_suitability(self):
        rel = self.release()
        x = self.one(endpoint_suitability, rel, load_card("os-luminal-a"))
        self.assertEqual((x.status, x.numbers["samples"]), ("block", 8))
        self.assertEqual(self.one(endpoint_suitability, rel, load_card("pfi-luminal-a")).status, "pass")
        self.assertEqual(self.one(endpoint_suitability, rel, questions.survival_question("DSS")).status, "warn")
        x = self.one(endpoint_suitability, rel, {"id": "t"})
        self.assertEqual((x.status, x.material), ("pass", False))

    def test_endpoint_suitability_when_it_cannot_tell(self):
        card = load_card("os-luminal-a")
        self.assertEqual(self.one(endpoint_suitability, self.release(skip=(S,)), card).status, "unknown")
        x = self.one(endpoint_suitability, self.release(skip=(C,)), card)
        self.assertEqual(x.status, "unknown")
        self.assertIn("clinical file is missing", x.title)
        fr = synth.copy(self.fr)
        fr[S] = fr[S].drop(columns=["OS.time"])
        x = self.one(endpoint_suitability, self.release(fr), card)
        self.assertEqual((x.status, x.numbers["missing_fields"]), ("unknown", ["OS.time"]))

    def test_focus_subtype_column_missing(self):
        fr = synth.copy(self.fr)
        fr[C] = fr[C].drop(columns=[PAM])
        x = self.one(endpoint_suitability, self.release(fr), load_card("os-luminal-a"))
        self.assertEqual((x.status, x.numbers["missing_fields"]), ("unknown", [PAM]))
        self.assertIn("no PAM50Call_RNAseq column, so the Luminal A tumors can't be picked out", x.title)

    def test_follow_up_that_cannot_be_estimated(self):
        fr = synth.copy(self.fr)
        fr[S]["OS.time"] = ""
        x = self.one(endpoint_suitability, self.release(fr), load_card("os-luminal-a"))
        self.assertIsNone(x.numbers["median_follow_up_months"])
        self.assertIn("can't be estimated", x.title)

    def test_inputs_label_and_outcome(self):
        rel = self.release()
        self.assertEqual(self.one(inputs_present, rel, load_card("er-alpha-by-er")).status, "pass")
        x = self.one(inputs_present, rel, {"id": "t", "uses": {P: ["NO_SUCH_PROTEIN"], "rna_hiseq.tsv.gz": ["ESR1"]}})
        self.assertEqual((x.status, x.numbers["missing_files"], x.numbers["missing_fields"]),
                         ("unknown", ["rna_hiseq.tsv.gz"], [f"{P}:NO_SUCH_PROTEIN"]))
        self.assertEqual(self.one(label_derivation, rel, load_card("subtype-classifier-rna")).status, "block")
        self.assertEqual(self.one(label_derivation, rel, questions.model_question(ER, [P])).status, "pass")
        self.assertEqual(self.one(label_derivation, rel, questions.model_question(ER, [])).status, "unknown")
        issues = self.check(outcome_available, rel, load_card("hormone-therapy-response"))
        self.assertEqual([x.status for x in issues], ["block", "block"])


class Verdicts(Base):
    def assess(self, card, fr=None, skip=(), against=None, allow_missing=False) -> dict:
        rel = self.release(fr, skip)
        cmp = results = None
        if against is not None:
            cmp = compare(against, rel)
            results, _ = rerun(against, rel, cmp.changes)
        doc = assess(card, rel, cmp, results, allow_missing=allow_missing)
        json.dumps(doc, allow_nan=False, default=str)
        markdown(doc)
        return doc

    def test_each_verdict(self):
        self.assertEqual(self.assess(load_card("er-alpha-by-er"))["verdict"], "Ready")
        self.assertEqual(self.assess(load_card("os-luminal-a"))["verdict"], "Blocked")
        self.assertEqual(self.assess(load_card("esr1-expression-vs-er"))["verdict"], "Insufficient Evidence")
        strict = {**load_card("er-alpha-by-er"), "limits": {"site_shift_tvd": 0.01, "missing_fraction": 0.10}}
        doc = self.assess(strict)
        self.assertEqual((doc["verdict"], doc["review"]["required"]), ("Conditional", ["site_shift"]))
        self.assertTrue(doc["next_steps"] and doc["cannot_tell"] and doc["lineage"])
        self.assertEqual(doc["group_size"], len(doc["group_samples"]))

    def test_a_block_outranks_everything(self):
        card = {**load_card("os-luminal-a"), "checks": ["endpoint_suitability", "no_such_check", "survival_zero_time"]}
        self.assertEqual(self.assess(card)["verdict"], "Blocked")

    def test_a_check_that_is_not_built(self):
        card = {**load_card("er-alpha-by-er"), "checks": ["inputs_present", "no_such_check"]}
        self.assertEqual(self.assess(card)["verdict"], "Insufficient Evidence")
        doc = self.assess(card, allow_missing=True)
        self.assertEqual((doc["verdict"], doc["pending_checks"]), ("Ready", ["no_such_check"]))

    def test_a_release_change_makes_it_conditional(self):
        a = self.release(name="release-A")
        pos, neg = synth.a1_samples(self.fr)
        fr = synth.copy(self.fr)
        fr[P] = fr[P].rename(columns={pos[0]: neg[0], neg[0]: pos[0]})[list(fr[P].columns)]
        doc = self.assess(load_card("er-alpha-by-er"), fr, against=a)
        self.assertEqual(doc["verdict"], "Conditional")
        self.assertEqual([t["finding"] for t in doc["release_changes"]], ["F1"])
        self.assertEqual(sorted(doc["release_changes"][0]["samples"]), sorted([pos[0], neg[0]]))
        self.assertEqual(doc["review"]["required"], ["F1"])
        self.assertEqual(doc["error_budget"]["items"][0]["this_release"], 1)
        self.assertEqual(doc["robustness"]["status"], "holds")
        how = doc["robustness"]["range_method"]
        self.assertEqual((how["resamples"], how["seed"]), (1000, 7))
        self.assertIn("bootstrap", how["method"])
        again = self.assess(load_card("er-alpha-by-er"), fr, against=a)
        self.assertEqual(again["robustness"]["range_95"], doc["robustness"]["range_95"])
        other = self.assess(load_card("subtype-mix"), fr, against=a)       # the swap doesn't touch this question
        self.assertEqual(other["release_changes"], [])

    def test_the_verdict_follows_the_question(self):
        rel = self.release()
        got = {c["id"]: assess(c, rel)["verdict"] for c in list_cards()}
        self.assertEqual(got["os-luminal-a"], "Blocked")
        self.assertEqual(got["subtype-classifier-rna"], "Blocked")
        self.assertEqual(got["hormone-therapy-response"], "Blocked")
        self.assertEqual(got["esr1-expression-vs-er"], "Insufficient Evidence")
        self.assertNotEqual(got["pfi-luminal-a"], "Blocked")

    def test_a_check_that_crashes_is_reported_not_raised(self):
        from tower import checks
        checks.CHECKS["boom"] = lambda release, card: 1 / 0
        self.addCleanup(checks.CHECKS.pop, "boom")
        issues = run_checks(self.release(), {"id": "t", "checks": ["boom"]})
        self.assertEqual((issues[0].status, issues[0].material), ("unknown", True))


class Cards(unittest.TestCase):
    def test_cards_list_only_checks_that_exist(self):
        load_all()
        cards = list_cards()
        self.assertEqual(len(cards), 8)
        for c in cards:
            with self.subTest(card=c["id"]):
                self.assertEqual([k for k in REQUIRED if k not in c], [])
                self.assertEqual([n for n in c["checks"] if n not in CHECKS], [])

    def test_questions_built_on_screen(self):
        load_all()
        built = [questions.survival_question(e, f) for e in questions.ENDPOINTS for f in (None, *questions.SUBTYPES)]
        built += [questions.protein_question("ERALPHA", g) for g in questions.GROUPINGS]
        built += [questions.model_question(lab, [P]) for lab in questions.LABELS]
        built += [questions.treatment_question(t) for t in questions.THERAPIES]
        for c in built:
            with self.subTest(card=c["id"]):
                self.assertEqual([k for k in REQUIRED if k not in c], [])
                self.assertEqual([n for n in c["checks"] if n not in CHECKS], [])
                self.assertTrue(c["id"].startswith("custom-"))
        a1 = questions.protein_question("ERALPHA", ER)
        self.assertEqual(a1.get("analyses"), ["A1"])


if __name__ == "__main__":
    unittest.main()
