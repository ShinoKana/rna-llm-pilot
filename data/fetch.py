"""Download benchmark data into data/raw/ (git-ignored).

ArchiveII (Sloma & Mathews 2016) was originally distributed by the Mathews lab
as archiveII.tar.gz (.ct/.seq files) at rna.urmc.rochester.edu; that URL
returned 404 when this harness was built (2026-11). We use the MultiMolecule
mirror on Hugging Face (parquet: id, sequence, secondary_structure, family).
If no mirror works, put the original .ct/.bpseq files in a folder and use
``python -m data.sample --ct-dir <folder>``.

Usage:
    python -m data.fetch              # ArchiveII only
    python -m data.fetch --bprna      # also bpRNA-spot test split (contains TS0)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"
SOURCES = {
    "archiveii": [
        "https://huggingface.co/datasets/multimolecule/archiveii/resolve/main/test.parquet",
    ],
    "bprna_spot": [
        "https://huggingface.co/datasets/multimolecule/bprna-spot/resolve/main/test.parquet",
    ],
}
ORIGINAL_ARCHIVEII = "https://rna.urmc.rochester.edu/pub/archiveII.tar.gz (404 as of 2026-11)"


def fetch(name: str) -> Path | None:
    dest = RAW / name / "test.parquet"
    if dest.exists():
        print(f"[fetch] {name}: already present ({dest})")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for url in SOURCES[name]:
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
        except Exception as e:  # noqa: BLE001 - try the next mirror
            print(f"[fetch] {name}: {url} failed: {e}", file=sys.stderr)
            continue
        if not data.startswith(b"PAR1"):
            print(f"[fetch] {name}: {url} did not return a parquet file", file=sys.stderr)
            continue
        dest.write_bytes(data)
        print(f"[fetch] {name}: {len(data)} bytes sha256={hashlib.sha256(data).hexdigest()[:16]}")
        return dest
    print(f"[fetch] {name}: no source worked. Original: {ORIGINAL_ARCHIVEII}. "
          "Fall back to a local .ct/.bpseq folder.", file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bprna", action="store_true", help="also fetch bpRNA-spot test split")
    a = ap.parse_args()
    ok = fetch("archiveii") is not None
    if a.bprna:
        fetch("bprna_spot")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
