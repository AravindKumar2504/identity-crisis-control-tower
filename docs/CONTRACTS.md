# Contracts for the Friday pieces

Build against these so the pieces fit together at the 9 PM merge. The release engine (`tower/release.py`, `tower/diff.py`, `tower/analyses.py`, `tower/findings.py`) is done; use it, don't rebuild it.

## 1. Research-question card (`cards/<id>.yaml`) · Chirag

Fields follow the organizers' card (`warmup/wisconsin/track1-cohort-firewall/question_card.md` in the challenge repo), plus what the tool needs to run it.

```yaml
id: os-luminal-a
title: Overall survival by subtype, Luminal A focus
intended_use: Compare overall survival between PAM50 subtypes, with Luminal A as the reference group
group_studied: Primary tumors (sample type 01) with a PAM50 call
outcome: Overall survival (OS, OS.time in survival.tsv)
acceptable_limitations: Up to 5% of the group excluded for documented reasons
not_acceptable: Counting a patient twice; an endpoint the data's own curators advise against for this group
out_of_scope: Treatment advice, risk scores, any clinical claim
uses:                      # every file and field the question reads (drives lineage and impact)
  clinical.tsv: [PAM50Call_RNAseq]
  survival.tsv: [OS, OS.time, _PATIENT, Redaction]
analyses: []               # protected analyses this question depends on: A1, A2
checks: [survival_endpoint, survival_redacted, survival_zero_time, patient_double_count, subtype_columns_disagree]
```

## 2. A check (`tower/checks/<name>.py`) · Aakruti

```python
def run(release, card) -> list[Issue]: ...
```

`Issue` fields (a dataclass in `tower/checks/__init__.py`):

| Field | Meaning |
|---|---|
| `id` | Short stable id, e.g. `survival_redacted` |
| `title` | One line a non-specialist understands |
| `status` | `pass`, `warn` (usable with conditions), `block` (can't support this use), `unknown` (can't tell, e.g. a needed file is missing) |
| `material` | Does it matter **for this card**? Checks that don't apply return `pass` with `material: false` and are listed as "checked, not material" |
| `pre_existing` | True when the problem is already in release A (never goes into `findings.json`) |
| `fields` | The columns read, e.g. `["survival.tsv:OS", "survival.tsv:Redaction"]` |
| `rows` | Every sample id involved (lineage) |
| `numbers` | The counts behind the result, e.g. `{"redacted": 5, "group": 844}` |
| `rule` | The decision rule in words, e.g. "Block if the curators advise against the endpoint for the group" |
| `source` | Citation or URL (TCGA-CDR, TCGA barcode docs, GDC annotations, the organizers' FAQ) |
| `limitation` | What the check can't see |
| `next_step` | A fix sized to the problem |
| `evidence_needed` | What would change the result |

## 3. Verdict rule (`tower/readiness.py`) · Aravind

Over the material issues for the card, in order: any `unknown` gives **Insufficient Evidence**; any `block` gives **Blocked**; any `warn`, or any release change touching what the card reads, gives **Conditional**; otherwise **Ready**. The reasons list every issue that decided it.

## 4. `readiness.json` (output) · Aravind

```json
{
  "card": {"id": "...", "title": "..."},
  "verdict": "Conditional",
  "reasons": ["..."],
  "issues": [ {"id": "...", "status": "warn", "material": true, "pre_existing": true, "...": "..."} ],
  "release_changes": "findings.json summary: counts by kind, which touch this card",
  "robustness": {"A2": {"PAM50Call_RNAseq": {"...": "..."}, "PAM50_mRNA_nature2012": {"...": "..."}}},
  "review": {"items": [{"id": "F1", "decision": "approve", "reviewer": "...", "role": "...", "reason": "...", "time": "..."}],
             "signed_off": null},
  "lineage": [{"conclusion": "...", "issues": ["..."], "fields": ["..."], "rows": ["..."], "files": {"clinical.tsv": "<sha256>"}}]
}
```

The screen reads only `findings.json` and `readiness.json`. If it needs anything else, add a field here first.
