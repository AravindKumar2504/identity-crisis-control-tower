# Identity_Crisis · Cohort Control Tower

Team Identity_Crisis's entry for the OncoSys Cancer AI Lab hackathon (The Open Accelerator, OncoSys AI, Northeastern University, Red Hat; November 11-14, 2026). Track 1: Cohort Firewall.

## The user and the one workflow

**User:** a research data engineer who keeps an analysis-ready copy of TCGA breast cancer data for the scientists who use it, and receives new releases of it. Who they are and what goes wrong for them, with sources: [docs/USER.md](docs/USER.md).

**Workflow they finish:** point the tool at a new release. It names every sample that changed (swapped, copied under a new id, missing, relabelled), reruns only the analyses those changes touch, says whether the release is still fit for the research question, and writes `findings.json` in the event's shared format so a reviewer can approve or reject each proposed fix.

## Status (Friday, November 13)

- Release comparison, A1/A2 reruns, `findings.json` and the sealed-envelope command work.
- On the organizers' practice envelope it reports the same swap, the same five copies with their sources, the same five lost samples and the same A1 result (3.051 to 3.019) as the organizers' reference output, and its file passes `format/validate.py`. Unsealing plus checking takes about 2 seconds.
- Scorecard: 20 of 20 test releases pass. 13 are built with the organizers' `make_release.py` (swaps, copies, losses and relabels across all five files, chains of swaps, combinations, and a no-change release). 7 more test changes their generator can't make: edited values, a removed protein row, edited survival outcomes, a renamed sample id, and three damaged releases (a truncated file, a comma-separated file and an empty file), which are refused with Insufficient Evidence instead of crashing. Their answers are written into `EXPECTED.json` when each release is built, before the tool runs. Every planted sample found, nothing extra reported, about a second per release. We also built 481 releases with the organizers' generator at random settings: 476 match its answer keys exactly. In four of the other five, the answer key lists a change that left no trace in the data (a copy that a later change deleted, or a value changed and then changed back); the fifth is a copy whose original was later removed, which the tool reports as a rename.
- Research-question cards and verdicts work: eight cards (`cards/`) cover all four verdicts, and the verdict changes when the question or the release changes (for example, overall survival in Luminal A is Blocked while progression-free interval in the same tumors is not; ESR1 expression vs ER status is Insufficient Evidence on the practice envelope because envelopes have no RNA; and ER-alpha by ER status is Conditional even on release A, because requiring protein data shifts the group's hospital mix by 0.155, over the card's 0.15 limit).
- Does the conclusion still hold? Each change's own effect is measured by undoing it alone and rerunning the analysis, so severity rests on a number (on the practice envelope this reproduces the organizers' reference severities: swap high, copies high, lost samples medium). For A1 the tool also reports a 95% range of the ER+ minus ER- difference from 1,000 resamples, with and without the flagged samples.
- The review screen works (`python -m streamlit run app.py --server.address localhost`), in five pages: Overview, What changed, Evidence, Review and sign-off, and Fool the Tower. The Overview shows the verdict, what to do next, what the tool can't tell you, and a question board with the verdict for every research question on the same release. The Analyses view (on the Evidence page) runs the organizers' own `reference_analyses.py` on the same release so a judge can see the numbers match.
- Two ways to test the answers themselves: the error budget says how many worst-case errors an answer survives (on release A the ER-alpha answer survives 63 swaps between ER groups), and Fool the Tower lets a judge plant errors with the organizers' generator and see the tool's score.
- The nine release A data checks are built and merged to main: `survival.py`, `labels.py`, `coverage.py` and `design.py` in `tower/checks/`. Next: the 9 PM dry run and the demo video. Who does what, and what was added on Friday: [docs/PLAN.md](docs/PLAN.md).

## Quick start (fresh machine)

Needs Python 3.10 or newer and git. Put both repositories in the same folder.

Check `python3 --version` first. If it says 3.9 (the built-in Python on many Macs), the install below fails with "No matching distribution found for altair>=6.3": install Python 3.12 (python.org, or `brew install python@3.12`) and run the venv command with `python3.12` instead of `python3`.

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
cd identity-crisis-control-tower
```
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

### Required output (what the organizers' checker reads)

- **`findings.json`** in the shared format v0.2: one finding per change, every affected sample cited, nothing that didn't change. Example from the practice envelope: [examples/practice/findings.json](examples/practice/findings.json) (passes `format/validate.py`), with its plain-English report [examples/practice/report.md](examples/practice/report.md).
- On Saturday the envelope command writes it to `out/E<number>/findings.json` (for example `out/E07/findings.json`) with `report.md`, and runs the organizers' validator on it.
- With `--card all`, each research question also gets `readiness.json` and `.md` in `out/E<number>/readiness/`: the verdict, the reasons, what the tool can't tell you, the next steps and the evidence trail.

### The review screen

```bash
python -m streamlit run app.py --server.address localhost
```

Opens http://localhost:8501. Pick a release (an opened envelope, a test release, or release A alone) and a research question in the sidebar. The screen has five pages: **Overview** (the verdict and a one-line summary, the counts, the question board, what to do next and what the tool can't tell you), **What changed** (every finding with its samples, and a before-and-after table of the values behind each one), **Evidence** (every check with its rule and source, the analyses rerun, and the evidence trail), **Review and sign-off**, and **Fool the Tower**. In **Review and sign-off**, a reviewer enters a name and role, then approves, rejects or asks for more evidence on every proposed fix and problem (a reason is required to reject or ask for more), then signs off. The sign-off decision starts from the verdict, approving a Blocked or Insufficient Evidence verdict needs a note, and changing any decision afterwards withdraws the sign-off.

**Error budget** (under the verdict on the Overview, and in the Analyses view): how wrong the data can get before the answer changes, counted in the errors the tool detects. On release A the ER-alpha answer survives 63 worst-case swaps between ER groups, 125 wrong ER labels or 146 copied profiles, and the screen says how much of that each release used.

**Fool the Tower** (its own page): plant your own errors (swaps, copies, changed labels) and the organizers' `make_release.py` builds that release; the tool then looks for them without the answer key and is scored against it. Only `out/fool/` is written.

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
python ../oncosys-hackathon-challenge/data/tcga-brca/make_release.py
```
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
| `tower/diff.py` | Explains each change: swaps and chains, copies, losses, gains, relabels, blanked or edited values, and sample ids on more than one row (join_inflation) |
| `tower/analyses.py` | A1 and A2, matching the organizers' `reference_analyses.py`, and which changes touch them |
| `tower/findings.py` | Writes `findings.json`: one finding per change, every affected sample cited, severity with its reason |
| `tower/cards.py` | Loads research-question cards and works out which samples each question studies |
| `tower/questions.py` | Builds a card from the choices in the screen's "Ask your own question" form |
| `tower/evidence.py` | The before-and-after values behind every cited sample |
| `tower/budget.py` | The error budget: how many worst-case errors an answer survives |
| `tower/plant.py` | Fool the Tower: plants errors with the organizers' generator and scores the tool |
| `tower/doctor.py` | `python -m tower doctor`: is this machine ready for the sealed envelope? |
| `tower/readiness.py` | The verdict (Ready, Conditional, Blocked, Insufficient Evidence), its reasons and the evidence trail |
| `tower/checks/` | The checks cards run: question-reasoning rules (`fitness.py`), the bias check (`bias.py`) and the release A data checks (`survival.py`, `labels.py`, `coverage.py`, `design.py`) |
| `cards/` | Eight research-question cards |
| `tower/cli.py` | `compare`, `envelope`, `cards` and `check` commands |
| `tower/review.py` | Review decisions, the sign-off, and the exports |
| `app.py` | The review screen (Streamlit): Overview, What changed, Evidence, Review and sign-off, Fool the Tower |
| `.streamlit/config.toml` | The screen's light theme, and serving it on this machine only |
| `tests/releases/` | Configs for the scorecard's test releases |
| `scripts/scorecard.py` | Scores the tool against the generator's answer keys |
| `scripts/make_adversarial.py` | Builds the 7 test releases the organizers' generator can't make, each with its answer written first |
| `scripts/try_check.py` | Runs one check for every card that lists it, on release A and the practice envelope, and flags contract problems |
| `docs/` | Team plan, user research, contracts and the demo script |
| `examples/practice/` | The tool's output on the organizers' practice envelope: `findings.json` (passes their validator) and the plain-English `report.md` |

## Third-party code and licenses

No third-party code is copied into this repo, and it contains no third-party fonts, scripts or images (the screen uses system fonts only). At run time the tool calls two of the organizers' scripts from the challenge repo, unchanged: `envelopes/unseal.py` and `format/validate.py`.

| Package | Version | License | Used for |
|---|---|---|---|
| pandas | 3.1.1 | BSD-3-Clause | Reading and comparing the release tables |
| NumPy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Numeric matrices, fingerprints, resampling |
| PyYAML | 6.0.3 | MIT | Reading the research-question cards |
| Streamlit | 1.67.0 | Apache-2.0 | The review screen (`app.py`) |
| Altair | 6.3.0 | BSD-3-Clause | Charts on the review screen (installed with Streamlit) |
| jsonschema | 4.26.0 | MIT | Used by the organizers' `format/validate.py` to check `findings.json` |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Used by the organizers' `envelopes/unseal.py` to open the sealed envelopes |

Versions are the ones installed when this list was made; `requirements.txt` sets minimums only.

### Data sources and credits

| Data | Source | License |
|---|---|---|
| TCGA-BRCA clinical, mutation, copy number, RNA and protein files | UCSC Xena TCGA hub, fetched with `data/tcga-brca/fetch.py` from the [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge) (checksums verified; not committed here) | TCGA open-access data (see the challenge repo's `DATA_LICENSES.md`) |
| TCGA-BRCA curated survival | TCGA Pan-Cancer Clinical Data Resource, via UCSC Xena | As above |

- TCGA: "The results shown here are in whole or part based upon data generated by the TCGA Research Network: https://www.cancer.gov/tcga."
- UCSC Xena: Goldman, M.J. et al. Visualizing and interpreting cancer genomics data via the Xena platform. *Nat Biotechnol* 38, 675–678 (2020).
- Survival data: Liu, J. et al. An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive High-Quality Survival Outcome Analytics. *Cell* 173, 400–416 (2018).
- Subtype and HER2 columns (cited by the label and design checks): Cancer Genome Atlas Network. Comprehensive molecular portraits of human breast tumours. *Nature* 490, 61–70 (2012).
- PAM50 (cited by the model-design rule): Parker, J.S. et al. Supervised Risk Predictor of Breast Cancer Based on Intrinsic Subtypes. *J Clin Oncol* 27, 1160–1167 (2009).

No keys, tokens or private links are committed to this repo (.gitignore excludes .env, *.key and .streamlit/secrets.toml); a Gitleaks scan of the full history on Friday found none.

No AI model or API key is used.

The data is de-identified but patient-derived: research use only. This tool makes no diagnosis, treatment recommendation, risk score or clinical claim, and every finding asks a person to review it.

## Team

Identity_Crisis, Track 1 (Cohort Firewall):

- Aravind Sundaravadivelu
- Aakruti Ghatole
- Chirag Suthar
- Madhu Vadhani Madasamy
