"""Opens every page of the review screen without a browser (needs release A; skipped otherwise)."""
from __future__ import annotations

import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CHALLENGE = REPO.parent / "oncosys-hackathon-challenge"
RAW = CHALLENGE / "data" / "tcga-brca" / "raw"
PRACTICE = CHALLENGE / "envelopes" / "opened" / "practice" / "release"
PAGES = ("overview", "changed", "evidence", "review", "fool")

try:
    from streamlit.testing.v1 import AppTest
except Exception:           # Streamlit missing or too old
    AppTest = None


@unittest.skipUnless(AppTest is not None and (RAW / "clinical.tsv").exists(),
                     "needs Streamlit, the challenge repo and release A next to this repo")
class Screen(unittest.TestCase):
    def open(self, release: str, question: str, page: str):
        at = AppTest.from_file(str(REPO / "app.py"), default_timeout=300)
        at.run()
        at.sidebar.selectbox[0].set_value(release)
        at.run()
        cards = next(s for s in at.sidebar.selectbox if s.label == "Question card")
        cards.set_value(next(o for o in cards.options if question in o))
        at.session_state["_test_page"] = page
        at.run()
        next(b for b in at.sidebar.button if b.label == "Show results").click()
        at.run()
        return at

    def assert_clean(self, at, what: str):
        self.assertEqual([str(e.value)[:200] for e in at.exception], [], what)
        self.assertEqual([e.value[:200] for e in at.error], [], what)

    def test_empty_start(self):
        at = AppTest.from_file(str(REPO / "app.py"), default_timeout=300)
        at.run()
        self.assert_clean(at, "empty start")
        self.assertTrue(any("Start here" in m.value for m in at.markdown))

    def test_every_page_on_release_a(self):
        for page in PAGES:
            with self.subTest(page=page):
                self.assert_clean(self.open("Release A only (no new release)", "ER-alpha", page), page)

    def test_every_question_on_release_a(self):
        at = AppTest.from_file(str(REPO / "app.py"), default_timeout=300)
        at.run()
        titles = next(s for s in at.sidebar.selectbox if s.label == "Question card").options
        self.assertEqual(len(titles), 8)
        for title in titles:
            with self.subTest(question=title):
                at = self.open("Release A only (no new release)", title, "overview")
                self.assert_clean(at, title)
                self.assertTrue(any("Verdict for this question" in m.value for m in at.markdown))

    @unittest.skipUnless((PRACTICE / "clinical.tsv").exists(), "open the practice envelope first (python -m tower doctor)")
    def test_every_page_on_the_practice_envelope(self):
        for page in PAGES:
            with self.subTest(page=page):
                self.assert_clean(self.open("Envelope practice", "ER-alpha", page), page)

    @unittest.skipUnless((PRACTICE / "clinical.tsv").exists(), "open the practice envelope first (python -m tower doctor)")
    def test_review_and_sign_off(self):
        at = self.open("Envelope practice", "ER-alpha", "review")
        next(t for t in at.text_input if t.label == "Your name").set_value("Test Reviewer").run()
        next(t for t in at.text_input if t.label == "Your role").set_value("research data engineer").run()
        for control in at.button_group:
            control.set_value(str(control.options[0]))
        at.run()
        sign = next(b for b in at.button if b.label == "Sign off")
        self.assertFalse(sign.disabled)
        sign.click()
        at.run()
        self.assert_clean(at, "sign-off")
        self.assertTrue(any("Signed off by Test Reviewer" in s.value for s in at.success))


if __name__ == "__main__":
    unittest.main()
