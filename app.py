"""Cohort Control Tower: the review screen.

  streamlit run app.py

Pick a release and a research question; see the verdict, the reasons, what changed and the evidence trail; then
a person decides on every proposed fix and problem and signs off. Research use only.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pandas as pd
import streamlit as st

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from tower.analyses import rerun  # noqa: E402
from tower.cards import list_cards, load_card  # noqa: E402
from tower.diff import compare  # noqa: E402
from tower.findings import build  # noqa: E402
from tower.readiness import assess  # noqa: E402
from tower.release import load_release  # noqa: E402
from tower.review import (ISSUE_CHOICES, REPAIR_CHOICES, SIGNOFF_CHOICES, missing_decisions, now,  # noqa: E402
                          record_markdown, signed, with_decisions)

st.set_page_config(page_title="Cohort Control Tower", page_icon="🗼", layout="wide")

VERDICT_STYLE = {"Ready": ("✅", st.success), "Conditional": ("⚠️", st.warning),
                 "Blocked": ("⛔", st.error), "Insufficient Evidence": ("❓", st.info)}
STATUS_LABEL = {"pass": "✅ passed", "warn": "⚠️ condition", "block": "⛔ blocks this use", "unknown": "❓ can't tell"}
A_ONLY = "Release A only (no new release)"


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


@st.cache_data(show_spinner="Checking the release...")
def analyze(b_path: str | None, card_id: str, allow_missing: bool):
    card = load_card(card_id)
    a = load_release(RAW, "release-A")
    if b_path is None:
        return None, assess(card, a, allow_missing=allow_missing)
    b = load_release(b_path)
    cmp = compare(a, b)
    results, impact = rerun(a, b, cmp.changes)
    findings = build(cmp, results, impact)
    return findings, assess(card, b, cmp, results, allow_missing=allow_missing)


# ------------------------------------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("1 · The data")
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

    st.header("2 · The research question")
    cards = list_cards()
    titles = {c["title"]: c["id"] for c in cards}
    card_title = st.selectbox("Question card", list(titles))
    card = load_card(titles[card_title])
    with st.expander("What this question needs"):
        for k, label in [("intended_use", "Intended use"), ("group_studied", "Group studied"), ("outcome", "Outcome"),
                         ("acceptable_limitations", "Acceptable limitations"), ("not_acceptable", "Not acceptable"),
                         ("out_of_scope", "Out of scope")]:
            st.markdown(f"**{label}:** {card[k]}")

    st.header("3 · Reviewer")
    reviewer = st.text_input("Your name")
    role = st.text_input("Your role", placeholder="e.g. research data engineer")
    allow_missing = st.checkbox("List checks that aren't built yet as pending", value=True,
                                help="Off: an unbuilt check counts as 'can't tell', the strict reading.")

# ------------------------------------------------------------------------------------------------ analysis
b_path = opts[release_label]
try:
    findings, ready = analyze(b_path, card["id"], allow_missing)
except Exception as e:  # never show a stack trace to a judge
    st.error(f"The check couldn't run: {e}")
    st.stop()

ctx = f"{release_label}|{card['id']}"
state = st.session_state.setdefault("review", {}).setdefault(ctx, {"repairs": {}, "issues": {}, "signed": None})
first_seen = st.session_state.setdefault("decided_at", {})


def collect(kind: str, ids: list[str]) -> dict:
    """Read every decision from the widgets' saved values, so counts are right before the widgets are drawn."""
    out = {}
    for i in ids:
        d = st.session_state.get(f"{ctx}|{kind}|{i}")
        if d:
            stamp = first_seen.setdefault(f"{ctx}|{kind}|{i}|{d}", now())
            out[i] = {"decision": d, "reason": st.session_state.get(f"{ctx}|{kind}r|{i}", "") or "", "time": stamp}
    return out

st.title("Cohort Control Tower")
st.caption("Is a new TCGA breast cancer release still fit for your research question? Team Identity_Crisis. "
           "Research use only: no diagnosis, treatment advice, risk score or clinical claim.")

icon, box = VERDICT_STYLE[ready["verdict"]]
box(f"**{icon} {ready['verdict']}** for “{card['title']}” on "
    f"{'release A' if b_path is None else release_label}\n\n{ready['summary']}")

repairs = findings["repairs"] if findings else []
required_issues = [i for i in ready["review"]["required"] if not i.startswith("F")]
state["repairs"] = collect("rep", [r["id"] for r in repairs])
state["issues"] = collect("iss", required_issues)
total = len(repairs) + len(required_issues)
decided = len(state["repairs"]) + len(state["issues"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Samples studied", ready["group_size"])
c2.metric("Changes found", len(findings["findings"]) if findings else 0)
c3.metric("Touch this question", len(ready["release_changes"]))
c4.metric("Decisions made", f"{decided} of {total}")
st.write("**Signed off:** " + (f"yes, by {state['signed']['review']['signed_off']['by']}" if state["signed"]
                               else "not yet. A person must review before this data is used."))

tab_why, tab_changed, tab_analyses, tab_trail, tab_review = st.tabs(
    ["Why this verdict", "What changed", "Analyses rerun", "Evidence trail", "Review and sign-off"])

with tab_why:
    st.subheader("Reasons")
    for r in ready["reasons"]:
        st.markdown(f"- {r}")
    if ready["next_steps"]:
        st.subheader("Next steps")
        for s in ready["next_steps"]:
            st.markdown(f"- {s['step']}  \n  *Evidence that would change the verdict:* {s['evidence_needed']}")
    st.subheader("Every check run for this question")
    st.dataframe(pd.DataFrame([{"Check": x["id"], "Result": STATUS_LABEL[x["status"]],
                                "Matters for this question": "yes" if x["material"] else "no (pending or not material)",
                                "Already in release A": "yes" if x["pre_existing"] else "no",
                                "What it found": x["title"]} for x in ready["issues"]]),
                 hide_index=True, width="stretch")
    for x in ready["issues"]:
        if x["material"] and x["status"] != "pass":
            with st.expander(f"{STATUS_LABEL[x['status']]} · {x['title']}"):
                st.markdown(f"**Decision rule:** {x['rule']}")
                st.markdown(f"**Source:** {x['source']}")
                if x["numbers"]:
                    st.json(x["numbers"], expanded=False)
                st.markdown(f"**What this check can't see:** {x['limitation']}")
                if x["row_count"]:
                    st.markdown(f"**Samples involved:** {x['row_count']} (first {len(x['rows'])} shown)")
                    st.code(", ".join(x["rows"]))

with tab_changed:
    if not findings:
        st.info("Pick a new release in the sidebar to see what changed against release A.")
    else:
        st.markdown(f"**Release check:** {findings['verdict']}. {findings['verdict_reason']}")
        for n in findings.get("notes", []):
            st.caption(n)
        touching = {t["finding"] for t in ready["release_changes"]}
        for f in findings["findings"]:
            samples = [e for e in f["evidence"] if e["kind"] == "sample"]
            tag = " · touches this question" if f["id"] in touching else ""
            with st.expander(f"{f['id']} · {f['kind']} · severity {f['severity']} · confidence {f['confidence']} · "
                             f"{len(samples)} sample(s) · affects {', '.join(f['affects_analyses']) or 'no protected analysis'}{tag}"):
                st.markdown(f["summary"])
                st.markdown(f"**Limitation:** {f['limitation']}")
                st.dataframe(pd.DataFrame([{"Sample": e["id"], "Release": e.get("release"), "File": e.get("file"),
                                            "Note": e.get("note")} for e in f["evidence"]]),
                             hide_index=True, width="stretch")
                fixes = [r for r in repairs if f["id"] in r["addresses"]]
                for r in fixes:
                    st.markdown(f"Proposed fix **{r['id']}** ({r['action']}): {r['justification']}")

with tab_analyses:
    if findings:
        for a in findings["analyses"]:
            st.markdown(f"**{a['id']}** · {a['title']} · **{a['status']}**  \n{a['reason']}")
            before, after = a.get("before") or {}, a.get("after") or {}
            if after:
                rows = [{"Measure": k, "Release A": json.dumps(before.get(k)), "New release": json.dumps(after.get(k))}
                        for k in before]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if a.get("samples_entered") or a.get("samples_left"):
                st.caption(f"Entered: {', '.join(a.get('samples_entered', [])) or 'none'} · "
                           f"Left: {', '.join(a.get('samples_left', [])) or 'none'}")
    elif ready["analyses"]:
        for aid, a in ready["analyses"].items():
            st.markdown(f"**{aid}** on release A: {a['status']}")
            st.json(a.get("result", a), expanded=False)
    else:
        st.info("This question depends on no protected analysis.")

with tab_trail:
    st.markdown("Every conclusion, the rule behind it, its source, the fields read, every sample involved and the "
                "fingerprint of the file it came from.")
    st.dataframe(pd.DataFrame([{"Conclusion": e["conclusion"], "Status": e["status"], "Rule": e["rule"],
                                "Source": e["source"], "Fields": ", ".join(e["fields"]), "Samples": e["row_count"],
                                "File fingerprints": "; ".join(f"{k}: {(v or '')[:12]}" for k, v in e["files"].items())}
                               for e in ready["lineage"]]), hide_index=True, width="stretch")
    st.caption("Fields this question reads: " + ", ".join(ready["fields_read"]))

with tab_review:
    if not (reviewer and role):
        st.warning("Enter your name and role in the sidebar to review.")
    st.subheader("Proposed fixes for the release changes")
    if not repairs:
        st.caption("No release changes, so nothing to fix.")
    for r in repairs:
        st.markdown(f"**{r['id']} · {r['action']}** for {', '.join(r['addresses'])} ({len(r['targets'])} target(s)): "
                    f"{r['justification']}")
        st.segmented_control(f"Decision for {r['id']}", REPAIR_CHOICES, key=f"{ctx}|rep|{r['id']}",
                             disabled=not (reviewer and role))
        st.text_input(f"Reason for {r['id']}", key=f"{ctx}|repr|{r['id']}", disabled=not (reviewer and role),
                      placeholder="Why (needed to reject or ask for more)")

    st.subheader("Problems for this question")
    if not required_issues:
        st.caption("No problems need a decision for this question.")
    by_id = {x["id"]: x for x in ready["issues"]}
    for iid in required_issues:
        x = by_id[iid]
        st.markdown(f"**{STATUS_LABEL[x['status']]}** · {x['title']}")
        st.segmented_control(f"Do you agree? ({iid})", ISSUE_CHOICES, key=f"{ctx}|iss|{iid}",
                             disabled=not (reviewer and role))
        st.text_input(f"Reason for {iid}", key=f"{ctx}|issr|{iid}", disabled=not (reviewer and role))

    st.subheader("Sign-off")
    missing = missing_decisions(findings, ready, state["repairs"], state["issues"])
    unexplained = [k for k, d in {**state["repairs"], **state["issues"]}.items()
                   if d["decision"] in ("reject", "request_more_evidence", "disagree", "need more evidence") and not d["reason"]]
    if missing:
        st.info(f"Decide these first: {', '.join(missing)}")
    if unexplained:
        st.info(f"Give a reason for: {', '.join(unexplained)}")
    decision = st.selectbox("Your decision for this question", SIGNOFF_CHOICES)
    note = st.text_area("Note (conditions, what you need next)")
    can_sign = bool(reviewer and role) and not missing and not unexplained
    if st.button("Sign off", type="primary", disabled=not can_sign):
        signed_doc = signed(ready, findings, state["repairs"], state["issues"], reviewer, role, decision, note)
        reviewed = with_decisions(findings, state["repairs"], reviewer, role) if findings else None
        state["signed"] = signed_doc
        out = REPO / "out" / "reviews" / f"{card['id']}-{release_label.split()[-1]}-{now().replace(':', '')}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "readiness.signed.json").write_text(json.dumps(signed_doc, indent=2, default=str))
        (out / "review_record.md").write_text(record_markdown(signed_doc, reviewed))
        check = ""
        if reviewed:
            (out / "findings.reviewed.json").write_text(json.dumps(reviewed, indent=2))
            v = subprocess.run([sys.executable, str(CHALLENGE / "format" / "validate.py"), str(out / "findings.reviewed.json")],
                               capture_output=True, text=True)
            check = f"Organizers' validator on findings.reviewed.json: {(v.stdout or v.stderr).strip().split()[0]}"
        state["flash"] = (f"Signed off by {reviewer} ({role}): {decision}. Saved in {out.relative_to(REPO)}", check)
        st.rerun()                                   # redraw so the status line at the top shows the sign-off
    if state["signed"]:
        sd = state["signed"]
        msg, check = state.get("flash", ("Signed off.", ""))
        st.success(msg)
        if check:
            st.caption(check)
        st.download_button("Download the review record (Markdown)", record_markdown(sd, findings), "review_record.md")
        st.download_button("Download readiness.json with the sign-off", json.dumps(sd, indent=2, default=str),
                           "readiness.signed.json")
        if findings:
            st.download_button("Download findings.json with the decisions",
                               json.dumps(with_decisions(findings, state["repairs"], reviewer, role), indent=2),
                               "findings.reviewed.json")
