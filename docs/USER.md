# Who we build for

The founder's kickoff tip: the team that researches its user has an advantage. This page is that research, with a source for every claim. Checked November 13, 2026.

## The persona: a research data engineer

They keep an analysis-ready copy of a public cancer dataset for the scientists who use it: here, TCGA breast cancer data from the UCSC Xena hub, with survival from the TCGA Pan-Cancer Clinical Data Resource. Job titles vary (data quality engineer, bioinformatician, bioinformatics developer, research software engineer). They sit either in a consortium data center (the NCI Genomic Data Commons, the CPTAC Proteomic Data Commons, UCSC Xena) or in a cancer-center bioinformatics group.

Their sources ship numbered releases, often:
- The Genomic Data Commons (GDC) has released about every 4 to 5 months since 2024 (DR40 March 2024 through DR46 August 2026) [1].
- The Proteomic Data Commons releases about monthly (V6.3 to V6.5, August to October 2026) [2].
- AACR GENIE publishes a public release about every six months, with retraction counts [3].
- Mirrors lag: Xena's GDC hub page still describes GDC DR41.0 (August 2024) while the GDC is at DR46.0 [4].

Today the workflow is manual: read prose release notes, check per-file version history (the GDC API keeps the provenance of every file version [5]), download again, rerun the analyses, and explain any change to the principal investigators. Their worst day: a survival curve or mutation count shifts after a refresh and nobody can say why, or a paper turns out to rest on a swapped, retracted or redacted sample.

## Five pain points, each with a real incident

1. **Reprocessing moves results even when no sample changes.** When the GDC reprocessed TCGA mutation calls in Data Release 32 (March 2022), open-access mutations fell by 26% [1].
2. **Clinical fields move and survival breaks silently.** In Data Release 42 (January 2025) some TCGA follow-up data moved to a new field and some TCGA projects lost cases from their survival plots until Data Release 43 moved it back in May 2025 [1]. Data Release 17 (2019) had already moved vital status and days to death [1].
3. **The same data comes back under a new id.** Most TCGA slide image ids changed in Data Release 31 (October 2021) [1]. Waldron and colleagues found probable duplicate expression profiles in more than half of the studies they checked, TCGA included, and warn that duplicates inflate prediction accuracy [6]. TCGA keeps a "Duplicate case" category for patients accessioned more than once [7].
4. **Samples vanish, and the record of why is incomplete.** 397 contaminated TCGA alignments had their mutation files removed (known issue through DR46.0) [1]. AACR GENIE's 17.0 public release retracted 1,402 samples that were in the previous public release [3]. A GDC redaction hides a case and everything under it [8].
5. **Swaps and mislabels are common, including in TCGA breast cancer.** A cross-omics matching method (MODMatcher) found 8 mismatched profile pairs among 317 TCGA breast tumors, including an expression swap between TCGA-BH-A18K-01 and TCGA-BH-A18T-01 [9]. COSMO independently recovered eight swapped breast cancer microarray pairs and found errors in 7.5% of pre-QC CPTAC lung samples [10]. Apparent sex mislabels appeared in 46% of 70 transcriptomics datasets checked [11].

## Why the tools they already have don't solve it

| Tool | What it does | What it can't do for this user |
|---|---|---|
| Great Expectations, Pandera | Rule and schema checks on one dataset | A swapped sample passes every type and range check; no identity across releases, no analysis impact, no verdict |
| TensorFlow Data Validation, Deepchecks | Distribution drift and train/test overlap | Swapping two samples leaves every distribution unchanged |
| DVC, lakeFS | Version whole files; DVC reruns stages whose input hash changed | One changed sample reruns everything, and nothing says what changed or whether the result still holds |
| datacompy and other dataframe diffs | Compare two tables joined on an id | Trust the id: a copy under a new id looks like a new row, a swap looks like edits |
| somalier, NGSCheckMate | Sample swap checks from sequencing reads | Need BAM/VCF files, not the processed matrices this user maintains |
| COSMO, MODMatcher | Find mislabels inside one snapshot | No release-to-release diff, no reruns, no decision or review step |
| GDC release notes and file history | Prose notes, per-file versions | Per file and read by a human; never says which of your samples or analyses moved |

Sources for the table: each tool's own documentation [12].

## What this means for our product

- **Name samples, not counts.** Identity checks must survive the count staying the same (pain points 3 to 5).
- **Say which analyses moved and leave the rest alone.** Rerun only what a change touches (pain points 1 and 2).
- **Judge fitness for a specific question.** The FDA's real-world data guidance defines reliability as accuracy, completeness and traceability, and relevance as having the key variables and enough representative patients for the study [13]. TCGA's own clinical resource already recommends different survival endpoints for different cancers [14]. Readiness depends on the question.
- **Keep an audit trail and a person's sign-off.** The same FDA guidance calls traceability an audit trail of where data came from [13]. Datasheets for Datasets asks how users learn about updates and corrections [15]; our tool answers that from the data when the publisher doesn't.

## Questions to ask a real data engineer (event Discord or a mentor)

1. When a new GDC or Xena release ships, how do you find out which of your samples and clinical fields changed, and how long does it take?
2. Has a result ever changed after a data refresh? How did you trace the cause?
3. Before a refreshed dataset goes back into a study, who signs off, and what evidence do they need to see?

## Sources

1. GDC Data Release Notes: https://docs.gdc.cancer.gov/Data/Release_Notes/Data_Release_Notes/ (DR17.0, DR31.0, DR32.0, DR42.0, DR43.0, DR46.0)
2. PDC Data Release Notes: https://pdc-release-notes.s3.amazonaws.com/PDC_Data_Release_Notes.htm
3. AACR GENIE release news: https://docs.cbioportal.org/news-genie/
4. UCSC Xena GDC hub page: https://ucsc-xena.gitbook.io/project/public-data-we-host/gdc
5. GDC API, search and retrieval (file history): https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/
6. Waldron et al., JNCI 2016: https://doi.org/10.1093/jnci/djw146
7. GDC TCGA annotations (legacy reference): https://docs.gdc.cancer.gov/Encyclopedia/pages/Annotations_TCGA/
8. GDC redaction: https://docs.gdc.cancer.gov/Encyclopedia/pages/Redaction/
9. MODMatcher, PLoS Computational Biology 2014: https://doi.org/10.1371/journal.pcbi.1003790
10. COSMO, Patterns 2021: https://doi.org/10.1016/j.patter.2021.100245
11. Toker et al., F1000Research 2016: https://f1000research.com/articles/5-2103/v2
12. Great Expectations https://docs.greatexpectations.io, Pandera https://pandera.readthedocs.io, TFDV https://www.tensorflow.org/tfx/data_validation/get_started, Deepchecks https://docs.deepchecks.com, DVC https://doc.dvc.org, lakeFS https://docs.lakefs.io, datacompy https://github.com/capitalone/datacompy, somalier https://github.com/brentp/somalier, COSMO https://github.com/bzhanglab/COSMO
13. FDA, Real-World Data: Assessing Electronic Health Records and Medical Claims Data (final guidance, July 2024): https://www.fda.gov/media/152503/download
14. Liu et al., An Integrated TCGA Pan-Cancer Clinical Data Resource, Cell 2018: https://doi.org/10.1016/j.cell.2018.02.052
15. Gebru et al., Datasheets for Datasets: https://arxiv.org/abs/1803.09010
