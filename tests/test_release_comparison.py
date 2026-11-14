"""Tests for the release comparison, the A1/A2 reruns and findings.json (no download)."""
from __future__ import annotations

import gzip
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import synth  # noqa: E402
from synth import C, CN, ER, MU, P, PAM, S  # noqa: E402
from tower.analyses import rerun  # noqa: E402
from tower.cli import plain_report  # noqa: E402
from tower.diff import compare, file_summary  # noqa: E402
from tower.evidence import before_after  # noqa: E402
from tower.findings import build, finite  # noqa: E402
from tower.release import load_release  # noqa: E402

SCHEMA = REPO.parent / "oncosys-hackathon-challenge" / "format" / "findings.schema.json"


def cited(doc: dict) -> set[tuple[str, str, str]]:
    return {(f["kind"], e.get("file", ""), e["id"]) for f in doc["findings"] for e in f["evidence"] if e["kind"] == "sample"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.fr = synth.frames()
        self.a = synth.write(self.tmp / "release-A", self.fr)
        self.pos, self.neg = synth.a1_samples(self.fr)
        self.n = 0

    def release(self, fr=None, skip=()) -> pathlib.Path:
        self.n += 1
        return synth.write(self.tmp / f"b{self.n}", fr if fr is not None else self.fr, skip)

    def run_tool(self, b_dir: pathlib.Path) -> dict:
        a, b = load_release(self.a, "release-A"), load_release(b_dir)
        cmp = compare(a, b)
        results, impact = rerun(a, b, cmp.changes)
        doc = build(cmp, results, impact)
        json.dumps(doc, allow_nan=False)
        plain_report(doc)
        before_after(cmp)
        if SCHEMA.exists():
            import jsonschema
            errors = [e.message for e in jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
                      .iter_errors(doc)]
            self.assertEqual(errors, [])
        for f in doc["findings"]:
            self.assertTrue(f["evidence"], f"{f['id']} has no evidence")
            self.assertTrue(f["needs_human_review"])
        return doc

    def analysis(self, doc: dict, aid: str) -> dict:
        return next(a for a in doc["analyses"] if a["id"] == aid)


class Changes(Base):
    def test_no_change(self):
        doc = self.run_tool(self.release())
        self.assertEqual(doc["findings"], [])
        self.assertEqual(doc["verdict"], "Ready")
        self.assertEqual(self.analysis(doc, "A1")["status"], "not_rerun")

    def test_swap_across_er_groups(self):
        fr = synth.copy(self.fr)
        x, y = self.pos[0], self.neg[0]
        fr[P] = fr[P].rename(columns={x: y, y: x})[list(fr[P].columns)]
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("sample_swap", P, x), ("sample_swap", P, y)})
        f = doc["findings"][0]
        self.assertEqual((f["severity"], f["affects_analyses"], f["not_affected_analyses"]), ("high", ["A1"], ["A2"]))
        self.assertEqual(doc["verdict"], "Conditional")
        self.assertEqual(self.analysis(doc, "A1")["status"], "changed")
        self.assertEqual(self.analysis(doc, "A2")["status"], "not_rerun")
        self.assertEqual(doc["repairs"][0]["action"], "restore_from_previous_release")

    def test_swap_within_one_er_group(self):
        fr = synth.copy(self.fr)
        x, y = self.pos[0], self.pos[1]
        fr[P] = fr[P].rename(columns={x: y, y: x})[list(fr[P].columns)]
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("sample_swap", P, x), ("sample_swap", P, y)})
        self.assertEqual(doc["findings"][0]["severity"], "medium")

    def test_chain_of_three(self):
        fr = synth.copy(self.fr)
        x, y, z = self.pos[0], self.neg[0], self.pos[1]
        fr[P] = fr[P].rename(columns={x: y, y: z, z: x})[list(fr[P].columns)]
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("sample_swap", P, s) for s in (x, y, z)})
        self.assertEqual(len(doc["findings"]), 1)

    def test_swap_in_a_file_no_analysis_reads(self):
        fr = synth.copy(self.fr)
        x, y = list(fr[CN].columns[:2])
        fr[CN] = fr[CN].rename(columns={x: y, y: x})[list(fr[CN].columns)]
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("sample_swap", CN, x), ("sample_swap", CN, y)})
        self.assertEqual((doc["findings"][0]["severity"], doc["verdict"]), ("low", "Ready"))

    def test_copies_replace_samples(self):
        fr = synth.copy(self.fr)
        victims, donors = [self.pos[2], self.neg[1]], [self.pos[3], self.pos[4]]
        free = [s for s in fr[C].sampleID if s[13:15] == "01" and s not in fr[P].columns][:2]
        p = fr[P].drop(columns=victims)
        for d, n in zip(donors, free):
            p[n] = p[d]
        fr[P] = p
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("duplicate", P, s) for s in free} | {("membership_change", P, s) for s in victims})
        dup = next(f for f in doc["findings"] if f["kind"] == "duplicate")
        self.assertEqual(dup["severity"], "high")
        self.assertEqual({e["note"].split(" ")[2] for e in dup["evidence"] if e["kind"] == "sample"}, set(donors))
        lost = next(f for f in doc["findings"] if f["kind"] == "membership_change")
        self.assertIn("total sample count is unchanged", lost["summary"])
        self.assertEqual({r["action"] for r in doc["repairs"]}, {"exclude", "flag_for_review"})

    def test_relabel_er(self):
        fr = synth.copy(self.fr)
        picks = self.pos[:3]
        fr[C].loc[fr[C].sampleID.isin(picks), ER] = "Negative"
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("label_conflict", C, s) for s in picks})
        self.assertEqual(doc["findings"][0]["affects_analyses"], ["A1"])
        self.assertEqual(self.analysis(doc, "A1")["status"], "changed")

    def test_relabel_subtype_touches_a2_only(self):
        fr = synth.copy(self.fr)
        picks = [s for s in fr[C].sampleID if s[13:15] == "01"][:4]
        was = fr[C].set_index("sampleID").loc[picks, PAM]
        fr[C].loc[fr[C].sampleID.isin(picks), PAM] = ["LumB" if v != "LumB" else "LumA" for v in was]
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("label_conflict", C, s) for s in picks})
        self.assertEqual(doc["findings"][0]["affects_analyses"], ["A2"])
        self.assertEqual(self.analysis(doc, "A2")["status"], "changed")
        self.assertEqual(self.analysis(doc, "A1")["status"], "not_rerun")

    def test_relabel_a_column_no_analysis_reads(self):
        fr = synth.copy(self.fr)
        s = fr[C].sampleID[0]
        fr[C].loc[fr[C].sampleID == s, synth.IHC] = "Equivocal"
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("label_conflict", C, s)})
        self.assertEqual((doc["findings"][0]["severity"], doc["verdict"]), ("low", "Ready"))

    def test_survival_edit(self):
        fr = synth.copy(self.fr)
        s = fr[S].index[1]
        fr[S].loc[s, "OS"] = "1"
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("label_conflict", S, s)})
        self.assertEqual(doc["verdict"], "Ready")

    def test_rename(self):
        fr = synth.copy(self.fr)
        old = self.pos[0]
        new = next(s for s in fr[C].sampleID if s[13:15] == "01" and s not in fr[P].columns)
        fr[P] = fr[P].rename(columns={old: new})
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("other", P, old), ("other", P, new)})

    def test_edited_and_blanked_values(self):
        fr = synth.copy(self.fr)
        x, y = self.pos[0], self.pos[1]
        fr[P].loc["ERALPHA", x] = "9.500000"
        fr[P].loc["HER2", y] = ""
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("other", P, x), ("missing_data", P, y)})
        edit = next(f for f in doc["findings"] if f["kind"] == "other")
        blank = next(f for f in doc["findings"] if f["kind"] == "missing_data")
        self.assertEqual((edit["affects_analyses"], blank["affects_analyses"]), (["A1"], []))

    def test_samples_removed_and_added(self):
        fr = synth.copy(self.fr)
        gone = self.pos[:2]
        p = fr[P].drop(columns=gone)
        p["TCGA-ZZ-9999-01"] = [f"{0.1 * i:.6f}" for i in range(len(p))]
        fr[P] = p
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("membership_change", P, s) for s in gone + ["TCGA-ZZ-9999-01"]})

    def test_sample_id_on_two_clinical_rows(self):
        fr = synth.copy(self.fr)
        x, y = self.pos[0], self.pos[1]
        fr[C].loc[fr[C].sampleID == x, "sampleID"] = y
        doc = self.run_tool(self.release(fr))
        self.assertIn(("join_inflation", C, y), cited(doc))
        self.assertIn(("membership_change", C, x), cited(doc))
        self.assertEqual(doc["verdict"], "Blocked")          # A1 needs one ER status per sample id

    def test_column_order_is_not_a_change(self):
        fr = synth.copy(self.fr)
        fr[P] = fr[P][list(fr[P].columns[::-1])]
        doc = self.run_tool(self.release(fr))
        self.assertEqual((doc["findings"], doc["verdict"]), ([], "Ready"))

    def test_only_planted_samples_are_cited(self):
        fr = synth.copy(self.fr)
        x, y = self.pos[0], self.neg[0]
        fr[P] = fr[P].rename(columns={x: y, y: x})[list(fr[P].columns)]
        m1, m2 = list(fr[MU].columns[:2])
        fr[MU] = fr[MU].rename(columns={m1: m2, m2: m1})[list(fr[MU].columns)]
        z = self.pos[5]
        fr[C].loc[fr[C].sampleID == z, ER] = "Negative"
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("sample_swap", P, x), ("sample_swap", P, y), ("sample_swap", MU, m1),
                                      ("sample_swap", MU, m2), ("label_conflict", C, z)})


class MissingAndDamaged(Base):
    def test_no_rna_file_is_a_note_not_a_finding(self):
        import shutil
        shutil.copy(self.a / P, self.a / "rna_hiseq.tsv.gz")      # release A has RNA, the new release doesn't
        doc = self.run_tool(self.release())
        self.assertEqual(doc["findings"], [])
        self.assertTrue(any("rna_hiseq.tsv.gz" in n for n in doc["notes"]))

    def test_missing_protein_file(self):
        doc = self.run_tool(self.release(skip=(P,)))
        self.assertEqual(doc["verdict"], "Insufficient Evidence")
        self.assertEqual([f["kind"] for f in doc["findings"]], ["missing_data"])

    def test_damaged_files_are_refused_not_crashed(self):
        raw = (self.a / P).read_bytes()
        damaged = {"truncated gzip": (P, raw[: len(raw) // 2]), "empty clinical": (C, b""),
                   "commas for tabs": (C, (self.a / C).read_bytes().replace(b"\t", b",")),
                   "not a table": (C, bytes(range(256)) * 4), "header only": (C, b"sampleID\tx\n")}
        for label, (name, content) in damaged.items():
            with self.subTest(label):
                b = self.release()
                (b / name).write_bytes(content)
                doc = self.run_tool(b)
                self.assertEqual(doc["verdict"], "Insufficient Evidence")
                self.assertEqual(cited(doc), set())

    def test_missing_folder(self):
        with self.assertRaises(FileNotFoundError):
            load_release(self.tmp / "nowhere")


class Regressions(Base):
    def test_row_name_on_two_rows(self):
        import pandas as pd
        fr = synth.copy(self.fr)
        fr[P] = pd.concat([fr[P], fr[P].loc[["ERALPHA"]]])
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), set())
        self.assertEqual(doc["verdict"], "Blocked")
        f = doc["findings"][0]
        self.assertEqual((f["kind"], f["severity"], f["affects_analyses"]), ("other", "high", ["A1"]))
        self.assertIn("ERALPHA#2", f["detail"]["rows_added"])

    def test_er_group_with_no_values(self):
        fr = synth.copy(self.fr)
        fr[P] = fr[P].drop(columns=self.neg)
        doc = self.run_tool(self.release(fr))
        self.assertEqual(doc["verdict"], "Blocked")
        self.assertEqual(doc["findings"][0]["severity"], "high")
        self.assertNotIn("nan", json.dumps(doc).lower().replace("tcga", ""))
        a1 = self.analysis(doc, "A1")
        self.assertEqual(a1["status"], "not_rerun")
        self.assertIn("no ER-alpha value for the ER-negative", a1["reason"])

    def test_eralpha_blank_for_everyone(self):
        fr = synth.copy(self.fr)
        fr[P].loc["ERALPHA", :] = ""
        doc = self.run_tool(self.release(fr))
        self.assertEqual(doc["verdict"], "Blocked")
        self.assertEqual(doc["findings"][0]["severity"], "high")

    def test_sample_id_on_two_matrix_columns(self):
        b = self.release()
        x, y = self.pos[0], self.pos[1]
        head, rest = gzip.decompress((b / P).read_bytes()).decode().split("\n", 1)
        cols = head.split("\t")
        cols[cols.index(y)] = x                                # y's column is now headed x
        (b / P).write_bytes(gzip.compress(("\t".join(cols) + "\n" + rest).encode(), mtime=0))
        doc = self.run_tool(b)
        self.assertEqual(cited(doc), {("join_inflation", P, x), ("membership_change", P, y)})
        dup = next(f for f in doc["findings"] if f["kind"] == "join_inflation")
        self.assertIn("more than one column", dup["summary"])
        self.assertEqual(doc["verdict"], "Blocked")
        a1 = self.analysis(doc, "A1")
        self.assertEqual(a1["status"], "not_rerun")
        self.assertIn("more than one column of the protein file", a1["reason"])
        self.assertNotIn("repeated_ids", json.dumps(doc))

    def test_tumor_on_two_clinical_rows_is_not_counted_twice(self):
        fr = synth.copy(self.fr)
        x, y = [s for s in fr[C].sampleID if s[13:15] == "01" and s not in fr[P].columns][:2]
        fr[C].loc[fr[C].sampleID == x, "sampleID"] = y
        doc = self.run_tool(self.release(fr))
        self.assertEqual(cited(doc), {("join_inflation", C, y), ("membership_change", C, x)})
        a2 = self.analysis(doc, "A2")
        self.assertEqual(a2["status"], "not_rerun")
        self.assertIn("more than one clinical row", a2["reason"])
        self.assertIn(y, a2["reason"])
        self.assertEqual(doc["verdict"], "Blocked")
        self.assertIn("no change touches", self.analysis(doc, "A1")["reason"])

    def test_file_by_file_counts(self):
        fr = synth.copy(self.fr)
        x, y, z = self.pos[0], self.neg[0], self.pos[5]
        fr[P] = fr[P].rename(columns={x: y, y: x})[list(fr[P].columns)].drop(columns=[self.pos[6]])
        fr[C].loc[fr[C].sampleID == z, ER] = "Negative"
        b = self.release(fr)
        cmp = compare(load_release(self.a, "release-A"), load_release(b))
        rows = {r["file"]: r for r in file_summary(cmp)}
        self.assertEqual({k: rows[P][k] for k in ("in_release_a", "identical", "changed", "missing", "new")},
                         {"in_release_a": 36, "identical": 33, "changed": 2, "missing": 1, "new": 0})
        self.assertEqual((rows[C]["identical"], rows[C]["changed"], rows[C]["in_release_a"]), (43, 1, 44))
        self.assertEqual((rows[CN]["status"], rows[CN]["identical"], rows[CN]["in_release_a"]), ("identical file", 44, 44))
        for r in rows.values():
            self.assertEqual(r["identical"] + r["changed"] + r["missing"], r["in_release_a"], r["file"])
        report = plain_report(self.run_tool(b), file_summary(cmp))
        self.assertIn("## File by file", report)
        self.assertIn(f"| {P} | 36 | 33 of 36 | 2 | 1 | 0 |", report)

    def test_file_missing_from_the_new_release(self):
        b = self.release(skip=(P,))
        cmp = compare(load_release(self.a, "release-A"), load_release(b))
        row = next(r for r in file_summary(cmp) if r["file"] == P)
        self.assertEqual((row["status"], row["in_release_a"], row["identical"]), ("not in the new release", 36, None))

    def test_finite(self):
        self.assertEqual(finite({"a": float("nan"), "b": [1.5, float("inf"), "x"], "c": (2, None)}),
                         {"a": None, "b": [1.5, None, "x"], "c": [2, None]})


if __name__ == "__main__":
    unittest.main()
