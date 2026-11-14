"""Release A survival-record checks (Aakruti): problems in survival.tsv that would bias a survival comparison.

  survival_redacted     group samples whose survival record the provider marked as redacted (keep, flag, review)
  survival_zero_time    group samples with a follow-up time of 0 for the card's endpoint (exclude and report)
  patient_double_count  patients with more than one sample in the card's group (would be counted twice)

Every count is computed from the release passed in, so the same checks work on sealed envelopes.
Each returns Issues in the shared contract (tower/checks/__init__.py).
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from ..cards import BLANKS, card_group
from ..release import sample_type
from . import Issue, register
from .fitness import CDR, ENDPOINTS

SV = "survival.tsv"
RULING = "Organizers' ruling on Discord (Friday): keep redacted survival rows, but flag them for review; never drop them"


def _blank(v) -> bool:
    return str(v).strip() in BLANKS


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _plain(col: str) -> str:
    """A survival column's plain name (used in titles), or the raw column when it has none."""
    base, timed = (col[:-5], True) if col.endswith(".time") else (col, False)
    if base in ENDPOINTS:
        return f"the follow-up time for {ENDPOINTS[base]}" if timed else f"the {ENDPOINTS[base]} event marker"
    return {"Redaction": "the redaction marker", "_PATIENT": "the patient ID"}.get(col, col)


def _named(col: str) -> str:
    """The plain name with the raw column in brackets (used in next steps and limitations)."""
    plain = _plain(col)
    return f"{plain} ({col})" if plain != col else col


def _load(release, card, name: str, columns: list[str]):
    """The survival table and the card's group within it, or an 'unknown' Issue explaining why it can't be judged."""
    fields = [f"{SV}:{c}" for c in columns]
    if not release.has(SV):
        state = "unreadable" if SV in release.unreadable else "missing"
        return None, None, Issue(
            id=name, title=f"The survival file is {state}, so this can't be checked", status="unknown",
            material=True, pre_existing=False, fields=fields,
            rule="This check can only be judged from a readable survival.tsv.", source=CDR,
            limitation="Without the survival file the tool can't see any survival record.",
            next_step="Get a release with a readable survival file (survival.tsv).",
            evidence_needed="A release containing survival.tsv, matching its published fingerprint.")
    sv = release.table(SV).frame
    missing = [c for c in columns if c not in sv.columns]
    if missing:
        what = ", ".join(f"{SV}:{c}" for c in missing)
        plain = " or ".join(_plain(c) for c in missing)
        return None, None, Issue(
            id=name, title=f"The survival file has no column for {plain}, so this can't be checked", status="unknown",
            material=True, pre_existing=False, fields=fields, numbers={"missing_fields": missing},
            rule="This check needs every column it reads to exist.", source=CDR,
            limitation="Without the column the tool can't see this part of the survival records.",
            next_step=f"Get a release whose survival file includes {' and '.join(_named(c) for c in missing)}.",
            evidence_needed=f"A release with {what}.")
    group = sorted(card_group(release, card) & set(sv.index))
    if not group:
        return None, None, Issue(
            id=name, title="No samples of this question's group have a survival record here, so this can't be checked",
            status="unknown", material=True, pre_existing=False, fields=fields, numbers={"group_samples": 0},
            rule="This check needs the question's group to have survival records.", source=CDR,
            limitation="The group may be empty because the clinical file is missing or the group's columns are absent.",
            next_step="Check that the clinical file (clinical.tsv) and the survival file (survival.tsv) are both "
                      "present and readable.",
            evidence_needed="A release where the question's group has survival records.")
    return sv, group, None


def _endpoint(card, name: str):
    ep = (card.get("endpoint") or {}).get("name")
    if ep in ENDPOINTS:
        return ep, None
    return None, Issue(id=name, title="The card names no survival endpoint, so this check doesn't apply",
                       status="pass", material=False, pre_existing=False)


@register("survival_redacted")
def survival_redacted(release, card):
    name = "survival_redacted"
    _, na = _endpoint(card, name)
    if na:
        return [na]
    sv, group, bad = _load(release, card, name, ["Redaction"])
    if bad:
        return [bad]
    red_all = [s for s in sv.index if not _blank(sv.at[s, "Redaction"])]
    red = [s for s in group if not _blank(sv.at[s, "Redaction"])]
    numbers = {"redacted_in_group": len(red), "group_samples": len(group),
               "redacted_rows_in_file": len(red_all),
               "redacted_primary_tumors_in_file": sum(sample_type(s) == "01" for s in red_all),
               "redaction_values": dict(Counter(str(sv.at[s, "Redaction"]).strip() for s in red))}
    common = dict(id=name, pre_existing=True, fields=[f"{SV}:Redaction"], rows=red, numbers=numbers,
                  source=f"{CDR}; {RULING}",
                  rule="Warn if any sample in the question's group has a value in survival.tsv Redaction.",
                  limitation="The survival file doesn't say why a record was redacted. A record with the same problem "
                             "that wasn't marked can't be seen here.")
    if not red:
        return [Issue(title="No survival record in this group is marked as redacted", status="pass", material=True,
                      **common)]
    return [Issue(title=f"{_plural(len(red), 'sample', 'samples')} in this group "
                        f"{'has a survival record' if len(red) == 1 else 'have survival records'} the data provider "
                        f"marked as redacted (of {len(group)})",
                  status="warn", material=True,
                  next_step=f"Keep the {_plural(len(red), 'sample', 'samples')}, but have a person review "
                            f"{'it' if len(red) == 1 else 'each one'} before use: {', '.join(red)}. Don't drop them "
                            "silently (the organizers' ruling).",
                  evidence_needed="The reason for each redaction, or a release where these records are confirmed or "
                                  "corrected.",
                  **common)]


@register("survival_zero_time")
def survival_zero_time(release, card):
    name = "survival_zero_time"
    ep, na = _endpoint(card, name)
    if na:
        return [na]
    tcol = f"{ep}.time"
    sv, group, bad = _load(release, card, name, [ep, tcol])
    if bad:
        return [bad]
    t = pd.to_numeric(sv[tcol], errors="coerce")
    e = pd.to_numeric(sv[ep], errors="coerce")
    zero = [s for s in group if t[s] == 0]
    primaries = [s for s in sv.index if sample_type(s) == "01"]
    label = ENDPOINTS[ep]
    numbers = {"endpoint": ep, "zero_time_in_group": len(zero), "group_samples": len(group),
               "share": round(len(zero) / len(group), 4),
               "zero_time_with_event": int((e[zero] == 1).sum()) if zero else 0,
               "blank_or_not_a_number_time_in_group": int(t[group].isna().sum()),
               "zero_time_primary_tumors_in_file": int((t[primaries] == 0).sum())}
    common = dict(id=name, pre_existing=True, fields=[f"{SV}:{tcol}", f"{SV}:{ep}"], rows=zero, numbers=numbers,
                  source=CDR,
                  rule=f"Warn if any sample in the question's group has {tcol} equal to 0: a record with no follow-up "
                       "time adds nothing to a time-to-event comparison and may be a placeholder.",
                  limitation=f"It sees only follow-up times of exactly 0 in {_named(tcol)}. A time that is wrong but "
                             "not 0 can't be detected here. Blank times are counted in the numbers but don't trigger "
                             "the warning.")
    if not zero:
        return [Issue(title=f"No sample in this group has a follow-up time of 0 for {label}", status="pass",
                      material=True, **common)]
    return [Issue(title=f"{_plural(len(zero), 'sample', 'samples')} in this group "
                        f"{'has' if len(zero) == 1 else 'have'} a follow-up time of 0 days for {label} "
                        f"(of {len(group)})",
                  status="warn", material=True,
                  next_step=f"Exclude the {_plural(len(zero), 'sample', 'samples')} with no follow-up time from the "
                            f"{label} comparison, and report how many were excluded and why.",
                  evidence_needed="The actual follow-up dates for these patients, or confirmation that 0 is correct.",
                  **common)]


@register("patient_double_count")
def patient_double_count(release, card):
    name = "patient_double_count"
    _, na = _endpoint(card, name)
    if na:
        return [na]
    sv, group, bad = _load(release, card, name, [])
    if bad:
        return [bad]
    has_col = "_PATIENT" in sv.columns

    def patient(s):
        p = sv.at[s, "_PATIENT"] if has_col else ""
        return s[:12] if _blank(p) else str(p).strip()

    # In the group: who appears more than once?
    by_patient: dict[str, list[str]] = {}
    for s in group:
        by_patient.setdefault(patient(s), []).append(s)
    twice = {p: v for p, v in by_patient.items() if len(v) > 1}

    # Context, whole file: patients with several rows, and whether those rows are identical.
    all_by: dict[str, list[str]] = {}
    for s in sv.index:
        all_by.setdefault(patient(s), []).append(s)
    multi = {p: v for p, v in all_by.items() if len(v) > 1}
    cols = [c for c in sv.columns if c != "_PATIENT"]
    identical = [p for p, v in multi.items() if len(sv.loc[v, cols].drop_duplicates()) == 1]
    combos = Counter("+".join(sorted(sample_type(s) for s in multi[p])) for p in identical)
    numbers = {"patients_in_group": len(by_patient), "group_samples": len(group),
               "patients_more_than_once_in_group": len(twice),
               "patients_with_several_rows_in_file": len(multi),
               "patients_with_identical_rows_in_file": len(identical),
               "identical_rows_by_sample_types": dict(sorted(combos.items())),
               "patient_id_from": "_PATIENT" if has_col else "first 12 characters of the sample id"}
    fields = [f"{SV}:_PATIENT"] if has_col else []
    common = dict(id=name, pre_existing=True, fields=fields, numbers=numbers, source=CDR,
                  rule="Warn if any patient has more than one sample in the question's group: survival is a property "
                       "of the patient, so each patient must count once.",
                  limitation=f"Patients are matched by {_named('_PATIENT')}, the start of the TCGA barcode. One "
                             "person recorded under two different IDs can't be caught here.")
    if not twice:
        extra = (f"; {_plural(len(identical), 'patient has', 'patients have')} identical survival rows on more than "
                 "one sample (tumor, normal or metastasis), which would count twice if those were included"
                 if identical else "")
        return [Issue(title=f"Each patient appears once in this group ({len(by_patient)} patients){extra}",
                      status="pass", material=False, rows=[], **common)]
    rows = sorted(s for v in twice.values() for s in v)
    return [Issue(title=f"{_plural(len(twice), 'patient appears', 'patients appear')} more than once in this group, "
                        "so they would be counted twice",
                  status="warn", material=True, rows=rows,
                  next_step="Keep one sample per patient (the primary tumor) and report which samples were set aside.",
                  evidence_needed="A group with exactly one sample per patient.",
                  **common)]
