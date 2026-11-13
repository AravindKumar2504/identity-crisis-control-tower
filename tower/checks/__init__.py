"""Release A data checks: the contract every check follows (docs/CONTRACTS.md, section 2).

A check reads one release and one research-question card and returns Issues:

    from tower.checks import Issue, register

    @register("survival_redacted")
    def survival_redacted(release, card):
        ...
        return [Issue(id="survival_redacted", title="...", status="warn", material=True, ...)]

`release` is a tower.release.Release (use release.table("clinical.tsv").frame, release.path, and so on).
`card` is the research-question card as a dict (fields in docs/CONTRACTS.md, section 1).
A check that doesn't apply to the card returns status "pass" with material=False, so the report can say it was
checked and found not material. Issues never go into findings.json, which holds release changes only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

STATUSES = ("pass", "warn", "block", "unknown")


@dataclass
class Issue:
    id: str                         # short stable id, e.g. "survival_redacted"
    title: str                      # one line a non-specialist understands
    status: str                     # pass | warn (usable with conditions) | block (can't support this use) | unknown
    material: bool                  # does it matter for this card?
    pre_existing: bool = True       # already in release A
    fields: list[str] = field(default_factory=list)   # columns read, as "file:column"
    rows: list[str] = field(default_factory=list)     # every sample id involved (the evidence trail)
    numbers: dict = field(default_factory=dict)       # the counts behind the result
    rule: str = ""                  # the decision rule in words
    source: str = ""                # citation or URL
    limitation: str = ""            # what the check can't see
    next_step: str = ""             # a fix sized to the problem
    evidence_needed: str = ""       # what would change the result

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"Issue {self.id}: status must be one of {STATUSES}, got {self.status!r}")

    def to_dict(self) -> dict:
        return asdict(self)


CHECKS: dict[str, Callable] = {}


def register(name: str):
    """Decorator that makes a check available to cards by name."""
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


def run_checks(release, card: dict) -> list[Issue]:
    """Run every check the card lists; a listed check that doesn't exist yet comes back as 'unknown'."""
    out: list[Issue] = []
    for name in card.get("checks", []):
        fn = CHECKS.get(name)
        if fn is None:
            out.append(Issue(id=name, title=f"Check '{name}' is not implemented yet", status="unknown",
                             material=True, limitation="The tool cannot judge this part of the question yet."))
            continue
        out.extend(fn(release, card))
    return out
