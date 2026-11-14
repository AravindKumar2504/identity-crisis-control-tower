"""Cohort Control Tower: the review screen.

  streamlit run app.py

Pick a release and a research question; see the verdict, the reasons, what changed and the evidence trail; then
a person decides on every proposed fix and problem and signs off. Research use only.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import re
import subprocess
import sys

import altair as alt
import pandas as pd
import streamlit as st
import yaml

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from tower import ai_summary  # noqa: E402
from tower.analyses import rerun  # noqa: E402
from tower.cards import list_cards, load_card  # noqa: E402
from tower.checks import LOAD_ERRORS  # noqa: E402
from tower.questions import (ENDPOINTS, FEATURES, GROUPINGS, LABELS, SUBTYPES, THERAPIES,  # noqa: E402
                             model_question, protein_question, survival_question, treatment_question)
from tower.diff import compare, file_summary  # noqa: E402
from tower.evidence import before_after  # noqa: E402
from tower.plant import plant, score  # noqa: E402
from tower.findings import build  # noqa: E402
from tower.readiness import assess  # noqa: E402
from tower.release import ROW_FILES, load_release  # noqa: E402
from tower.cli import plain_report  # noqa: E402
from tower.review import (ISSUE_CHOICES, REPAIR_CHOICES, SIGNOFF_CHOICES, missing_decisions, now,  # noqa: E402
                          record_markdown, save as save_review, signed, with_decisions)

st.set_page_config(page_title="Cohort Control Tower", page_icon=":material/cell_tower:", layout="wide")

# ------------------------------------------------------------------------------------------------ look
VERDICT = {  # colour, tint, chip class
    "Ready": ("#0E7C45", "#EAF7F0", "chip-ready"),
    "Conditional": ("#B45309", "#FFF5E3", "chip-cond"),
    "Blocked": ("#B91C1C", "#FDECEC", "chip-block"),
    "Insufficient Evidence": ("#1D4ED8", "#EAF0FD", "chip-unknown"),
}
STATUS = {"pass": ("passed", "chip-ready"), "warn": ("condition", "chip-cond"),
          "block": ("blocks this use", "chip-block"), "unknown": ("can't tell", "chip-unknown")}
SEVERITY = {"high": "chip-block", "medium": "chip-cond", "low": "chip-muted", "none": "chip-muted"}
KIND = {"sample_swap": "Swapped samples", "duplicate": "Copied profiles", "membership_change": "Samples missing or new",
        "label_conflict": "Changed labels", "missing_data": "Values removed", "other": "Unexplained change",
        "join_inflation": "Rows multiplied by a table join", "unlinked_record": "Record with no matching sample"}
A1_DIFF = "ER-alpha protein: ER-positive minus ER-negative"
ACTION = {"restore_from_previous_release": "Restore from release A", "exclude": "Exclude",
          "flag_for_review": "Flag for review", "relabel": "Relabel", "other": "Other"}
A_ONLY = "Release A only (no new release)"
# The sign-off decision starts from what the tool found; a person can change it, with a reason if they overrule it.
DEFAULT_SIGNOFF = {"Ready": "Approve use as stated", "Conditional": "Approve with the conditions listed",
                   "Blocked": "Do not use", "Insufficient Evidence": "Request more evidence"}
# Plain one-sentence meanings for the terms the screen uses (the Overview's glossary and the help tooltips).
GLOSSARY = {
    "TCGA": "The Cancer Genome Atlas, a public research project; this tool checks its breast cancer data.",
    "Release": "One version of the data files. Release A is the reference, and each new release is compared "
               "against it.",
    "Fingerprint": "A short code computed from a sample's data. If the data changes, the code changes, so matching "
                   "codes mean matching data.",
    "Primary tumor": "The tumor where the cancer started (TCGA sample type 01), as opposed to a metastasis or normal "
                     "tissue.",
    "Redacted": "A survival record the data provider flagged in its Redaction column; the tool keeps it but asks a "
                "person to review it before use.",
    "OS": "Overall survival, the time from diagnosis to death from any cause or to the last follow-up.",
    "PFI": "Progression-free interval, the time until the disease is recorded as progressing or returning, or to the "
           "last follow-up.",
    "ER": "Estrogen receptor, a lab result recording whether tumor cells carry this hormone receptor (positive or "
          "negative).",
    "ER-alpha": "The estrogen receptor measured as a protein level, a number rather than positive or negative.",
    "HER2": "A protein on the cell surface, recorded as positive, negative or equivocal from lab tests.",
    "IHC": "Immunohistochemistry, a tissue stain that shows how much of a protein is present. \"Equivocal\" means "
           "unclear.",
    "FISH": "A lab test that counts copies of a gene. Here it settles HER2 results the stain left unclear.",
    "RPPA": "Reverse-phase protein array, the lab method behind the protein data file; it measures the level of many "
            "proteins in each sample.",
    "PAM50": "A method that sorts breast tumors into five subtypes using 50 genes.",
    "Luminal A / Luminal B": "Two of the five PAM50 subtype labels. The others are HER2-enriched, Basal-like and "
                             "Normal-like.",
    "A1": "The protected analysis comparing average ER-alpha protein between ER-positive and ER-negative tumors.",
    "A2": "The protected analysis counting the share of each PAM50 subtype.",
}
VERDICT_HELP = {
    "Ready": "Ready: nothing found that stops this use; the checks that ran passed.",
    "Conditional": "Conditional: usable only after a person reviews the problems or changes listed.",
    "Blocked": "Blocked: the data can't support this use as the question states it.",
    "Insufficient Evidence": "Insufficient Evidence: the tool can't tell yet, for example because a file or a check "
                             "is missing.",
}
# What each built-in question asks, in plain words (hover help on the question board); custom questions use their title.
QUESTION_PLAIN = {
    "er-alpha-by-er": "is the average ER-alpha protein level different between ER-positive and ER-negative tumors?",
    "os-luminal-a": "does overall survival differ between PAM50 subtypes, looking most closely at Luminal A tumors?",
    "pfi-luminal-a": "does the progression-free interval differ between PAM50 subtypes, looking most closely at "
                     "Luminal A tumors?",
    "esr1-expression-vs-er": "how often does ESR1 gene activity (from RNA) agree with the clinical ER test?",
    "her2-positive-protein": "is the HER2 protein level different between HER2-positive and HER2-negative tumors?",
    "subtype-classifier-rna": "can a model learn to predict a tumor's PAM50 subtype from its RNA data?",
    "hormone-therapy-response": "does the ER-alpha protein level go with how tumors responded to hormone therapy?",
    "subtype-mix": "what share of primary tumors falls in each PAM50 subtype?",
}
KPI_HELP = {
    "Changes found": "How many differences the tool found between this release and release A, in any file.",
    "Touch this question": "How many of those changes reach the files, columns or samples this question reads.",
    "Decisions": "How many proposed fixes and problems a reviewer has approved, rejected or asked more about, on the "
                 "Review page.",
    "Sign-off": "Whether a named reviewer has signed off this result, on the Review page.",
}
SECTION_HELP = {
    "verdict": "The tool's answer: is this release fit for the question as it is stated?",
    "board": "The same release judged for every question, to show that the answer depends on what you ask.",
    "next": "The first fixes or checks to do before using the data for this question.",
    "cant": "Limits of this result: things the checks that ran can't see.",
    "more": "The full reasoning, the question's details, and what the terms on this screen mean.",
    "budget": "How many worst-case data errors the answer survives before it changes.",
}
INTRO = ("How to read this page: we compare a new version of the TCGA breast cancer data with the original (release A), "
         "sample by sample. For the research question you pick, the verdict says whether the new data can still answer "
         "it: Ready (fine to use), Conditional (usable after a person checks the flagged items), Blocked (the data can't "
         "support this question) or Insufficient Evidence (the tool can't tell). Below it: what changed, what to do "
         "next, and what the tool can't tell you.")
OUTCOME_HELP = (f"OS: {GLOSSARY['OS']} PFI: {GLOSSARY['PFI']} DSS: disease-specific survival, the time to death from "
                "the cancer itself or to the last follow-up. DFI: disease-free interval, the time until the disease "
                "returns after treatment left no sign of it, or to the last follow-up.")

st.markdown("""
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1320px;}
.ct-head {display:flex; align-items:center; gap:.8rem; flex-wrap:wrap; margin-bottom:.9rem;}
.ct-title {font-size:1.6rem; font-weight:700; letter-spacing:-.01em; color:#132A3A;}
.ct-sub {color:#556676; font-size:.95rem;}
.ct-note {font-size:.82rem; color:#556676;}
.ct-hero {border:1px solid #E2E8EE; border-left:6px solid var(--c); border-radius:8px; padding:18px 22px;
          background:var(--bg); height:100%;}
.ct-eyebrow {font-size:.82rem; font-weight:600; color:#556676;}
.ct-verdict {font-size:2rem; font-weight:700; color:var(--c); line-height:1.15; margin:.15rem 0 .35rem;}
.ct-q {font-weight:600; font-size:1.05rem; color:#132A3A;}
.ct-meta {color:#556676; font-size:.85rem; margin:.25rem 0 .65rem;}
.ct-sum {color:#21384A; font-size:.95rem; line-height:1.55;}
.ct-qcard {font-size:.95rem;}
.ct-qcard .row {margin:0 0 7px; color:#33495A; line-height:1.45;}
.ct-qcard .lab {font-size:.82rem; font-weight:600; color:#556676; display:block;}
.chip {display:inline-block; padding:1px 8px; border-radius:4px; font-size:.76rem; font-weight:600; margin:0 6px 4px 0;
       border:1px solid transparent; white-space:nowrap;}
.chip-ready {background:#E7F6EE; color:#0B6236; border-color:#B7E1C8;}
.chip-cond {background:#FFF3DC; color:#7A4100; border-color:#F2CF96;}
.chip-block {background:#FDE7E7; color:#8F1717; border-color:#F3B3B3;}
.chip-unknown {background:#E7EDFB; color:#1A3580; border-color:#BAC9F1;}
.chip-muted {background:#F1F4F6; color:#43535F; border-color:#E2E8EE;}
.chip-teal {background:#E3F4F1; color:#0B5C55; border-color:#B4DFD8;}
.ct-step {padding:2px 0;}
.ct-step .k {font-size:.82rem; color:#556676; font-weight:600;}
.ct-step .v {font-size:1.6rem; font-weight:600; color:#132A3A; line-height:1.25;}
.ct-step .s {font-size:.82rem; color:#556676;}
.ct-sec {font-size:1.05rem; font-weight:600; color:#132A3A; margin:26px 0 8px;}
.ct-reason {border-left:2px solid #CBD5E1; padding:2px 0 2px 14px; margin:0 0 10px; font-size:.95rem; color:#21384A;}
.ct-next {border-left:2px solid #0F766E; padding:2px 0 2px 14px; margin:0 0 12px; font-size:.95rem; color:#21384A;}
.ct-rule {border-top:1px solid #E2E8EE; margin:14px 0 12px;}
.ct-mono {font-family:'SF Mono', Menlo, Consolas, monospace; font-size:.8rem; color:#33495A;}
.ct-small {font-size:.82rem; color:#556676;}
.ct-cant {border-left:2px solid #CBD5E1; padding:2px 0 2px 14px; margin-top:6px; font-size:.95rem; color:#33495A;}
.ct-cant .it {margin:3px 0;}
.ct-budget {margin-top:14px; border-left:2px solid #0F766E; padding:2px 0 2px 14px; font-size:.95rem; color:#21384A;}
.ct-side {font-size:.82rem; font-weight:600; color:#9FB3C3; margin:16px 0 2px;}
.ct-ctx {margin:-.35rem 0 1.1rem; font-size:.88rem; color:#33495A; line-height:1.9;}
.ct-ctx .sep {color:#94A3B8; margin:0 .5rem;}
.ct-kpis {display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:16px 28px; height:100%; align-content:center;}
.ct-kpis .ct-step {display:flex; flex-direction:column; justify-content:center;}
.ct-step .k {overflow-wrap:normal; word-break:normal;}
@media (max-width: 1100px) {.ct-kpis {grid-template-columns:1fr;}}
.ct-todo {border-left:2px solid #0F766E; padding:2px 0 2px 14px; margin-top:6px; font-size:.95rem; color:#21384A;}
.ct-todo .it {display:flex; gap:10px; align-items:flex-start; margin:5px 0; line-height:1.45;}
.ct-todo .n {flex:none; min-width:1.1em; color:#0F766E; font-weight:600;}
/* A wider sidebar (still dark, from config.toml), so its labels and help fit on one or two lines. */
section[data-testid="stSidebar"][aria-expanded="true"] {width:380px !important; min-width:380px !important;}
[title] {cursor:help;}
.ct-guide {font-size:.95rem; color:#21384A; line-height:1.6; margin:4px 0;}
.ct-intro {font-size:.95rem; color:#21384A; line-height:1.55; margin:0 0 1rem; max-width:1100px;}
</style>
""", unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x))


def plural(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def block():
    """An unboxed block, set off from what comes before it by a hairline (in place of a bordered card)."""
    st.markdown('<div class="ct-rule"></div>', unsafe_allow_html=True)
    return st.container()


def chip(text: str, cls: str, title: str = "") -> str:
    tip = f' title="{esc(title)}"' if title else ""
    return f'<span class="chip {cls}"{tip}>{esc(text)}</span>'


def challenge_repo() -> pathlib.Path | None:
    p = REPO.parent / "oncosys-hackathon-challenge"
    return p if (p / "envelopes" / "unseal.py").exists() else None


CHALLENGE = challenge_repo()
if CHALLENGE is None:
    st.error("Can't find the challenge repo. Clone https://github.com/disleveK/oncosys-hackathon-challenge next to "
             "this repo and run its data/tcga-brca/fetch.py, then reload.")
    st.stop()
RAW = CHALLENGE / "data" / "tcga-brca" / "raw"


def release_options() -> dict[str, str | None]:
    opts: dict[str, str | None] = {A_ONLY: None}
    for p in sorted((CHALLENGE / "envelopes" / "opened").glob("*/release")):
        opts[f"Envelope {p.parent.name}"] = str(p)
    for p in sorted((CHALLENGE / "data" / "tcga-brca" / "releases").glob("*")):
        if p.is_dir():
            opts[f"Test release {p.name}"] = str(p)
    planted = sorted((p for p in (REPO / "out" / "fool").glob("planted-*") if (p / "clinical.tsv").exists()),  # skip broken leftovers
                     key=lambda q: q.stat().st_mtime)[-5:]
    for p in planted:
        opts[f"Planted release {p.name.split('-', 1)[1]}"] = str(p)
    return opts


def membership(cmp) -> list[dict]:
    """Per changed file: how many samples each release holds, and what happened to the ones that changed."""
    rows = []
    for f in cmp.compared_files:
        n_a, n_b = len(cmp.a.table(f).samples()), len(cmp.b.table(f).samples())
        ch = [c for c in cmp.changes if c.file == f]

        def ids(pred):
            return sorted({s for c in ch if pred(c) for s in c.samples})
        rows.append({"file": f, "n_a": n_a, "n_b": n_b, "row_file": f in ROW_FILES,
                     "swapped": ids(lambda c: c.kind == "sample_swap"),
                     "copied": ids(lambda c: c.kind == "duplicate"),
                     "lost": ids(lambda c: c.kind == "membership_change" and c.detail.get("direction") == "lost"),
                     "gained": ids(lambda c: c.kind == "membership_change" and c.detail.get("direction") == "gained"),
                     "relabeled": ids(lambda c: c.kind in ("label_conflict", "missing_data", "other"))})
    return rows


def inputs_sig() -> tuple:
    """Changes whenever a card or the tower code changes, so a cached verdict is never stale."""
    root = pathlib.Path(__file__).resolve().parent
    return tuple((str(p.relative_to(root)), p.stat().st_mtime_ns)
                 for p in sorted([*root.glob("cards/*.yaml"), *root.glob("tower/**/*.py")]))


@st.cache_data(show_spinner=False)     # the caller shows a spinner naming the release and question
def analyze(b_path: str | None, card_id: str, allow_missing: bool, sig: tuple = (), card_json: str = ""):
    card = json.loads(card_json) if card_json else load_card(card_id)   # a question asked on screen has no file
    a = load_release(RAW, "release-A")
    if b_path is None:
        return None, assess(card, a, allow_missing=allow_missing), [], []
    b = load_release(b_path)
    cmp = compare(a, b)
    results, impact = rerun(a, b, cmp.changes)
    findings = build(cmp, results, impact)
    return findings, assess(card, b, cmp, results, allow_missing=allow_missing), membership(cmp), file_summary(cmp)


@st.cache_data(show_spinner="Judging every question on this release...")
def board(b_path: str | None, allow_missing: bool, sig: tuple = (), extra_json: str = "[]") -> list[dict]:
    """Every question card judged on the same release, so the screen can show that the verdict depends on the question."""
    a = load_release(RAW, "release-A")
    rel, cmp, results = a, None, None
    if b_path is not None:
        rel = load_release(b_path)
        cmp = compare(a, rel)
        results, _ = rerun(a, rel, cmp.changes)
    out = []
    for c in list_cards() + json.loads(extra_json):
        try:
            d = assess(c, rel, cmp, results, allow_missing=allow_missing)
            out.append({"id": c["id"], "title": c["title"], "short": c.get("short_title", c["title"]),
                        "verdict": d["verdict"], "reason": d["reasons"][0] if d["reasons"] else "",
                        "pending": len(d.get("pending_checks") or [])})
        except Exception as e:  # one card failing must not hide the others
            out.append({"id": c["id"], "title": c["title"], "short": c.get("short_title", c["title"]),
                        "verdict": "Insufficient Evidence", "reason": f"could not be judged: {e}", "pending": 0})
    return out


@st.cache_data(show_spinner="Running the organizers' reference script...")
def reference_numbers(path: str) -> dict:
    """The organizers' own data/tcga-brca/reference_analyses.py on the same release, for a side-by-side check."""
    script = CHALLENGE / "data" / "tcga-brca" / "reference_analyses.py"
    try:
        r = subprocess.run([sys.executable, str(script), path], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return {"error": (r.stderr or r.stdout).strip()[-300:]}
        return {x["analysis"]: x for x in json.loads(r.stdout)}
    except Exception as e:  # the comparison is a convenience; it must never break the screen
        return {"error": f"{type(e).__name__}: {e}"[:300]}


@st.cache_data(show_spinner="Reading the values behind each finding...")
def before_after_tables(b_path: str | None, sig: tuple = ()) -> dict:
    """Finding id -> what release A and the new release hold for each cited sample (tower/evidence.py)."""
    if b_path is None:
        return {}
    try:
        return before_after(compare(load_release(RAW, "release-A"), load_release(b_path)))
    except Exception:  # the table is extra evidence; it must never break the findings view
        return {}


@st.cache_data
def protein_rows() -> list[str]:
    """Protein rows of release A, the commonly asked ones first (for the ask-your-own-question form)."""
    first = ["ERALPHA", "PR", "HER2", "AR", "GATA3", "BCL2", "EGFR"]
    try:
        rows = load_release(RAW, "release-A").table("protein_rppa.tsv.gz").features()
    except Exception:
        rows = []
    return [r for r in first if r in rows or not rows] + sorted(r for r in rows if r not in first)


def add_question(card: dict) -> None:
    """Add a question built on screen and open it (runs before the rerun, so it may set the card picker)."""
    if card["title"] not in {c["title"] for c in list_cards()}:     # the same question as a card in cards/: open that card
        st.session_state["custom_cards"] = [c for c in st.session_state.get("custom_cards", [])
                                            if c["id"] != card["id"]] + [card]
    st.session_state["card_title"] = card["title"]
    if st.session_state.get("release_label"):            # judging a question is an explicit request to see it
        st.session_state["shown"] = (st.session_state["release_label"], card["title"])


FOOL_FILES = {"protein_rppa.tsv.gz": "protein (RPPA)", "copy_number_gistic.tsv.gz": "copy number",
              "mutation_gene_level.tsv.gz": "gene mutations"}
FOOL_LABELS = {"ER status": ("breast_carcinoma_estrogen_receptor_status", ["Negative", "Positive"]),
               "PR status": ("breast_carcinoma_progesterone_receptor_status", ["Negative", "Positive"]),
               "PAM50 subtype": ("PAM50Call_RNAseq", ["LumB", "LumA", "Basal", "Her2"])}
FOOL_FIELD_NAMES = {"ER status": "ER status (estrogen receptor)", "PR status": "PR status (progesterone receptor)"}


def open_release(label: str) -> None:
    st.session_state["pending_release"] = label
    st.session_state["goto_overview"] = True
    st.session_state["shown"] = (label, st.session_state.get("card_title"))   # an explicit request to see it
    for k in ("card_title", "allow_missing"):     # st.switch_page would reset these sidebar choices; keep them
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]


def pick(title: str) -> None:
    """A question-board click opens that question on the same release, with its results."""
    st.session_state["card_title"] = title
    st.session_state["shown"] = (st.session_state.get("release_label"), title)


def show_results() -> None:
    st.session_state["shown"] = (st.session_state.get("release_label"), st.session_state.get("card_title"))


REVIEW_KEYS = ("|rep|", "|repr|", "|iss|", "|issr|", "|signoff")


def has_decisions() -> bool:
    """Has a reviewer decided anything in this browser session (on any release and question)?"""
    review = st.session_state.get("review", {})
    if any(v.get("repairs") or v.get("issues") or v.get("signed") for v in review.values()):
        return True
    return any(isinstance(k, str) and any(r in k for r in ("|rep|", "|iss|")) and st.session_state[k]
               for k in list(st.session_state.keys()))


def start_fresh() -> None:
    """Back to the empty start: no selections, no results, no review decisions (the reviewer's name stays)."""
    for k in list(st.session_state.keys()):
        if k in ("release_label", "card_title", "shown", "review", "decided_at", "fool", "confirm_fresh",
                 "pending_release", "demo_missing") or (isinstance(k, str) and any(r in k for r in REVIEW_KEYS)):
            del st.session_state[k]


def ask_fresh() -> None:
    if has_decisions():
        st.session_state["confirm_fresh"] = True       # confirm first: decisions would be lost
    else:
        start_fresh()


# ------------------------------------------------------------------------------------------------ sidebar
def keep(dst: str, src: str) -> None:
    """Copy a widget's value to a key that outlives the page it's drawn on (the reviewer's name and role)."""
    st.session_state[dst] = st.session_state[src]


with st.sidebar:
    st.markdown("### Cohort Control Tower")
    st.caption("Team Identity_Crisis · OncoSys Cancer AI Lab")
    st.markdown('<div class="ct-side" title="Which data release the tool checks, and how to open a new one.">Release</div>',
                unsafe_allow_html=True)
    opts = release_options()
    labels = list(opts)
    cards = list_cards() + st.session_state.get("custom_cards", [])
    titles = {c["title"]: c["id"] for c in cards}
    if st.query_params.get("demo") == "1" and not st.session_state.get("demo_done"):
        st.session_state["demo_done"] = True               # once per session, so "Start fresh" still works
        demo_q = next((c["title"] for c in cards if c["id"] == "er-alpha-by-er"), None)
        if "Envelope practice" in labels and demo_q:
            st.session_state.update(release_label="Envelope practice", card_title=demo_q,
                                    shown=("Envelope practice", demo_q))
        else:
            st.session_state["demo_missing"] = True        # shown on the empty start until "Start fresh"
    if st.session_state.get("pending_release") in labels:          # set by the envelope opener or "Fool the Tower"
        st.session_state["release_label"] = st.session_state.pop("pending_release")
    if st.session_state.get("release_label") not in labels:
        st.session_state["release_label"] = None                    # nothing chosen yet: the placeholder shows
    release_label = st.selectbox("New release to check against release A", labels, key="release_label",
                                 placeholder="Choose the new data",
                                 help="Pick which new data release to compare against release A. \"Release A only\" "
                                      "checks the reference data on its own.")
    with st.expander("Open a sealed envelope"):
        st.caption("Unseal a judge's envelope; its release is then added to the picker above.")
        with st.form("envelope"):
            num = st.text_input("Envelope number", placeholder="07 or practice",
                                help="The number the judge gives you, for example 07, or \"practice\" for the "
                                     "practice envelope.")
            words = st.text_input("Four-word code", placeholder="amber falcon river quartz",
                                  help="The four words that unlock the envelope, separated by spaces.")
            if st.form_submit_button("Open it", help="Unseal the envelope with the organizers' script and add its "
                                                     "release to the release picker."):
                r = subprocess.run([sys.executable, "envelopes/unseal.py", num.strip(), *words.split()],
                                   cwd=CHALLENGE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})   # Windows pipes use cp1252
                st.code((r.stdout + r.stderr)[-1500:])
                if r.returncode == 0:
                    name = "practice" if num.strip().lower() == "practice" else f"E{int(num.strip().upper().lstrip('E')):02d}"
                    st.session_state["pending_release"] = f"Envelope {name}"
                    st.rerun()

    st.markdown('<div class="ct-side" title="Which research question the release is judged for.">Research question</div>',
                unsafe_allow_html=True)
    if st.session_state.get("card_title") not in titles:
        st.session_state["card_title"] = None
    card_title = st.selectbox("Question card", list(titles), key="card_title", placeholder="Choose a research question",
                              help="Pick the research question to judge against the chosen release.")
    card = next((c for c in cards if c["title"] == card_title), None)
    with st.expander("Ask your own question"):
        st.caption("Build a question from a few choices; the same rules judge it as the built-in questions.")
        kind = st.selectbox("Kind of question", ["Survival by subtype", "A protein between groups", "A prediction model",
                                                 "Response to a treatment"], key="q_kind",
                            help="Pick the kind of question to build; the choices below change with it.")
        if kind == "Survival by subtype":
            ep = st.selectbox("Outcome", list(ENDPOINTS), format_func=lambda k: ENDPOINTS[k], key="q_ep",
                              help=OUTCOME_HELP)
            focus = st.selectbox("Subtype to focus on", ["", *SUBTYPES], key="q_focus",
                                 format_func=lambda k: SUBTYPES.get(k, "none (all subtypes)"),
                                 help="Optionally pick one PAM50 subtype as the group the question looks at most "
                                      "closely.")
            new = survival_question(ep, focus or None)
        elif kind == "A protein between groups":
            prot = st.selectbox("Protein (from the protein data, RPPA)", protein_rows(), key="q_prot", help=f"RPPA: {GLOSSARY['RPPA']}")
            grp = st.selectbox("Groups to compare", list(GROUPINGS), format_func=lambda k: GROUPINGS[k][0], key="q_grp",
                               help="Pick the lab result that splits tumors into the groups to compare.")
            new = protein_question(prot, grp)
        elif kind == "A prediction model":
            lab = st.selectbox("Label to predict", list(LABELS), format_func=lambda k: LABELS[k], key="q_lab",
                               help="Pick what the model would try to predict for each tumor.")
            feats = st.multiselect("Data the model learns from", list(FEATURES), default=["protein_rppa.tsv.gz"],
                                   format_func=lambda k: FEATURES[k], key="q_feats",
                                   help="Pick the data files the model would learn from.")
            new = model_question(lab, feats)
        else:
            new = treatment_question(st.selectbox("Treatment", list(THERAPIES), key="q_ther",
                                                  help="Pick the treatment whose response the question asks about."))
        st.caption(new["title"])
        st.button("Judge this question", key="q_go", type="primary", on_click=add_question, args=(new,),
                  help="Add this question to the question board and judge it on the chosen release.")
        st.caption("The same rules judge it as the cards in cards/. Nothing is saved unless you download it.")
        if card and card["id"].startswith("custom-"):
            st.download_button("Save the open question as a card", yaml.safe_dump(card, sort_keys=False),
                               f"{card['id']}.yaml", icon=":material/download:",
                               help="Download the open question as a card file; `python -m tower check --card <file>` "
                                    "runs it too.")
    st.button("Show results", key="show_results", type="primary", width="stretch", on_click=show_results,
              disabled=not (release_label and card),
              help="Check the chosen release for the chosen question. Choose both first.")
    with st.expander("Settings"):
        st.caption("How checks that aren't built yet are counted.")
        if "allow_missing" not in st.session_state:     # the default lives here, so the toggle keeps its state by key
            st.session_state["allow_missing"] = True
        allow_missing = st.toggle("List unbuilt checks as pending", key="allow_missing",
                                  help="On: a check that isn't built yet is listed as pending and doesn't decide the "
                                       "verdict. Off: it counts as 'can't tell', the strict reading.")
    if st.session_state.get("confirm_fresh"):
        st.warning("Starting fresh clears the review decisions made in this browser session. Start fresh anyway?")
        f1, f2 = st.columns(2)
        f1.button("Yes, start fresh", key="fresh_yes", type="primary", on_click=start_fresh)
        f2.button("Cancel", key="fresh_no", on_click=lambda: st.session_state.pop("confirm_fresh", None))
    else:
        st.button("Start fresh", key="fresh", width="stretch", on_click=ask_fresh,
                  help="Clear both choices, the results and this session's review decisions, back to the empty start.")
    st.caption("Research use only. No diagnosis, treatment advice, risk score or clinical claim.")
reviewer = st.session_state.get("reviewer", "")          # entered on the Review page, kept across pages
role = st.session_state.get("reviewer_role", "")

# ------------------------------------------------------------------------------------------------ gate
HEAD = ('<div class="ct-head"><span class="ct-title">Cohort Control Tower</span>'
        '<span class="ct-sub">Is a new TCGA breast cancer release still fit for your research question?</span>'
        '<span class="ct-note">Research use only</span></div>')
shown = st.session_state.get("shown")
if not (release_label and card) or tuple(shown or ()) != (release_label, card_title):
    st.markdown(HEAD, unsafe_allow_html=True)
    if shown and release_label and card:            # results were shown, then the selection changed
        st.info(f"Selection changed: click Show results to check {release_label} for "
                f"{card.get('short_title') or card['title']}.")
    else:
        if st.session_state.get("demo_missing"):
            st.info("Open the practice envelope first (python -m tower doctor does this), then reload.")
        st.markdown('<div class="ct-sec">Start here</div>'
                    '<div class="ct-guide">1. Choose the new data in the sidebar, or open a sealed envelope.<br>'
                    '2. Choose a research question.<br>3. Click <b>Show results</b>.</div>'
                    '<div class="ct-sec">What the verdicts mean</div>'
                    + "".join(f'<div class="ct-guide">{chip(v, VERDICT[v][2], VERDICT_HELP[v])} '
                              f'{esc(VERDICT_HELP[v].split(": ", 1)[1])}</div>' for v in VERDICT),
                    unsafe_allow_html=True)
    st.stop()

# ------------------------------------------------------------------------------------------------ analysis
b_path = opts[release_label]
try:
    with st.spinner(f"Checking {release_label} for {card.get('short_title') or card['title']}…"):
        findings, ready, members, files = analyze(b_path, card["id"], allow_missing, inputs_sig(),
                                           json.dumps(card) if card["id"].startswith("custom-") else "")
except Exception as e:  # never show a stack trace to a judge
    st.error(f"The check couldn't run: {e}")
    st.stop()

ctx = f"{release_label}|{card['id']}"
state = st.session_state.setdefault("review", {}).setdefault(ctx, {"repairs": {}, "issues": {}, "signed": None})
first_seen = st.session_state.setdefault("decided_at", {})
dkey, nkey = f"{ctx}|signoff", f"{ctx}|signoff_note"
# Streamlit forgets a widget's value while the widget isn't drawn (on another page, or while another question is
# open), and the browser forgets it too. So every review widget's value for this question is kept here and set
# again on every run: the counts are right on every page, and the Review page always shows what was decided.
kept = state.setdefault("widgets", {})
for k in [k for k in list(st.session_state.keys()) if isinstance(k, str) and k.startswith(ctx + "|")]:
    kept[k] = st.session_state[k]
for k, v in kept.items():
    st.session_state[k] = v
st.session_state.setdefault(dkey, DEFAULT_SIGNOFF[ready["verdict"]])
if LOAD_ERRORS:
    st.sidebar.warning("A check file failed to load, so its checks show as not built: "
                       + "; ".join(f"{k}.py ({v})" for k, v in LOAD_ERRORS.items()))


def collect(kind: str, ids: list[str]) -> dict:
    """Read every decision from the widgets' saved values, so counts are right before the widgets are drawn."""
    out = {}
    for i in ids:
        d = st.session_state.get(f"{ctx}|{kind}|{i}")
        if d:
            stamp = first_seen.setdefault(f"{ctx}|{kind}|{i}|{d}", now())
            out[i] = {"decision": d, "reason": st.session_state.get(f"{ctx}|{kind}r|{i}", "") or "", "time": stamp}
    return out


repairs = findings["repairs"] if findings else []
required_issues = list(dict.fromkeys(i for i in ready["review"]["required"] if not i.startswith("F")))
state["repairs"] = collect("rep", [r["id"] for r in repairs])
state["issues"] = collect("iss", required_issues)
total = len(repairs) + len(required_issues)
decided = len(state["repairs"]) + len(state["issues"])
# A sign-off covers exactly what was decided. If any decision, the verdict or the reviewer changes afterwards, the
# sign-off is withdrawn so the record can never disagree with the screen.
signature = json.dumps({"repairs": {k: [v["decision"], v["reason"]] for k, v in state["repairs"].items()},
                        "issues": {k: [v["decision"], v["reason"]] for k, v in state["issues"].items()},
                        "verdict": ready["verdict"], "decision": st.session_state.get(dkey),
                        "note": st.session_state.get(nkey) or "", "reviewer": reviewer, "role": role}, sort_keys=True)
if state["signed"] and state.get("signed_inputs") != signature:
    state["signed"], state["withdrawn"] = None, True
    state.pop("flash", None)
touching = {t["finding"] for t in ready["release_changes"]}

# ------------------------------------------------------------------------------------------------ header (every page)
colour, tint, vchip = VERDICT[ready["verdict"]]
where = "release A on its own" if b_path is None else f"{release_label} compared with release A"
st.markdown(HEAD, unsafe_allow_html=True)
st.markdown(f'<div class="ct-ctx"><b>Now showing:</b> {esc(where)}, for: {esc(card["title"])}<span class="sep">·</span>'
            f'<b>Verdict:</b> {chip(ready["verdict"], vchip, VERDICT_HELP[ready["verdict"]])}</div>',
            unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------------ overview
def headline() -> str:
    """One sentence a judge can read at a glance; the full reasoning sits one click away."""
    req = ready["review"]["required"]
    problems = [i for i in req if not i.startswith("F")]
    if ready["verdict"] == "Conditional":
        parts = ([plural(len(touching), "release change")] if touching else []) + \
                ([plural(len(problems), "data problem")] if problems else [])
        verb = "touches" if len(touching) + len(problems) == 1 else "touch"
        return f"Usable after a person reviews {' and '.join(parts) or 'the items below'} that {verb} this question."
    if ready["verdict"] == "Ready":
        pending = ready.get("pending_checks") or []
        return "Nothing material found in the checks that ran." + (
            f" {plural(len(pending), 'check')} not built yet." if pending else "")
    return ready["reasons"][0] if ready["reasons"] else ""


def budget_plain(eb: dict) -> str:
    """The error budget in plain words, from the same numbers as tower/budget.py's headline."""
    def name(error: str, n: int) -> str:
        m = re.fullmatch(r"(\w+) tumors relabelled (\w+)", error)
        if m:
            a, b = SUBTYPES.get(m[1], m[1]), SUBTYPES.get(m[2], m[2])
            return f"{a} {'tumor' if n == 1 else 'tumors'} relabelled as {b}"
        one, many = {"swaps between ER groups": ("swap between ER-positive and ER-negative tumors",
                                                 "swaps between ER-positive and ER-negative tumors"),
                     "wrong ER labels": ("wrong ER label", "wrong ER labels"),
                     "copied profiles": ("copied sample", "copied samples")}.get(error, (error, error))
        return one if n == 1 else many

    items = eb["items"]
    if all(it["this_release"] is None for it in items):          # release A on its own: no release to count
        holds = [f"{it['survives']} {name(it['error'], it['survives'])}" for it in items]
        joined = holds[0] if len(holds) == 1 else ", ".join(holds[:-1]) + " or " + holds[-1]
        return f"The answer would still hold with up to {joined}."
    spent = [it for it in items if it["this_release"] and it["survives"]]
    if not spent:
        it = items[0]
        return (f"This release has none of these errors. The answer would still hold with up to {it['survives']} "
                f"{name(it['error'], it['survives'])}.")
    it = max(spent, key=lambda x: x["this_release"] / x["survives"])
    if eb.get("analysis") == "A2":               # A2's count covers every changed subtype label, not only the worst case
        return (f"This release changed {plural(it['this_release'], 'PAM50 subtype label')}. The answer would still "
                f"hold with up to {it['survives']} {name(it['error'], it['survives'])}.")
    return (f"This release has {it['this_release']} {name(it['error'], it['this_release'])}. "
            f"The answer would still hold with up to {it['survives']}.")


def board_help(q: dict) -> str:
    """Hover help for a question-board button: what the question asks, then why it got its verdict."""
    asks = QUESTION_PLAIN.get(q["id"]) or q["title"]
    return f"**{q['short']}:** {asks}\n\n{VERDICT_HELP.get(q['verdict'], q['verdict'])}\n\nWhy: {q['reason']}"


def ai_box() -> None:
    """Optional: a language model puts this result into plain words. The rules made the verdict; every id the model
    cites is checked against the results it was given (tower/ai_summary.py)."""
    key = f"ai|{release_label}|{card['id']}"
    got = st.session_state.get(key)
    with st.expander("AI summary (optional): this result in plain English", expanded=bool(got)):
        st.caption("A language model rewrites this page's results in plain words. It reads the verdict, the reasons, "
                   "the next steps and the release changes that touch this question, never the raw data files, and it "
                   f"never makes the call: the rules above do. It runs on {ai_summary.backend()}.")
        if st.button("Write the summary", key=f"ai_go|{card['id']}", icon=":material/auto_awesome:"):
            with st.spinner("Writing the summary (5 to 20 seconds on the local model)..."):
                try:
                    got = ai_summary.summarize(ready, findings, where)
                except ai_summary.ModelUnavailable as e:
                    got = {"error": str(e)}
                except Exception as e:                       # a model problem must never stop the screen
                    got = {"error": f"The summary failed ({type(e).__name__}). The results above are unaffected."}
            st.session_state[key] = got
        if got and got.get("error"):
            st.info(got["error"])
        elif got:
            st.markdown(got["text"])
            bad, n = got["citations"]["unknown"], got["citations"]["cited"]
            if bad:
                st.warning(f"The model cited {plural(len(bad), 'id')} that this result doesn't contain: "
                           f"{', '.join(bad)}. Don't rely on that part of the summary.")
            else:
                st.caption("Citation check: it cites no finding or sample ids." if not n else
                           "Citation check: the one id it cites is in this result." if n == 1 else
                           f"Citation check: all {n} finding and sample ids it cites are in this result.")
            if not got["states_verdict"]:
                st.caption(f"It doesn't use the verdict's own word ({ready['verdict']}); the verdict above is the tool's.")
            st.caption(f"Written by {got['model']} in {got['seconds']:.0f} s.")


def page_overview() -> None:
    n_changes = len(findings["findings"]) if findings else 0
    signed_by = state["signed"]["review"]["signed_off"]["by"] if state["signed"] else None
    signed_as = state["signed"]["review"]["signed_off"]["decision"] if state["signed"] else None
    st.markdown('<div class="ct-intro">' + esc(INTRO) + '</div>', unsafe_allow_html=True)
    left, right = st.columns([3, 2], gap="medium")
    left.markdown(f"""
<div class="ct-hero" style="--c:{colour}; --bg:{tint}">
  <div class="ct-eyebrow" title="{esc(SECTION_HELP["verdict"])}">Verdict for this question</div>
  <div class="ct-verdict" title="{esc(VERDICT_HELP[ready['verdict']])}">{esc(ready['verdict'])}</div>
  <div class="ct-q">{esc(card['title'])}</div>
  <div class="ct-meta">{esc(where)} · {ready['group_size']} samples studied</div>
  <div class="ct-sum">{esc(headline())}</div>
</div>""", unsafe_allow_html=True)
    kpis = [   # label, value, what it means in one plain line, state
        ("Changes found", f"{n_changes}" if findings else "n/a",
         "things that differ between the new data and release A", "warn" if n_changes else "done"),
        ("Touch this question", f"{len(touching)}" if findings else "n/a",
         "of those, changes in data this question uses", "warn" if touching else "done"),
        ("Decisions", f"{decided} of {total}",
         "flagged items a reviewer has approved, rejected or questioned", "done" if decided == total else "warn"),
        ("Sign-off", "Signed" if signed_by else "Pending",
         f"by {signed_by}: {signed_as}" if signed_by else "whether a named reviewer has approved this result",
         "done" if signed_by else "todo"),
    ]
    right.markdown('<div class="ct-kpis">' + "".join(
        f'<div class="ct-step {s}" title="{esc(KPI_HELP[k])}"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div><div class="s">{esc(sub)}</div></div>'
        for k, v, sub, s in kpis) + "</div>", unsafe_allow_html=True)
    if ready.get("error_budget"):
        st.markdown(f'<div class="ct-budget" title="{esc(SECTION_HELP["budget"])}"><b>Error budget.</b> {esc(budget_plain(ready["error_budget"]))}</div>',
                    unsafe_allow_html=True)

    st.markdown(f'<div class="ct-sec" title="{esc(SECTION_HELP["board"])}">Same release, every question: the verdict depends '
                'on the question</div>',
                unsafe_allow_html=True)
    st.caption("Click a question to open it here. The highlighted one is shown above.")
    qcols = st.columns(4)
    for i, q in enumerate(board(b_path, allow_missing, inputs_sig(), json.dumps(st.session_state.get("custom_cards", [])))):
        with qcols[i % 4]:
            st.button(q["short"], key=f"pick|{q['id']}", on_click=pick, args=(q["title"],),
                      type="primary" if q["id"] == card["id"] else "secondary", help=board_help(q), width="stretch")
            extra = ([f"{plural(q['pending'], 'check')} not built"] if q.get("pending") else []) + \
                    (["shown above"] if q["id"] == card["id"] else [])
            st.markdown(chip(q["verdict"], VERDICT[q["verdict"]][2], VERDICT_HELP[q["verdict"]])
                        + (f'<span class="ct-small">{esc(" · ".join(extra))}</span>' if extra else ""),
                        unsafe_allow_html=True)

    nxt, cant = st.columns(2, gap="medium")
    with nxt:
        st.markdown(f'<div class="ct-sec" title="{esc(SECTION_HELP["next"])}">What to do next</div>', unsafe_allow_html=True)
        if ready["next_steps"]:
            st.markdown('<div class="ct-todo">' + "".join(
                f'<div class="it"><span class="n">{i}</span><span>{esc(s["step"])}</span></div>'
                for i, s in enumerate(ready["next_steps"][:3], 1)) + "</div>", unsafe_allow_html=True)
        else:
            st.caption("Nothing to fix for this question.")
        if any(s["for"][:1] == "F" and s["for"][1:].isdigit() for s in ready["next_steps"][:3]):
            st.caption("F1, F2 and so on are the release changes, numbered as on the What changed page.")
        if len(ready["next_steps"]) > 3:
            st.caption(f"{len(ready['next_steps']) - 3} more, with the evidence that would change each, on the Evidence page.")
    with cant:
        st.markdown(f'<div class="ct-sec" title="{esc(SECTION_HELP["cant"])}">What this can\'t tell you</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="ct-cant">' + "".join(f'<div class="it">• {esc(x)}</div>' for x in ready["cannot_tell"])
                    + "</div>", unsafe_allow_html=True)

    st.markdown(f'<div class="ct-sec" title="{esc(SECTION_HELP["more"])}">More about this result</div>', unsafe_allow_html=True)
    ai_box()
    with st.expander("The full reasoning"):
        st.markdown(ready["summary"])
        for r in ready["reasons"]:
            st.markdown(f"- {r}")
    with st.expander("About this question"):
        st.markdown(f"""
<div class="ct-qcard">
  <div class="row"><span class="lab">Intended use</span>{esc(card['intended_use'])}</div>
  <div class="row"><span class="lab" title="Primary tumor: {esc(GLOSSARY['Primary tumor'])}">Group studied</span>{esc(card['group_studied'])}</div>
  <div class="row"><span class="lab">Outcome</span>{esc(card['outcome'])}</div>
  <div class="row"><span class="lab">Acceptable limitations</span>{esc(card['acceptable_limitations'])}</div>
</div>""", unsafe_allow_html=True)
        if ready.get("group_samples"):
            st.download_button(f"The {len(ready['group_samples'])} samples this question can use (CSV)",
                               "sample_id,patient_id\n" + "".join(f"{s},{s[:12]}\n" for s in ready["group_samples"]),
                               f"{card['id']}-samples.csv", help="The samples in this release that can answer the "
                               "question, after the question's own filters: which samples the verdict is about.",
                               icon=":material/download:")
    with st.expander("What these terms mean"):
        st.markdown("\n".join(f"- **{term}:** {meaning}" for term, meaning in GLOSSARY.items()))


# ------------------------------------------------------------------------------------------------ why
def render_checks() -> None:
    st.markdown('<div class="ct-sec">Reasons</div>', unsafe_allow_html=True)
    for r in ready["reasons"]:
        st.markdown(f'<div class="ct-reason">{esc(r)}</div>', unsafe_allow_html=True)
    if ready["next_steps"]:
        st.markdown('<div class="ct-sec">Next steps</div>', unsafe_allow_html=True)
        for s in ready["next_steps"]:
            st.markdown(f'<div class="ct-next"><b>{esc(s["step"])}</b><br><span class="ct-small">Evidence that would '
                        f'change the verdict: {esc(s["evidence_needed"])}</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="ct-sec">Every check run for this question</div>', unsafe_allow_html=True)
    for x in ready["issues"]:
        label, cls = STATUS[x["status"]]
        if not x["material"]:
            label, cls = ("not built yet" if (x.get("numbers") or {}).get("pending")
                          else "can't tell" if x["status"] == "unknown" else "not material here"), "chip-muted"
        with block():
            st.markdown(chip(label, cls) + (chip("already in release A", "chip-muted") if x["pre_existing"] and x["material"] else "")
                        + f'<b>{esc(x["title"])}</b> &nbsp;<span class="ct-mono">{esc(x["id"])}</span>',
                        unsafe_allow_html=True)
            if x["material"] and x["status"] != "pass":
                with st.expander("Rule, source and evidence"):
                    st.markdown(f"**Decision rule:** {x['rule']}")
                    st.markdown(f"**Source:** {x['source']}")
                    st.markdown(f"**What this check can't see:** {x['limitation']}")
                    if x["numbers"]:
                        st.json(x["numbers"], expanded=False)
                    if x["row_count"]:
                        st.markdown(f"**Samples involved:** {x['row_count']}"
                                    + (f" (the first {len(x['rows'])} are listed)" if len(x["rows"]) < x["row_count"] else ""))
                        st.markdown(f'<div class="ct-mono">{esc(", ".join(x["rows"]))}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------------ what changed
def page_changed() -> None:
    if not findings:
        st.info("Pick a new release in the sidebar to see what changed against release A.")
    else:
        rv = VERDICT[findings["verdict"]]
        with block():
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown('<div class="ct-eyebrow">Release check</div>' + chip(findings["verdict"], rv[2], VERDICT_HELP[findings["verdict"]])
                        + f'<span class="ct-small">{esc(findings["verdict_reason"])}</span>', unsafe_allow_html=True)
            for n in findings.get("notes", []):
                c1.caption(n)
            c2.download_button("Release notes", plain_report(findings, files), "release_notes.md", width="stretch", icon=":material/download:",
                               help="Every finding in plain English, as Markdown.")
        if files:
            st.markdown('<div class="ct-sec">File by file: identical, changed, missing and new samples</div>',
                        unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{
                "File": r["file"], "Samples in release A": r["in_release_a"],
                "Identical": "" if r["identical"] is None else f"{r['identical']} of {r['in_release_a']}",
                "Changed": r["changed"], "Missing": r["missing"], "New": r["new"],
                "Note": "; ".join(x for x in (r["status"] if r["status"] != "compared" else "", r["structure"]) if x)}
                for r in files]), hide_index=True, width="stretch")
            st.caption("Identical means the sample holds the same values in both releases (same fingerprint). These "
                       "are counts per file, not a score, and they don't show that a sample's files belong to the "
                       "same patient.")
        if members:
            st.markdown('<div class="ct-sec">Same count, different members</div>', unsafe_allow_html=True)
            for m in members:
                changed = sorted(set(m["swapped"]) | set(m["copied"]) | set(m["lost"]) | set(m["gained"]) | set(m["relabeled"]))
                with block():
                    st.markdown(f'<span class="ct-mono"><b>{esc(m["file"])}</b></span>', unsafe_allow_html=True)
                    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
                    c1.metric("Release A", m["n_a"], help="Samples in this file in release A")
                    c2.metric("New release", m["n_b"], delta=(m["n_b"] - m["n_a"]) or None,
                              help="Samples in this file in the new release")
                    c3.metric("Changed samples", len(changed))
                    rows = [{"what": w, "n": len(m[k])} for k, w in [("swapped", "swapped"), ("copied", "copied in"),
                                                                     ("lost", "removed"), ("gained", "new"),
                                                                     ("relabeled", "relabelled or edited")] if m[k]]
                    if rows:
                        c4.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadius=2, color="#0F766E").encode(
                            x=alt.X("n:Q", title="samples", axis=alt.Axis(tickMinStep=1)),
                            y=alt.Y("what:N", title=None, sort="-x"),
                            tooltip=["what", "n"]).properties(height=46 * len(rows) + 40))
                    if m["n_a"] == m["n_b"] and changed:
                        st.caption("The total count is identical, so a count check would say nothing changed. "
                                   "Fingerprinting every sample is what catches it.")
        st.markdown('<div class="ct-sec">Every change, with every sample</div>', unsafe_allow_html=True)
        ba_tables = before_after_tables(b_path, inputs_sig())
        for f in findings["findings"]:
            samples = [e for e in f["evidence"] if e["kind"] == "sample"]
            with block():
                head = (f'<b>{esc(f["id"])} · {esc(KIND.get(f["kind"], f["kind"]))}</b> &nbsp;'
                        + chip(f"severity {f['severity']}", SEVERITY.get(f["severity"], "chip-muted"))
                        + chip(f"confidence {f['confidence']}", "chip-muted")
                        + chip(plural(len(samples), "sample"), "chip-muted")
                        + "".join(chip(f"affects {a}", "chip-teal") for a in f["affects_analyses"])
                        + (chip("touches this question", "chip-cond") if f["id"] in touching else "")
                        + "".join(chip(f"own effect on {aid}: {v['change']:+} ({v['relative_pct']}%)" if aid == "A1"
                                       else f"own effect on {aid}: {v['change']} points", "chip-muted")
                                  for aid, v in (f.get("effect") or {}).items()))
                st.markdown(head, unsafe_allow_html=True)
                what, _, why = f["summary"].partition(" Why it matters: ")
                st.markdown(what)
                if why:
                    st.markdown(f"**Why it matters:** {why}")
                st.caption(f"Limitation: {f['limitation']}")
                with st.expander(f"Evidence: {plural(len(f['evidence']), 'pointer')}"):
                    st.dataframe(pd.DataFrame([{"Sample": e["id"], "Release": e.get("release"), "File": e.get("file"),
                                                "Note": e.get("note")} for e in f["evidence"]]),
                                 hide_index=True, width="stretch")
                rows_ba = ba_tables.get(f["id"])
                if rows_ba:
                    with st.expander("Before and after, sample by sample"):
                        st.dataframe(pd.DataFrame(rows_ba), hide_index=True, width="stretch")
                        if "Now holds release A's data of" in rows_ba[0]:
                            st.caption("A fingerprint covers everything a sample holds in this file. When a sample's "
                                       "fingerprint in the new release equals another sample's fingerprint in release "
                                       "A, it now holds that sample's data.")
                for r in [r for r in repairs if f["id"] in r["addresses"]]:
                    st.markdown(f"Proposed fix **{r['id']}** · {ACTION.get(r['action'], r['action'])}: {r['justification']}")

# ------------------------------------------------------------------------------------------------ analyses
def a1_chart(before: dict, after: dict | None):
    rows = [{"ER status": "ER-positive", "release": "Release A", "mean": before["mean_positive"]},
            {"ER status": "ER-negative", "release": "Release A", "mean": before["mean_negative"]}]
    if after:
        rows += [{"ER status": "ER-positive", "release": "New release", "mean": after["mean_positive"]},
                 {"ER status": "ER-negative", "release": "New release", "mean": after["mean_negative"]}]
    return (alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadius=3).encode(
        x=alt.X("release:N", title=None, sort=["Release A", "New release"]), y=alt.Y("mean:Q", title="Average ER-alpha protein level (RPPA)"),
        color=alt.Color("release:N", legend=None), column=alt.Column("ER status:N", title=None),
        tooltip=["ER status", "release", "mean"]).properties(width=140, height=220))


def a2_chart(before: dict, after: dict | None):
    rows = [{"subtype": k, "release": "Release A", "percent": v} for k, v in before["percent"].items()]
    if after:
        rows += [{"subtype": k, "release": "New release", "percent": v} for k, v in after["percent"].items()]
    # a y title longer than the chart height leaves no room for the bars
    return (alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadius=3).encode(
        x=alt.X("subtype:N", title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("percent:Q", title="% of tumors"),
        xOffset="release:N", color=alt.Color("release:N", legend=alt.Legend(title=None, orient="bottom")),
        tooltip=["subtype", "release", "percent"]).properties(height=260))


def render_analyses() -> None:
    items = []
    if findings:
        items = [(a["id"], a["title"], a["status"], a.get("reason", ""), a.get("before") or {}, a.get("after"))
                 for a in findings["analyses"]]
    else:
        items = [(aid, aid, a["status"], "run on release A", a.get("result") or {}, None)
                 for aid, a in ready["analyses"].items()]
    rob = ready.get("robustness") or {}
    if rob:
        lab, cls = {"holds": ("The conclusion holds", "chip-ready"), "fragile": ("The conclusion is fragile", "chip-cond"),
                    "reversed": ("The conclusion reverses", "chip-block")}[rob["status"]]
        with block():
            st.markdown('<div class="ct-eyebrow">Does the conclusion still hold?</div>' + chip(lab, cls)
                        + f'<span class="ct-small">{esc(rob["claim"])}</span>', unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric(A1_DIFF, rob["difference"], help=f"A1: {GLOSSARY['A1']} ER-alpha: {GLOSSARY['ER-alpha']}",
                      delta=round(rob["difference"] - rob["release_a_difference"], 3) if rob.get("release_a_difference") is not None else None)
            k2.metric("95% range (1,000 resamples)", f"{rob['range_95'][0]} to {rob['range_95'][1]}")
            if rob.get("release_a_difference") is not None:
                k3.metric("Release A", rob["release_a_difference"])
                if rob["flagged_samples"]:
                    k4.metric(f"Without the {rob['flagged_samples']} flagged samples", rob["difference_without_flagged"])
            loo = next(((x.get("numbers") or {}).get("leave_one_site_out") for x in ready["issues"]
                        if x["id"] == "site_shift" and (x.get("numbers") or {}).get("leave_one_site_out")), None)
            if loo:
                st.caption(f"With each of the {len(loo['sites'])} largest hospitals left out in turn, the difference is "
                           f"{loo['lowest']} to {loo['highest']}"
                           + ("; it holds every time." if loo["holds_everywhere"] else
                              "; it doesn't hold every time (see site_shift under Checks and reasons)."))
            how = rob.get("range_method") or {}
            st.caption("Holds if the difference stays positive and its 95% range stays above zero. The range covers "
                       "sampling variation only, not systematic errors such as a mislabelled ER test."
                       + (f" Method: {how['method']}; {how['resamples']:,} resamples, seed {how['seed']}." if how else ""))
    eb = ready.get("error_budget") or {}
    if eb:
        with block():
            st.markdown('<div class="ct-eyebrow">Error budget: how wrong can the data be before the answer changes?</div>'
                        + f'<span class="ct-small">{esc(eb["conclusion"])}</span>', unsafe_allow_html=True)
            cols = st.columns(len(eb["items"]))
            for col, it in zip(cols, eb["items"]):
                col.metric(f"Worst-case {it['error']} it survives", it["survives"],
                           delta=None if it["this_release"] is None else f"this release: {it['this_release']}",
                           delta_color="off")
            st.markdown(f"**{budget_plain(eb)}**")
            st.caption(eb["method"])
    if items:
        ref = reference_numbers(b_path or str(RAW))
        with block():
            st.markdown('<div class="ct-eyebrow">Check it yourself: the organizers\' own script on the same release</div>',
                        unsafe_allow_html=True)
            if "error" in ref:
                st.caption(f"The organizers' reference script couldn't run here: {ref['error']}")
            else:
                rows = []
                for aid, _title, _status, _reason, before, after in items:
                    ours, theirs = (after or before or {}), ref.get(aid, {})
                    if aid == "A1":
                        pairs = [(A1_DIFF, ours.get("difference"), theirs.get("difference")),
                                 ("Samples", ours.get("n_samples"), theirs.get("n_samples"))]
                    else:
                        pairs = [("Samples", ours.get("n_samples"), theirs.get("n_samples")),
                                 ("Subtype counts", ", ".join(f"{k} {v}" for k, v in sorted((ours.get("counts") or {}).items())),
                                  ", ".join(f"{k} {v}" for k, v in sorted((theirs.get("counts") or {}).items())))]
                    rows += [{"Analysis": aid, "Number": n, "Match": "same" if o == r else "different",
                              "This tool": str(o), "Organizers' script": str(r)} for n, o, r in pairs]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                target = pathlib.Path(b_path) if b_path else RAW
                try:
                    arg = str(target.resolve().relative_to(CHALLENGE.resolve()))
                except ValueError:
                    arg = str(target)
                st.code(f"python data/tcga-brca/reference_analyses.py {arg}", language="bash")
                st.caption("Run this from the challenge repo to reproduce these numbers without our tool. For an analysis "
                           "this tool left alone, its number for the new release is release A's, and the script confirms it.")
    if not items:
        st.info("This question depends on no protected analysis.")
    for aid, title, status, reason, before, after in items:
        with block():
            cls = {"changed": "chip-cond", "unchanged": "chip-ready", "not_rerun": "chip-muted", "run": "chip-teal"}.get(status, "chip-muted")
            st.markdown(f"<b>{esc(aid)} · {esc(title)}</b> &nbsp;" + chip(status.replace("_", " "), cls), unsafe_allow_html=True)
            st.caption(reason)
            if aid == "A1" and before.get("mean_positive") is not None:
                c1, c2 = st.columns([1, 2])
                c1.metric(A1_DIFF, after["difference"] if after else before["difference"],
                          help=f"A1: {GLOSSARY['A1']} ER-alpha: {GLOSSARY['ER-alpha']}",
                          delta=round(after["difference"] - before["difference"], 3) if after else None)
                c1.metric("Samples", after["n_samples"] if after else before["n_samples"],
                          delta=(after["n_samples"] - before["n_samples"]) if after else None)
                c2.altair_chart(a1_chart(before, after))
            elif aid == "A2" and before.get("percent"):
                st.altair_chart(a2_chart(before, after))
                st.caption("Each bar is a share of the primary tumors that have a subtype call. "
                           f"A2: {GLOSSARY['A2']} PAM50: {GLOSSARY['PAM50']}")
            if findings:
                a = next(x for x in findings["analyses"] if x["id"] == aid)
                if a.get("samples_entered") or a.get("samples_left"):
                    st.caption(f"Entered: {', '.join(a.get('samples_entered', [])) or 'none'} · "
                               f"Left: {', '.join(a.get('samples_left', [])) or 'none'}")

# ------------------------------------------------------------------------------------------------ evidence trail
def blast_radius() -> str:
    """Each change, the file it hit, the analysis that reads it, and this question."""
    vcol = VERDICT[ready["verdict"]][0]
    q = card["title"] if len(card["title"]) < 48 else card["title"][:45] + "..."
    g = ['digraph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.6;',
         'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="#CBD5DF", fillcolor="#FFFFFF", fontcolor="#132A3A"];',
         'edge [color="#9AA9B6", arrowsize=0.6];',
         f'Q [label="{q}\\n{ready["verdict"]}", color="{vcol}", penwidth=2, fillcolor="#FFFFFF"];']
    uses = card.get("uses") or {}
    files = set()
    if findings:
        for f in findings["findings"]:
            sev = {"high": "#FDE7E7", "medium": "#FFF3DC"}.get(f["severity"], "#F1F4F6")
            n = sum(1 for e in f["evidence"] if e["kind"] == "sample")
            g.append(f'{f["id"]} [label="{f["id"]} {KIND.get(f["kind"], f["kind"])}\\n{plural(n, "sample")}", fillcolor="{sev}"];')
            file = next((e.get("file") for e in f["evidence"] if e.get("file")), None)
            if file:
                files.add(file)
                g.append(f'{f["id"]} -> "{file}";')
            for a in f["affects_analyses"] if file else []:
                g.append(f'"{file}" -> {a} [color="#B45309"];')
            if f["id"] in touching:
                g.append(f'{f["id"]} -> Q [color="#B45309", penwidth=1.6];')
        related = set(card.get("analyses") or []) | {x for f in findings["findings"] for x in f["affects_analyses"]}
        for a in [a for a in findings["analyses"] if a["id"] in related]:
            col = {"changed": "#FFF3DC", "unchanged": "#E7F6EE"}.get(a["status"], "#F1F4F6")
            g.append(f'{a["id"]} [label="{a["id"]}\\n{a["status"].replace("_", " ")}", fillcolor="{col}", shape=box];')
            if a["id"] in (card.get("analyses") or []):
                g.append(f'{a["id"]} -> Q;')
    for f in files:
        g.append(f'"{f}" [fillcolor="#F3F6F8", fontname="Courier"];')
    for x in ready["issues"]:
        if x["material"] and x["status"] != "pass":
            col = {"block": "#FDE7E7", "warn": "#FFF3DC", "unknown": "#E7EDFB"}[x["status"]]
            label = x["id"].replace('"', "'")
            g.append(f'"{label}" [label="{label}\\n{STATUS[x["status"]][0]}", fillcolor="{col}"];')
            g.append(f'"{label}" -> Q [color="{VERDICT[ready["verdict"]][0]}"];')
    if len(g) == 5:
        g.append('ok [label="nothing material touches this question", fillcolor="#E7F6EE"]; ok -> Q;')
    for file in uses:
        if file not in files:
            g.append(f'"{file}" [fillcolor="#F3F6F8", fontname="Courier"]; "{file}" -> Q [style=dashed];')
    g.append("}")
    return "\n".join(g)


def render_trail() -> None:
    st.markdown('<div class="ct-sec">How each change reaches this question (change → file → analysis → question)</div>', unsafe_allow_html=True)
    st.graphviz_chart(blast_radius())
    st.markdown('<div class="ct-sec">Every conclusion and what it rests on</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{"Conclusion": e["conclusion"], "Status": e["status"], "Rule": e["rule"],
                                "Source": e["source"], "Fields": ", ".join(e["fields"]), "Samples": e["row_count"],
                                "File fingerprints": "; ".join(f"{k}: {(v or '')[:12]}" for k, v in e["files"].items())}
                               for e in ready["lineage"]]), hide_index=True, width="stretch",
                 column_config={"File fingerprints": st.column_config.TextColumn(
                     "File fingerprints", help=f"Fingerprint: {GLOSSARY['Fingerprint']}")})
    st.caption("Fields this question reads: " + ", ".join(ready["fields_read"]))

# ------------------------------------------------------------------------------------------------ review
def page_review() -> None:
    st.markdown('<div class="ct-sec">Reviewer</div>', unsafe_allow_html=True)
    r1, r2 = st.columns(2)
    r1.text_input("Your name", value=reviewer, key="_reviewer_in", on_change=keep, args=("reviewer", "_reviewer_in"))
    r2.text_input("Your role", value=role, key="_role_in", placeholder="e.g. research data engineer",
                  on_change=keep, args=("reviewer_role", "_role_in"))
    if not (reviewer and role):
        st.warning("Enter your name and role above to review.")
    if state.pop("withdrawn", False):
        st.warning("Something changed after the sign-off (a decision, the verdict or the reviewer), so the sign-off "
                   "was withdrawn. Check the decisions and sign off again.")
    st.progress(decided / total if total else 1.0, text=f"{decided} of {total} decisions made")
    st.markdown('<div class="ct-sec">Proposed fixes for the release changes</div>', unsafe_allow_html=True)
    if not repairs:
        st.caption("No release changes, so nothing to fix.")
    for r in repairs:
        with block():
            st.markdown(f"<b>{esc(r['id'])} · {esc(ACTION.get(r['action'], r['action']))}</b> &nbsp;"
                        + chip(f"for {', '.join(r['addresses'])}", "chip-muted")
                        + chip(plural(len(r["targets"]), "target"), "chip-muted"), unsafe_allow_html=True)
            st.markdown(r["justification"])
            row = st.container(horizontal=True, vertical_alignment="bottom")     # side by side; wraps when narrow
            row.segmented_control(f"Decision for {r['id']}", REPAIR_CHOICES, key=f"{ctx}|rep|{r['id']}",
                                 disabled=not (reviewer and role),
                                 format_func=lambda o: {"approve": "approve", "reject": "reject",
                                                        "request_more_evidence": "ask for more"}[o])
            row.text_input(f"Reason for {r['id']}", key=f"{ctx}|repr|{r['id']}", disabled=not (reviewer and role),
                          placeholder="Why (needed to reject or ask for more)")

    st.markdown('<div class="ct-sec">Problems for this question</div>', unsafe_allow_html=True)
    if not required_issues:
        st.caption("No problems need a decision for this question.")
    by_id: dict[str, list] = {}
    for x in ready["issues"]:
        by_id.setdefault(x["id"], []).append(x)      # a check may return several problems under one id
    for iid in required_issues:
        xs = by_id.get(iid) or [{"status": "unknown", "title": iid}]
        x = xs[0]
        with block():
            st.markdown(chip(STATUS[x["status"]][0], STATUS[x["status"]][1]) + f"<b>{esc(iid)}</b>", unsafe_allow_html=True)
            for y in xs:
                st.markdown(y["title"])
            row = st.container(horizontal=True, vertical_alignment="bottom")
            row.segmented_control(f"Do you agree? ({iid})", ISSUE_CHOICES, key=f"{ctx}|iss|{iid}",
                                 disabled=not (reviewer and role))
            row.text_input(f"Reason for {iid}", key=f"{ctx}|issr|{iid}", disabled=not (reviewer and role),
                          placeholder="Why (needed to disagree or ask for more)")

    st.markdown('<div class="ct-sec">Sign-off</div>', unsafe_allow_html=True)
    missing = missing_decisions(findings, ready, state["repairs"], state["issues"])
    unexplained = [k for k, d in {**state["repairs"], **state["issues"]}.items()
                   if d["decision"] in ("reject", "request_more_evidence", "disagree", "need more evidence") and not d["reason"]]
    with block():
        counts = pd.Series([d["decision"] for d in {**state["repairs"], **state["issues"]}.values()]).value_counts()
        if len(counts):
            st.markdown("".join(chip(f"{v} {k.replace('_', ' ')}", "chip-muted") for k, v in counts.items()),
                        unsafe_allow_html=True)
        if missing:
            st.info(f"Decide these first: {', '.join(missing)}")
        if unexplained:
            st.info(f"Give a reason for: {', '.join(unexplained)}")
        c1, c2 = st.columns([2, 3])
        decision = c1.selectbox("Your decision for this question", SIGNOFF_CHOICES, key=dkey)
        note = c2.text_input("Note (conditions, what you need next)", key=nkey)
        overrules = ready["verdict"] in ("Blocked", "Insufficient Evidence") and decision.startswith("Approve")
        if overrules:
            st.warning(f"The tool says {ready['verdict']}. Approving overrules it, so the note must say why.")
        can_sign = (bool(reviewer and role) and not missing and not unexplained
                    and not (overrules and not (note or "").strip()))
        if st.button("Sign off", type="primary", disabled=not can_sign):
            signed_doc = signed(ready, findings, state["repairs"], state["issues"], reviewer, role, decision, note)
            reviewed = with_decisions(findings, state["repairs"], reviewer, role) if findings else None
            slug = re.sub(r"[^A-Za-z0-9]+", "-", release_label).strip("-").lower()
            out = REPO / "out" / "reviews" / f"{card['id']}-{slug}-{now().replace(':', '')}"
            try:
                check = save_review(out, signed_doc, reviewed, reviewed, CHALLENGE / "format" / "validate.py")
            except Exception as e:
                st.error(f"Not signed off: {e}")
            else:
                state["signed"], state["signed_inputs"] = signed_doc, signature
                state["flash"] = (f"Signed off by {reviewer} ({role}): {decision}. Saved in {out.relative_to(REPO)}", check)
                st.rerun()                           # redraw so the header and the Overview show the sign-off
    if state["signed"]:
        sd = state["signed"]
        msg, check = state.get("flash", ("Signed off.", ""))
        st.success(msg)
        if check:
            st.caption(check)
        d1, d2, d3 = st.columns(3)
        d1.download_button("Review record (Markdown)", record_markdown(sd, findings), "review_record.md",
                           icon=":material/download:")
        d2.download_button("readiness.json with sign-off", json.dumps(sd, indent=2, default=str),
                           "readiness.signed.json", icon=":material/download:")
        if findings:
            d3.download_button("findings.json with decisions",
                               json.dumps(with_decisions(findings, state["repairs"], reviewer, role), indent=2),
                               "findings.reviewed.json", icon=":material/download:")


# ------------------------------------------------------------------------------------------------ fool the tower
def page_fool() -> None:
    st.markdown('<div class="ct-sec">Fool the Tower: plant your own errors</div>', unsafe_allow_html=True)
    st.caption("Pick some errors. The organizers' own generator (data/tcga-brca/make_release.py) builds a release with "
               "exactly those changes and writes its answer key. The tool then looks for them without the key, and the "
               "score compares the two. It only writes under out/fool/.")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("**Swap samples' data**")
        n_swap = st.number_input("Pairs to swap", 0, 5, 1, key="fool_swaps")
        swap_file = st.selectbox("In", list(FOOL_FILES), format_func=FOOL_FILES.get, key="fool_swap_file")
        opposite = st.checkbox("Across ER-positive and ER-negative tumors (the hardest case for analysis A1)", True, key="fool_opposite")
    with f2:
        st.markdown("**Copy profiles over samples**")
        n_copy = st.number_input("Copies", 0, 10, 2, key="fool_copies")
        copy_file = st.selectbox("In ", list(FOOL_FILES), format_func=FOOL_FILES.get, key="fool_copy_file")
        subtype = st.selectbox("Replacing tumors of subtype", ["Her2", "Basal", "LumA", "LumB"], key="fool_subtype",
                               format_func=lambda k: f"{SUBTYPES.get(k, k)} ({k})")
    with f3:
        st.markdown("**Change clinical labels**")
        n_rel = st.number_input("Labels to change", 0, 10, 3, key="fool_relabels")
        field = st.selectbox("Field", list(FOOL_LABELS), key="fool_field",
                             format_func=lambda k: FOOL_FIELD_NAMES.get(k, k))
        new_value = st.selectbox("Set to", FOOL_LABELS[field][1], key="fool_value",
                                 format_func=lambda v: f"{SUBTYPES[v]} ({v})" if v in SUBTYPES else v)
    if st.button("Plant these errors and let the tool look", type="primary", key="fool_go"):
        planted = []
        if n_swap:
            planted.append({"type": "swap_samples", "file": swap_file, "count": int(n_swap), "opposite_er": bool(opposite)})
        if n_copy:
            planted.append({"type": "replace_with_duplicates", "file": copy_file, "count": int(n_copy), "subtype": subtype})
        if n_rel:
            planted.append({"type": "relabel_clinical", "file": "clinical.tsv", "column": FOOL_LABELS[field][0],
                            "new_value": new_value, "count": int(n_rel)})
        if not planted:
            st.warning("Pick at least one error to plant.")
        else:
            try:
                with st.spinner("The organizers' generator is building your release, then the tool looks for the errors..."):
                    rel, answer = plant(CHALLENGE, planted)
                    st.session_state["fool"] = {"label": f"Planted release {rel.name.split('-', 1)[1]}",
                                                **score(CHALLENGE, rel, answer)}
            except Exception as e:  # e.g. more copies than the subtype has samples in that file
                st.session_state.pop("fool", None)          # don't leave the last run's score under this error
                st.error(f"The generator couldn't plant that combination ({type(e).__name__}: {e}). Try fewer errors.")
    res = st.session_state.get("fool")
    if res:
        caught = not res["missed"] and not res["false_alarms"]
        st.markdown(chip("Not fooled" if caught else "Partly fooled", "chip-ready" if caught else "chip-cond")
                    + f"<b>The tool found {res['found']} of the {res['planted_samples']} planted samples, with "
                    f"{plural(len(res['false_alarms']), 'false alarm')}.</b>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(res["rows"]), hide_index=True, width="stretch")
        if res["missed"] or res["false_alarms"]:
            st.caption(f"Missed: {res['missed'][:5]}. False alarms: {res['false_alarms'][:5]}.")
        st.caption(f"Release check: {res['verdict']}. {res['verdict_reason']}")
        st.button(f"Open {res['label'].lower()} on the Overview", key="fool_open", on_click=open_release,
                  args=(res["label"],))


# ------------------------------------------------------------------------------------------------ evidence + pages
def page_evidence() -> None:
    checks, analyses, trail = st.tabs([":material/checklist: Checks and reasons", ":material/bar_chart: Analyses",
                                       ":material/account_tree: Evidence trail"])
    with checks:
        render_checks()
    with analyses:
        render_analyses()
    with trail:
        render_trail()


PAGES = {"overview": page_overview, "changed": page_changed, "evidence": page_evidence, "review": page_review,
         "fool": page_fool}
overview = st.Page(page_overview, title="Overview", icon=":material/dashboard:", default=True)
nav = st.navigation([overview,
                     st.Page(page_changed, title="What changed", icon=":material/difference:", url_path="what-changed"),
                     st.Page(page_evidence, title="Evidence", icon=":material/fact_check:", url_path="evidence"),
                     st.Page(page_review, title="Review and sign-off", icon=":material/rate_review:", url_path="review"),
                     st.Page(page_fool, title="Fool the Tower", icon=":material/science:", url_path="fool-the-tower")],
                    position="top")
if st.session_state.pop("goto_overview", False):
    st.switch_page(overview)
if st.session_state.get("_test_page") in PAGES:          # lets headless tests open any page
    PAGES[st.session_state["_test_page"]]()
else:
    nav.run()
