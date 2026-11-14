# Contracts

Build against these so the pieces fit together. The release engine (`tower/release.py`, `tower/diff.py`, `tower/analyses.py`, `tower/findings.py`, `tower/evidence.py`), the question layer (`tower/cards.py`, `tower/readiness.py`, `tower/checks/fitness.py`, `tower/checks/bias.py`), the release A checks (`tower/checks/survival.py`, `labels.py`, `coverage.py`, `design.py`), the error budget (`tower/budget.py`), Fool the Tower (`tower/plant.py`) and the screen (`app.py`, section 6) are built; use them, don't rebuild them. If you need a new field, add it here first and tell the group.

## 1. Research-question card (`cards/<id>.yaml`)

Eight cards exist; `python -m tower cards` lists them. The text fields follow the organizers' card (`warmup/wisconsin/track1-cohort-firewall/question_card.md` in the challenge repo): `id`, `title`, `intended_use`, `group_studied`, `outcome`, `acceptable_limitations`, `not_acceptable`, `out_of_scope`. The fields the tool runs on:

| Field | Meaning |
|---|---|
| `uses` | Every file and column (or matrix row) the question reads, e.g. `survival.tsv: [OS, OS.time]`. An empty list means the whole file. Drives the evidence trail and which release changes touch the question. |
| `group` | Which samples the question studies: `sample_type` ("01"), `in_files` (must have data in these files), `values` (column: allowed values), `not_blank` (columns that must be filled). Read it with `card_group(release, card)` from `tower/cards.py`; never rebuild it in a check. |
| `checks` | The checks to run, by name (section 5). |
| `limits` | Thresholds the checks read, e.g. `missing_fraction: 0.10`, `site_shift_tvd: 0.15`, `subtype_disagreement: 0.05`. |
| `analyses` | Protected analyses the question depends on (`A1`, `A2`). |
| `endpoint` | For survival questions: `name` (OS, DSS, DFI, PFI) and `focus_subtype`. |
| `label`, `features` | For model-training questions: the label column and the files the model learns from. |
| `requires` | Data the question needs that may not exist: `need`, `columns_any`, `near_misses`, `why`, `next_step`, `evidence_needed`. |

## 2. A check (`tower/checks/<name>.py`)

```python
from tower.checks import Issue, register
from tower.cards import card_group

@register("survival_redacted")
def survival_redacted(release, card):
    group = card_group(release, card)
    ...
    return [Issue(id="survival_redacted", title="...", status="warn", material=True, ...)]
```

Any file in `tower/checks/` is picked up automatically. `release.table("survival.tsv").frame` gives a table of text values indexed by sample id (matrices have samples as columns). The `Issue` fields:

| Field | Meaning |
|---|---|
| `id` | The check name. When one check reports several problems, give each its own id (for example `missing_values_ER` and `missing_values_HER2`), so each gets its own review decision |
| `title` | One line a non-specialist understands, with the key number |
| `status` | `pass`, `warn` (usable with conditions), `block` (can't support this use), `unknown` (can't tell) |
| `material` | Does it matter **for this card**? Not applicable: return `pass` with `material=False` |
| `pre_existing` | True when the problem is already in release A (these never go into `findings.json`) |
| `fields` | Columns read, as `"file:column"` |
| `rows` | Every sample id involved (the evidence trail) |
| `numbers` | The counts behind the result |
| `rule` | The decision rule in words, including the threshold from `card["limits"]` |
| `source` | Citation or URL |
| `limitation` | What the check can't see |
| `next_step` | A fix sized to the problem |
| `evidence_needed` | What would change the result |

A check that crashes is reported as `unknown`, never as a crash of the whole report. A check file that fails to import doesn't stop the tool either: the screen names the file, and its checks show as not built.

Where an Issue shows up: every check is listed on the screen's Evidence page (Checks and reasons). When it decides the verdict (a `block` for Blocked, an `unknown` for Insufficient Evidence, a `warn` for Conditional), its `title` becomes one of the verdict's reasons, its `next_step` and `evidence_needed` join the next steps, and its `limitation` joins "What this can't tell you". Every material `warn`, `block` or `unknown` needs the reviewer's decision on the Review and sign-off page, whether or not it decided the verdict.

## 3. Verdict rule (`tower/readiness.py`, built)

Over the material issues for the card, in this order: any `block` gives **Blocked** (the data can't support the use, whatever else is true); any `unknown` gives **Insufficient Evidence**; any `warn`, or any release change touching what the card reads, gives **Conditional**; otherwise **Ready**. The reasons list every issue and release change that decided it. A check listed on a card but not built is `unknown`; `--allow-missing-checks` lists it as pending instead. Every check the eight cards list is built.

## 4. `readiness.json` (built)

Written by `python -m tower check --card <id>` (and by `envelope ... --card <id>`). Keys: `card`, `release`, `compared_with`, `group_size`, `verdict`, `reasons`, `summary` (plain English), `issues`, `checked_not_material`, `pending_checks` (listed on a card but not built yet), `release_changes`, `robustness` (A1: the 95% range of the ER+ minus ER- difference, with and without the flagged samples, and `range_method`: the bootstrap method, the number of resamples and the seed), `analyses`, `next_steps`, `review` (`required`, `items`, `signed_off`), `lineage` (each conclusion with its rule, source, fields, rows and file fingerprints), `fields_read`, `group_samples` (the sample ids the question can use), `cannot_tell` (what the result can't tell you), `error_budget` (worst-case errors the answer survives, and how many this release made), `generated`, `disclaimer`. The screen shows these two documents (section 6).

## 5. Checks the cards list

| Check | Owner | Status | What it should report on release A (verified numbers) | Cards |
|---|---|---|---|---|
| `inputs_present` | Aravind | built | Every file, column and row the card reads exists | all |
| `endpoint_suitability` | Aravind | built | TCGA curators' endpoint advice for breast cancer (OS blocked for Luminal A) | os-luminal-a, pfi-luminal-a |
| `label_derivation` | Aravind | built | A classifier's label isn't computed from its own inputs | subtype-classifier-rna |
| `outcome_available` | Aravind | built | The data the question needs exists, with near-miss fields shown | hormone-therapy-response |
| `subtype_columns_disagree` | Aakruti | built (`labels.py`) | `PAM50Call_RNAseq` vs `PAM50_mRNA_nature2012` (map LumA to Luminal A and so on): 52 of 508 primary tumors disagree (10.2%), above the 5% limit | subtype-mix, os-luminal-a, pfi-luminal-a |
| `subtype_missing` | Chirag | built (`coverage.py`) | 257 of 1,101 primary tumors (23.3%) have no `PAM50Call_RNAseq` (count over `card_base_group`) | subtype-mix |
| `a2_robustness` | Chirag | built (`design.py`) | A2's subtype shares under each subtype column, among the 508 tumors with both calls: Luminal A 51.0% vs 44.9% (6.1 points, so warn) | subtype-mix |
| `survival_redacted` | Aakruti | built (`survival.py`) | 2 in each card's group (TCGA-A7-A0DC-01, TCGA-AR-A0U1-01); the file has 6 redacted rows, 5 of them primary tumors. Flag them for review rather than dropping them (the organizers' ruling) | os-luminal-a, pfi-luminal-a |
| `survival_zero_time` | Aakruti | built (`survival.py`) | 11 in each card's group with `OS.time` (or `PFI.time`) of 0; 13 primary tumors in the whole file have `OS.time` of 0 | os-luminal-a, pfi-luminal-a |
| `patient_double_count` | Aakruti | built (`survival.py`) | 0 patients twice in each card's group (pass); 135 patients have identical survival rows on more than one sample (128 tumor + normal, 4 tumor + normal + metastasis, 3 tumor + metastasis), which would count twice if those samples were included | os-luminal-a, pfi-luminal-a |
| `duplicate_subjects` | Aakruti | dropped (Fri) | Not reported: neither sample is in any analysis, and the fact comes from outside annotations, which RULES.md asks us not to link | none |
| `site_shift` | Aravind | built (`bias.py`) | Hospital (tissue source site) mix of the card's group vs all primary tumors, as total variation distance: 0.155 for the ER-alpha card (over its 0.15 limit, so warn) and 0.137 for the HER2 card (pass). For a card that depends on A1 it also reruns A1 with each hospital holding at least 5% of its samples left out, and says whether the result holds each time | er-alpha-by-er, her2-positive-protein |
| `missing_values` | Chirag | built (`coverage.py`) | Share of `card_base_group` blank in each clinical field the card reads, against `limits.missing_fraction`: ER-alpha card 42 of 742 (5.7%); HER2 card IHC 111 of 742 (15.0%), final status 110 of 742 (14.8%); ESR1 card 50 of 1,097 (4.6%) | er-alpha-by-er, her2-positive-protein, esr1-expression-vs-er |
| `leakage_columns` | Chirag | built (`design.py`) | The 9 subtype-derived columns (PAM50, SigClust, Integrated_Clusters, RPPA_Clusters, CN_Clusters) a model must not use as features; none are features of the card, so pass | subtype-classifier-rna |
| `her2_field_conflict` | Aakruti | built (`labels.py`) | HER2 IHC vs `HER2_Final_Status_nature2012` in the card's group: 146 of 551 differ (105 IHC equivocal, 29 positive vs negative); 175 of 669 across all primary tumors | her2-positive-protein |

Step-by-step instructions, status rules and the test command are in `docs/PLAN.md`, "Friday and Saturday: who does what". The numbers above are counted on each card's own group in release A; if your check finds a different number, trust the data and tell the group.

Every check has unit tests in `tests/` that run on small made-up releases (`python -m unittest discover -s tests`); `tests/test_release_a_checks.py` also checks the release A numbers above when release A is fetched.

## 6. The screen (`app.py`, built)

The release and the question are picked in the sidebar, which also has the sealed-envelope opener, "Ask your own question" (`tower/questions.py`) and Settings. The menu at the top has five pages:

| Page | What it shows | Where it comes from |
|---|---|---|
| Overview | The verdict and a one-line summary; four counts (changes found, changes that touch the question, decisions, sign-off); the error budget; the question board (every card judged on the same release); the first three next steps; what this can't tell you; the full reasoning; the samples the question can use | `readiness.json`: `verdict`, `reasons`, `summary`, `next_steps`, `cannot_tell`, `error_budget`, `group_samples`; `findings.json` for the counts |
| What changed | The release check; a file-by-file count of identical, changed, missing and new samples (`file_summary` in `tower/diff.py`); sample counts per file; every finding with its samples, why it matters, its limitation, the before-and-after values and the proposed fix | `findings.json`; `tower/evidence.py` |
| Evidence | Checks and reasons (every check with its status, and for a problem its rule, source, numbers and samples); Analyses (A1 and A2 rerun, the robustness check, the error budget, and the organizers' own `reference_analyses.py` on the same release); Evidence trail (a graph from each change to its file, the analysis and this question, and every conclusion with its rule, source, fields, samples and file fingerprints) | `readiness.json`: `issues`, `next_steps`, `analyses`, `robustness`, `error_budget`, `lineage`, `fields_read`; `findings.json` |
| Review and sign-off | The reviewer's name and role, a decision on every proposed fix and every material problem, the sign-off, and the three exports | `findings.json` (`repairs`), `readiness.json` (`review.required`), `tower/review.py` |
| Fool the Tower | Plant errors with the organizers' generator, then the tool's score against its answer key | `tower/plant.py` |

Decisions are kept per release and question while you move between pages; changing any of them after the sign-off withdraws it.
