"""Stratified sample of ArchiveII -> data/manifest.jsonl.

Steps: load -> keep length <= max_len and A/C/G/U only -> scope filter
(cellular, non-pathogen) -> drop duplicate sequences -> allocate the sample
across families as evenly as availability allows -> within each family,
split by length into equal-size bins and sample evenly from each (fixed seed).

Usage:
    python -m data.sample                       # parquet mirror, n=50, seed=20261104
    python -m data.sample --ct-dir path/to/archiveII
    python -m data.sample --bprna-ts0 --out data/manifest_ts0.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from data.loaders import (apply_scope_filter, load_archiveii_parquet, load_bprna_ts0_filtered,
                          load_ct_bpseq_folder)

HERE = Path(__file__).resolve().parent
DEFAULT_SEED = 20261104


def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Water-filling: equal share per family, capped by availability."""
    alloc, remaining = {}, n
    fams = sorted(sizes, key=lambda f: (sizes[f], f))
    for k, fam in enumerate(fams):
        left = len(fams) - k
        share = -(-remaining // left)  # ceil
        alloc[fam] = min(sizes[fam], share)
        remaining -= alloc[fam]
    return alloc


def _split(items: list, k: int) -> list[list]:
    q, r = divmod(len(items), k)
    out, start = [], 0
    for b in range(k):
        size = q + (1 if b < r else 0)
        out.append(items[start:start + size])
        start += size
    return out


def stratified_sample(records: list[dict], n: int, seed: int, n_len_bins: int = 3) -> list[dict]:
    rng = random.Random(seed)
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_fam[r["family"]].append(r)
    alloc = allocate({f: len(v) for f, v in by_fam.items()}, n)
    picked = []
    for fam in sorted(by_fam):
        items = sorted(by_fam[fam], key=lambda r: (len(r["seq"]), r["id"]))
        want = alloc[fam]
        if want == 0:
            continue
        k = min(n_len_bins, want)
        bins = _split(items, k)
        quotas = [len(c) for c in _split(list(range(want)), k)]
        carry = 0
        for b, (chunk, quota) in enumerate(zip(bins, quotas)):
            take = min(len(chunk), quota + carry)
            carry = quota + carry - take
            for r in rng.sample(chunk, take):
                picked.append({**r, "length_bin": f"{b + 1}/{k}"})
    picked.sort(key=lambda r: (r["family"], len(r["seq"]), r["id"]))
    return picked


def prepare(records, max_len: int, log_path: Path):
    records = [r for r in records if len(r["seq"]) <= max_len and set(r["seq"]) <= set("ACGU")]
    kept, dropped = apply_scope_filter(records, log_path)
    seen, uniq = set(), []
    for r in sorted(kept, key=lambda r: r["id"]):
        if r["seq"] not in seen:
            seen.add(r["seq"])
            uniq.append(r)
    print(f"[sample] {len(records)} <= {max_len} nt; scope-excluded {len(dropped)} "
          f"(log: {log_path.name}); {len(uniq)} unique sequences remain")
    return uniq


def write_manifest(rows: list[dict], out: Path):
    with open(out, "w") as fh:
        for r in rows:
            fh.write(json.dumps({
                "id": r["id"], "family": r["family"], "length": len(r["seq"]),
                "seq": r["seq"], "ref_db": r["ref_db"],
                "source": r["source"], "length_bin": r.get("length_bin"),
            }) + "\n")
    print(f"[sample] wrote {len(rows)} rows -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--max-len", type=int, default=200)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--parquet", default=str(HERE / "raw/archiveii/test.parquet"))
    ap.add_argument("--ct-dir", help="read ArchiveII .ct/.bpseq files from this folder instead")
    ap.add_argument("--bprna-ts0", action="store_true", help="sample from filtered bpRNA TS0")
    ap.add_argument("--bprna-parquet", default=str(HERE / "raw/bprna_spot/test.parquet"))
    ap.add_argument("--bprna-metadata", help="optional id<TAB>description TSV for bpRNA TS0")
    ap.add_argument("--out", default=str(HERE / "manifest.jsonl"))
    a = ap.parse_args()

    if a.bprna_ts0:
        records, _ = load_bprna_ts0_filtered(a.bprna_parquet, a.bprna_metadata,
                                             log_path=HERE / "bprna_ts0_filter_log.jsonl")
        log = HERE / "bprna_ts0_scope_exclusions.jsonl"
    else:
        records = list(load_ct_bpseq_folder(a.ct_dir) if a.ct_dir else load_archiveii_parquet(a.parquet))
        log = HERE / "scope_exclusions.jsonl"
    rows = stratified_sample(prepare(records, a.max_len, log), a.n, a.seed)
    write_manifest(rows, Path(a.out))
    counts = defaultdict(int)
    for r in rows:
        counts[r["family"]] += 1
    print("[sample] per family:", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
