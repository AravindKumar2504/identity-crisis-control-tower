# Identity_Crisis · Cohort Control Tower

Team Identity_Crisis's entry for the OncoSys Cancer AI Lab hackathon (The Open Accelerator, OncoSys AI, Northeastern University, Red Hat; November 11-14, 2026). Track 1: Cohort Firewall.

## The user and the one workflow

**User:** a research data engineer who keeps an analysis-ready copy of TCGA breast cancer data for the scientists who use it, and receives new releases of it. Who they are and what goes wrong for them, with sources: [docs/USER.md](docs/USER.md).

**Workflow they finish:** point the tool at a new release. It names every sample that changed (swapped, copied under a new id, missing, relabelled), reruns only the analyses those changes touch, says whether the release is still fit for the research question, and writes `findings.json` in the event's shared format so a reviewer can approve or reject each proposed fix.

## Status (Friday, November 13)

- Release comparison, A1/A2 reruns, `findings.json` and the sealed-envelope command work.
- On the organizers' practice envelope it reports the same swap, the same five copies with their sources, the same five lost samples and the same A1 result (3.051 to 3.019) as the organizers' reference output, and its file passes `format/validate.py`. Unsealing plus checking takes about 2 seconds.
- Scorecard: 13 test releases built with the organizers' `make_release.py` (swaps, copies, losses and relabels across all five files, chains of swaps, combinations, and a no-change release). Every planted sample found, nothing extra reported, every release checked in about a second.
- Next: research-question cards and verdicts, release A data checks, the review screen. Plan: [docs/PLAN.md](docs/PLAN.md).

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

### Saturday's sealed envelope (the live test)

From inside `identity-crisis-control-tower`, with the envelope number and four words the judge gives you:

```bash
python -m tower envelope practice orange meadow pilot lantern
```

It unseals the envelope with the organizers' `unseal.py`, compares the new release with release A, writes `out/<envelope>/findings.json` and `out/<envelope>/report.md`, and runs the organizers' validator. The practice code above is public; on Saturday use your own number and words.

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
| `tower/cli.py` | `compare` and `envelope` commands |
| `tests/releases/` | Configs for the scorecard's test releases |
| `scripts/scorecard.py` | Scores the tool against the generator's answer keys |
| `docs/` | Team plan and user research |

## Data and credits

Judged results use the event's frozen TCGA-BRCA release, fetched with the challenge repo's `data/tcga-brca/fetch.py` and checked against its published checksums. No raw TCGA files are committed here. Data credits: `DATA_LICENSES.md` in the [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge).

The data is de-identified but patient-derived: research use only. This tool makes no diagnosis, treatment recommendation, risk score or clinical claim, and every finding asks a person to review it.

## Third-party code

No third-party code is copied into this repo. At run time the tool calls the organizers' `envelopes/unseal.py` and `format/validate.py` from the challenge repo. Libraries: pandas (BSD-3-Clause), NumPy (BSD-3-Clause), jsonschema (MIT), cryptography (Apache-2.0 or BSD-3-Clause, used by `unseal.py`).

## Team

Identity_Crisis. Members will be listed here.
