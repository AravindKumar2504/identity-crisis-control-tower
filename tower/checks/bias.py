"""Bias: does the group a question studies come from a different mix of hospitals than the release as a whole?

TCGA samples come from many tissue source sites (hospitals and biobanks), coded in characters 6 and 7 of the barcode.
Requiring a data type (for example protein) changes which hospitals the studied group comes from, and hospitals differ
in patients and in how they handled samples, so a shifted mix can bias a result. The check measures the shift as the
total variation distance between the group's hospital mix and that of all primary tumors in the release: 0 means the
same mix, 1 means no hospital in common.
"""
from __future__ import annotations

from collections import Counter

from ..cards import card_group
from ..release import sample_type
from . import Issue, register

SOURCE = ("TCGA barcodes: characters 6 and 7 name the tissue source site "
          "(GDC Encyclopedia, https://docs.gdc.cancer.gov/Encyclopedia/pages/TCGA_Barcode/)")
LIMITATION = ("The tool sees which hospitals contributed the samples, not whether their patients or their sample "
              "handling actually differ.")


@register("site_shift")
def site_shift(release, card):
    limit = float((card.get("limits") or {}).get("site_shift_tvd", 0.15))
    rule = (f"Warn when the group's hospital mix differs from that of all primary tumors by more than {limit} "
            "(total variation distance: 0 for the same mix, 1 for no hospital in common).")
    if not release.has("clinical.tsv"):
        return [Issue(id="site_shift", title="The clinical file is missing or unreadable, so the hospital mix can't be "
                      "measured", status="unknown", material=True, pre_existing=False, fields=["clinical.tsv:sampleID"],
                      rule=rule, source=SOURCE, evidence_needed="A release with a readable clinical.tsv.")]
    everyone = [s for s in release.table("clinical.tsv").frame.index if sample_type(s) == "01"]
    group = sorted(card_group(release, card))
    if not group or not everyone:
        return [Issue(id="site_shift", title="The group has no samples, so its hospital mix can't be measured",
                      status="unknown", material=True, pre_existing=False, fields=["clinical.tsv:sampleID"],
                      rule=rule, source=SOURCE, evidence_needed="A release where the question's group has samples.")]
    pa, pg = Counter(s[5:7] for s in everyone), Counter(s[5:7] for s in group)
    na, ng = len(everyone), len(group)
    sites = set(pa) | set(pg)
    shift = 0.5 * sum(abs(pa[k] / na - pg[k] / ng) for k in sites)
    moved = sorted(sites, key=lambda k: -abs(pg[k] / ng - pa[k] / na))[:3]
    top = {k: {"share_of_group_pct": round(100 * pg[k] / ng, 1), "share_of_all_primary_pct": round(100 * pa[k] / na, 1)}
           for k in moved}
    numbers = {"total_variation_distance": round(shift, 3), "limit": limit, "group_samples": ng,
               "all_primary_tumors": na, "sites_in_group": len(pg), "sites_that_moved_most": top}
    fields = ["clinical.tsv:sampleID"]
    if shift > limit:
        k = moved[0]
        return [Issue(id="site_shift",
                      title=(f"The group's hospital mix differs from all primary tumors by {shift:.3f}, over the card's "
                             f"{limit} limit (site {k} is {top[k]['share_of_group_pct']}% of the group but "
                             f"{top[k]['share_of_all_primary_pct']}% of all primary tumors)"),
                      status="warn", material=True, pre_existing=True, fields=fields, rows=group, numbers=numbers,
                      rule=rule, source=SOURCE, limitation=LIMITATION,
                      next_step="Report the hospital mix with the result, and check that the result holds when each of "
                                "the largest hospitals is left out in turn.",
                      evidence_needed="The result holds with each large hospital left out, or evidence that the "
                                      "hospitals' samples are comparable.")]
    return [Issue(id="site_shift",
                  title=f"The group's hospital mix is close to that of all primary tumors (shift {shift:.3f}, within the "
                        f"card's {limit} limit)",
                  status="pass", material=True, pre_existing=True, fields=fields, numbers=numbers, rule=rule,
                  source=SOURCE, limitation=LIMITATION)]
