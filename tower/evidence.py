"""Before-and-after values for every sample a finding cites, so a judge can check a finding cell by cell.

For a matrix file (protein, copy number, mutations) each cited sample gets its profile fingerprint in both releases
and the sample whose release-A profile it now carries: a swap shows each sample carrying the other's profile, a copy
shows a new id carrying another sample's profile. Protein findings also show the ERALPHA value A1 reads, and every
finding shows the clinical ER label, so the effect on A1 can be traced to the cells that cause it.
"""
from __future__ import annotations

from .diff import Comparison
from .release import ROW_FILES

ER = "breast_carcinoma_estrogen_receptor_status"


def _value(table, row: str, sample: str) -> str:
    """One cell of a matrix, as text a person can read."""
    if table is None or row not in table.frame.index or sample not in table.frame.columns:
        return "not in file"
    v = table.frame.at[row, sample]
    try:
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return str(v) or "(blank)"


def _label(release, sample: str) -> str:
    if not release.has("clinical.tsv"):
        return "no clinical file"
    cl = release.table("clinical.tsv").frame
    if sample not in cl.index or ER not in cl.columns:
        return "not in file"
    return str(cl.at[sample, ER]) or "(blank)"


def before_after(cmp: Comparison) -> dict[str, list[dict]]:
    """Finding id (F1, F2, ...) -> one row per cited sample, every value as text."""
    a, b = cmp.a, cmp.b
    prints: dict[str, tuple] = {}
    out: dict[str, list[dict]] = {}
    for i, ch in enumerate(cmp.changes):
        if not ch.samples:
            continue
        rows = []
        if ch.file in ROW_FILES:
            col = ch.detail.get("column")
            before, after = ch.detail.get("before", {}), ch.detail.get("after", {})
            in_a = set(a.table(ch.file).samples()) if a.has(ch.file) else set()
            in_b = set(b.table(ch.file).samples()) if b.has(ch.file) else set()
            for s in ch.samples:
                if col:
                    rows.append({"Sample": s, "Field": col, "Release A": before.get(s, "") or "(blank)",
                                 "New release": after.get(s, "") or "(blank)"})
                else:
                    rows.append({"Sample": s, "Field": f"row in {ch.file}",
                                 "Release A": "present" if s in in_a else "absent",
                                 "New release": "present" if s in in_b else "absent"})
            out[f"F{i + 1}"] = rows
            continue
        if ch.file not in prints:               # fingerprint each matrix once, over the features both releases share
            ta = a.table(ch.file) if a.has(ch.file) else None
            tb = b.table(ch.file) if b.has(ch.file) else None
            common = None
            if ta is not None and tb is not None and ta.features() != tb.features():
                shared = set(tb.features())
                common = [x for x in ta.features() if x in shared]
            fa = ta.fingerprints(common) if ta is not None else {}
            fb = tb.fingerprints(common) if tb is not None else {}
            owners: dict[str, list[str]] = {}
            for s, h in fa.items():
                owners.setdefault(h, []).append(s)
            prints[ch.file] = (ta, tb, fa, fb, owners)
        ta, tb, fa, fb, owners = prints[ch.file]
        for s in ch.samples:
            ha, hb = fa.get(s), fb.get(s)
            if hb is None:
                carries = "(gone from the new release)"
            elif hb == ha:
                carries = "itself (unchanged)"
            else:
                others = [x for x in owners.get(hb, []) if x != s]
                carries = ", ".join(others) if others else "no one's (new or edited values)"
            row = {"Sample": s, "Now holds release A's data of": carries}
            if ch.file == "protein_rppa.tsv.gz":
                row["ERALPHA, release A"] = _value(ta, "ERALPHA", s)
                row["ERALPHA, new release"] = _value(tb, "ERALPHA", s)
            row["ER status, release A"] = _label(a, s)
            row["ER status, new release"] = _label(b, s)
            row["Fingerprint, release A"] = (ha or "absent")[:8]
            row["Fingerprint, new release"] = (hb or "absent")[:8]
            rows.append(row)
        if all(r["ER status, release A"] == r["ER status, new release"] for r in rows):
            for r in rows:                       # the label didn't change: one column is enough
                r["ER status"] = r.pop("ER status, release A")
                del r["ER status, new release"]
            rows = [{k: r[k] for k in ["Sample", "Now holds release A's data of", "ERALPHA, release A",
                                       "ERALPHA, new release", "ER status", "Fingerprint, release A",
                                       "Fingerprint, new release"] if k in r} for r in rows]
        out[f"F{i + 1}"] = rows
    return out
