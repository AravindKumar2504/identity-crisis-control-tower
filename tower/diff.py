"""Find what changed between two releases, sample by sample.

Every sample in every changed file gets a fingerprint (a hash of everything it holds). Comparing fingerprints
across the two releases explains each change exactly:
  swap        two or more samples traded profiles (a cycle of moves)
  duplicate   a profile from release A now also appears under another id (a new id, or an overwritten one)
  lost        a sample is gone from the file
  gained      a new sample whose profile matches nothing in release A
  relabel     a clinical or survival field changed value for some samples
  blanked     values became empty
  edited      values changed in a way none of the above explains (reported, never guessed at)
Profiles that were already identical in release A (for example a tumor and a normal sample sharing one
survival record) are never reported as copies, because nothing changed about them.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .release import ALL_FILES, OPTIONAL_FILES, ROW_FILES, Release, UnreadableFile

BLANKS = {"", "NA", "nan", "NaN", "null", "None"}


@dataclass
class Change:
    kind: str                        # shared-format finding kind
    file: str
    samples: list[str]               # every affected sample, in citation order
    summary: str
    confidence: str = "high"
    notes: dict[str, str] = field(default_factory=dict)        # sample -> note for its evidence pointer
    evidence_release: dict[str, str] = field(default_factory=dict)  # sample -> "A" or "B"
    detail: dict = field(default_factory=dict)                  # structured facts (pairs, sources, column, values)


@dataclass
class Comparison:
    a: Release
    b: Release
    changes: list[Change]
    unchanged_files: list[str]
    compared_files: list[str]
    notes: list[str]                 # things worth saying that are not findings (e.g. no RNA file in B)


def compare(a: Release, b: Release) -> Comparison:
    changes: list[Change] = []
    unchanged, compared, notes = [], [], []
    for f in ALL_FILES:
        if f in a.unreadable:
            raise UnreadableFile(f"release {a.name}'s {f} can't be read ({a.unreadable[f]}); fetch release A again")
        in_a, in_b = a.has(f), b.has(f)
        if f in b.unreadable and in_a:
            changes.append(_unreadable(f, b))
            continue
        if not in_a and not in_b:
            continue
        if in_a and not in_b:
            if f in OPTIONAL_FILES:
                notes.append(f"{f} is not in release {b.name}. That is expected for envelope releases, "
                             "so it was not compared and is not reported as a problem.")
            else:
                changes.append(Change("missing_data", f, [], f"{f} is missing from release {b.name}, so nothing "
                                      "that reads it can be checked.", detail={"file_missing": True}))
            continue
        if in_b and not in_a:
            notes.append(f"{f} appears in release {b.name} but not in release {a.name}; it was not compared.")
            continue
        if a.content_sha256[f] == b.content_sha256[f]:
            unchanged.append(f)
            continue
        ta = a.table(f)
        try:
            tb = b.table(f)
        except UnreadableFile:
            changes.append(_unreadable(f, b))
            continue
        compared.append(f)
        if f in ROW_FILES:
            changes += _diff_rows(f, ta.frame, tb.frame, a, b)
        else:
            changes += _diff_matrix(f, ta, tb, a, b)
    return Comparison(a, b, changes, unchanged, compared, notes)


def _unreadable(f: str, b: Release) -> Change:
    return Change("missing_data", f, [], f"{f} in release {b.name} can't be read ({b.unreadable.get(f, 'unreadable')}), "
                  "so it was refused instead of compared, and nothing that reads it can be checked.",
                  detail={"file_missing": True, "unreadable": b.unreadable.get(f, "")})


# ----------------------------------------------------------------------------------------------- matrices
def _diff_matrix(f, ta, tb, a, b) -> list[Change]:
    out: list[Change] = []
    feats_a, feats_b = ta.features(), tb.features()
    set_a, set_b = set(feats_a), set(feats_b)          # build once: 40,000+ genes in the large files
    common_feats = [x for x in feats_a if x in set_b] if feats_a != feats_b else feats_a
    lost_feats = [x for x in feats_a if x not in set_b]
    new_feats = [x for x in feats_b if x not in set_a]
    if lost_feats or new_feats:
        out.append(Change("other", f, [], f"{f}: {len(lost_feats)} measured rows were removed and {len(new_feats)} "
                          "were added, so analyses that read those rows may not be comparable.", confidence="high",
                          detail={"rows_removed": lost_feats[:50], "rows_added": new_feats[:50]}))
    fa = ta.fingerprints(None if common_feats == feats_a else common_feats)
    fb = tb.fingerprints(None if common_feats == feats_b else common_feats)
    out += _explain(f, fa, fb, ta, tb, common_feats, a, b)
    return out


def _explain(f, fa: dict, fb: dict, ta, tb, feats, a, b) -> list[Change]:
    out: list[Change] = []
    sa, sb = set(fa), set(fb)
    removed = sorted(sa - sb)
    added = sorted(sb - sa)
    changed = sorted(x for x in sa & sb if fa[x] != fb[x])
    inv_a = defaultdict(list)
    for s, h in fa.items():
        inv_a[h].append(s)

    # Where does each changed or added sample's new profile come from in release A?
    source = {}
    for x in changed + added:
        cands = [y for y in inv_a.get(fb[x], []) if y != x]
        if cands:
            source[x] = cands

    explained: set[str] = set()
    changed_set = set(changed)
    # 1) Cycles among changed samples: swaps (2) and rotations (3+).
    nxt = {x: [y for y in source.get(x, []) if y in changed_set] for x in changed}
    seen = set()
    for start in changed:
        if start in seen or not nxt.get(start):
            continue
        path, x = [start], start
        while True:
            options = [y for y in nxt.get(x, []) if y not in path or y == start]
            if not options:
                break
            y = start if start in options else options[0]
            if y == start:
                break
            path.append(y)
            x = y
        if len(path) >= 2 and start in nxt.get(path[-1], []):
            seen.update(path)
            explained.update(path)
            notes = {p: f"now holds the profile {path[(i + 1) % len(path)]} had in release {a.name}"
                     for i, p in enumerate(path)}
            kind_txt = "traded places" if len(path) == 2 else f"moved in a chain of {len(path)}"
            out.append(Change("sample_swap", f, path, f"In {f}, the profiles of {', '.join(path)} {kind_txt} "
                              "between releases: each sample now carries another sample's data.",
                              notes=notes, evidence_release={p: "B" for p in path},
                              detail={"cycle": path, "pairs": [[path[i], path[(i + 1) % len(path)]] for i in range(len(path))]}))

    # 2) Copies: an added id, or a changed id overwritten, now carrying a profile that still exists elsewhere.
    b_profiles = set(fb.values())

    def copy_of_present(y):
        """The sample whose release-A profile y now carries, when that sample still holds its own profile."""
        return next((z for z in source.get(y, []) if z in sb and fb.get(z) == fa[z]), None)

    dups, renames, renamed_from, later_swaps, reused, dup_notes = [], [], set(), [], [], {}
    removed_set = set(removed)
    for x in added + [c for c in changed if c not in explained]:
        if x not in source or x in explained:
            continue
        src = source[x]
        still_there = [y for y in src if y in sb and fb.get(y) == fa[y]]
        if x in sa and fa.get(x) in {fa[y] for y in src}:
            continue                       # already identical in release A: not a new copy
        gone = [y for y in src if y in removed_set and y not in renamed_from]
        if x in added and not still_there and not gone:
            # A new id holds a changed sample's release-A profile, and that sample now holds a copy of a sample that
            # is still in place: a copy was made under the new id, then the new id traded places with that sample.
            y = next((y for y in src if y in changed_set and y not in explained and copy_of_present(y)), None)
            if y is not None:
                d = copy_of_present(y)
                later_swaps.append((x, y, d))
                dups.append((x, d))
                dup_notes[x] = f"made as a copy of {d}'s profile, then traded places with {y}, which now holds the copy"
                explained.update({x, y})
                continue
        if x in added and not still_there and gone:
            renames.append((x, gone[0]))   # the profile moved to a new id and the old id is gone: a rename
            renamed_from.add(gone[0])
            explained.add(x)
        elif still_there or x in added:
            dups.append((x, (still_there or src)[0]))
            explained.add(x)
            if x in sa and fa[x] not in b_profiles:
                reused.append(x)           # the id's own profile is gone and the id now holds a copy: lost, then re-used
    for x, y, d in later_swaps:
        out.append(Change("sample_swap", f, [x, y],
                          f"In {f}, {x} (a new id made as a copy of {d}) and {y} traded places: {x} now carries the "
                          f"profile {y} had in release {a.name}, and {y} carries the copy of {d}.",
                          notes={x: f"now holds the profile {y} had in release {a.name}",
                                 y: f"now holds the copy of {d} that was made under {x}"},
                          evidence_release={x: "B", y: "B"}, confidence="medium",
                          detail={"cycle": [x, y], "pairs": [[x, y], [y, x]], "after_copy_of": d}))
    if dups:
        out.append(Change("duplicate", f, [d[0] for d in dups],
                          f"In {f}, {len(dups)} sample id(s) carry a profile identical to another sample's "
                          f"profile from release {a.name}, so the same measurements are counted twice.",
                          notes={x: dup_notes.get(x, f"identical to {y} (release {a.name})") for x, y in dups},
                          evidence_release={x: "B" for x, _ in dups},
                          detail={"copies": [{"new_id": x, "copied_from": y, "new_id_is_new": x in added} for x, y in dups]}))

    if renames:
        out.append(Change("other", f, [i for pair in renames for i in pair],
                          f"In {f}, {len(renames)} sample id(s) were renamed: each profile now appears under a new id "
                          f"and its old id is gone, so analyses would treat it as a different sample.",
                          notes={**{x: f"carries the profile {y} had in release {a.name}" for x, y in renames},
                                 **{y: f"gone from release {b.name}; its profile now sits under {x}" for x, y in renames}},
                          evidence_release={**{x: "B" for x, _ in renames}, **{y: "A" for _, y in renames}},
                          detail={"renames": [{"new_id": x, "old_id": y} for x, y in renames]}))

    # 3) A sample now carries the profile another id had in release A, and that id no longer holds it: the two
    #    traded places and the partner was then removed (a removed partner is also reported as missing below).
    moves = [(x, source[x][0]) for x in changed if x not in explained and x in source]
    for x, y in moves:
        explained.add(x)
        y_gone = y not in sb
        out.append(Change("sample_swap", f, [x, y],
                          f"In {f}, {x} now carries the profile {y} had in release {a.name}"
                          + (f", and {y} is no longer in release {b.name}: the two traded places and {y} was then "
                             "removed (it is also reported as missing)." if y_gone else
                             f", and {y} no longer holds it: the two traded places."),
                          notes={x: f"now holds the profile {y} had in release {a.name}",
                                 y: (f"traded places with {x}, then removed from release {b.name}" if y_gone
                                     else f"its release-{a.name} profile now sits under {x}")},
                          evidence_release={x: "B", y: "A" if y_gone else "B"}, confidence="medium",
                          detail={"cycle": [x, y], "pairs": [[x, y], [y, x]], "partner_removed": y_gone}))

    # 4) Lost and gained samples.
    lost = [x for x in removed if x not in renamed_from] + reused
    if lost:
        ctx = _subgroups(lost, a)
        same_count = len(sa) == len(sb)
        out.append(Change("membership_change", f, lost,
                          f"In {f}, {len(lost)} sample(s) present in release {a.name} are missing from release {b.name}"
                          f"{ctx}{'; the total sample count is unchanged, so a count check would not notice' if same_count else ''}.",
                          notes={x: (f"its release-{a.name} profile is gone from release {b.name}; the id now holds a copy "
                                     "of another sample" if x in reused else f"present in {a.name}, absent in {b.name}")
                                 for x in lost},
                          evidence_release={x: "A" for x in lost},
                          detail={"direction": "lost", "same_total": same_count}))
    gained = [x for x in added if x not in explained]
    if gained:
        out.append(Change("membership_change", f, gained,
                          f"In {f}, {len(gained)} new sample(s) appear in release {b.name} whose profiles match "
                          f"nothing in release {a.name}.",
                          notes={x: f"absent in {a.name}, present in {b.name}" for x in gained},
                          evidence_release={x: "B" for x in gained}, confidence="medium",
                          detail={"direction": "gained"}))

    # 5) Remaining changed samples: values blanked or edited.
    rest = [x for x in changed if x not in explained]
    if rest:
        blanked, edited = [], []
        for x in rest:
            va, vb = _col(ta, x, feats), _col(tb, x, feats)
            diff = _neq(va, vb)
            if diff.any() and _all_blank(vb[diff]):
                blanked.append((x, int(diff.sum())))
            else:
                edited.append((x, int(diff.sum())))
        if blanked:
            out.append(Change("missing_data", f, [x for x, _ in blanked],
                              f"In {f}, {len(blanked)} sample(s) lost measured values (cells became empty).",
                              notes={x: f"{n} value(s) became empty" for x, n in blanked},
                              evidence_release={x: "B" for x, _ in blanked}, detail={"blanked": dict(blanked)}))
        if edited:
            out.append(Change("other", f, [x for x, _ in edited],
                              f"In {f}, {len(edited)} sample(s) have changed values that are not a swap, copy or "
                              "removal; the tool reports them but cannot say why they changed.",
                              notes={x: f"{n} value(s) changed" for x, n in edited},
                              evidence_release={x: "B" for x, _ in edited}, confidence="low",
                              detail={"edited": dict(edited)}))
    return out


def _col(t, s, feats):
    col = t.frame[s]
    if feats is not None and list(t.frame.index) != list(feats):
        col = col.loc[feats]
    return col.to_numpy()


def _neq(va, vb):
    if va.dtype.kind in "fc" and vb.dtype.kind in "fc":
        both_nan = np.isnan(va) & np.isnan(vb)
        return (va != vb) & ~both_nan
    return np.array([str(x) != str(y) for x, y in zip(va, vb)])


def _all_blank(vals) -> bool:
    if vals.dtype.kind in "fc":
        return bool(np.isnan(vals).all())
    return all(str(v).strip() in BLANKS for v in vals)


# ----------------------------------------------------------------------------------------------- row files
def _diff_rows(f, da: pd.DataFrame, db: pd.DataFrame, a, b) -> list[Change]:
    out: list[Change] = []
    sa, sb = set(da.index), set(db.index)
    lost, gained = sorted(sa - sb), sorted(sb - sa)
    cols_a, cols_b = list(da.columns), list(db.columns)
    common_cols = [c for c in cols_a if c in set(cols_b)]
    if len(common_cols) != len(cols_a) or len(cols_b) != len(cols_a):
        out.append(Change("other", f, [], f"{f}: columns changed ({len(set(cols_a) - set(cols_b))} removed, "
                          f"{len(set(cols_b) - set(cols_a))} added).",
                          detail={"columns_removed": sorted(set(cols_a) - set(cols_b)),
                                  "columns_added": sorted(set(cols_b) - set(cols_a))}))
    common = sorted(sa & sb)
    if common and common_cols:
        A = da.loc[common, common_cols].astype(str)
        B = db.loc[common, common_cols].astype(str)
        diff = A.ne(B)
        for col in [c for c in common_cols if diff[c].any()]:
            ids = list(diff.index[diff[col]])
            before = {s: A.at[s, col] for s in ids}
            after = {s: B.at[s, col] for s in ids}
            # A changed clinical or survival field is reported as a label conflict even when the new value is
            # blank, matching how the organizers' release generator describes it (relabel_clinical).
            kind = "label_conflict"
            verb = "lost its value for" if all(v.strip() in BLANKS for v in after.values()) else "changed value in"
            vals = pd.Series([f"{before[s] or '(blank)'} -> {after[s] or '(blank)'}" for s in ids]).value_counts()
            moves = "; ".join(f"{k} ({v})" for k, v in vals.head(4).items())
            out.append(Change(kind, f, ids, f"In {f}, {len(ids)} sample(s) {verb} '{col}' between releases ({moves}).",
                              notes={s: f"{col}: '{before[s]}' in {a.name}, '{after[s]}' in {b.name}" for s in ids},
                              evidence_release={s: "B" for s in ids},
                              detail={"column": col, "before": before, "after": after}))
    if lost:
        out.append(Change("membership_change", f, lost,
                          f"In {f}, {len(lost)} sample row(s) present in release {a.name} are missing from release {b.name}.",
                          notes={s: f"present in {a.name}, absent in {b.name}" for s in lost},
                          evidence_release={s: "A" for s in lost}, detail={"direction": "lost"}))
    if gained:
        out.append(Change("membership_change", f, gained,
                          f"In {f}, {len(gained)} new sample row(s) appear in release {b.name}.",
                          notes={s: f"absent in {a.name}, present in {b.name}" for s in gained},
                          evidence_release={s: "B" for s in gained}, confidence="medium", detail={"direction": "gained"}))
    return out


# ----------------------------------------------------------------------------------------------- context
def _subgroups(ids: list[str], rel: Release) -> str:
    """Describe which subtype and ER groups the lost samples come from, using release A's clinical file."""
    if not rel.has("clinical.tsv"):
        return ""
    cl = rel.table("clinical.tsv").frame
    parts = []
    for col, label in (("PAM50Call_RNAseq", "subtype"), ("breast_carcinoma_estrogen_receptor_status", "ER status")):
        if col in cl.columns:
            vals = cl.reindex(ids)[col].fillna("").replace("", "unknown").value_counts()
            parts.append(f"{label}: " + ", ".join(f"{k} {v}" for k, v in vals.items()))
    return " (" + "; ".join(parts) + ")" if parts else ""
