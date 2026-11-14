"""Tests for the nine release A checks in tower/checks/ (survival.py, labels.py, coverage.py, design.py).

Run from the repo root:
  .venv/bin/python -m unittest tests.test_release_a_checks -v

1. Release A with the real cards gives the numbers in docs/PLAN.md and docs/CONTRACTS.md, for all nine checks
   (skipped if the challenge repo isn't next to this one).
2. Tiny synthetic releases, written to a temporary folder, exercise missing files and columns, empty groups, odd
   values and cards a check doesn't apply to. Each must return the right status and never raise.
3. One made-up release on which each of the nine checks must return a known status and count (no download).
4. Every Issue returned anywhere in this file meets the contract (docs/CONTRACTS.md, section 2).
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tower.cards import card_base_group, card_group, load_card  # noqa: E402
from tower.checks import STATUSES, Issue  # noqa: E402
from tower.checks.coverage import missing_values, subtype_missing  # noqa: E402
from tower.checks.design import a2_robustness, leakage_columns  # noqa: E402
from tower.checks.labels import her2_field_conflict, subtype_columns_disagree  # noqa: E402
from tower.checks.survival import patient_double_count, survival_redacted, survival_zero_time  # noqa: E402
from tower.release import load_release  # noqa: E402

RELEASE_A = REPO.parent / "oncosys-hackathon-challenge" / "data" / "tcga-brca" / "raw"
SURVIVAL_CHECKS = {"survival_redacted": survival_redacted, "survival_zero_time": survival_zero_time,
                   "patient_double_count": patient_double_count}
LABEL_CHECKS = {"subtype_columns_disagree": subtype_columns_disagree, "her2_field_conflict": her2_field_conflict}
ALL_CHECKS = {**SURVIVAL_CHECKS, **LABEL_CHECKS}

IHC, FINAL = "lab_proc_her2_neu_immunohistochemistry_receptor_status", "HER2_Final_Status_nature2012"
CLIN_COLS = ["PAM50Call_RNAseq", "PAM50_mRNA_nature2012", IHC, FINAL]
SURV_COLS = ["_PATIENT", "OS", "OS.time", "DSS", "DSS.time", "DFI", "DFI.time", "PFI", "PFI.time", "Redaction"]


class ContractMixin:
    """Run a check, assert it didn't raise, and assert every Issue meets the contract."""

    def run_check(self, name, release, card) -> list[Issue]:
        try:
            issues = ALL_CHECKS[name](release, card)
        except Exception as e:  # noqa: BLE001
            self.fail(f"{name} raised {type(e).__name__}: {e}")
        self.assertIsInstance(issues, list)
        self.assertTrue(issues, f"{name} returned no Issue")
        group = card_group(release, card)
        for x in issues:
            self.assertIsInstance(x, Issue)
            self.assertTrue(str(x.id).startswith(name), f"id {x.id!r} should start with {name!r}")
            self.assertTrue(x.title.strip(), f"{x.id}: empty title")
            self.assertIn(x.status, STATUSES)
            self.assertIsInstance(x.material, bool)
            self.assertLessEqual(set(x.rows), group, f"{x.id}: rows that aren't in the card's group")
            self.assertEqual(len(x.rows), len(set(x.rows)), f"{x.id}: duplicate rows")
            for f in x.fields:
                self.assertIn(":", f, f"{x.id}: field {f!r} should read 'file:column'")
            if x.status in ("warn", "block"):
                for attr in ("rule", "source", "next_step", "evidence_needed"):
                    self.assertTrue(getattr(x, attr), f"{x.id}: a {x.status} needs {attr}")
                self.assertTrue(x.numbers, f"{x.id}: a {x.status} needs numbers")
        return issues

    def one(self, name, release, card) -> Issue:
        issues = self.run_check(name, release, card)
        self.assertEqual(len(issues), 1, f"{name} should return one Issue")
        return issues[0]


# ---------------------------------------------------------------------------------------------- 1. release A


@unittest.skipUnless(RELEASE_A.is_dir(), f"release A not found at {RELEASE_A}")
class ReleaseANumbers(ContractMixin, unittest.TestCase):
    """The expected answers on release A (docs/PLAN.md, 'Aakruti: release A checks, part 1')."""

    @classmethod
    def setUpClass(cls):
        cls.rel = load_release(RELEASE_A, "release-A")
        cls.cards = {c: load_card(c) for c in ("os-luminal-a", "pfi-luminal-a", "subtype-mix",
                                               "her2-positive-protein")}

    def test_survival_redacted(self):
        for cid in ("os-luminal-a", "pfi-luminal-a"):
            with self.subTest(card=cid):
                x = self.one("survival_redacted", self.rel, self.cards[cid])
                self.assertEqual(x.status, "warn")
                self.assertTrue(x.material)
                self.assertEqual(set(x.rows), {"TCGA-A7-A0DC-01", "TCGA-AR-A0U1-01"})
                self.assertEqual(x.numbers["redacted_in_group"], 2)

    def test_survival_zero_time(self):
        for cid, ep in (("os-luminal-a", "OS"), ("pfi-luminal-a", "PFI")):
            with self.subTest(card=cid):
                x = self.one("survival_zero_time", self.rel, self.cards[cid])
                self.assertEqual(x.status, "warn")
                self.assertEqual(x.numbers["endpoint"], ep)
                self.assertEqual(x.numbers["zero_time_in_group"], 11)
                self.assertEqual(len(x.rows), 11)
                self.assertIn(f"survival.tsv:{ep}.time", x.fields)

    def test_patient_double_count(self):
        for cid in ("os-luminal-a", "pfi-luminal-a"):
            with self.subTest(card=cid):
                x = self.one("patient_double_count", self.rel, self.cards[cid])
                self.assertEqual(x.status, "pass")
                self.assertFalse(x.material)
                self.assertEqual(x.numbers["patients_more_than_once_in_group"], 0)
                self.assertEqual(x.numbers["patients_with_identical_rows_in_file"], 135)
                self.assertEqual(x.rows, [])

    def test_subtype_columns_disagree(self):
        for cid in ("subtype-mix", "os-luminal-a", "pfi-luminal-a"):
            with self.subTest(card=cid):
                x = self.one("subtype_columns_disagree", self.rel, self.cards[cid])
                self.assertEqual(x.status, "warn")
                self.assertEqual(x.numbers["disagree"], 52)
                self.assertEqual(x.numbers["compared"], 508)
                self.assertEqual(len(x.rows), 52)
                self.assertAlmostEqual(x.numbers["share"], 0.1024, places=4)

    def test_her2_field_conflict(self):
        x = self.one("her2_field_conflict", self.rel, self.cards["her2-positive-protein"])
        self.assertEqual(x.status, "warn")
        self.assertEqual(x.numbers["positive_vs_negative"], 29)
        self.assertEqual(x.numbers["differ"], 146)
        self.assertEqual(x.numbers["compared"], 551)
        self.assertEqual(x.numbers["ihc_equivocal_resolved"], 105)
        self.assertEqual(len(x.rows), 29)
        self.assertEqual(len(x.numbers["all_differing_samples"]), 146)
        self.assertLessEqual(set(x.rows), set(x.numbers["all_differing_samples"]))


DOCUMENTED = "this number is documented in docs/CONTRACTS.md, section 5; if the data says otherwise, trust the data"


@unittest.skipUnless(RELEASE_A.is_dir(), f"release A not found at {RELEASE_A}")
class ReleaseANumbersCoverageAndDesign(unittest.TestCase):
    """The coverage and design checks on release A (numbers from docs/CONTRACTS.md, section 5)."""

    @classmethod
    def setUpClass(cls):
        cls.rel = load_release(RELEASE_A, "release-A")
        cls.cards = {c: load_card(c) for c in ("subtype-mix", "er-alpha-by-er", "her2-positive-protein",
                                               "esr1-expression-vs-er", "subtype-classifier-rna")}

    def blanks(self, card_id: str) -> dict[str, Issue]:
        card = self.cards[card_id]
        issues = missing_values(self.rel, card)
        base = card_base_group(self.rel, card)
        for x in issues:
            self.assertLessEqual(set(x.rows), base, f"{x.id}: rows outside the card's base group")
            self.assertEqual(len(x.rows), x.numbers["blank"])
        return {x.numbers["field"]: x for x in issues}

    def test_subtype_missing(self):
        x, = subtype_missing(self.rel, self.cards["subtype-mix"])
        self.assertEqual((x.status, x.material), ("warn", True))
        self.assertEqual((x.numbers["blank"], x.numbers["base_group_samples"]), (257, 1101), DOCUMENTED)
        self.assertEqual(len(x.rows), 257)
        self.assertAlmostEqual(x.numbers["share"], 0.2334, places=4)

    def test_missing_values_er_alpha_card(self):
        got = self.blanks("er-alpha-by-er")
        x = got["breast_carcinoma_estrogen_receptor_status"]
        self.assertEqual((x.status, x.material, x.id), ("pass", False, "missing_values_breast_carcinoma_estrogen_receptor_status"))
        self.assertEqual((x.numbers["blank"], x.numbers["base_group_samples"]), (42, 742), DOCUMENTED)

    def test_missing_values_her2_card(self):
        got = self.blanks("her2-positive-protein")
        self.assertEqual(sorted(got), sorted([IHC, FINAL]))
        self.assertEqual({k: x.status for k, x in got.items()}, {IHC: "warn", FINAL: "warn"})
        self.assertEqual((got[IHC].numbers["blank"], got[IHC].numbers["base_group_samples"]), (111, 742), DOCUMENTED)
        self.assertEqual((got[FINAL].numbers["blank"], got[FINAL].numbers["base_group_samples"]), (110, 742), DOCUMENTED)

    def test_missing_values_esr1_card(self):
        x = self.blanks("esr1-expression-vs-er")["breast_carcinoma_estrogen_receptor_status"]
        self.assertEqual(x.status, "pass")
        self.assertEqual((x.numbers["blank"], x.numbers["base_group_samples"]), (50, 1097), DOCUMENTED)

    def test_leakage_columns(self):
        x, = leakage_columns(self.rel, self.cards["subtype-classifier-rna"])
        self.assertEqual((x.status, x.material, x.numbers["leaking"]), ("pass", True, []))
        self.assertEqual(len(x.numbers["columns_to_keep_out"]), 9)

    def test_a2_robustness(self):
        x, = a2_robustness(self.rel, self.cards["subtype-mix"])
        self.assertEqual((x.status, x.material), ("warn", True))
        self.assertEqual(x.numbers["compared"], 508, DOCUMENTED)
        self.assertEqual((x.numbers["largest_gap"], x.numbers["subtypes_over_threshold"]), ("Luminal A", ["Luminal A"]))
        a = x.numbers["shares"]["Luminal A"]
        self.assertEqual((a["PAM50Call_RNAseq_percent"], a["PAM50_mRNA_nature2012_percent"], a["difference_points"]),
                         (51.0, 44.9, 6.1), DOCUMENTED)
        self.assertEqual(len(x.rows), x.numbers["disagree"])


# ---------------------------------------------------------------------------------------- 2. synthetic releases


def _sid(n: int, kind: str = "01", vial: str = "") -> str:
    return f"TCGA-ZZ-{n:04d}-{kind}{vial}"


def _write(path: pathlib.Path, idcol: str, cols: list[str], rows: list[dict]) -> None:
    lines = ["\t".join([idcol] + cols)]
    for r in rows:
        lines.append("\t".join([r["id"]] + [str(r.get(c, "")) for c in cols]))
    path.write_text("\n".join(lines) + "\n")


def _surv_row(sid, os_time="100", pfi_time="100", redaction=""):
    return {"id": sid, "_PATIENT": sid[:12], "OS": "0", "OS.time": os_time, "DSS": "0", "DSS.time": os_time,
            "DFI": "0", "DFI.time": pfi_time, "PFI": "0", "PFI.time": pfi_time, "Redaction": redaction}


def _clin_row(sid, rna="LumA", nat="Luminal A", ihc="Negative", final="Negative"):
    return {"id": sid, "PAM50Call_RNAseq": rna, "PAM50_mRNA_nature2012": nat, IHC: ihc, FINAL: final}


def _card(endpoint="OS", in_files=("survival.tsv",), **extra):
    card = {"id": "synthetic", "group": {"sample_type": "01", "in_files": list(in_files),
                                         "not_blank": ["PAM50Call_RNAseq"]},
            "limits": {"subtype_disagreement": 0.05}}
    if endpoint:
        card["endpoint"] = {"name": endpoint, "focus_subtype": "LumA"}
    card.update(extra)
    return card


class SyntheticReleases(ContractMixin, unittest.TestCase):
    """Small releases built in a temporary folder outside the repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.n = 0

    def release(self, clinical=None, survival=None, clin_cols=None, surv_cols=None):
        """Write the given rows (None = leave the file out) and load the folder as a release."""
        self.n += 1
        d = pathlib.Path(self._tmp.name) / f"r{self.n}"
        d.mkdir()
        if clinical is not None:
            _write(d / "clinical.tsv", "sampleID", clin_cols or CLIN_COLS, clinical)
        if survival is not None:
            _write(d / "survival.tsv", "sample", surv_cols or SURV_COLS, survival)
        return load_release(d, f"synthetic-{self.n}")

    def basic(self, k=4):
        ids = [_sid(i) for i in range(k)]
        return ids, [_clin_row(s) for s in ids], [_surv_row(s) for s in ids]

    # -- missing file and columns

    def test_missing_survival_file(self):
        _, clin, _ = self.basic()
        rel = self.release(clinical=clin)
        for name in SURVIVAL_CHECKS:
            with self.subTest(check=name):
                self.assertEqual(self.one(name, rel, _card()).status, "unknown")

    def test_missing_survival_columns(self):
        _, clin, surv = self.basic()
        for name, drop in (("survival_redacted", "Redaction"), ("survival_zero_time", "OS.time")):
            with self.subTest(check=name, column=drop):
                rel = self.release(clinical=clin, survival=surv, surv_cols=[c for c in SURV_COLS if c != drop])
                x = self.one(name, rel, _card())
                self.assertEqual(x.status, "unknown")
                self.assertIn(drop, x.numbers["missing_fields"])

    def test_missing_label_columns(self):
        _, clin, surv = self.basic()
        for name, drop in (("subtype_columns_disagree", "PAM50_mRNA_nature2012"), ("her2_field_conflict", FINAL)):
            with self.subTest(check=name, column=drop):
                rel = self.release(clinical=clin, survival=surv, clin_cols=[c for c in CLIN_COLS if c != drop])
                x = self.one(name, rel, _card())
                self.assertEqual(x.status, "unknown")
                self.assertIn(drop, x.numbers["missing_fields"])

    def test_missing_clinical_file(self):
        _, _, surv = self.basic()
        rel = self.release(survival=surv)
        for name in ALL_CHECKS:
            with self.subTest(check=name):
                self.assertEqual(self.one(name, rel, _card()).status, "unknown")

    # -- empty group

    def test_empty_group(self):
        ids = [_sid(i, kind="11") for i in range(3)]          # normals only: no primary tumor
        rel = self.release(clinical=[_clin_row(s) for s in ids], survival=[_surv_row(s) for s in ids])
        for name in ALL_CHECKS:
            with self.subTest(check=name):
                self.assertEqual(self.one(name, rel, _card()).status, "unknown")

    # -- odd values

    def test_blank_and_non_numeric_times(self):
        ids, clin, _ = self.basic(5)
        times = ["0", "", "NA", "abc", "120"]
        surv = [_surv_row(s, os_time=t) for s, t in zip(ids, times)]
        x = self.one("survival_zero_time", self.release(clinical=clin, survival=surv), _card())
        self.assertEqual(x.status, "warn")
        self.assertEqual(x.rows, [ids[0]])
        self.assertEqual(x.numbers["blank_or_not_a_number_time_in_group"], 3)

    def test_no_zero_times(self):
        _, clin, surv = self.basic()
        x = self.one("survival_zero_time", self.release(clinical=clin, survival=surv), _card())
        self.assertEqual(x.status, "pass")
        self.assertEqual(x.rows, [])

    def test_unknown_subtype_code(self):
        ids = [_sid(i) for i in range(3)]
        clin = [_clin_row(ids[0], "LumA", "Luminal A"),     # agree
                _clin_row(ids[1], "LumB", "Luminal A"),     # disagree
                _clin_row(ids[2], "Claudin", "Luminal B")]  # code the mapping doesn't know
        rel = self.release(clinical=clin, survival=[_surv_row(s) for s in ids])
        x = self.one("subtype_columns_disagree", rel, _card())
        self.assertEqual(x.numbers["unmapped_rnaseq_values"], {"Claudin": 1})
        self.assertEqual(x.numbers["compared"], 2)
        self.assertEqual(x.rows, [ids[1]])
        self.assertNotIn(ids[2], x.rows)
        self.assertEqual(x.status, "warn")                  # 1 of 2 is above 5%

    def test_card_without_endpoint(self):
        _, clin, surv = self.basic()
        rel = self.release(clinical=clin, survival=surv)
        for name in SURVIVAL_CHECKS:
            with self.subTest(check=name):
                x = self.one(name, rel, _card(endpoint=None))
                self.assertEqual(x.status, "pass")
                self.assertFalse(x.material)

    # -- the three extra branches

    def test_patient_twice_in_group(self):
        a, b, c = _sid(1, vial="A"), _sid(1, vial="B"), _sid(2)   # a and b: same patient, both primary tumors
        rel = self.release(clinical=[_clin_row(s) for s in (a, b, c)],
                           survival=[_surv_row(s) for s in (a, b, c)])
        x = self.one("patient_double_count", rel, _card())
        self.assertEqual(x.status, "warn")
        self.assertTrue(x.material)
        self.assertEqual(sorted(x.rows), sorted([a, b]))
        self.assertEqual(x.numbers["patients_more_than_once_in_group"], 1)

    def test_her2_differences_without_positive_vs_negative(self):
        ids = [_sid(i) for i in range(3)]
        clin = [_clin_row(ids[0], ihc="Equivocal", final="Negative"),
                _clin_row(ids[1], ihc="Positive", final="Equivocal"),
                _clin_row(ids[2], ihc="Negative", final="Negative")]
        x = self.one("her2_field_conflict", self.release(clinical=clin, survival=[_surv_row(s) for s in ids]),
                     _card())
        self.assertEqual(x.status, "pass")
        self.assertEqual(x.rows, [])
        self.assertEqual(x.numbers["differ"], 2)
        self.assertEqual(x.numbers["positive_vs_negative"], 0)
        self.assertEqual(sorted(x.numbers["all_differing_samples"]), sorted(ids[:2]))


# ---------------------------------------------------------------------------------- 3. all nine, one release


class AllNineOnOneMadeUpRelease(unittest.TestCase):
    """All nine checks on one made-up release with planted problems."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tests"))
        import synth
        from synth import C, ER, NAT, PAM, S
        cls._tmp = tempfile.TemporaryDirectory()
        fr = synth.frames()
        tumors = [s for s in fr[C].sampleID if s[13:15] == "01"]
        cls.redacted, cls.zero = [tumors[2], tumors[4]], tumors[6]
        fr[S].loc[cls.redacted, "Redaction"] = "Redacted"
        fr[S].loc[cls.zero, ["OS.time", "PFI.time"]] = "0"
        cls.relabelled = [tumors[0], tumors[10]]      # Luminal A, with both calls
        fr[C].loc[fr[C].sampleID.isin(cls.relabelled), NAT] = "Luminal B"
        cls.conflict = tumors[8]
        fr[C].loc[fr[C].sampleID == cls.conflict, [IHC, FINAL]] = ["Positive", "Negative"]
        cls.no_subtype = [tumors[i] for i in (1, 3, 5, 7, 9)]
        fr[C].loc[fr[C].sampleID.isin(cls.no_subtype), PAM] = ""
        cls.no_ihc = [tumors[i] for i in (11, 12, 13, 14)]
        fr[C].loc[fr[C].sampleID.isin(cls.no_ihc), IHC] = ""
        cls.rel = load_release(synth.write(pathlib.Path(cls._tmp.name) / "release", fr))
        cls.er = ER

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_survival_checks(self):
        os_card = load_card("os-luminal-a")
        x, = survival_redacted(self.rel, os_card)
        self.assertEqual((x.status, sorted(x.rows)), ("warn", sorted(self.redacted)))
        x, = survival_zero_time(self.rel, os_card)
        self.assertEqual((x.status, x.rows, x.numbers["endpoint"]), ("warn", [self.zero], "OS"))
        x, = survival_zero_time(self.rel, load_card("pfi-luminal-a"))
        self.assertEqual((x.status, x.rows, x.numbers["endpoint"]), ("warn", [self.zero], "PFI"))
        x, = patient_double_count(self.rel, os_card)
        self.assertEqual((x.status, x.material, x.numbers["patients_more_than_once_in_group"]), ("pass", False, 0))

    def test_label_checks(self):
        x, = subtype_columns_disagree(self.rel, load_card("subtype-mix"))
        self.assertEqual((x.status, sorted(x.rows), x.numbers["compared"]), ("warn", sorted(self.relabelled), 20))
        x, = her2_field_conflict(self.rel, load_card("her2-positive-protein"))
        self.assertEqual((x.status, x.rows, x.numbers["positive_vs_negative"]), ("warn", [self.conflict], 1))

    def test_coverage_checks(self):
        x, = subtype_missing(self.rel, load_card("subtype-mix"))
        self.assertEqual((x.status, sorted(x.rows), x.numbers["base_group_samples"]), ("warn", sorted(self.no_subtype), 40))
        got = {x.numbers["field"]: x for x in missing_values(self.rel, load_card("her2-positive-protein"))}
        self.assertEqual((got[IHC].status, sorted(got[IHC].rows), got[IHC].numbers["base_group_samples"]),
                         ("warn", sorted(self.no_ihc), 34))
        self.assertEqual((got[FINAL].status, got[FINAL].material, got[FINAL].numbers["blank"]), ("pass", False, 0))
        x, = missing_values(self.rel, load_card("er-alpha-by-er"))
        self.assertEqual((x.status, x.numbers["field"], x.numbers["blank"]), ("pass", self.er, 0))

    def test_design_checks(self):
        x, = leakage_columns(self.rel, load_card("subtype-classifier-rna"))
        self.assertEqual((x.status, x.numbers["leaking"]), ("pass", []))
        x, = a2_robustness(self.rel, load_card("subtype-mix"))
        self.assertEqual((x.status, x.numbers["largest_gap"], x.numbers["largest_gap_points"]), ("warn", "Luminal A", 10.0))
        self.assertEqual(sorted(x.rows), sorted(self.relabelled))


if __name__ == "__main__":
    unittest.main()
