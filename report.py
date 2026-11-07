"""Summarise scored runs: per-method table, per-family F1, failure taxonomy.

Usage:
    python report.py                         # all results/*.jsonl
    python report.py results/dryrun/*.jsonl --out results/dryrun/report.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(paths):
    recs = []
    for p in paths:
        recs += [json.loads(ln) for ln in Path(p).read_text().splitlines() if ln.strip()]
    return recs


def label(r):
    return r["method"] if r["provider"] == "local" else f"{r['method']} ({r['provider']}/{r['model']})"


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def build_report(recs) -> str:
    by_method = defaultdict(list)
    for r in recs:
        by_method[label(r)].append(r)
    families = sorted({r["family"] for r in recs})
    def f(x):
        return "-" if x != x else f"{x:.3f}"  # NaN (no records) -> "-"

    rows = []
    for m, rs in sorted(by_method.items()):
        valid = [r for r in rs if r["valid"]]
        tok_in = sum((r.get("usage") or {}).get("input_tokens") or 0 for r in rs)
        tok_out = sum((r.get("usage") or {}).get("output_tokens") or 0 for r in rs)
        rows.append([m, len(rs), f"{len(valid)}/{len(rs)}",
                     f(mean(r["exact"]["precision"] for r in rs)), f(mean(r["exact"]["recall"] for r in rs)),
                     f(mean(r["exact"]["f1"] for r in rs)), f(mean(r["exact"]["f1"] for r in valid)),
                     f(mean(r["slip1"]["f1"] for r in rs)),
                     f(mean(r.get("latency_s") or 0 for r in rs)), f"{tok_in}/{tok_out}"])
    t1 = table(["method", "n", "valid", "P", "R", "F1", "F1 (valid only)", "F1 ±1 slip",
                "latency s", "tokens in/out"], rows)

    rows = []
    for m, rs in sorted(by_method.items()):
        cells = []
        for fam in families:
            fr = [r["exact"]["f1"] for r in rs if r["family"] == fam]
            cells.append(f"{mean(fr):.3f} (n={len(fr)})" if fr else "-")
        rows.append([m] + cells)
    t2 = table(["method"] + families, rows)

    primaries = ["call_error", "no_structure", "invalid_chars", "unbalanced", "length_mismatch",
                 "empty_prediction", "low_f1", "ok"]
    rows, flag_rows = [], []
    for m, rs in sorted(by_method.items()):
        c = Counter(r["failure"] for r in rs)
        rows.append([m] + [c.get(p, 0) for p in primaries])
        fc = Counter(fl for r in rs for fl in r["flags"])
        flag_rows.append([m, ", ".join(f"{k}: {v}" for k, v in sorted(fc.items())) or "-"])
    t3 = table(["method"] + primaries, rows)
    t4 = table(["method", "flags"], flag_rows)

    return "\n\n".join([
        "# Pilot report", f"Records: {len(recs)}. F1 is base-pair F1; invalid predictions score 0.",
        "## Summary per method", t1, "## Exact F1 per family", t2,
        "## Failure taxonomy (primary class)", t3, "## Flags", t4,
        "Taxonomy definitions: see evals/taxonomy.py."]) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--out", help="also write the markdown report here")
    a = ap.parse_args()
    files = a.files or sorted((ROOT / "results").glob("*.jsonl"))
    if not files:
        raise SystemExit("no result files found")
    md = build_report(load(files))
    print(md)
    if a.out:
        Path(a.out).write_text(md)


if __name__ == "__main__":
    main()
