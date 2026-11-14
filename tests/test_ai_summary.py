"""The AI summary's guards: what it sends, and the citation check. No model is called."""
import os
import unittest
from unittest import mock

from tower import ai_summary as ai

READY = {"card": {"title": "ER-alpha protein in ER-positive vs ER-negative primary tumors (A1)"},
         "release": {"name": "practice"}, "verdict": "Conditional",
         "reasons": ["3 release changes touch what this question reads."],
         "next_steps": [{"for": "F1", "step": "Restore the swapped profiles.", "evidence_needed": "The source records."}],
         "cannot_tell": ["Which release labels the swapped samples correctly."], "release_changes": [{"finding": "F1"}]}
FINDINGS = {"findings": [{"id": "F1", "kind": "sample_swap", "severity": "high", "affects_analyses": ["A1"],
                          "summary": "TCGA-A8-A09K-01 and TCGA-B6-A0WX-01 traded places.",
                          "evidence": [{"kind": "sample", "id": "TCGA-A8-A09K-01"},
                                       {"kind": "sample", "id": "TCGA-B6-A0WX-01"}]},
                         {"id": "F2", "kind": "label_conflict", "severity": "low", "affects_analyses": [],
                          "summary": "TCGA-E2-A1L7-01 changed its PR status.",
                          "evidence": [{"kind": "sample", "id": "TCGA-E2-A1L7-01"}]}]}


class AISummaryTest(unittest.TestCase):
    def test_context_holds_only_the_changes_that_touch_the_question(self):
        ctx = ai.context(READY, FINDINGS)
        self.assertEqual(ctx["verdict"], "Conditional")
        rel = ctx["release_changes_that_touch_this_question"]
        self.assertEqual([f["id"] for f in rel], ["F1"])
        self.assertEqual(rel[0]["kind"], "swapped samples")
        self.assertEqual(rel[0]["samples"], ["TCGA-A8-A09K-01", "TCGA-B6-A0WX-01"])
        self.assertEqual(ctx["release_changes_that_do_not_touch_this_question"], 1)

    def test_a_change_that_does_not_touch_the_question_counts_as_unknown(self):
        c = ai.check("Conditional, because of [F2] and TCGA-E2-A1L7-01.", READY, FINDINGS)
        self.assertEqual(c["unknown"], ["F2", "TCGA-E2-A1L7-01"])

    def test_citations_flag_ids_that_are_not_in_the_results(self):
        c = ai.check("Conditional: [F1] swapped TCGA-A8-A09K-01 with TCGA-ZZ-0000-01, see [F7].", READY, FINDINGS)
        self.assertEqual(c["unknown"], ["F7", "TCGA-ZZ-0000-01"])
        self.assertEqual(c["cited"], 4)
        self.assertTrue(c["states_verdict"])

    def test_a_patient_level_id_counts_as_found(self):
        self.assertEqual(ai.check("TCGA-A8-A09K was swapped.", READY, FINDINGS)["unknown"], [])

    def test_summary_strips_thinking_and_checks_it(self):
        with mock.patch.object(ai, "ask", return_value=("<think>notes</think>Conditional. [F1] matters.", "fake")):
            out = ai.summarize(READY, FINDINGS)
        self.assertEqual(out["text"], "Conditional. [F1] matters.")
        self.assertEqual(out["citations"], {"cited": 1, "unknown": []})
        self.assertTrue(out["states_verdict"])

    def test_no_model_gives_a_plain_message(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), mock.patch.object(ai, "OLLAMA", "http://127.0.0.1:9"):
            with self.assertRaises(ai.ModelUnavailable) as e:
                ai.ask("s", "u")
        self.assertIn("ollama serve", str(e.exception))


if __name__ == "__main__":
    unittest.main()
