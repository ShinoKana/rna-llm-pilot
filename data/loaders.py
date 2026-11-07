"""Loaders for reference structures.

Every loader yields dicts ``{id, family, seq, ref_db, source}`` where ``ref_db``
is the reference structure in dot-bracket (pseudoknots on [] {} <> pages).

* ``load_archiveii_parquet``: the MultiMolecule mirror of ArchiveII.
* ``load_ct_bpseq_folder``: the original ArchiveII distribution (.ct / .bpseq).
* ``load_bprna_ts0_filtered``: bpRNA TS0 (SPOT-RNA split), scope-filtered.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from data.scope import RULE_VERSION, scope_check
from evals.f1 import pairs_to_dotbracket

# File-name prefixes of the original ArchiveII .ct files -> family names used
# by the parquet mirror, so both sources produce the same labels.
ARCHIVEII_PREFIX = {
    "5s": "5S_rRNA", "16s": "16S_rRNA", "23s": "23S_rRNA", "trna": "tRNA",
    "srp": "SRP", "rnasep": "RNaseP", "tmrna": "tmRNA", "grp1": "group_I_intron",
    "grp2": "group_II_intron", "telomerase": "telomerase",
}


def _clean_seq(seq: str) -> str:
    return seq.strip().upper().replace("T", "U")


def load_archiveii_parquet(path: str | Path):
    import pyarrow.parquet as pq

    for r in pq.read_table(path).to_pylist():
        yield {
            "id": r["id"],
            "family": r["family"],
            "seq": _clean_seq(r["sequence"]),
            "ref_db": r["secondary_structure"],
            "source": "ArchiveII (huggingface.co/datasets/multimolecule/archiveii)",
        }


def read_ct(path: str | Path) -> tuple[str, list[tuple[int, int]]]:
    """Read a .ct file (first structure only). Returns (seq, 0-based pairs)."""
    lines = [ln for ln in Path(path).read_text().splitlines() if ln.strip()]
    n = int(lines[0].split()[0])
    seq, pairs = [], []
    for ln in lines[1:n + 1]:
        f = ln.split()
        i, base, j = int(f[0]), f[1], int(f[4])
        seq.append(base)
        if j > i:
            pairs.append((i - 1, j - 1))
    return _clean_seq("".join(seq)), pairs


def read_bpseq(path: str | Path) -> tuple[str, list[tuple[int, int]]]:
    seq, pairs = [], []
    for ln in Path(path).read_text().splitlines():
        f = ln.split()
        if len(f) != 3 or not f[0].isdigit():
            continue  # header / comment line
        i, base, j = int(f[0]), f[1], int(f[2])
        seq.append(base)
        if j > i:
            pairs.append((i - 1, j - 1))
    return _clean_seq("".join(seq)), pairs


def _family_from_name(stem: str) -> str:
    key = re.split(r"[_\-]", stem, maxsplit=1)[0].lower()
    return ARCHIVEII_PREFIX.get(key, key)


def load_ct_bpseq_folder(folder: str | Path):
    """Read every .ct / .bpseq file below ``folder`` (original ArchiveII layout)."""
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix.lower() not in (".ct", ".bpseq"):
            continue
        seq, pairs = (read_ct if p.suffix.lower() == ".ct" else read_bpseq)(p)
        yield {
            "id": p.stem,
            "family": _family_from_name(p.stem),
            "seq": seq,
            "ref_db": pairs_to_dotbracket(pairs, len(seq)),
            "source": f"ArchiveII local files ({p.suffix.lower()})",
        }


def apply_scope_filter(records, log_path: str | Path | None = None):
    """Keep only allowlisted family + organism records (data/scope.py); optionally log each exclusion (id only)."""
    kept, dropped = [], []
    for r in records:
        ok, reason = scope_check(r["id"], r.get("family"))
        if ok:
            kept.append(r)
        else:
            dropped.append({"id": r["id"], "reason": reason})
    if log_path:   # counts only: the allowlist rule needs no per-record exclusion reasons
        from collections import Counter
        by_fam = Counter(r.get("family", "?") for r in records if r["id"] in {d["id"] for d in dropped})
        with open(log_path, "w") as fh:
            fh.write(json.dumps({"rule": RULE_VERSION, "n_in": len(records), "n_kept": len(kept),
                                 "n_not_in_allowlist": len(dropped), "not_in_allowlist_by_family": dict(by_fam)}) + "\n")
    return kept, dropped


# --------------------------------------------------------------------------
# bpRNA TS0 (optional; the evaluation set for RNA-FM's secondary-structure head)
# --------------------------------------------------------------------------
# bpRNA ids look like bpRNA_<SOURCE>_<n>. The mirror carries no organism or
# Rfam family, so the allowlist rule is fail-closed: a record is kept only if
# its source is one of the cellular-ncRNA databases below AND a metadata file
# maps the id to a description naming an allowlisted organism. Without
# metadata every record is dropped (so the bpRNA-TS0 arm waits for metadata).
BPRNA_CELLULAR_SOURCES = {"CRW", "SRP", "RNP"}
BPRNA_FILTER_RULE = (
    f"{RULE_VERSION}/bpRNA-TS0: keep id only if source in {sorted(BPRNA_CELLULAR_SOURCES)} "
    "and the metadata description names an allowlisted organism; otherwise dropped (fail-closed)."
)


def load_bprna_ts0_filtered(parquet_path: str | Path, metadata_tsv: str | Path | None = None,
                            log_path: str | Path | None = None):
    """Load TS0 from the MultiMolecule ``bprna-spot`` test split, scope-filtered.

    ``metadata_tsv``: optional ``id<TAB>description`` file (e.g. Rfam family and
    organism) used to admit entries from mixed sources. Returns (kept, dropped).
    """
    import pyarrow.parquet as pq

    meta = {}
    if metadata_tsv:
        for ln in Path(metadata_tsv).read_text().splitlines():
            if "\t" in ln:
                k, v = ln.split("\t", 1)
                meta[k.strip()] = v.strip()

    kept, dropped = [], []
    for r in pq.read_table(parquet_path).to_pylist():
        rid = r["id"]
        if not rid.startswith("bpRNA_"):
            continue  # TS1 / TS2 (PDB-derived) rows share this parquet file
        source = rid.split("_")[1]
        desc = meta.get(rid)
        ok, reason = (scope_check(f"{rid} {desc}") if (desc and source in BPRNA_CELLULAR_SOURCES)
                      else (False, "not in allowlist"))
        if not ok:
            dropped.append({"id": rid, "source": source, "reason": reason})
            continue
        kept.append({
            "id": rid,
            "family": f"bpRNA_{source}",
            "seq": _clean_seq(r["sequence"]),
            "ref_db": r["secondary_structure"],
            "source": "bpRNA-TS0 (huggingface.co/datasets/multimolecule/bprna-spot)",
        })
    if log_path:
        with open(log_path, "w") as fh:
            fh.write(json.dumps({"rule": BPRNA_FILTER_RULE, "n_kept": len(kept),
                                 "n_dropped": len(dropped)}) + "\n")
    return kept, dropped
