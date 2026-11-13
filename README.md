# Identity_Crisis · Cohort Control Tower

Team Identity_Crisis's entry for the OncoSys Cancer AI Lab hackathon (The Open Accelerator, OncoSys AI, Northeastern University, Red Hat; November 11-14, 2026). Track 1: Cohort Firewall.

## The user and the one workflow

**User:** a research data engineer who keeps an analysis-ready copy of TCGA breast cancer data for the scientists who use it, and receives new releases of it. Who they are and what goes wrong for them, with sources: [docs/USER.md](docs/USER.md).

**Workflow they finish:** point the tool at a new release. It names every sample that changed (swapped, copied under a new id, missing, relabelled), reruns only the analyses those changes touch, says whether the release is still fit for the research question, and writes `findings.json` in the event's shared format so a reviewer can approve or reject each proposed fix.

## Status (Friday, November 13)

- Release comparison, A1/A2 reruns, `findings.json` and the sealed-envelope command work.
- On the organizers' practice envelope it reports the same swap, the same five copies with their sources, the same five lost samples and the same A1 result (3.051 to 3.019) as the organizers' reference output, and its file passes `format/validate.py`. Unsealing plus checking takes about 2 seconds.
- Scorecard: 20 of 20 test releases pass. 13 are built with the organizers' `make_release.py` (swaps, copies, losses and relabels across all five files, chains of swaps, combinations, and a no-change release). 7 more test changes their generator can't make: edited values, a removed protein row, edited survival outcomes, a renamed sample id, and three damaged releases (a truncated file, a comma-separated file and an empty file), which are refused with Insufficient Evidence instead of crashing. Their answers are written into `EXPECTED.json` when each release is built, before the tool runs. Every planted sample found, nothing extra reported, about a second per release. We also built 481 releases with the organizers' generator at random settings: 476 match its answer keys exactly. In four of the other five, the answer key lists a change that left no trace in the data (a copy that a later change deleted, or a value changed and then changed back); the fifth is a copy whose original was later removed, which the tool reports as a rename.
- Research-question cards and verdicts work: eight cards (`cards/`) cover all four verdicts, and the verdict changes when the question or the release changes (for example, ER-alpha by ER status is Ready on release A and Conditional on the practice envelope; ESR1 expression vs ER status becomes Insufficient Evidence because the envelope has no RNA).
- Does the conclusion still hold? Each change's own effect is measured by undoing it alone and rerunning the analysis, so severity rests on a number (on the practice envelope this reproduces the organizers' reference severities: swap high, copies high, lost samples medium). For A1 the tool also reports a 95% range of the ER+ minus ER- difference from 1,000 resamples, with and without the flagged samples.
- The review and sign-off screen works (`streamlit run app.py`). A question board shows the verdict for every research question on the same release, and the Analyses tab runs the organizers' own `reference_analyses.py` on the same release so a judge can see the numbers match.
- Next: release A data checks (in progress). Plan: [docs/PLAN.md](docs/PLAN.md).

## Quick start (fresh machine)

Needs Python 3.10 or newer and git. Put both repositories in the same folder.

```bash
git clone https://github.com/disleveK/oncosys-hackathon-challenge.git
```
```bash
git clone https://github.com/AravindKumar2504/identity-crisis-control-tower.git
```
```bash
python3 -m venv .venv && source .venv/bin/activate
```
```bash
pip install -r oncosys-hackathon-challenge/requirements.txt -r identity-crisis-control-tower/requirements.txt
```
```bash
python oncosys-hackathon-challenge/data/tcga-brca/fetch.py
```

On Windows, activate with `.venv\Scripts\activate`. On a Mac with Python from python.org, if `fetch.py` fails with a certificate error, run the "Install Certificates" command that came with Python once, then retry.

Then check everything in one command, from inside `identity-crisis-control-tower`. It checks Python and the packages, release A against its published checksums, and the sealed envelopes, then runs the practice envelope and compares the result with the organizers' reference output (about 3 seconds; add `--full` to also run the scorecard):

```bash
python -m tower doctor
```

### Saturday's sealed envelope (the live test)

From inside `identity-crisis-control-tower`, with the envelope number and four words the judge gives you:

```bash
python -m tower envelope practice orange meadow pilot lantern
```

It unseals the envelope with the organizers' `unseal.py`, compares the new release with release A, writes `out/<envelope>/findings.json` and `out/<envelope>/report.md`, and runs the organizers' validator. The practice code above is public; on Saturday use your own number and words.

Add `--card all` to also judge every research-question card against the envelope's release (one `readiness.json` and `.md` per card in `out/<envelope>/readiness/`).

### The review screen

```bash
streamlit run app.py --server.address localhost
```

Opens http://localhost:8501. Pick a release (an opened envelope, a test release, or release A alone) and a research question. The screen shows the verdict and a plain-English summary, why (every check), what changed (every finding with its samples, and a before-and-after table of the values behind each one), the analyses rerun, and the evidence trail. In **Review and sign-off**, a reviewer approves, rejects or asks for more evidence on every proposed fix and problem (a reason is required to reject or ask for more), then signs off. The sign-off decision starts from the verdict, approving a Blocked or Insufficient Evidence verdict needs a note, and changing any decision afterwards withdraws the sign-off.

**Ask your own question** (sidebar): build a question from a few choices (survival by subtype, a protein between groups, a prediction model, or response to a treatment). The same rules judge it, it joins the question board, and it can be saved as a card file that `python -m tower check --card <file>` runs too. The form only writes the question down; it never decides a verdict. Sign-off writes `out/reviews/<question>-<release>-<time>/` with `findings.reviewed.json` (the decisions in the shared format, checked with the organizers' validator), `readiness.signed.json` and a review record, and offers all three as downloads. A sealed envelope can also be opened from the sidebar.

### Is the data fit for a research question?

```bash
python -m tower cards
```
```bash
python -m tower check --card os-luminal-a
```

Each card states the intended use, the group studied, the outcome and the acceptable limitations. The tool returns Ready, Conditional, Blocked or Insufficient Evidence with the reasons, the next step, and the evidence trail (fields, every sample involved, file fingerprints), in `out/readiness/<card>.json` and `.md`. Add `--release <folder>` to judge a new release: it is compared with release A (or the folder given with `--against`), so the release changes that touch the question are included. Until every check is built, add `--allow-missing-checks` to list unbuilt checks as pending.

### Compare any two releases

```bash
python -m tower compare ../oncosys-hackathon-challenge/data/tcga-brca/raw <new release folder> --out out/findings.json --challenge ../oncosys-hackathon-challenge
```

`--analyses A1` limits the question to one analysis. A release folder holds the TCGA-BRCA files with their usual names; the RNA file is optional.

### Reproduce the scorecard

```bash
for c in tests/releases/t*.json; do python ../oncosys-hackathon-challenge/data/tcga-brca/make_release.py --config "$c"; done
```
```bash
python scripts/make_adversarial.py
```
```bash
python scripts/scorecard.py ../oncosys-hackathon-challenge/data/tcga-brca/releases
```

The answer keys (`CHANGES.json`) are written by the organizers' generator, not by us, and the tool never reads them.

## What's in this repo

| Path | What it is |
|---|---|
| `tower/release.py` | Loads a release; fingerprints every file and every sample |
| `tower/diff.py` | Explains each change: swaps and chains, copies, losses, gains, relabels, blanked or edited values |
| `tower/analyses.py` | A1 and A2, matching the organizers' `reference_analyses.py`, and which changes touch them |
| `tower/findings.py` | Writes `findings.json`: one finding per change, every affected sample cited, severity with its reason |
| `tower/cards.py` | Loads research-question cards and works out which samples each question studies |
| `tower/questions.py` | Builds a card from the choices in the screen's "Ask your own question" form |
| `tower/evidence.py` | The before-and-after values behind every cited sample |
| `tower/doctor.py` | `python -m tower doctor`: is this machine ready for the sealed envelope? |
| `tower/readiness.py` | The verdict (Ready, Conditional, Blocked, Insufficient Evidence), its reasons and the evidence trail |
| `tower/checks/` | The checks cards run: question-reasoning rules (`fitness.py`) and release A data checks |
| `cards/` | Eight research-question cards |
| `tower/cli.py` | `compare`, `envelope`, `cards` and `check` commands |
| `tower/review.py` | Review decisions, the sign-off, and the exports |
| `app.py` | The review screen (Streamlit) |
| `tests/releases/` | Configs for the scorecard's test releases |
| `scripts/scorecard.py` | Scores the tool against the generator's answer keys |
| `scripts/try_check.py` | Runs one check for every card that lists it, on release A and the practice envelope, and flags contract problems |
| `docs/` | Team plan, user research, contracts and the demo script |
| `examples/practice/` | The tool's output on the organizers' practice envelope: `findings.json` (passes their validator) and the plain-English `report.md` |

## Data and credits

Judged results use the event's frozen TCGA-BRCA release, fetched with the challenge repo's `data/tcga-brca/fetch.py` and checked against its published checksums. No raw TCGA files are committed here. Data credits, as `DATA_LICENSES.md` in the [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge) asks:

- TCGA: "The results shown here are in whole or part based upon data generated by the TCGA Research Network: https://www.cancer.gov/tcga."
- UCSC Xena: Goldman, M.J. et al. Visualizing and interpreting cancer genomics data via the Xena platform. *Nat Biotechnol* 38, 675-678 (2020).
- Survival data: Liu, J. et al. An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive High-Quality Survival Outcome Analytics. *Cell* 173, 400-416 (2018). The tool's endpoint rules cite this paper too.
- PAM50 (cited by the tool's model-design rule): Parker, J.S. et al. Supervised Risk Predictor of Breast Cancer Based on Intrinsic Subtypes. *J Clin Oncol* 27, 1160-1167 (2009).

The data is de-identified but patient-derived: research use only. This tool makes no diagnosis, treatment recommendation, risk score or clinical claim, and every finding asks a person to review it.

## Third-party code

No third-party code is copied into this repo. At run time the tool calls the organizers' `envelopes/unseal.py` and `format/validate.py` from the challenge repo. Libraries: pandas (BSD-3-Clause), NumPy (BSD-3-Clause), jsonschema (MIT), PyYAML (MIT), Streamlit (Apache-2.0, the review screen), Altair (BSD-3-Clause, charts, installed with Streamlit), cryptography (Apache-2.0 or BSD-3-Clause, used by `unseal.py`).

## Team

Identity_Crisis. Members will be listed here.
