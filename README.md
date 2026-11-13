# Identity_Crisis · Cohort Control Tower

Team Identity_Crisis's entry for the OncoSys Cancer AI Lab hackathon (The Open Accelerator, OncoSys AI, Northeastern University, Red Hat; November 11-14, 2026). Track 1: Cohort Firewall.

**Status:** work in progress. Setup and run steps will be added here as the tool takes shape.

## The user and the one workflow

**User:** a research engineer responsible for a dataset that gets new releases.

**Workflow they finish:** point the tool at two releases of the TCGA-BRCA files, see exactly what changed (swapped samples, duplicate profiles under new IDs, samples that appeared or disappeared, changed clinical labels), rerun only the analyses those changes affect, and export `findings.json` in the event's shared format so a reviewer can approve or reject each proposed repair.

## Data

Judged results use the event's frozen TCGA-BRCA release, fetched with the challenge repo's `data/tcga-brca/fetch.py` and checked against its published checksums. No raw TCGA files are committed here. Data credits: see `DATA_LICENSES.md` in the [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge).

The data is de-identified but patient-derived: research use only. This tool makes no diagnosis, treatment recommendation, risk score or clinical claim.

## Team

Identity_Crisis. Members will be listed here.
