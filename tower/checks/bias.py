"""Bias: does the group a question studies come from a different mix of hospitals than the release as a whole?

TCGA samples come from many tissue source sites (hospitals and biobanks), coded in characters 6 and 7 of the barcode.
Requiring a data type (for example protein) changes which hospitals the studied group comes from, and hospitals differ
in patients and in how they handled samples, so a shifted mix can bias a result. The check measures the shift as the
total variation distance between the group's hospital mix and that of all primary tumors in the release: 0 means the
same mix, 1 means no hospital in common. For a question that depends on A1, it also reruns A1 with each large hospital
left out in turn.
"""
from __future__ import annotations

from collections import Counter

from ..analyses import ER, _clinical, _protein
from ..budget import _lower
from ..cards import card_group
from ..release import sample_type
from . import Issue, register

MIN_SITE_SHARE = 0.05

SOURCE = ("TCGA barcodes: characters 6 and 7 name the tissue source site "
          "(GDC Encyclopedia, https://docs.gdc.cancer.gov/Encyclopedia/pages/TCGA_Barcode/)")
LIMITATION = ("The tool sees which hospitals contributed the samples, not whether their patients or their sample "
              "handling actually differ.")
LOO_LIMITATION = " Leaving out one hospital at a time can't show what two hospitals together do."


def leave_one_site_out(release, min_share: float = MIN_SITE_SHARE) -> dict:
    """A1's ER-positive minus ER-negative difference with each hospital that holds at least min_share of A1's samples
    left out in turn. Holds if the difference stays positive and the low end of its 95% range stays above zero."""
    clin, prot = _clinical(release), _protein(release)
    er = clin.set_index("sampleID")[ER]
    if er.index.has_duplicates or int((prot.index == "ERALPHA").sum()) != 1:
        return {}
    samples = [s for s in prot.columns if sample_type(str(s)) == "01" and er.get(s) in ("Positive", "Negative")]
    if not samples:
        return {}
    vals = prot.loc["ERALPHA", samples].astype(float)

    def diff(keep):
        pos = vals[[s for s in keep if er[s] == "Positive"]].dropna().to_numpy()
        neg = vals[[s for s in keep if er[s] == "Negative"]].dropna().to_numpy()
        if len(pos) < 3 or len(neg) < 3:
            return None
        return float(pos.mean() - neg.mean()), _lower(pos, neg)

    sites = Counter(str(s)[5:7] for s in samples)
    rows = []
    for site, n in sites.most_common():
        if n / len(samples) < min_share:
            break
        got = diff([s for s in samples if str(s)[5:7] != site])
        if got is None:
            continue
        d, lo = got
        rows.append({"site": site, "samples_left_out": n, "share_pct": round(100 * n / len(samples), 1),
                     "difference": round(d, 3), "range_95_low": round(lo, 3), "holds": bool(d > 0 and lo > 0)})
    full = diff(samples)
    if not rows or full is None:
        return {}
    return {"difference_all": round(full[0], 3), "sites": rows, "min_share": min_share,
            "lowest": min(r["difference"] for r in rows), "highest": max(r["difference"] for r in rows),
            "holds_everywhere": all(r["holds"] for r in rows),
            "method": f"A1 recomputed with each hospital holding at least {min_share:.0%} of its samples left out in "
                      "turn; the 95% range uses the normal approximation"}


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
    digits = 4 if round(shift, 3) == limit else 3      # 0.1503 shows as 0.1503, not "0.150, over the 0.15 limit"
    numbers = {"total_variation_distance": round(shift, digits), "limit": limit, "group_samples": ng,
               "all_primary_tumors": na, "sites_in_group": len(pg), "sites_that_moved_most": top}
    loo = {}
    if "A1" in (card.get("analyses") or []) and release.has("protein_rppa.tsv.gz"):
        try:
            loo = leave_one_site_out(release)
        except Exception:
            loo = {}
    if loo:
        numbers["leave_one_site_out"] = loo
    fields = ["clinical.tsv:sampleID"]
    if shift > limit:
        k = moved[0]
        title = (f"The group's hospital mix differs from all primary tumors by {shift:.{digits}f}, over the card's "
                 f"{limit} limit (site {k} is {top[k]['share_of_group_pct']}% of the group but "
                 f"{top[k]['share_of_all_primary_pct']}% of all primary tumors)")
        nxt = ("Report the hospital mix with the result, and check that the result holds when each of the largest "
               "hospitals is left out in turn.")
        need = "The result holds with each large hospital left out, or evidence that the hospitals' samples are comparable."
        failed = [r for r in loo.get("sites", []) if not r["holds"]]
        if loo and not failed:
            title += (f"; A1 still holds with each of the {len(loo['sites'])} largest hospitals left out (difference "
                      f"{loo['lowest']} to {loo['highest']})")
            nxt = "Report the hospital mix with the result. It already holds with each of the largest hospitals left out."
            need = "Evidence that the hospitals' samples are comparable."
        elif failed:
            r = failed[0]
            title += f"; A1 doesn't hold with site {r['site']} left out (difference {r['difference']})"
            nxt = (f"Report the hospital mix, and check the samples from site {r['site']} before relying on the result: "
                   f"without them the difference is {r['difference']}.")
            need = f"Evidence that site {r['site']}'s samples are comparable to the others."
        return [Issue(id="site_shift", title=title, status="warn", material=True, pre_existing=True, fields=fields,
                      rows=group, numbers=numbers, rule=rule, source=SOURCE,
                      limitation=LIMITATION + (LOO_LIMITATION if loo else ""),
                      next_step=nxt, evidence_needed=need)]
    return [Issue(id="site_shift",
                  title=f"The group's hospital mix is close to that of all primary tumors (shift {shift:.{digits}f}, within the "
                        f"card's {limit} limit)",
                  status="pass", material=True, pre_existing=True, fields=fields, numbers=numbers, rule=rule,
                  source=SOURCE, limitation=LIMITATION)]
