"""Cohort Control Tower: the review screen.

  streamlit run app.py

Pick a release and a research question; see the verdict, the reasons, what changed and the evidence trail; then
a person decides on every proposed fix and problem and signs off. Research use only.
"""
from __future__ import annotations

import html
import json
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

from tower.analyses import rerun  # noqa: E402
from tower.cards import list_cards, load_card  # noqa: E402
from tower.checks import LOAD_ERRORS  # noqa: E402
from tower.questions import (ENDPOINTS, FEATURES, GROUPINGS, LABELS, SUBTYPES, THERAPIES,  # noqa: E402
                             model_question, protein_question, survival_question, treatment_question)
from tower.diff import compare  # noqa: E402
from tower.evidence import before_after  # noqa: E402
from tower.findings import build  # noqa: E402
from tower.readiness import assess  # noqa: E402
from tower.release import ROW_FILES, load_release  # noqa: E402
from tower.cli import plain_report  # noqa: E402
from tower.review import (ISSUE_CHOICES, REPAIR_CHOICES, SIGNOFF_CHOICES, missing_decisions, now,  # noqa: E402
                          record_markdown, signed, with_decisions)

st.set_page_config(page_title="Cohort Control Tower", page_icon="🗼", layout="wide")

# ------------------------------------------------------------------------------------------------ look
VERDICT = {  # icon, colour, tint, chip class
    "Ready": ("✅", "#0E7C45", "#EAF7F0", "chip-ready"),
    "Conditional": ("⚠️", "#B45309", "#FFF5E3", "chip-cond"),
    "Blocked": ("⛔", "#B91C1C", "#FDECEC", "chip-block"),
    "Insufficient Evidence": ("❓", "#1D4ED8", "#EAF0FD", "chip-unknown"),
}
STATUS = {"pass": ("passed", "chip-ready"), "warn": ("condition", "chip-cond"),
          "block": ("blocks this use", "chip-block"), "unknown": ("can't tell", "chip-unknown")}
SEVERITY = {"high": "chip-block", "medium": "chip-cond", "low": "chip-muted", "none": "chip-muted"}
KIND = {"sample_swap": "Swapped samples", "duplicate": "Copied profiles", "membership_change": "Samples missing or new",
        "label_conflict": "Changed labels", "missing_data": "Values removed", "other": "Unexplained change",
        "join_inflation": "Join inflation", "unlinked_record": "Unlinked record"}
ACTION = {"restore_from_previous_release": "Restore from release A", "exclude": "Exclude",
          "flag_for_review": "Flag for review", "relabel": "Relabel", "other": "Other"}
A_ONLY = "Release A only (no new release)"
# The sign-off decision starts from what the tool found; a person can change it, with a reason if they overrule it.
DEFAULT_SIGNOFF = {"Ready": "Approve use as stated", "Conditional": "Approve with the conditions listed",
                   "Blocked": "Do not use", "Insufficient Evidence": "Request more evidence"}

st.markdown("""
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1320px;}
.ct-head {display:flex; align-items:center; gap:.8rem; flex-wrap:wrap; margin-bottom:.9rem;}
.ct-title {font-size:1.75rem; font-weight:800; letter-spacing:-.02em; color:#132A3A;}
.ct-sub {color:#556676; font-size:.95rem;}
.ct-note {font-size:.75rem; color:#556676; background:#F3F6F8; border:1px solid #E2E8EE; border-radius:999px; padding:2px 10px;}
.ct-hero {border:1px solid #E2E8EE; border-left:8px solid var(--c); border-radius:16px; padding:18px 22px;
          background:linear-gradient(100deg, var(--bg) 0%, #FFFFFF 75%); height:100%;}
.ct-eyebrow {font-size:.72rem; font-weight:800; letter-spacing:.09em; text-transform:uppercase; color:#556676;}
.ct-verdict {font-size:2.15rem; font-weight:800; color:var(--c); line-height:1.15; margin:.15rem 0 .35rem;}
.ct-q {font-weight:700; font-size:1.06rem; color:#132A3A;}
.ct-meta {color:#556676; font-size:.85rem; margin:.25rem 0 .65rem;}
.ct-sum {color:#21384A; font-size:.95rem; line-height:1.55;}
.ct-qcard {border:1px solid #E2E8EE; border-radius:16px; padding:14px 18px; background:#FBFCFD; font-size:.87rem; height:100%;}
.ct-qcard .row {margin:0 0 7px; color:#33495A; line-height:1.45;}
.ct-qcard .lab {font-size:.7rem; font-weight:800; letter-spacing:.07em; text-transform:uppercase; color:#556676; display:block;}
.chip {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.76rem; font-weight:700; margin:0 6px 4px 0;
       border:1px solid transparent; white-space:nowrap;}
.chip-ready {background:#E7F6EE; color:#0B6236; border-color:#B7E1C8;}
.chip-cond {background:#FFF3DC; color:#7A4100; border-color:#F2CF96;}
.chip-block {background:#FDE7E7; color:#8F1717; border-color:#F3B3B3;}
.chip-unknown {background:#E7EDFB; color:#1A3580; border-color:#BAC9F1;}
.chip-muted {background:#F1F4F6; color:#43535F; border-color:#E2E8EE;}
.chip-teal {background:#E3F4F1; color:#0B5C55; border-color:#B4DFD8;}
.ct-steps {display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; margin:14px 0 6px;}
.ct-step {border:1px solid #E2E8EE; border-radius:14px; padding:10px 14px; background:#FFFFFF;}
.ct-step .k {font-size:.68rem; color:#556676; text-transform:uppercase; letter-spacing:.07em; font-weight:800;}
.ct-step .v {font-size:1.2rem; font-weight:800; color:#132A3A; margin-top:3px;}
.ct-step .s {font-size:.76rem; color:#556676;}
.ct-step.done {border-color:#B7E1C8; background:#F3FBF6;}
.ct-step.warn {border-color:#F2CF96; background:#FFF9EE;}
.ct-step.todo {border-color:#E2E8EE; background:#FFFFFF;}
.ct-sec {font-size:.74rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em; color:#556676; margin:20px 0 8px;}
.ct-reason {border:1px solid #E2E8EE; border-radius:12px; padding:10px 14px; margin-bottom:8px; background:#FFFFFF;}
.ct-next {border:1px solid #B4DFD8; background:#F1FAF8; border-radius:12px; padding:12px 16px; margin:6px 0;}
.ct-mono {font-family:'SF Mono', Menlo, Consolas, monospace; font-size:.8rem; color:#33495A;}
.ct-small {font-size:.82rem; color:#556676;}
.ct-cant {border:1px dashed #94A3B8; background:#F8FAFC; border-radius:12px; padding:10px 14px; margin-top:10px;
          font-size:.86rem; color:#334155;}
.ct-cant .it {margin:3px 0;}
.ct-guide {display:flex; gap:10px; flex-wrap:wrap; margin:-.3rem 0 1rem;}
.ct-guide .g {display:flex; align-items:center; gap:8px; background:#F3F6F8; border:1px solid #E2E8EE; border-radius:999px;
              padding:4px 14px 4px 4px; font-size:.82rem; color:#33495A;}
.ct-guide .n {width:22px; height:22px; border-radius:50%; background:#0F766E; color:#FFFFFF; display:inline-flex;
              align-items:center; justify-content:center; font-weight:800; font-size:.74rem;}
@media (max-width: 900px) {.ct-steps {grid-template-columns:repeat(2, minmax(0, 1fr));}}
</style>
""", unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x))


def plural(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def chip(text: str, cls: str) -> str:
    return f'<span class="chip {cls}">{esc(text)}</span>'


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


@st.cache_data(show_spinner="Checking the release...")
def analyze(b_path: str | None, card_id: str, allow_missing: bool, sig: tuple = (), card_json: str = ""):
    card = json.loads(card_json) if card_json else load_card(card_id)   # a question asked on screen has no file
    a = load_release(RAW, "release-A")
    if b_path is None:
        return None, assess(card, a, allow_missing=allow_missing), []
    b = load_release(b_path)
    cmp = compare(a, b)
    results, impact = rerun(a, b, cmp.changes)
    findings = build(cmp, results, impact)
    return findings, assess(card, b, cmp, results, allow_missing=allow_missing), membership(cmp)


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


def pick(title: str) -> None:
    st.session_state["card_title"] = title


# ------------------------------------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 🗼 Cohort Control Tower")
    st.caption("Team Identity_Crisis · OncoSys Cancer AI Lab")
    st.markdown("**1 · The data**")
    opts = release_options()
    labels = list(opts)
    default = st.session_state.get("release_label", labels[1] if len(labels) > 1 else labels[0])
    release_label = st.selectbox("New release to check against release A", labels,
                                 index=labels.index(default) if default in labels else 0)
    st.session_state["release_label"] = release_label
    with st.expander("Open a sealed envelope"):
        with st.form("envelope"):
            num = st.text_input("Envelope number", placeholder="07 or practice")
            words = st.text_input("Four-word code", placeholder="amber falcon river quartz")
            if st.form_submit_button("Open it"):
                r = subprocess.run([sys.executable, "envelopes/unseal.py", num.strip(), *words.split()],
                                   cwd=CHALLENGE, capture_output=True, text=True)
                st.code((r.stdout + r.stderr)[-1500:])
                if r.returncode == 0:
                    name = "practice" if num.strip().lower() == "practice" else f"E{int(num.strip().upper().lstrip('E')):02d}"
                    st.session_state["release_label"] = f"Envelope {name}"
                    st.rerun()

    st.markdown("**2 · The research question**")
    cards = list_cards() + st.session_state.get("custom_cards", [])
    titles = {c["title"]: c["id"] for c in cards}
    if st.session_state.get("card_title") not in titles:
        st.session_state["card_title"] = list(titles)[0]
    card_title = st.selectbox("Question card", list(titles), key="card_title")
    card = next(c for c in cards if c["title"] == card_title)
    with st.expander("Ask your own question"):
        kind = st.selectbox("Kind of question", ["Survival by subtype", "A protein between groups", "A prediction model",
                                                 "Response to a treatment"], key="q_kind")
        if kind == "Survival by subtype":
            ep = st.selectbox("Outcome", list(ENDPOINTS), format_func=lambda k: ENDPOINTS[k], key="q_ep")
            focus = st.selectbox("Subtype to focus on", ["", *SUBTYPES], key="q_focus",
                                 format_func=lambda k: SUBTYPES.get(k, "none (all subtypes)"))
            new = survival_question(ep, focus or None)
        elif kind == "A protein between groups":
            prot = st.selectbox("Protein (RPPA)", protein_rows(), key="q_prot")
            grp = st.selectbox("Groups to compare", list(GROUPINGS), format_func=lambda k: GROUPINGS[k][0], key="q_grp")
            new = protein_question(prot, grp)
        elif kind == "A prediction model":
            lab = st.selectbox("Label to predict", list(LABELS), format_func=lambda k: LABELS[k], key="q_lab")
            feats = st.multiselect("Data the model learns from", list(FEATURES), default=["protein_rppa.tsv.gz"],
                                   format_func=lambda k: FEATURES[k], key="q_feats")
            new = model_question(lab, feats)
        else:
            new = treatment_question(st.selectbox("Treatment", list(THERAPIES), key="q_ther"))
        st.caption(new["title"])
        st.button("Judge this question", key="q_go", type="primary", on_click=add_question, args=(new,))
        st.caption("The same rules judge it as the cards in cards/. Nothing is saved unless you download it.")
        if card["id"].startswith("custom-"):
            st.download_button("⬇ Save the open question as a card", yaml.safe_dump(card, sort_keys=False),
                               f"{card['id']}.yaml")

    st.markdown("**3 · Reviewer**")
    reviewer = st.text_input("Your name")
    role = st.text_input("Your role", placeholder="e.g. research data engineer")
    allow_missing = st.toggle("List unbuilt checks as pending", value=True,
                              help="Off: an unbuilt check counts as 'can't tell', the strict reading.")
    st.caption("Research use only. No diagnosis, treatment advice, risk score or clinical claim.")

# ------------------------------------------------------------------------------------------------ analysis
b_path = opts[release_label]
try:
    findings, ready, members = analyze(b_path, card["id"], allow_missing, inputs_sig(),
                                       json.dumps(card) if card["id"].startswith("custom-") else "")
except Exception as e:  # never show a stack trace to a judge
    st.error(f"The check couldn't run: {e}")
    st.stop()

ctx = f"{release_label}|{card['id']}"
state = st.session_state.setdefault("review", {}).setdefault(ctx, {"repairs": {}, "issues": {}, "signed": None})
first_seen = st.session_state.setdefault("decided_at", {})
dkey, nkey = f"{ctx}|signoff", f"{ctx}|signoff_note"
# Streamlit forgets a widget's value while the widget isn't drawn (for example while another question is open), so
# every review widget's value for this question is also kept here and put back when the question is opened again.
kept = state.setdefault("widgets", {})
for k, v in kept.items():
    if k not in st.session_state:
        st.session_state[k] = v
for k in [k for k in list(st.session_state.keys()) if isinstance(k, str) and k.startswith(ctx + "|")]:
    kept[k] = st.session_state[k]
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

# ------------------------------------------------------------------------------------------------ header + hero
st.markdown('<div class="ct-head"><span class="ct-title">Cohort Control Tower</span>'
            '<span class="ct-sub">Is a new TCGA breast cancer release still fit for your research question?</span>'
            '<span class="ct-note">Research use only</span></div>', unsafe_allow_html=True)
st.markdown('<div class="ct-guide">'
            '<span class="g"><span class="n">1</span>Pick a new release in the sidebar, or open a sealed envelope</span>'
            '<span class="g"><span class="n">2</span>Read the verdict and why</span>'
            '<span class="g"><span class="n">3</span>Switch the question below and watch the verdict change</span>'
            '<span class="g"><span class="n">4</span>Review each fix and sign off</span></div>', unsafe_allow_html=True)

icon, colour, tint, vchip = VERDICT[ready["verdict"]]
where = "release A" if b_path is None else f"{release_label}, compared with release A"
left, right = st.columns([3, 2], gap="medium")
left.markdown(f"""
<div class="ct-hero" style="--c:{colour}; --bg:{tint}">
  <div class="ct-eyebrow">Verdict for this question</div>
  <div class="ct-verdict">{icon} {esc(ready['verdict'])}</div>
  <div class="ct-q">{esc(card['title'])}</div>
  <div class="ct-meta">{esc(where)} · {ready['group_size']} samples studied</div>
  <div class="ct-sum">{esc(ready['summary'])}</div>
</div>""", unsafe_allow_html=True)
if ready.get("cannot_tell"):
    left.markdown('<div class="ct-cant"><div class="ct-eyebrow">What this can\'t tell you</div>'
                  + "".join(f'<div class="it">• {esc(x)}</div>' for x in ready["cannot_tell"]) + "</div>",
                  unsafe_allow_html=True)
right.markdown(f"""
<div class="ct-qcard">
  <div class="row"><span class="lab">Intended use</span>{esc(card['intended_use'])}</div>
  <div class="row"><span class="lab">Group studied</span>{esc(card['group_studied'])}</div>
  <div class="row"><span class="lab">Outcome</span>{esc(card['outcome'])}</div>
  <div class="row"><span class="lab">Acceptable limitations</span>{esc(card['acceptable_limitations'])}</div>
</div>""", unsafe_allow_html=True)
if ready.get("group_samples"):
    right.download_button(f"⬇ The {len(ready['group_samples'])} samples this question can use (CSV)",
                          "sample_id,patient_id\n" + "".join(f"{s},{s[:12]}\n" for s in ready["group_samples"]),
                          f"{card['id']}-samples.csv", help="The samples in this release that can answer the question, "
                          "after the question's own filters: which samples the verdict is about.")

n_files = len(ready["release"]["files"])
n_changes = len(findings["findings"]) if findings else 0
signed_by = state["signed"]["review"]["signed_off"]["by"] if state["signed"] else None
steps = [
    ("Files fingerprinted", f"{n_files}", "every file this question reads", "done"),
    ("Changes found", f"{n_changes}" if findings else "n/a", "vs release A" if findings else "no new release picked",
     "warn" if n_changes else "done"),
    ("Touch this question", f"{len(touching)}", "need a person's review" if touching else "none",
     "warn" if touching else "done"),
    ("Decisions", f"{decided} of {total}", "fixes and problems decided",
     "done" if decided == total else "warn"),
    ("Sign-off", "Signed" if signed_by else "Pending", f"by {signed_by}" if signed_by else "a person must sign off",
     "done" if signed_by else "todo"),
]
st.markdown('<div class="ct-steps">' + "".join(
    f'<div class="ct-step {s}"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div><div class="s">{esc(sub)}</div></div>'
    for k, v, sub, s in steps) + "</div>", unsafe_allow_html=True)

st.markdown('<div class="ct-sec">Same release, every question: the verdict depends on the question</div>',
            unsafe_allow_html=True)
qcols = st.columns(4)
for i, q in enumerate(board(b_path, allow_missing, inputs_sig(), json.dumps(st.session_state.get("custom_cards", [])))):
    with qcols[i % 4]:
        st.button(f"{VERDICT[q['verdict']][0]} {q['short']}", key=f"pick|{q['id']}", on_click=pick, args=(q["title"],),
                  type="primary" if q["id"] == card["id"] else "secondary", help=q["reason"])
        st.caption(q["verdict"] + (f" · {q['pending']} not checked yet" if q.get("pending") else "")
                   + (" · open" if q["id"] == card["id"] else ""))

tab_why, tab_changed, tab_analyses, tab_trail, tab_review = st.tabs(
    ["🧭 Why this verdict", "🔀 What changed", "📊 Analyses", "🧬 Evidence trail", "✍️ Review and sign-off"])

# ------------------------------------------------------------------------------------------------ why
with tab_why:
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
        with st.container(border=True):
            st.markdown(chip(label, cls) + (chip("already in release A", "chip-muted") if x["pre_existing"] and x["material"] else "")
                        + f'<b>{esc(x["id"])}</b>', unsafe_allow_html=True)
            st.markdown(x["title"])
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
with tab_changed:
    if not findings:
        st.info("Pick a new release in the sidebar to see what changed against release A.")
    else:
        rv = VERDICT[findings["verdict"]]
        st.markdown(chip(f"{rv[0]} Release check: {findings['verdict']}", rv[3]) + f'<span class="ct-small">'
                    f'{esc(findings["verdict_reason"])}</span>', unsafe_allow_html=True)
        for n in findings.get("notes", []):
            st.caption(n)
        st.download_button("⬇ Release notes (plain English)", plain_report(findings), "release_notes.md")
        if members:
            st.markdown('<div class="ct-sec">Same count, different members</div>', unsafe_allow_html=True)
            colors = {"swapped": "#B45309", "copied in": "#B91C1C", "removed": "#6B7280", "new": "#1D4ED8",
                      "relabelled or edited": "#7C3AED"}
            for m in members:
                changed = sorted(set(m["swapped"]) | set(m["copied"]) | set(m["lost"]) | set(m["gained"]) | set(m["relabeled"]))
                with st.container(border=True):
                    st.markdown(f'<span class="ct-mono"><b>{esc(m["file"])}</b></span>', unsafe_allow_html=True)
                    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
                    c1.metric("Samples in release A", m["n_a"])
                    c2.metric("Samples in new release", m["n_b"], delta=(m["n_b"] - m["n_a"]) or None)
                    c3.metric("Samples that changed", len(changed))
                    rows = [{"what": w, "n": len(m[k])} for k, w in [("swapped", "swapped"), ("copied", "copied in"),
                                                                     ("lost", "removed"), ("gained", "new"),
                                                                     ("relabeled", "relabelled or edited")] if m[k]]
                    if rows:
                        c4.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadius=4).encode(
                            x=alt.X("n:Q", title="samples", axis=alt.Axis(tickMinStep=1)),
                            y=alt.Y("what:N", title=None, sort="-x"),
                            color=alt.Color("what:N", scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                                            legend=None),
                            tooltip=["what", "n"]).properties(height=46 * len(rows) + 40))
                    if m["n_a"] == m["n_b"] and changed:
                        st.caption("The total count is identical, so a count check would say nothing changed. "
                                   "Fingerprinting every sample is what catches it.")
        st.markdown('<div class="ct-sec">Every change, with every sample</div>', unsafe_allow_html=True)
        ba_tables = before_after_tables(b_path, inputs_sig())
        for f in findings["findings"]:
            samples = [e for e in f["evidence"] if e["kind"] == "sample"]
            with st.container(border=True):
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
        x=alt.X("release:N", title=None, sort=["Release A", "New release"]), y=alt.Y("mean:Q", title="mean ER-alpha protein (RPPA)"),
        color=alt.Color("release:N", legend=None), column=alt.Column("ER status:N", title=None),
        tooltip=["ER status", "release", "mean"]).properties(width=140, height=220))


def a2_chart(before: dict, after: dict | None):
    rows = [{"subtype": k, "release": "Release A", "percent": v} for k, v in before["percent"].items()]
    if after:
        rows += [{"subtype": k, "release": "New release", "percent": v} for k, v in after["percent"].items()]
    return (alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadius=3).encode(
        x=alt.X("subtype:N", title=None), y=alt.Y("percent:Q", title="% of subtyped primary tumors"),
        xOffset="release:N", color=alt.Color("release:N", legend=alt.Legend(title=None, orient="bottom")),
        tooltip=["subtype", "release", "percent"]).properties(height=240))


with tab_analyses:
    items = []
    if findings:
        items = [(a["id"], a["title"], a["status"], a.get("reason", ""), a.get("before") or {}, a.get("after"))
                 for a in findings["analyses"]]
    else:
        items = [(aid, aid, a["status"], "run on release A", a.get("result") or {}, None)
                 for aid, a in ready["analyses"].items()]
    rob = ready.get("robustness") or {}
    if rob:
        lab, cls = {"holds": ("✅ The conclusion holds", "chip-ready"), "fragile": ("⚠️ The conclusion is fragile", "chip-cond"),
                    "reversed": ("⛔ The conclusion reverses", "chip-block")}[rob["status"]]
        with st.container(border=True):
            st.markdown('<div class="ct-eyebrow">Does the conclusion still hold?</div>' + chip(lab, cls)
                        + f'<span class="ct-small">{esc(rob["claim"])}</span>', unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("ER+ minus ER- difference", rob["difference"],
                      delta=round(rob["difference"] - rob["release_a_difference"], 3) if rob.get("release_a_difference") is not None else None)
            k2.metric("95% range (1,000 resamples)", f"{rob['range_95'][0]} to {rob['range_95'][1]}")
            if rob.get("release_a_difference") is not None:
                k3.metric("Release A", rob["release_a_difference"])
                if rob["flagged_samples"]:
                    k4.metric(f"Without the {rob['flagged_samples']} flagged samples", rob["difference_without_flagged"])
            st.caption("Holds if the difference stays positive and its 95% range stays above zero. The range covers "
                       "sampling variation only, not systematic errors such as a mislabelled ER test.")
    if items:
        ref = reference_numbers(b_path or str(RAW))
        with st.container(border=True):
            st.markdown('<div class="ct-eyebrow">Check it yourself: the organizers\' own script on the same release</div>',
                        unsafe_allow_html=True)
            if "error" in ref:
                st.caption(f"The organizers' reference script couldn't run here: {ref['error']}")
            else:
                rows = []
                for aid, _title, _status, _reason, before, after in items:
                    ours, theirs = (after or before or {}), ref.get(aid, {})
                    if aid == "A1":
                        pairs = [("ER+ minus ER- difference", ours.get("difference"), theirs.get("difference")),
                                 ("Samples", ours.get("n_samples"), theirs.get("n_samples"))]
                    else:
                        pairs = [("Samples", ours.get("n_samples"), theirs.get("n_samples")),
                                 ("Subtype counts", ", ".join(f"{k} {v}" for k, v in sorted((ours.get("counts") or {}).items())),
                                  ", ".join(f"{k} {v}" for k, v in sorted((theirs.get("counts") or {}).items())))]
                    rows += [{"Analysis": aid, "Number": n, "This tool": str(o), "Organizers' script": str(r),
                              "Match": "✅ same" if o == r else "❌ different"} for n, o, r in pairs]
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
        with st.container(border=True):
            cls = {"changed": "chip-cond", "unchanged": "chip-ready", "not_rerun": "chip-muted", "run": "chip-teal"}.get(status, "chip-muted")
            st.markdown(f"<b>{esc(aid)} · {esc(title)}</b> &nbsp;" + chip(status.replace("_", " "), cls), unsafe_allow_html=True)
            st.caption(reason)
            if aid == "A1" and before.get("mean_positive") is not None:
                c1, c2 = st.columns([1, 2])
                c1.metric("ER+ minus ER- difference", after["difference"] if after else before["difference"],
                          delta=round(after["difference"] - before["difference"], 3) if after else None)
                c1.metric("Samples", after["n_samples"] if after else before["n_samples"],
                          delta=(after["n_samples"] - before["n_samples"]) if after else None)
                c2.altair_chart(a1_chart(before, after))
            elif aid == "A2" and before.get("percent"):
                st.altair_chart(a2_chart(before, after))
            if findings:
                a = next(x for x in findings["analyses"] if x["id"] == aid)
                if a.get("samples_entered") or a.get("samples_left"):
                    st.caption(f"Entered: {', '.join(a.get('samples_entered', [])) or 'none'} · "
                               f"Left: {', '.join(a.get('samples_left', [])) or 'none'}")

# ------------------------------------------------------------------------------------------------ evidence trail
def blast_radius() -> str:
    """Each change, the file it hit, the analysis that reads it, and this question."""
    vcol = VERDICT[ready["verdict"]][1]
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
            g.append(f'{f["id"]} [label="{f["id"]} {KIND.get(f["kind"], f["kind"])}\\n{plural(n, 'sample')}", fillcolor="{sev}"];')
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
            g.append(f'"{label}" -> Q [color="{VERDICT[ready["verdict"]][1]}"];')
    if len(g) == 5:
        g.append('ok [label="nothing material touches this question", fillcolor="#E7F6EE"]; ok -> Q;')
    for file in uses:
        if file not in files:
            g.append(f'"{file}" [fillcolor="#F3F6F8", fontname="Courier"]; "{file}" -> Q [style=dashed];')
    g.append("}")
    return "\n".join(g)


with tab_trail:
    st.markdown('<div class="ct-sec">Blast radius: change → file → analysis → this question</div>', unsafe_allow_html=True)
    st.graphviz_chart(blast_radius())
    st.markdown('<div class="ct-sec">Every conclusion and what it rests on</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{"Conclusion": e["conclusion"], "Status": e["status"], "Rule": e["rule"],
                                "Source": e["source"], "Fields": ", ".join(e["fields"]), "Samples": e["row_count"],
                                "File fingerprints": "; ".join(f"{k}: {(v or '')[:12]}" for k, v in e["files"].items())}
                               for e in ready["lineage"]]), hide_index=True, width="stretch")
    st.caption("Fields this question reads: " + ", ".join(ready["fields_read"]))

# ------------------------------------------------------------------------------------------------ review
with tab_review:
    if not (reviewer and role):
        st.warning("Enter your name and role in the sidebar to review.")
    if state.pop("withdrawn", False):
        st.warning("Something changed after the sign-off (a decision, the verdict or the reviewer), so the sign-off "
                   "was withdrawn. Check the decisions and sign off again.")
    st.progress(decided / total if total else 1.0, text=f"{decided} of {total} decisions made")
    st.markdown('<div class="ct-sec">Proposed fixes for the release changes</div>', unsafe_allow_html=True)
    if not repairs:
        st.caption("No release changes, so nothing to fix.")
    for r in repairs:
        with st.container(border=True):
            st.markdown(f"<b>{esc(r['id'])} · {esc(ACTION.get(r['action'], r['action']))}</b> &nbsp;"
                        + chip(f"for {', '.join(r['addresses'])}", "chip-muted")
                        + chip(plural(len(r["targets"]), "target"), "chip-muted"), unsafe_allow_html=True)
            st.markdown(r["justification"])
            st.segmented_control(f"Decision for {r['id']}", REPAIR_CHOICES, key=f"{ctx}|rep|{r['id']}",
                                 disabled=not (reviewer and role),
                                 format_func=lambda o: {"approve": "✅ approve", "reject": "⛔ reject",
                                                        "request_more_evidence": "❓ ask for more"}[o])
            st.text_input(f"Reason for {r['id']}", key=f"{ctx}|repr|{r['id']}", disabled=not (reviewer and role),
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
        with st.container(border=True):
            st.markdown(chip(STATUS[x["status"]][0], STATUS[x["status"]][1]) + f"<b>{esc(iid)}</b>", unsafe_allow_html=True)
            for y in xs:
                st.markdown(y["title"])
            st.segmented_control(f"Do you agree? ({iid})", ISSUE_CHOICES, key=f"{ctx}|iss|{iid}",
                                 disabled=not (reviewer and role))
            st.text_input(f"Reason for {iid}", key=f"{ctx}|issr|{iid}", disabled=not (reviewer and role))

    st.markdown('<div class="ct-sec">Sign-off</div>', unsafe_allow_html=True)
    missing = missing_decisions(findings, ready, state["repairs"], state["issues"])
    unexplained = [k for k, d in {**state["repairs"], **state["issues"]}.items()
                   if d["decision"] in ("reject", "request_more_evidence", "disagree", "need more evidence") and not d["reason"]]
    with st.container(border=True):
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
            state["signed"], state["signed_inputs"] = signed_doc, signature
            slug = re.sub(r"[^A-Za-z0-9]+", "-", release_label).strip("-").lower()
            out = REPO / "out" / "reviews" / f"{card['id']}-{slug}-{now().replace(':', '')}"
            out.mkdir(parents=True, exist_ok=True)
            (out / "readiness.signed.json").write_text(json.dumps(signed_doc, indent=2, default=str))
            (out / "review_record.md").write_text(record_markdown(signed_doc, reviewed))
            check = ""
            if reviewed:
                (out / "findings.reviewed.json").write_text(json.dumps(reviewed, indent=2))
                v = subprocess.run([sys.executable, str(CHALLENGE / "format" / "validate.py"),
                                    str(out / "findings.reviewed.json")], capture_output=True, text=True)
                check = f"Organizers' validator on findings.reviewed.json: {(v.stdout or v.stderr).strip().split()[0]}"
            state["flash"] = (f"Signed off by {reviewer} ({role}): {decision}. Saved in {out.relative_to(REPO)}", check)
            st.rerun()                               # redraw so the step tracker at the top shows the sign-off
    if state["signed"]:
        sd = state["signed"]
        msg, check = state.get("flash", ("Signed off.", ""))
        st.success(msg)
        if check:
            st.caption(check)
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇ Review record (Markdown)", record_markdown(sd, findings), "review_record.md")
        d2.download_button("⬇ readiness.json with sign-off", json.dumps(sd, indent=2, default=str),
                           "readiness.signed.json")
        if findings:
            d3.download_button("⬇ findings.json with decisions",
                               json.dumps(with_decisions(findings, state["repairs"], reviewer, role), indent=2),
                               "findings.reviewed.json")
