"""Load one release folder of the TCGA-BRCA files.

A release is a folder holding some of these files (an envelope release has no RNA file):
  clinical.tsv                 one row per sample, sample id in column `sampleID`
  survival.tsv                 one row per sample, sample id in column `sample`
  mutation_gene_level.tsv.gz   one column per sample, one row per gene (0/1)
  copy_number_gistic.tsv.gz    one column per sample, one row per gene (-2..2)
  protein_rppa.tsv.gz          one column per sample, one row per protein
  rna_hiseq.tsv.gz             one column per sample, one row per gene

Files are fingerprinted before they are parsed, so a file that is identical in two releases is never opened.
Small files keep every cell as its exact text; the three large matrices are parsed as numbers, which is exact
for copied or moved samples because a copy carries the same text and therefore the same number.
"""
from __future__ import annotations

import gzip
import hashlib
import pathlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ROW_FILES = {"clinical.tsv": "sampleID", "survival.tsv": "sample"}
MATRIX_FILES = ["mutation_gene_level.tsv.gz", "copy_number_gistic.tsv.gz", "protein_rppa.tsv.gz", "rna_hiseq.tsv.gz"]
ALL_FILES = list(ROW_FILES) + MATRIX_FILES
TEXT_MATRICES = {"protein_rppa.tsv.gz"}          # small enough to keep as exact text
OPTIONAL_FILES = {"rna_hiseq.tsv.gz"}            # envelopes never include RNA; never a finding
NAN_SENTINEL = np.float64(-1.234567e300)          # stands in for a blank cell when hashing numbers


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_content(path: pathlib.Path) -> str:
    """Hash of the decompressed content, so gzip settings on different machines don't matter."""
    opener = gzip.open if str(path).endswith(".gz") else open
    h = hashlib.sha256()
    with opener(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Table:
    """One parsed file. `frame` has samples as the index (row files) or as columns (matrices)."""
    name: str
    frame: pd.DataFrame
    layout: str                     # "rows" or "columns"
    exact_text: bool
    duplicated_ids: list[str] = field(default_factory=list)   # ids on more than one row or column (the first is kept)

    def samples(self) -> list[str]:
        return list(self.frame.index) if self.layout == "rows" else list(self.frame.columns)

    def features(self) -> list[str]:
        return list(self.frame.columns) if self.layout == "rows" else list(self.frame.index)

    def fingerprints(self, features: list[str] | None = None) -> dict[str, str]:
        """One short hash per sample of everything that sample holds in this file (optionally a feature subset)."""
        f = self.frame
        if self.layout == "rows":
            sub = f if features is None else f[features]
            joined = sub.astype(str).agg("\x1f".join, axis=1)
            return {s: hashlib.sha1(v.encode()).hexdigest()[:20] for s, v in joined.items()}
        sub = f if features is None else f.loc[features]
        out = {}
        if self.exact_text:
            for s in sub.columns:
                out[s] = hashlib.sha1("\x1f".join(sub[s].astype(str)).encode()).hexdigest()[:20]
        else:
            arr = sub.to_numpy(dtype=np.float64, copy=True)
            arr[np.isnan(arr)] = NAN_SENTINEL
            for j, s in enumerate(sub.columns):
                out[s] = hashlib.sha1(np.ascontiguousarray(arr[:, j]).tobytes()).hexdigest()[:20]
        return out


class UnreadableFile(Exception):
    """A file exists but can't be read as the expected table (damaged, empty or wrongly formatted)."""


@dataclass
class Release:
    name: str
    path: pathlib.Path
    file_sha256: dict[str, str] = field(default_factory=dict)
    content_sha256: dict[str, str] = field(default_factory=dict)
    unreadable: dict[str, str] = field(default_factory=dict)     # file -> why it can't be read
    _tables: dict[str, Table] = field(default_factory=dict, repr=False)

    @property
    def files(self) -> list[str]:
        return [f for f in ALL_FILES if f in self.content_sha256]

    @property
    def missing(self) -> list[str]:
        return [f for f in ALL_FILES if f not in self.content_sha256]

    def has(self, name: str) -> bool:
        return name in self.content_sha256

    def table(self, name: str) -> Table:
        if name not in self._tables:
            try:
                self._tables[name] = _parse(self.path / name, name)
            except Exception as e:     # refuse a malformed file instead of comparing garbage
                self.unreadable[name] = f"could not be parsed as the expected table ({type(e).__name__}: {e})"[:240]
                self.content_sha256.pop(name, None)
                raise UnreadableFile(f"{name}: {self.unreadable[name]}") from e
        return self._tables[name]


def _unique_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Suffix repeated row names (ERALPHA, ERALPHA#2) so each row has one name."""
    if not df.index.has_duplicates:
        return df
    seen: dict[str, int] = {}
    names = []
    for x in df.index:
        key = "" if pd.isna(x) else str(x)
        seen[key] = seen.get(key, 0) + 1
        names.append(x if seen[key] == 1 else f"{key}#{seen[key]}")
    out = df.copy()
    out.index = pd.Index(names, name=df.index.name)
    return out


def header_ids(path: pathlib.Path) -> list[str]:
    """Sample ids in a matrix file's header line (pandas would rename a repeat to id.1)."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.readline().rstrip("\r\n").split("\t")[1:]


def repeated(ids) -> list[str]:
    seen, twice = set(), set()
    for x in ids:
        (twice if x in seen else seen).add(x)
    return sorted(twice)


def _one_column_per_id(df: pd.DataFrame, ids: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Keep the first column per sample id; return the frame and the repeated ids."""
    twice = repeated(ids)
    if not twice or len(ids) != df.shape[1]:
        return df, []
    keep = [i for i, x in enumerate(ids) if x not in ids[:i]]
    out = df.iloc[:, keep].copy()
    out.columns = [ids[i] for i in keep]
    return out, twice


def sample_count(path: pathlib.Path, name: str) -> int | None:
    """Samples in a file, from its header or line count."""
    opener = gzip.open if str(path).endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
            header = fh.readline().rstrip("\r\n").split("\t")
            if name in ROW_FILES:
                return sum(1 for line in fh if line.strip())
            return len(set(header[1:]))
    except Exception:
        return None


def _parse(path: pathlib.Path, name: str) -> Table:
    if name in ROW_FILES:
        df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
        idcol = ROW_FILES[name]
        if idcol not in df.columns:
            raise ValueError(f"no '{idcol}' column; the file may not be tab-separated")
        df = df.set_index(idcol, drop=True)
        if df.empty:
            raise ValueError("the table has no rows")
        dup = sorted(set(df.index[df.index.duplicated()]))
        if dup:                     # one row per id, so every lookup is a single value; the comparison reports them
            df = df[~df.index.duplicated(keep="first")]
        return Table(name, df, "rows", True, dup)
    if name in TEXT_MATRICES:
        df = pd.read_csv(path, sep="\t", index_col=0, dtype=str, keep_default_na=False)
        if df.shape[1] == 0 or not any(str(c).startswith("TCGA-") for c in df.columns):
            raise ValueError("no TCGA sample columns found")
        df, twice = _one_column_per_id(df, header_ids(path))
        return Table(name, _unique_rows(df), "columns", True, twice)
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
    dtypes = {c: np.float32 for c in header[1:]}
    dtypes[header[0]] = str                       # gene or protein names
    df = pd.read_csv(path, sep="\t", index_col=0, dtype=dtypes, engine="c")
    if df.shape[1] == 0 or not any(str(c).startswith("TCGA-") for c in df.columns):
        raise ValueError("no TCGA sample columns found")
    df, twice = _one_column_per_id(df, header[1:])
    return Table(name, _unique_rows(df), "columns", False, twice)


def load_release(path: str | pathlib.Path, name: str | None = None) -> Release:
    """Fingerprint every known file in a release folder; parsing happens later, only when needed."""
    p = pathlib.Path(path).expanduser().resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"release folder not found: {p}")
    # An opened envelope keeps its files in <envelope>/release/; name it after the envelope.
    default = p.parent.name if p.name == "release" else p.name
    rel = Release(name=name or default, path=p)
    for f in ALL_FILES:
        fp = p / f
        if fp.exists():
            rel.file_sha256[f] = sha256_file(fp)
            try:
                if fp.stat().st_size == 0:
                    raise ValueError("the file is empty")
                rel.content_sha256[f] = sha256_content(fp)
            except Exception as e:     # e.g. a truncated gzip: report it, never crash
                rel.unreadable[f] = f"{type(e).__name__}: {e}"[:240]
    if not rel.content_sha256 and not rel.unreadable:
        raise FileNotFoundError(f"no TCGA-BRCA files found in {p}")
    return rel


def sample_type(sample_id: str) -> str:
    """Two-digit TCGA sample-type code: 01 primary tumor, 06 metastasis, 11 normal tissue."""
    return sample_id[13:15] if len(sample_id) >= 15 else ""
