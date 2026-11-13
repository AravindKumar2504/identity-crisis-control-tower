"""Question-reasoning rules: does this release fit the research question on the card?

These differ from the data checks (release A problems, owned by Aakruti): they judge the question itself against
the data. Each returns Issues in the shared contract (tower/checks/__init__.py).
  inputs_present        every file, column and row the card reads exists here; otherwise the tool can't tell
  endpoint_suitability  the survival endpoint suits this cancer and subtype (TCGA Pan-Cancer Clinical Data Resource)
  label_derivation      a classifier's label was not computed from the features it learns from
  outcome_available     the release records what the question needs (e.g. who got a treatment and how they responded)
"""
from __future__ import annotations

import pandas as pd

from ..cards import BLANKS, card_group
from . import Issue, register

CDR = ("Liu et al., An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive High-Quality Survival Outcome "
       "Analytics, Cell 2018, https://doi.org/10.1016/j.cell.2018.02.052")
PAM50_SRC = ("Parker et al., Supervised Risk Predictor of Breast Cancer Based on Intrinsic Subtypes, J Clin Oncol "
             "2009, https://doi.org/10.1200/JCO.2008.18.1370")

# Which data a label in clinical.tsv was computed from (so a model trained on that data would be circular).
DERIVED_FROM = {
    "PAM50Call_RNAseq": (["rna_hiseq.tsv.gz"], "the PAM50 call is computed from the expression of 50 genes"),
    "PAM50_mRNA_nature2012": (["rna_hiseq.tsv.gz"], "the PAM50 call is computed from mRNA expression"),
    "SigClust_Intrinsic_mRNA_nature2012": (["rna_hiseq.tsv.gz"], "these clusters were computed from mRNA expression"),
    "SigClust_Unsupervised_mRNA_nature2012": (["rna_hiseq.tsv.gz"], "these clusters were computed from mRNA expression"),
    "RPPA_Clusters_nature2012": (["protein_rppa.tsv.gz"], "these clusters were computed from the RPPA protein data"),
    "CN_Clusters_nature2012": (["copy_number_gistic.tsv.gz"], "these clusters were computed from copy number"),
}
ENDPOINTS = {"OS": "overall survival", "DSS": "disease-specific survival",
             "DFI": "disease-free interval", "PFI": "progression-free interval"}


def _blank(v) -> bool:
    return str(v).strip() in BLANKS


@register("inputs_present")
def inputs_present(release, card):
    missing_files, missing_items, fields = [], [], []
    for f, items in (card.get("uses") or {}).items():
        fields += [f"{f}:{i}" for i in items or []]
        if not release.has(f):
            missing_files.append(f)
            continue
        t = release.table(f)
        have = set(t.features())
        missing_items += [f"{f}:{i}" for i in items or [] if i not in have]
    if missing_files or missing_items:
        what = ", ".join(missing_files + missing_items)
        return [Issue(id="inputs_present", title=f"The question reads data this release doesn't have: {what}",
                      status="unknown", material=True, pre_existing=False, fields=fields,
                      numbers={"missing_files": missing_files, "missing_fields": missing_items},
                      rule="If any file, column or row the question reads is missing, the tool can't judge the "
                           "question on this release.",
                      source="The card's `uses` list, checked against the files in this release",
                      limitation="A file that exists but was quietly corrupted is caught by the release comparison, "
                                 "not by this check.",
                      next_step=f"Get a release that includes {what}, or narrow the question to data this release has.",
                      evidence_needed=f"A release containing {what}, matching its published fingerprint.")]
    return [Issue(id="inputs_present", title="Every file, column and row the question reads is present",
                  status="pass", material=True, pre_existing=False, fields=fields,
                  rule="Every input in the card's `uses` list must exist in the release.",
                  source="The card's `uses` list")]


@register("endpoint_suitability")
def endpoint_suitability(release, card):
    ep = (card.get("endpoint") or {})
    name, focus = ep.get("name"), ep.get("focus_subtype")
    if name not in ENDPOINTS:
        return [Issue(id="endpoint_suitability", title="The card names no survival endpoint", status="pass",
                      material=False, pre_existing=False)]
    if not release.has("survival.tsv"):
        return [Issue(id="endpoint_suitability", title="No survival file, so the endpoint can't be judged",
                      status="unknown", material=True, pre_existing=False, fields=["survival.tsv"],
                      rule="An endpoint can only be judged from the survival records.", source=CDR,
                      evidence_needed="A release with survival.tsv.")]
    sv = release.table("survival.tsv").frame
    group = sorted(card_group(release, card) & set(sv.index))
    cl = release.table("clinical.tsv").frame
    if focus and "PAM50Call_RNAseq" in cl.columns:
        sub = [s for s in group if cl.at[s, "PAM50Call_RNAseq"] == focus]
    else:
        sub = group
    ev = pd.to_numeric(sv.loc[sub, name], errors="coerce") if sub else pd.Series(dtype=float)
    tm = pd.to_numeric(sv.loc[sub, f"{name}.time"], errors="coerce") if sub else pd.Series(dtype=float)
    months = float(tm.median() / 30.44) if len(tm.dropna()) else float("nan")
    numbers = {"endpoint": name, "focus_subtype": focus or "all", "samples": len(sub),
               "events": int((ev == 1).sum()), "censored": int((ev == 0).sum()),
               "median_follow_up_months": round(months, 1)}
    fields = [f"survival.tsv:{name}", f"survival.tsv:{name}.time", "clinical.tsv:PAM50Call_RNAseq"]
    label = ENDPOINTS[name]
    if name in ("PFI", "DFI"):
        status, title = "pass", (f"{label.capitalize()} is an endpoint the TCGA curators recommend for breast cancer "
                                 f"({numbers['events']} events in {len(sub)} samples)")
        rule = "PFI and DFI were recommended for breast cancer without reservation."
        nxt, need = "", ""
    elif name == "OS" and focus == "LumA":
        status = "block"
        title = (f"Overall survival can't support a Luminal A comparison here: median follow-up is {numbers['median_follow_up_months']} "
                 f"months, and the TCGA curators advise against overall survival for Luminal A")
        rule = ("Block when the curators advise against the endpoint for the group studied: Luminal A tumors may take "
                "10 years or more to recur, far beyond this follow-up.")
        nxt = "Use progression-free interval (PFI), which the curators recommend for breast cancer without reservation."
        need = "Follow-up long enough for Luminal A tumors (10 years or more), or an outcome source with that follow-up."
    else:
        status = "warn"
        title = (f"{label.capitalize()} needs caution for breast cancer: median follow-up is "
                 f"{numbers['median_follow_up_months']} months with {numbers['events']} events")
        rule = "The curators suggested caution for OS and DSS in breast cancer because follow-up is short."
        nxt = "Report PFI or DFI as the main endpoint and treat this endpoint as secondary."
        need = "Longer follow-up for the group studied."
    return [Issue(id="endpoint_suitability", title=title, status=status, material=True, pre_existing=True,
                  fields=fields, rows=sub, numbers=numbers, rule=rule, source=CDR,
                  limitation="The recommendation comes from the curators' analysis of all TCGA breast cancers, not a "
                             "test on this exact group.",
                  next_step=nxt, evidence_needed=need)]


@register("label_derivation")
def label_derivation(release, card):
    label = card.get("label")
    feats = set(card.get("features") or [])
    if not label:
        return [Issue(id="label_derivation", title="The card trains no model", status="pass", material=False,
                      pre_existing=False)]
    src, why = DERIVED_FROM.get(label, ([], ""))
    overlap = sorted(set(src) & feats)
    if overlap:
        return [Issue(id="label_derivation",
                      title=f"Circular design: the label {label} was computed from {', '.join(overlap)}, the same data "
                            "the model would learn from",
                      status="block", material=True, pre_existing=True,
                      fields=[f"clinical.tsv:{label}"] + [f"{f}:*" for f in overlap],
                      numbers={"label": label, "derived_from": src, "features": sorted(feats)},
                      rule="Block when a model's label was derived from its own input features: high accuracy would "
                           "only show it relearned the rule that made the label.",
                      source=PAM50_SRC + f" ({why})",
                      limitation="This judges the design, not the data quality.",
                      next_step="Predict a label that was measured independently of the features (for example "
                                "clinical ER status from protein), or use the subtype only as a descriptive grouping.",
                      evidence_needed="A label measured independently of the model's inputs.")]
    return [Issue(id="label_derivation", title=f"The label {label} was not computed from the model's inputs",
                  status="pass", material=True, pre_existing=False, fields=[f"clinical.tsv:{label}"],
                  rule="A model's label must not be derived from its own input features.", source=PAM50_SRC)]


@register("outcome_available")
def outcome_available(release, card):
    reqs = card.get("requires") or []
    if not reqs:
        return [Issue(id="outcome_available", title="The card lists no special data requirements", status="pass",
                      material=False, pre_existing=False)]
    cl = release.table("clinical.tsv").frame if release.has("clinical.tsv") else pd.DataFrame()
    group = sorted(card_group(release, card))
    out = []
    for i, r in enumerate(reqs):
        found = [c for c in r.get("columns_any", []) or [] if c in cl.columns
                 and any(not _blank(v) for v in cl.loc[group, c])]
        near = {}
        for c in r.get("near_misses", []) or []:
            if c in cl.columns:
                vals = cl.loc[group, c]
                filled = [v for v in vals if not _blank(v)]
                near[c] = {"filled": len(filled), "of": len(vals),
                           "values": sorted({str(v) for v in filled})[:6]}
        if found:
            out.append(Issue(id=f"outcome_available_{i + 1}", title=f"The release records {r['need']}",
                             status="pass", material=True, pre_existing=False,
                             fields=[f"clinical.tsv:{c}" for c in found], rule="The question's key data must exist."))
            continue
        near_txt = "; ".join(f"{c} is filled for {v['filled']} of {v['of']} ({', '.join(v['values'])})"
                             for c, v in near.items())
        out.append(Issue(id=f"outcome_available_{i + 1}",
                         title=f"The release doesn't record {r['need']}",
                         status="block", material=True, pre_existing=True,
                         fields=[f"clinical.tsv:{c}" for c in near], rows=[],
                         numbers={"need": r["need"], "near_misses": near},
                         rule="Block when the release has no field that records what the question needs. "
                              "Closest fields found: " + (near_txt or "none") + ". " + r.get("why", ""),
                         source="clinical.tsv column list and values in this release",
                         limitation="The tool searched this release's fields; another source might record it.",
                         next_step=r.get("next_step", "Narrow the question to what the release records."),
                         evidence_needed=r.get("evidence_needed", f"A source that records {r['need']}.")))
    return out
