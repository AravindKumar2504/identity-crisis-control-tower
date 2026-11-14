"""Research-question cards: load them, and work out which samples a card's question is about.

A card is a YAML file in cards/ (fields in docs/CONTRACTS.md, section 1). Its `group` block says which samples
the question studies; every check and the verdict use the same group, so they never disagree about who is in.
"""
from __future__ import annotations

import pathlib

import yaml

from .release import Release, sample_type

CARDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "cards"
BLANKS = {"", "NA", "nan", "NaN", "[Not Available]", "[Not Evaluated]", "[Unknown]", "[Not Applicable]"}
REQUIRED = ["id", "title", "intended_use", "group_studied", "outcome", "acceptable_limitations",
            "not_acceptable", "out_of_scope", "uses", "checks"]


def load_card(path_or_id: str) -> dict:
    p = pathlib.Path(path_or_id)
    if not p.exists():
        p = CARDS_DIR / f"{path_or_id}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"no card '{path_or_id}' (looked for {p}); see `python -m tower cards`")
    card = yaml.safe_load(p.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in card]
    if missing:
        raise ValueError(f"card {p.name} is missing {', '.join(missing)}")
    card["_path"] = str(p)
    return card


def list_cards() -> list[dict]:
    return [load_card(str(p)) for p in sorted(CARDS_DIR.glob("*.yaml"))]


def card_group(release: Release, card: dict) -> set[str]:
    """Sample ids the card's question is about, in this release. Empty if the release can't say."""
    g = card.get("group", {}) or {}
    if not release.has("clinical.tsv"):
        return set()
    cl = release.table("clinical.tsv").frame
    ids = set(cl.index)
    if g.get("sample_type"):
        ids = {s for s in ids if sample_type(s) == str(g["sample_type"])}
    for f in g.get("in_files", []) or []:
        if not release.has(f):
            return set()
        ids &= set(release.table(f).samples())
    for col, allowed in (g.get("values") or {}).items():
        if col not in cl.columns:
            return set()
        ids = {s for s in ids if cl.at[s, col] in set(allowed)}
    for col in g.get("not_blank", []) or []:
        if col not in cl.columns:
            return set()
        ids = {s for s in ids if str(cl.at[s, col]).strip() not in BLANKS}
    return ids


def card_base_group(release: Release, card: dict) -> set[str]:
    """The card's samples before its value and not-blank filters (sample type and files only).

    Use it to measure missing values: a card's own group already drops the blanks, so blanks counted inside it are zero.
    """
    base = {k: v for k, v in (card.get("group") or {}).items() if k in ("sample_type", "in_files")}
    return card_group(release, {**card, "group": base})


def card_fields(card: dict) -> list[str]:
    """Every field the card reads, as 'file:column-or-row' (for the evidence trail)."""
    return [f"{f}:{c}" for f, cols in (card.get("uses") or {}).items() for c in (cols or [])]
