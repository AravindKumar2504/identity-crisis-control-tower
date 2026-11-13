"""Build a research-question card from a few plain choices, so a judge can ask a new question on the spot.

The card has the same fields as the files in cards/ and runs through the same checks and verdict rule. Nothing here
decides a verdict: it only writes down the question precisely (group, outcome, the data it reads, what it needs).
A built card can be saved as YAML and run from the command line with `python -m tower check --card <file>`.
"""
from __future__ import annotations

import re

SUBTYPES = {"LumA": "Luminal A", "LumB": "Luminal B", "Basal": "Basal-like", "Her2": "HER2-enriched",
            "Normal": "Normal-like"}
ENDPOINTS = {"OS": "overall survival", "PFI": "progression-free interval", "DSS": "disease-specific survival",
             "DFI": "disease-free interval"}
# clinical column -> (plain name, the two groups compared, or None to compare every value)
GROUPINGS = {
    "breast_carcinoma_estrogen_receptor_status": ("clinical ER status", ["Positive", "Negative"]),
    "breast_carcinoma_progesterone_receptor_status": ("clinical PR status", ["Positive", "Negative"]),
    "lab_proc_her2_neu_immunohistochemistry_receptor_status": ("HER2 status by IHC", ["Positive", "Negative"]),
    "PAM50Call_RNAseq": ("PAM50 subtype", None),
}
LABELS = {
    "PAM50Call_RNAseq": "PAM50 subtype",
    "breast_carcinoma_estrogen_receptor_status": "clinical ER status",
    "breast_carcinoma_progesterone_receptor_status": "clinical PR status",
    "lab_proc_her2_neu_immunohistochemistry_receptor_status": "HER2 status by IHC",
}
FEATURES = {"rna_hiseq.tsv.gz": "RNA expression", "protein_rppa.tsv.gz": "protein (RPPA)",
            "copy_number_gistic.tsv.gz": "copy number", "mutation_gene_level.tsv.gz": "gene mutations"}
# therapy -> (fields that record who received it, fields that come close but don't, why they fall short)
THERAPIES = {
    "hormone (endocrine) therapy": ([], ["targeted_molecular_therapy", "additional_pharmaceutical_therapy",
                                         "history_of_neoadjuvant_treatment"],
                                    "These fields record yes or no for broad treatment types without naming the drug."),
    "chemotherapy": ([], ["additional_pharmaceutical_therapy", "history_of_neoadjuvant_treatment"],
                     "These fields record yes or no for broad treatment types without naming the drug."),
    "HER2-targeted therapy": ([], ["targeted_molecular_therapy"],
                              "This field records yes or no for any targeted therapy without naming the drug."),
    "radiation therapy": (["radiation_therapy"], ["additional_radiation_therapy"], ""),
}

GROUP_SHORT = {"breast_carcinoma_estrogen_receptor_status": "ER", "breast_carcinoma_progesterone_receptor_status": "PR",
               "lab_proc_her2_neu_immunohistochemistry_receptor_status": "HER2 IHC", "PAM50Call_RNAseq": "subtype"}
LABEL_SHORT = {"PAM50Call_RNAseq": "PAM50", "breast_carcinoma_estrogen_receptor_status": "ER",
               "breast_carcinoma_progesterone_receptor_status": "PR",
               "lab_proc_her2_neu_immunohistochemistry_receptor_status": "HER2"}
FEATURE_SHORT = {"rna_hiseq.tsv.gz": "RNA", "protein_rppa.tsv.gz": "protein", "copy_number_gistic.tsv.gz": "CN",
                 "mutation_gene_level.tsv.gz": "mutations"}
THERAPY_SHORT = {"hormone (endocrine) therapy": "Hormone response", "chemotherapy": "Chemo response",
                 "HER2-targeted therapy": "HER2 drug response", "radiation therapy": "Radiation response"}

_COMMON = {
    "acceptable_limitations": "Up to 5% of the group excluded for documented reasons, if reported.",
    "out_of_scope": "Prognosis or treatment advice for any patient, risk scores or any clinical claim.",
}


def _slug(*parts: str) -> str:
    return "custom-" + re.sub(r"[^a-z0-9]+", "-", "-".join(p.lower() for p in parts if p)).strip("-")


def survival_question(endpoint: str, focus: str | None = None) -> dict:
    """Survival endpoint by PAM50 subtype, optionally with one subtype as the focus."""
    name, who = ENDPOINTS[endpoint], SUBTYPES.get(focus or "", "")
    return {
        "id": _slug("survival", endpoint, focus or "all"),
        "title": f"{name.capitalize()} by PAM50 subtype" + (f", with {who} as the focus" if who else ""),
        "short_title": f"{endpoint}, {who or 'all subtypes'}",
        "intended_use": f"Compare {name} between PAM50 subtypes"
                        + (f", with {who} primary tumors as the group of interest" if who else "")
                        + ", in a research analysis.",
        "group_studied": "Primary tumors (sample type 01) with a PAM50 subtype call and a survival record.",
        "outcome": f"{name.capitalize()} ({endpoint} event and {endpoint}.time in survival.tsv).",
        "not_acceptable": "Counting a patient twice, using redacted records, or an endpoint the data's own curators "
                          "advise against for this group.",
        **_COMMON,
        "uses": {"clinical.tsv": ["PAM50Call_RNAseq"], "survival.tsv": [endpoint, f"{endpoint}.time", "Redaction", "_PATIENT"]},
        "group": {"sample_type": "01", "in_files": ["survival.tsv"], "not_blank": ["PAM50Call_RNAseq"]},
        "endpoint": {"name": endpoint, "focus_subtype": focus or None},
        "checks": ["inputs_present", "endpoint_suitability", "survival_redacted", "survival_zero_time",
                   "patient_double_count", "subtype_columns_disagree"],
    }


def protein_question(protein: str, grouping: str) -> dict:
    """Mean protein level (RPPA) compared between clinical groups of primary tumors."""
    label, values = GROUPINGS[grouping]
    compared = " vs ".join(values) if values else "each subtype"
    group = {"sample_type": "01", "in_files": ["protein_rppa.tsv.gz"]}
    group.update({"values": {grouping: values}} if values else {"not_blank": [grouping]})
    is_a1 = protein == "ERALPHA" and grouping == "breast_carcinoma_estrogen_receptor_status"
    return {
        "id": _slug("protein", protein, label),
        "title": f"{protein} protein by {label} ({compared}), primary tumors",
        "short_title": f"{protein} by {GROUP_SHORT[grouping]}"[:24],
        "intended_use": f"A descriptive comparison of mean {protein} protein (RPPA) by {label} ({compared}), in a "
                        "research analysis.",
        "group_studied": f"Primary tumors (sample type 01) with protein data and a {label}"
                         + (f" of {' or '.join(values)}." if values else "."),
        "outcome": f"Mean {protein} protein (the {protein} row of protein_rppa.tsv.gz) in each group.",
        "not_acceptable": "Comparing groups whose labels or measurements changed without saying so.",
        **_COMMON,
        "uses": {"clinical.tsv": [grouping], "protein_rppa.tsv.gz": [protein]},
        "group": group,
        "limits": {"missing_fraction": 0.10},
        "checks": ["inputs_present", "missing_values"],
        **({"analyses": ["A1"]} if is_a1 else {}),
    }


def model_question(label: str, features: list[str]) -> dict:
    """A model that learns a clinical or molecular label from one or more data types."""
    feats = [f for f in FEATURES if f in features]
    what = " and ".join(FEATURES[f] for f in feats) or "no data"
    return {
        "id": _slug("model", LABELS[label], *[f.split("_")[0].split(".")[0] for f in feats]),
        "title": f"Train a model to predict {LABELS[label]} from {what}",
        "short_title": (f"{LABEL_SHORT[label]} from {FEATURE_SHORT[feats[0]]}" if len(feats) == 1
                        else f"{LABEL_SHORT[label]} model"),
        "intended_use": f"Train and evaluate a research model that predicts {LABELS[label]} from {what}.",
        "group_studied": f"Primary tumors (sample type 01) with {what} and a {LABELS[label]}.",
        "outcome": f"How well the model predicts {LABELS[label]} on held-out patients.",
        "not_acceptable": "A label computed from the same data the model learns from, or features that leak the label.",
        **_COMMON,
        "uses": {"clinical.tsv": [label], **{f: [] for f in feats}},
        "group": {"sample_type": "01", "in_files": feats, "not_blank": [label]},
        "label": label,
        "features": feats,
        "checks": ["inputs_present", "label_derivation", "leakage_columns"],
    }


def treatment_question(therapy: str) -> dict:
    """Whether tumors responded to a treatment. The release must record both who got it and how they responded."""
    recorded, near, why = THERAPIES[therapy]
    return {
        "id": _slug("treatment", therapy),
        "title": f"Did tumors respond to {therapy}?",
        "short_title": THERAPY_SHORT[therapy],
        "intended_use": f"Compare outcomes of primary tumors that did and did not receive {therapy}, as a response to "
                        "that treatment, in a research analysis.",
        "group_studied": "Primary tumors (sample type 01).",
        "outcome": f"Response to {therapy}.",
        "not_acceptable": "Treating any later tumor event as a response to this treatment, or comparing treated and "
                          "untreated tumors as if the treatment had been assigned at random.",
        **_COMMON,
        "uses": {"clinical.tsv": sorted(set(recorded + near + ["new_tumor_event_after_initial_treatment"]))},
        "group": {"sample_type": "01"},
        "requires": [
            {"need": f"which tumors received {therapy}", "columns_any": recorded, "near_misses": near, "why": why,
             "next_step": "Narrow the question to what the release records, or link a source that records this "
                          "treatment for each patient.",
             "evidence_needed": f"A field that records {therapy} for each patient."},
            {"need": f"a response measure for {therapy}", "columns_any": [],
             "near_misses": ["new_tumor_event_after_initial_treatment"],
             "why": "A new tumor event after any initial treatment is not a response to this treatment, and treatments "
                    "were not assigned at random, so comparing treated and untreated tumors would mix in the reasons "
                    "each treatment was chosen.",
             "next_step": "Use a study that measured response to this treatment, or narrow the question to recurrence "
                          "without claiming a treatment effect.",
             "evidence_needed": "A recorded response to the treatment, ideally from a randomized or well-controlled source."},
        ],
        "checks": ["inputs_present", "outcome_available"],
    }
