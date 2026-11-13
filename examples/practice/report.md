# Release check: practice against release-A

**Question:** Did release practice change anything that affects analyses A1 (ER-alpha protein by clinical ER status (primary tumors)) and A2 (PAM50 subtype mix of primary tumors)?

**Verdict: Conditional.** 3 findings touch what the question reads; A1 changed when rerun. A person must review the findings before this release is used.

Research use only. This report makes no clinical claim. A person must review every finding.

## What changed

### F1 · sample_swap · severity high · confidence high

In protein_rppa.tsv.gz, the profiles of TCGA-A8-A09K-01, TCGA-B6-A0WX-01 traded places between releases: each sample now carries another sample's data. Why it matters: The swapped samples sit in different ER groups (TCGA-A8-A09K-01 Positive, TCGA-B6-A0WX-01 Negative), so A1 now compares the wrong protein values in each group. Measured: undoing this change alone moves A1's ER+ minus ER- difference from 3.019 to 3.054 (1.16%).

Affects: A1. A1: 2 of these samples are in A1's group of samples; A2: A2 does not read protein_rppa.tsv.gz

Limitation: Fingerprints prove the profiles moved between ids; they cannot say which release labels them correctly. A person should confirm against the source before trusting either.

Evidence:
- sample `TCGA-A8-A09K-01` (protein_rppa.tsv.gz, release practice): now holds the profile TCGA-B6-A0WX-01 had in release-A
- sample `TCGA-B6-A0WX-01` (protein_rppa.tsv.gz, release practice): now holds the profile TCGA-A8-A09K-01 had in release-A
- protein `ERALPHA` (protein_rppa.tsv.gz, release practice): the protein row A1 reads

### F2 · duplicate · severity high · confidence high

In protein_rppa.tsv.gz, 5 sample ids carry a profile identical to another sample's profile from release-A, so the same measurements are counted twice. Why it matters: Copied profiles are counted twice in A1, which inflates a group with measurements that belong to other samples. Measured: undoing this change alone moves A1's ER+ minus ER- difference from 3.019 to 3.015 (0.12%).

Affects: A1. A1: 5 of these samples are in A1's group of samples; A2: A2 does not read protein_rppa.tsv.gz

Limitation: Identical profiles under two ids are almost never real biology; the tool cannot tell which id the measurements truly belong to.

Evidence:
- sample `TCGA-E2-A106-01` (protein_rppa.tsv.gz, release practice): identical to TCGA-C8-A133-01 (release-A)
- sample `TCGA-E2-A9RU-01` (protein_rppa.tsv.gz, release practice): identical to TCGA-EW-A1PE-01 (release-A)
- sample `TCGA-GM-A5PX-01` (protein_rppa.tsv.gz, release practice): identical to TCGA-E9-A2JT-01 (release-A)
- sample `TCGA-LL-A5YN-01` (protein_rppa.tsv.gz, release practice): identical to TCGA-AR-A1AP-01 (release-A)
- sample `TCGA-LL-A73Z-01` (protein_rppa.tsv.gz, release practice): identical to TCGA-E9-A1N3-01 (release-A)
- protein `ERALPHA` (protein_rppa.tsv.gz, release practice): the protein row A1 reads

### F3 · membership_change · severity medium · confidence high

In protein_rppa.tsv.gz, 5 samples present in release-A are missing from release practice (subtype: Her2 5; ER status: Negative 3, Positive 1, unknown 1); by subtype, it removes 5 of the 61 HER2-enriched primary tumors (8.2%) with data in this file; the total sample count is unchanged, so a count check would not notice. Why it matters: It changes which samples A1 uses, but the answer barely moves: undoing this change alone moves A1's ER+ minus ER- difference from 3.019 to 3.02 (0.03%).

Affects: A1. A1: 4 of these samples are in A1's group of samples; A2: A2 does not read protein_rppa.tsv.gz

Limitation: The tool sees that samples are missing or new, not why; a removal can be a legitimate redaction.

Evidence:
- sample `TCGA-A8-A08J-01` (protein_rppa.tsv.gz, release release-A): present in release-A, absent in practice
- sample `TCGA-C8-A12Q-01` (protein_rppa.tsv.gz, release release-A): present in release-A, absent in practice
- sample `TCGA-C8-A26Y-01` (protein_rppa.tsv.gz, release release-A): present in release-A, absent in practice
- sample `TCGA-E9-A1RH-01` (protein_rppa.tsv.gz, release release-A): present in release-A, absent in practice
- sample `TCGA-GM-A2DH-01` (protein_rppa.tsv.gz, release release-A): present in release-A, absent in practice
- protein `ERALPHA` (protein_rppa.tsv.gz, release practice): the protein row A1 reads

## Analyses

- **A1** (ER-alpha protein by clinical ER status (primary tumors)): changed. rerun because 3 finding(s) touch what A1 reads
  - before: `{"n_samples": 698, "n_positive": 529, "n_negative": 169, "mean_positive": 2.179, "mean_negative": -0.872, "difference": 3.051}`
  - after: `{"n_samples": 699, "n_positive": 533, "n_negative": 166, "mean_positive": 2.176, "mean_negative": -0.843, "difference": 3.019}`
- **A2** (PAM50 subtype mix of primary tumors): not_rerun. no change touches what A2 reads, so it was left alone
  - before: `{"n_samples": 844, "counts": {"Basal": 141, "Her2": 67, "LumA": 421, "LumB": 192, "Normal": 23}, "percent": {"Basal": 16.7, "Her2": 7.9, "LumA": 49.9, "LumB": 22.7, "Normal": 2.7}}`

## Proposed fixes (each needs a person's approval)

- R1 restore_from_previous_release for F1: Each sample's release-A profile is known exactly from its fingerprint; restoring puts every profile back under its own id. Evidence to reconsider: the data provider confirms the new labels are correct.
- R2 exclude for F2: These ids carry copies of other samples' measurements; excluding them removes the double counting. Evidence to reconsider: the provider shows the ids are distinct specimens with their own measurements.
- R3 flag_for_review for F3: Ask the provider why these samples were removed; a redaction or a withdrawn consent is legitimate, a processing loss is not. Report the smaller group until it is explained.

## Notes

- rna_hiseq.tsv.gz is not in release practice. That is expected for envelope releases, so it was not compared and is not reported as a problem.
