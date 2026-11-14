# Team plan: Identity_Crisis · Cohort Control Tower

Ten-minute read for the team. Track 1 (Cohort Firewall). Code freeze **Saturday 2:15 PM ET**; be at the Cabral Center by 10 AM (doors 9:30).

## Status, Saturday November 14

- All nine release A checks are built and merged (`survival.py`, `labels.py`, `coverage.py` and `design.py` in `tower/checks/`), so nothing shows as pending on the screen.
- The README lists the team, links the demo video and has the current numbers. Aravind presents (see [DEMO.md](DEMO.md), Roles).
- 93 automated tests: `python -m unittest discover -s tests` (README, Run the tests).
- The assignments below are Friday's plan, kept as the record of who built what. Before the demo: `git pull` in both repos, `python -m tower doctor --full`, then the steps under "Saturday (everyone)".

## Friday and Saturday: who does what (read this first)

Aravind may be asleep for a while, so everything you need is here. The remaining work is split three ways, about 4 to 5 hours each, and **nobody edits the same files**, so you can all work at the same time without merge conflicts. If something here is unclear, use your best judgment, write down what you decided in your pull request, and post it in the group.

### Start here (everyone, 10 minutes)

1. Get the latest code: `git pull` in both repos (or clone, see Setup below), then activate the venv.
2. From inside `identity-crisis-control-tower`, run `python -m tower doctor`. It must end with "Ready for the sealed envelope." If it doesn't, follow the fix it prints.
3. Make your branch: `git checkout -b aakruti/checks`, `chirag/checks` or `madhu/docs`.
4. Madhu and Chirag: until Aravind adds you to the repo, fork it on GitHub and open pull requests from your fork. Send Aravind your GitHub username in the group.
5. Post "starting" in the group.

### What's new since this plan was first posted (Friday morning)

Your assignments didn't change: the same files, checks, expected numbers and status rules. Two things were added: the organizers ruled that redacted survival rows are kept but flagged (`survival_redacted` warns; it never drops a row), and our Checkpoint 2 pair is Highlanders. Every member attends on Saturday.

Aravind added the following (all pushed, so `git pull` gets it):

- **The screen is now five pages**, with a menu at the top:
  - **Overview:** the verdict with a one-line summary, four counts (changes found, changes that touch the question, decisions made, sign-off), the error budget, the question board, the next steps, and what the tool can't tell you.
  - **What changed:** every finding with its samples and the before-and-after values.
  - **Evidence:** three tabs: Checks and reasons, Analyses, and Evidence trail.
  - **Review and sign-off:** the reviewer now types a name and role here, not in the sidebar.
  - **Fool the Tower:** see below.
  - The sidebar keeps the release picker, the sealed-envelope opener, the question picker, "Ask your own question" and Settings (the "List unbuilt checks as pending" switch).
- **Bias check** `site_shift` (`tower/checks/bias.py`): compares the hospital (tissue source site) mix of the question's group with all primary tumors. The ER-alpha group shifts by 0.155, over its card's 0.15 limit, so that card is Conditional even on release A. The HER2 group (0.137) passes.
- **What this can't tell you:** on the Overview, up to three things the result can't tell you, taken from the `limitation` of the checks and changes that decided the verdict.
- **The samples this question can use:** a CSV download under "About this question" on the Overview, and `group_samples` in `readiness.json`.
- **Error budget** (`tower/budget.py`): how many worst-case errors an answer survives before its 95% range touches zero, and how many the release made. On release A the ER-alpha answer survives 63 swaps between ER groups, 125 wrong ER labels or 146 copied profiles, and Luminal A stays the most common subtype unless 115 tumors are relabelled. The practice envelope used 5 of the 141 copied profiles (4%).
- **Fool the Tower** (`tower/plant.py`): a judge picks errors, the organizers' `make_release.py` builds that release, and the tool looks for the errors without the answer key, then is scored against it (for example "found 9 of the 9 planted samples, with 0 false alarms"). It writes only to `out/fool/`.
- **The official sample list as evidence** (`tower/diff.py`): a finding's notes now cite the organizers' `sample_manifest.csv` when it contradicts a copy or doesn't explain a lost sample. The samples cited and the finding kinds are unchanged.
- **README:** a "Required output" section that links `findings.json`, as the judging page asks.
- **DEMO.md:** names our user, says one limit aloud, adds the error budget and a Fool the Tower move for Q&A, and follows the new pages. Madhu: pull before you edit it.

**Status, Friday 10:30 AM:** all nine release A checks below were still to build, and the board marked them as pending (for example "Ready · 4 pending" for PFI in Luminal A). **Since Friday evening all nine are built and merged**; the cards table further down gives the verdict expected with every check built.

### Who owns which files

| Person | Creates or edits only these | Everything else |
|---|---|---|
| Aakruti | `tower/checks/survival.py`, `tower/checks/labels.py` | don't edit |
| Chirag | `tower/checks/coverage.py`, `tower/checks/design.py` | don't edit |
| Madhu | the README **Team** section and video link, `docs/DEMO.md`, `docs/USER.md` | don't edit |
| Aravind | `app.py`, `.streamlit/`, `cards/`, the rest of `tower/` (including `tower/checks/bias.py`, `tower/checks/fitness.py`, `tower/budget.py` and `tower/plant.py`), `docs/CONTRACTS.md`, the rest of the README | |

Need a change in someone else's file? Post the exact change in the group instead of editing it. Don't rename checks, don't change the cards, and don't change the `Issue` fields: the cards and the screen already expect them.

### How to write a check (Aakruti and Chirag)

- Copy the pattern of the built checks in `tower/checks/fitness.py` and the contract in [CONTRACTS.md](CONTRACTS.md) section 2. A check is a function `fn(release, card)` with `@register("<exact name>")` above it, returning a list of `Issue`s.
- `release.table("clinical.tsv").frame` and `release.table("survival.tsv").frame` are text tables indexed by sample id. `card_group(release, card)` gives the card's samples. For **missing values**, use `card_base_group(release, card)` instead (the group before its value filters; inside the card's own group the blanks were already dropped). Both are in `tower/cards.py`, and `BLANKS` there lists what counts as blank.
- Status: `pass` (fine), `warn` (usable with conditions: makes the verdict Conditional), `block` (makes it Blocked). Use `material=False` for a pass that doesn't matter to the card.
- Fill `rows` with every sample id involved, `numbers` with the counts, `fields` as `"file:column"`, and for a warn: `rule` (with the threshold), `source`, `next_step` and `evidence_needed`.
- One Issue per problem. If one check reports several problems, give each its own id: `missing_values_ER`, `missing_values_HER2_IHC`.
- Where your check shows up on the screen: every check is listed on the Evidence page (Checks and reasons). When it decides the verdict (a `warn` for Conditional, a `block` for Blocked), its `title` becomes one of the reasons, its `next_step` joins "What to do next" (the Overview shows the first three), and its `limitation` joins "What this can't tell you". Every `warn`, `block` or `unknown` also needs the reviewer's decision on the Review and sign-off page. So write all of them for someone who isn't a specialist. To see yours, restart the screen and open a card that lists your check.
- Test as you go: `python scripts/try_check.py <name>` runs your check for every card that lists it, on release A and on the practice envelope, and flags contract problems. `python -m tower check --card <card id>` shows the card's verdict with your check in it.
- **Expected answers on release A are given below.** If your number differs, trust the data, write down how you counted, and post it.

### Aakruti: release A checks, part 1 (about 4.5 hours)

These five decide verdicts, so they come first.

| Check | File | Cards | What to compute | Expected on release A | Status rule |
|---|---|---|---|---|---|
| `survival_redacted` | survival.py | os-luminal-a, pfi-luminal-a | Samples in the card's group whose `survival.tsv` row has a value in `Redaction` | 2 in each card's group: TCGA-A7-A0DC-01, TCGA-AR-A0U1-01 (release A has 6 redacted rows, 5 of them primary tumors) | warn if any; next step: keep them, but have a person review them before use (the organizers' ruling on Discord: keep redacted survival rows, but flag them) |
| `survival_zero_time` | survival.py | os-luminal-a, pfi-luminal-a | Group samples whose `<endpoint>.time` is 0 (endpoint = `card["endpoint"]["name"]`) | 11 for OS, 11 for PFI | warn if any; next step: exclude and report them |
| `patient_double_count` | survival.py | os-luminal-a, pfi-luminal-a | Patients (`_PATIENT`, or the first 12 characters of the id) with more than one sample in the card's group | 0, so `pass` (material=False). Put in `numbers` that 135 patients have identical survival rows on more than one sample (128 tumor + normal, 4 tumor + normal + metastasis, 3 tumor + metastasis), which would count twice if those samples were included | warn if any patient appears twice |
| `subtype_columns_disagree` | labels.py | subtype-mix, os-luminal-a, pfi-luminal-a | `PAM50Call_RNAseq` vs `PAM50_mRNA_nature2012` among group samples with both filled, mapping LumA to Luminal A, LumB to Luminal B, Basal to Basal-like, Her2 to HER2-enriched, Normal to Normal-like | 52 of 508 disagree (10.2%) | warn if the share is above `card["limits"]["subtype_disagreement"]` (0.05; use 0.05 when a card has no limit); next step: name the subtype column used and report the result under both |
| `her2_field_conflict` | labels.py | her2-positive-protein | `lab_proc_her2_neu_immunohistochemistry_receptor_status` vs `HER2_Final_Status_nature2012` among group samples with both filled | 146 of 551 differ: 105 where IHC was Equivocal and FISH decided, 29 Positive vs Negative | warn if any Positive vs Negative conflict; next step: define HER2 status from `HER2_Final_Status_nature2012` (it includes FISH) and list the 29 |

Sources to cite: the TCGA Pan-Cancer Clinical Data Resource (Liu et al., Cell 2018) for the survival checks, and the TCGA BRCA paper (Nature 2012) for the subtype and HER2 columns.

**Done when** `python scripts/try_check.py <name>` shows no contract problems for all five, and `python -m tower check --card os-luminal-a --allow-missing-checks` no longer lists them as not built. Open one pull request from `aakruti/checks`.

### Chirag: Checkpoint 2, then release A checks, part 2 (about 4.5 hours)

**1. Checkpoint 2 first (the organizers require it today, about 1 hour).**
- Clone our repo into an empty folder, follow only the README Quick start, and run `python -m tower doctor --full`. Write down every step that broke or confused you.
- **Our pair is Highlanders** (the organizers posted the pairs on Discord, Thursday 5:59 PM). They haven't posted anything yet, so post first in #oncosys-hackathon: our repo link (https://github.com/AravindKumar2504/identity-crisis-control-tower) and the exact commit (`git log -1 --format=%h`), and ask for theirs. Reply "swapped" there once links are exchanged.
- Run their repo from an empty folder using only their README, and send them what broke or was unclear. They do the same with ours; fix what they find before Saturday.
- Post what worked and what broke, for both repos, in Discord and in our group.

**2. Then four checks.**

| Check | File | Cards | What to compute | Expected on release A | Status rule |
|---|---|---|---|---|---|
| `subtype_missing` | coverage.py | subtype-mix | Share of `card_base_group` (all primary tumors) with a blank `PAM50Call_RNAseq` | 257 of 1,101 (23.3%) | warn if above `card["limits"]["missing_fraction"]` (0.10); next step: report the subtype mix with the missing share, and don't treat the missing tumors as missing at random |
| `missing_values` | coverage.py | er-alpha-by-er, her2-positive-protein, esr1-expression-vs-er | For each clinical field the card reads (`card["uses"]["clinical.tsv"]`), the share of `card_base_group` with a blank value. One Issue per field, id `missing_values_<field>` | ER-alpha card: ER blank for 42 of 742 (5.7%), pass. HER2 card: IHC blank for 111 of 742 (15.0%) and final status for 110 of 742 (14.8%), both warn. ESR1 card: 50 of 1,097 (4.6%), pass | warn if above `limits.missing_fraction` (0.10); a pass is `material=False` |
| `leakage_columns` | design.py | subtype-classifier-rna | Which of the 9 subtype-derived clinical columns are in `card["features"]`: `PAM50Call_RNAseq`, `PAM50_mRNA_nature2012`, `SigClust_Intrinsic_mRNA_nature2012`, `SigClust_Unsupervised_mRNA_nature2012`, `Integrated_Clusters_no_exp__nature2012`, `Integrated_Clusters_unsup_exp__nature2012`, `Integrated_Clusters_with_PAM50__nature2012`, `RPPA_Clusters_nature2012`, `CN_Clusters_nature2012` | None (the card learns from RNA only), so pass, with the 9 listed in `numbers` as columns to keep out | block if any is a feature; next step: drop them from the features |
| `a2_robustness` | design.py | subtype-mix | A2's subtype shares computed with each subtype column, among primary tumors with both calls (508), side by side | Luminal A 51.0% vs 44.9% (6.1 points), Luminal B 20.1 vs 24.2, Basal-like 18.1 vs 18.5, HER2-enriched 8.9 vs 11.0, Normal-like 2.0 vs 1.4 | warn if any share differs by 5 points or more (expected: warn, for Luminal A); next step: report the subtype mix under both columns, or say which one is used and why |

**Done when** `python scripts/try_check.py <name>` shows no contract problems for all four. Open one pull request from `chirag/checks`.

### Madhu: story, demo and outreach (about 4.5 hours)

1. **README Team section** (5 minutes): replace "Members will be listed here." with our four names. Pull request from `madhu/docs`.
2. **Discord, this morning:**
   - Repair Review Desk handoff: the brief says Repair Review Desk teams import our `findings.json`. Post the link to `examples/practice/findings.json` (https://github.com/AravindKumar2504/identity-crisis-control-tower/blob/main/examples/practice/findings.json) in their channel and ask whether their tool imports it. Post any reply in our group; if one imports it, we say so on stage.
   - User research (the founder's "know your user" advice): post the questions in `docs/USER.md` to the mentors and to any data engineers in the Discord. Add 2 or 3 answers to `docs/USER.md`, with each person's OK, first name and role only, and send the best line to the group for the pitch.
   - Watch the organizers' announcements (judging, envelopes, FAQ) and post anything new in the group.
3. **Silent judge test** (with our paired team, after Chirag's checkpoint swap): run the screen on your laptop (`streamlit run app.py`), let someone from the paired team use it for 3 minutes without help, and write down where they got stuck. Watch whether they find the five pages in the top menu, and the reviewer name and role on the Review and sign-off page. Post the notes.
4. **Rehearse** `docs/DEMO.md` aloud twice with a timer (under 3 minutes). You own its wording now: fix any line that sounds unnatural, but keep the numbers unless the screen shows different ones. The click path is now: Overview, What changed, Evidence (Analyses tab), back to the Overview, then Review and sign-off.
5. **9 PM dry run:** play judge with the rubric at the top of this file. Score each line and post the three weakest points.
6. **After the dry run:** record the demo video (screen recording with your voice, following DEMO.md, under 3 minutes), upload it (YouTube unlisted, or Google Drive with "anyone with the link"), and put the link in the README Team section.

### Aravind (when awake)

Done Friday morning (pushed): the five-page screen, the bias check, what the tool can't tell you, the samples download, the error budget, Fool the Tower and the official sample list notes. Still to do: invite Madhu and Chirag, review and merge pull requests, run the 9 PM dry run, then the optional verified AI summary. On Saturday, clear old Fool the Tower runs before the demo, and submit the judging form (repo link, commit and video link) before 2:15 PM.

### Merging while Aravind is asleep

- Aakruti may merge a pull request that only adds files in `tower/checks/`, or only changes `docs/USER.md`, `docs/DEMO.md` or the README Team section, once its description includes the last lines of `python -m tower doctor --full` ending in "Ready for the sealed envelope."
- Anything else waits for Aravind.
- After a merge, everyone pulls and restarts the screen.

### If you get stuck

- **"No check named X is registered"**: the name in `@register("...")` must match the card's check name exactly, and the file must be in `tower/checks/`.
- **"A check file failed to load"** (the screen's sidebar or `try_check.py` shows the error): fix that file's import error; the rest of the tool keeps working meanwhile.
- **The screen still says "not built yet"**: pull, then restart the screen (an old screen keeps old code in memory).
- **Your number differs from this plan**: trust the data, write down how you counted, and post it.
- **You want a different threshold**: don't change the card; post the suggestion.
- **You're blocked**: post in the group what you tried; meanwhile move to your next task.
- **You can't find something on the screen**: the reviewer's name and role are on the Review and sign-off page; the analyses and the evidence trail are on the Evidence page; "List unbuilt checks as pending" is under Settings in the sidebar.
- **The release list shows "Planted release ..."**: those are Fool the Tower runs, kept in `out/fool/` (git ignores it). Delete that folder to clear them.

### What the judges want (from the organizers)

- Every working tool finds the same changes, so show what happens after: why it matters, what the user should do next, and what the tool can't tell them (Discord, Friday 8:55 AM). Where we show it: on the Overview, the verdict and its reasons, then "What to do next" beside "What this can't tell you"; on What changed, "Why it matters" under each finding.
- One result a judge can verify and one limitation they can inspect, and a judge can use the tool without us narrating (challenge README and slides). To verify: the Analyses tab runs the organizers' own script on the same release, every finding has a before-and-after table, and Fool the Tower scores the tool on errors the judge plants. To inspect: the "What this can't tell you" box.
- Cohort Firewall must prove which samples can answer the question (slides). Where we show it: the samples download under "About this question" on the Overview.
- The unseen input can be a changed release or a changed research question (event page). We handle both: the envelope command and "Ask your own question".
- The required data problems include missing values, unlikely values, unclear field meanings, bias, information that gives a model a shortcut, and missing source details (event page). Ours: bias is `site_shift` (built); missing values are `missing_values` and `subtype_missing` (Chirag); unlikely values include `survival_zero_time` (Aakruti); unclear field meanings are `subtype_columns_disagree` and `her2_field_conflict` (Aakruti); shortcuts are `leakage_columns` (Chirag) and `label_derivation` (built); a missing or unreadable file gives Insufficient Evidence (`inputs_present`, built).
- Judges are mostly industry and startup people plus a hospital researcher, so say everything plainly.

### Saturday (everyone)

- Every team member attends (the organizers' rule).
- At the Cabral Center by 10 AM (doors 9:30), laptop charged, charger with you.
- `git pull` in both repos, then `python -m tower doctor --full`.
- One full rehearsal around 11. Code freeze at 2:15 PM: no pushes after that.
- Before the demo, set the screen up as DEMO.md's "Before you start" says: the practice envelope, the ER-alpha question, and a reviewer name and role on the Review and sign-off page.
- Demo: Aravind speaks and drives (a teammate can drive instead). The sealed-envelope steps are in [DEMO.md](DEMO.md).

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

Fields follow the organizers' card: intended use, group studied, outcome, acceptable limitations, not acceptable, out of scope. All numbers below were measured on the frozen release A. The first verdict column is what the screen showed on Friday morning, with the unbuilt checks pending; the next is the verdict expected with every check built. Print the current verdicts with `python -m tower check --card all`.

| Card (id) | Friday morning on release A (checks pending) | With every check built | Why |
|---|---|---|---|
| ER-alpha protein, ER-positive vs ER-negative primary tumors, A1 (`er-alpha-by-er`) | Conditional, 1 pending | Conditional | The group's hospital mix shifts by 0.155, over the card's 0.15 limit (`site_shift`); ER is blank for only 5.7%. On a new release it also names every changed sample, shows before and after, and says whether the conclusion still holds |
| ESR1 gene expression vs clinical ER status (`esr1-expression-vs-er`) | Ready, 1 pending | Ready on release A; Insufficient Evidence on an envelope | ER is blank for 4.6% (passes); envelopes have no RNA |
| PAM50 subtype mix of primary tumors, A2 (`subtype-mix`) | Ready, 3 pending | Conditional | The two subtype columns disagree on 52 of 508 tumors (10.2%); 257 primary tumors (23%) have no subtype; Luminal A is 51.0% under one column and 44.9% under the other |
| Overall survival by subtype, Luminal A focus (`os-luminal-a`) | Blocked, 4 pending | Blocked | Median follow-up 31.3 months (reverse Kaplan-Meier) with 151 deaths among 1,096 primary tumors, and 35.4 months for Luminal A; the TCGA survival resource (Liu et al., Cell 2018) advises against overall survival for Luminal A; 13 tumors with zero follow-up; 5 redacted tumors still carry survival values; 135 patients have identical survival rows on more than one sample (128 tumor + normal, 4 tumor + normal + metastasis, 3 tumor + metastasis) |
| Same question with progression-free interval, one row per patient (`pfi-luminal-a`) | Ready, 4 pending | Conditional | PFI is recommended without reservation (145 events); in the group, 2 redacted rows and 11 with zero follow-up, and the subtype columns disagree |
| Train a subtype classifier from RNA (`subtype-classifier-rna`) | Blocked, 1 pending | Blocked | The subtype label was computed from RNA (circular); 9 columns leak the label; the envelope has no RNA |
| Response to hormone therapy by ER-alpha level (`hormone-therapy-response`) | Blocked | Blocked | The release has no treatment or response data |
| HER2 protein in HER2-positive vs HER2-negative tumors (`her2-positive-protein`) | Ready, 2 pending | Conditional | In the group, HER2 IHC and the final status differ on 146 of 551 (105 equivocal results resolved by FISH, 29 positive vs negative); IHC is blank for 15.0% and the final status for 14.8%. Its hospital mix (0.137) passes |
| Any question whose input file is missing or fails its fingerprint | Insufficient Evidence | Insufficient Evidence | The data's origin can't be confirmed |

## Problems already in release A (verified, for the readiness report)

- Two subtype columns (`PAM50Call_RNAseq`, `PAM50_mRNA_nature2012`) disagree on 52 of 508 tumors. The two ER columns agree on all 780 (do **not** report an ER conflict).
- Survival: 6 rows marked Redacted (5 tumors still carry values), 13 tumors with zero follow-up, 135 patients with identical survival rows on more than one sample (128 tumor + normal, 4 tumor + normal + metastasis, 3 tumor + metastasis), OS events disagree with `OS_event_nature2012` for 28 of 816.
- Requiring protein data shifts the hospital (tissue source site) mix: total variation distance 0.155 for the ER-alpha card's group (over its 0.15 limit, so `site_shift` warns) and 0.137 for the HER2 card's group (passes).
- 142 patients have more than one sample; 7 have both a primary and a metastatic sample; 66 samples have more than one diagnostic slide; 24 normal samples appear only in the slide manifest.
- 12 male patients; 9 ages capped at 90; one near-identical protein pair from two patients (TCGA-A2-A0SV and TCGA-A2-A0SW, r = 0.99).

## Build order (cut from the bottom if time runs out)

| Priority | Piece | Owner | Status / done when |
|---|---|---|---|
| P0 | Release diff (all 5 files), A1/A2 rerun, `findings.json`, envelope command | Aravind | **Done**: matches the organizers' reference output on the practice envelope in about 2 s; scorecard 20/20, plus 481 random releases from the organizers' generator (README) |
| P0 | README quick start | Aravind | **Done**; Chirag confirms it from a fresh clone |
| P0 | Scorecard: generated releases, answer keys written by the organizers' generator, no-change release | Aravind | **Done**: `scripts/scorecard.py`, configs in `tests/releases/` |
| P1 | Question cards + verdict rules + `readiness.json` with the evidence trail | Aravind | **Done** (Fri): 8 cards with verdicts, reasons, next steps and the evidence trail |
| P1 | Release A checks with sources + A2 robustness (both subtype columns) | Aakruti (5), Chirag (4) | **Done** (Fri): nine checks in `tower/checks/`, each returning `Issue`s with evidence rows and a source; unit tests in `tests/` |
| P1 | Screen: verdict, reasons, evidence trail, review and sign-off | Aravind | **Done** (Fri): five pages with a top menu (Overview, What changed, Evidence, Review and sign-off, Fool the Tower). Still to test at the dry run: a judge finishes it without us talking |
| P1 | Checkpoint 2: run our paired team's repo from a fresh folder using only their README, and run ours from scratch | Chirag | A list of what broke, posted in Discord and the group. For ours, `python -m tower doctor` checks the whole setup in one command |
| P1 | Bias check (`site_shift`), "What this can't tell you", the samples this question can use | Aravind | **Done** (Fri) |
| P2 | README Team section, demo video, 3-minute pitch (docs/DEMO.md), user research and Discord outreach | Madhu | Team section and demo video **done** (README); pitch in docs/DEMO.md |
| P2 | Ask your own question: a form builds a card from a few choices and judges it with the same rules | Aravind | **Done** (Fri). Optional next: a local model fills the form from a typed sentence (Chirag); the rules still decide |
| P2 | Error budget and Fool the Tower | Aravind | **Done** (Fri) |
| P2 | The official sample list cited in findings notes | Aravind | **Done** (Fri) |
| P2 | Verified AI summary (restates only computed facts, with links to them) | Aravind | Not built (optional) |
| P2 | Automated tests that run without the TCGA download | | **Done** (Sat): 93 tests in `tests/`, 75 of them on made-up releases |

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

1. Hook (20 s, Overview): still 747 protein samples, but two swapped, five copied and five gone. A row count sees nothing.
2. New release (60 s, What changed, then Evidence's Analyses tab, then back to the Overview): every changed sample named; the lost ones are all HER2-enriched; only A1 rerun, A2 left alone; the conclusion holds and survives 61 worst-case swaps; the next steps and what the tool can't tell you.
3. Change the question (60 s, the question board on the Overview): overall survival in Luminal A is Blocked, with the source; switch to progression-free interval and the block is gone.
4. Review (30 s, Review and sign-off): a person approves or rejects each fix and signs off; the evidence trail exports with it.
5. Close (10 s): the scorecard, then "hand us the envelope, plant your own errors, or ask your own research question".

## Rules we never break

No clinical claims, diagnosis, treatment advice or risk scores. No re-identification and no linking to outside records about individuals. No keys or secrets in the repo; no raw TCGA files committed. AI runs on a local model or the user's own key and shows its sources.
