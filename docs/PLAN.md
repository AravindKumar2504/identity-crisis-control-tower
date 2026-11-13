# Team plan: Identity_Crisis · Cohort Control Tower

Five-minute read for the team. Track 1 (Cohort Firewall). Code freeze **Saturday 2:15 PM ET**; be at the Cabral Center by 10 AM (doors 9:30).

## The idea in one paragraph

A research engineer gets a new release of the TCGA breast cancer data. Our tool answers two questions: **what changed** (every swapped, copied, missing or relabelled sample, named one by one) and **is the data still fit for my research question** (Ready, Conditional, Blocked or Insufficient Evidence, with the reasons, the evidence trail and the fix). Other Control Tower teams answer only the first question. The rubric gives 40 of its 100 points to the second.

## How we are judged (official Track 1 rubric, event page)

| Points | Criterion | How we earn it |
|---|---|---|
| 20 | Finding data problems: material problems, nothing the data doesn't support | Exact release diff, plus real problems already in release A, reported only when they matter to the question |
| 20 | Reasoning for the research question: the result changes appropriately when the question changes | Research-question cards; the verdict and reasons change live when the card changes |
| 15 | Evidence and sources | A visible evidence trail (lineage) for every verdict, plus cited sources |
| 15 | Safety and uncertainty (full points need a visible human review step and an evidence record) | Release sign-off gate, confidence on every finding, robustness check, no clinical claims |
| 15 | Working tool and clear setup | One command from a fresh clone; envelope to `findings.json` in under a minute |
| 10 | Useful next steps | Fixes sized to the problem, each with the evidence needed to reconsider |
| 5 | Communication | A plain-English summary at the top |

**Live test on Saturday:** at the start of our Q&A a judge gives us an envelope number and a four-word code. We run one command, and the tool must find the changes in a release it has never seen (5 files, no RNA). The organizers' checker compares our `findings.json` with their answer key and shows the judges the result.

## The four rules from the kickoff (founder's own words, paraphrased)

1. **Know the user.** He said the team that researches its user has an advantage. Our README and pitch open with the research engineer, their real pain, and real incidents. We also ask real data engineers in the Discord (questions in `docs/USER.md`).
2. **Show where every answer comes from.** AI is welcome, but its answers must be traceable. Every verdict links to the checks, the fields, the exact rows and the file fingerprints. Any AI-written sentence only restates facts the tool computed, with a link to them.
3. **Cite every changed sample, never an unchanged one.** We mirror the organizers' reference output: one finding per change, every affected sample listed as evidence. A missing RNA file is noted, never reported as a finding.
4. **Finish the main workflow first.** Nothing else starts mattering until the envelope-to-`findings.json` path works and validates.

## Two outputs, on purpose

- **`findings.json`**: only what changed between the two releases. This is what the checker scores, so it never contains anything else.
- **Readiness report** (`readiness.json` + the screen): the verdict for the chosen research question, problems already in release A (clearly labelled "already in release A"), the robustness check, the fixes and the review record.

## Research-question cards (first set)

Fields follow the organizers' card: intended use, group studied, outcome, acceptable limitations, not acceptable, out of scope. All numbers below were measured on the frozen release A.

| Card | Expected verdict on release A | Why |
|---|---|---|
| ER-alpha protein, ER-positive vs ER-negative primary tumors (A1) | Ready (Conditional when a release changes its samples) | Names every changed sample, shows before and after, says whether the conclusion still holds |
| PAM50 subtype mix of primary tumors (A2) | Conditional | The two subtype columns disagree on 52 of 508 tumors (10.2%); 257 primary tumors (23%) have no subtype |
| Overall survival by subtype, Luminal A focus | Blocked | Median follow-up 31.3 months (reverse Kaplan-Meier) with 151 deaths among 1,096 primary tumors, and 35.4 months for Luminal A; the TCGA survival resource (Liu et al., Cell 2018) advises against overall survival for Luminal A; 13 tumors with zero follow-up; 5 redacted tumors still carry survival values; 135 patients have duplicated survival rows (tumor + normal) |
| Same question with progression-free interval, one row per patient | Conditional | PFI is recommended without reservation (145 events); the remaining caveats are listed |
| Train a subtype classifier from RNA | Blocked | The subtype label was computed from RNA (circular); 9 columns leak the label; the envelope has no RNA |
| Response to hormone therapy by ER-alpha level | Blocked | The release has no treatment or response data |
| HER2-positive group | Conditional | HER2 IHC and final status differ on 175 of 669 (106 equivocal results resolved by FISH, 38 real conflicts); IHC missing for 16.5% |
| Any question whose input file is missing or fails its fingerprint | Insufficient Evidence | The data's origin can't be confirmed |

## Problems already in release A (verified, for the readiness report)

- One person under two IDs: TCGA-AN-A0FE and TCGA-AN-A0FG (TCGA redaction 2010, "Identical subject"); both still in `clinical.tsv`. The tool doesn't report it: neither sample is in any analysis, and the fact comes from outside annotations (RULES.md: don't link records to outside sources about individuals).
- Two subtype columns (`PAM50Call_RNAseq`, `PAM50_mRNA_nature2012`) disagree on 52 of 508 tumors. The two ER columns agree on all 780 (do **not** report an ER conflict).
- Survival: 6 rows marked Redacted (5 tumors still carry values), 13 tumors with zero follow-up, 135 patients with identical tumor and normal survival rows, OS events disagree with `OS_event_nature2012` for 28 of 816.
- Requiring protein data shifts the hospital (tissue source site) mix: total variation distance 0.137.
- 142 patients have more than one sample; 7 have both a primary and a metastatic sample; 66 samples have more than one diagnostic slide; 24 normal samples appear only in the slide manifest.
- 12 male patients; 9 ages capped at 90; one near-identical protein pair from two patients (TCGA-A2-A0SV and TCGA-A2-A0SW, r = 0.99).

## Build order (cut from the bottom if time runs out)

| Priority | Piece | Owner | Status / done when |
|---|---|---|---|
| P0 | Release diff (all 5 files), A1/A2 rerun, `findings.json`, envelope command | Aravind | **Done**: matches the organizers' reference output on the practice envelope in about 2 s; scorecard 20/20, plus 481 random releases from the organizers' generator (README) |
| P0 | README quick start | Aravind | **Done**; Chirag confirms it from a fresh clone |
| P0 | Scorecard: generated releases, answer keys written by the organizers' generator, no-change release | Aravind | **Done**: `scripts/scorecard.py`, configs in `tests/releases/` |
| P1 | Question cards + verdict rules + `readiness.json` with the evidence trail | Aravind | **Done** (Fri): 8 cards with verdicts, reasons, next steps and the evidence trail |
| P1 | Release A checks with sources + A2 robustness (both subtype columns) | Aakruti | Each check returns `Issue`s (`tower/checks/`, docs/CONTRACTS.md) with evidence rows and a source |
| P1 | Screen: verdict, reasons, evidence trail, review and sign-off | Aravind | **Done** (Fri): question board, review and sign-off. Still to test at the dry run: a judge finishes it without us talking |
| P1 | Checkpoint 2: run our paired team's repo from a fresh folder using only their README, and run ours from scratch | Chirag | A list of what broke, posted in Discord and the group |
| P2 | README polish, demo video, 3-minute pitch built on docs/USER.md | Madhu | Rehearsed under 3 minutes |
| P2 | Optional: type a question in plain English, get an editable draft card (local model) | Chirag | Only if everything above is done |

## Timeline

- **Fri morning:** everyone sets up (below) and starts their piece against the contracts in `docs/CONTRACTS.md`.
- **Fri ~1 PM:** Chirag confirms our README works from a fresh clone; we send our repo and commit to our Checkpoint 2 pair and run theirs.
- **Fri 2 PM call:** demo the engine, lock the cards, the checks and the screen layout.
- **Fri 9 PM:** everything merged; full dry run on the practice envelope plus every card.
- **Sat morning:** fixes from the pair, video, rehearsal; freeze at 2:15 PM.

## How we work

- Post in the team group before starting anything new, so nobody builds the same thing twice.
- Work on your own branch and open a pull request; Aravind merges.
- Build against `docs/CONTRACTS.md`. If you need a new field, add it there first and tell the group.

## Setup (everyone)

```bash
git clone https://github.com/disleveK/oncosys-hackathon-challenge.git
```
```bash
cd oncosys-hackathon-challenge && pip install -r requirements.txt && python data/tcga-brca/fetch.py
```
```bash
python envelopes/unseal.py practice orange meadow pilot lantern
```

Clone this repo **next to** the challenge repo (same parent folder).

## The 3-minute demo

The full script, with timings, clicks and the envelope steps, is in [DEMO.md](DEMO.md).

1. Hook (20 s): same files, same 747 protein samples, but two swapped, five copied and five gone. A row count sees nothing.
2. New release (60 s): every changed sample named; the lost ones are all HER2-enriched; only A1 rerun, A2 left alone; the conclusion holds, with the numbers.
3. Change the question (60 s): overall survival in Luminal A is Blocked, with the source; switch to progression-free interval and the block is gone.
4. Review (30 s): a person approves or rejects each fix and signs off; the evidence trail exports with it.
5. Close (10 s): the scorecard.

## Rules we never break

No clinical claims, diagnosis, treatment advice or risk scores. No re-identification and no linking to outside records about individuals. No keys or secrets in the repo; no raw TCGA files committed. AI runs on a local model or the user's own key and shows its sources.
