"""Second-level analysis over results/*.jsonl: MCC, fabricated stems, self-check mismatch, B-arm tool outcome,
and a per-family / known-vs-rare split. Writes results/analysis.md and results/analysis.json.

    python analysis.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from evals.extra import claims_self_check, fabricated_stems, mcc, tool_outcome
from evals.f1 import parse_dotbracket
from report import label, load, mean, table

ROOT = Path(__file__).resolve().parent


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/manifest.jsonl")
    ap.add_argument("--results", default="results")
    a = ap.parse_args()
    man = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / a.manifest).read_text().splitlines() if l.strip()}
    recs = load(sorted((ROOT / a.results).glob("*.jsonl")))
    by = defaultdict(list)
    for r in recs:
        if r["id"] in man:
            by[label(r)].append(r)
    rows, fam_rows, tool_rows, summary = [], [], [], {}
    fams = sorted({m["family"] for m in man.values()})
    for lab, rs in sorted(by.items()):
        fab = tot = 0
        claim_bad = claim_n = 0
        for r in rs:
            ref = parse_dotbracket(man[r["id"]]["ref_db"])
            if r["valid"]:
                from evals.f1 import validate
                v = validate(r["pred_db"], man[r["id"]]["seq"])
                f, n = fabricated_stems(v.pairs, ref); fab += f; tot += n
            if claims_self_check(r.get("raw_output")):
                claim_n += 1
                claim_bad += 0 if r["valid"] else 1
        s = dict(n=len(rs), valid=sum(r["valid"] for r in rs), f1=mean(r["exact"]["f1"] for r in rs),
                 f1_valid=mean(r["exact"]["f1"] for r in rs if r["valid"]), slip_f1=mean(r["slip1"]["f1"] for r in rs),
                 mcc=mean(mcc(r["exact"]["precision"], r["exact"]["recall"]) for r in rs),
                 fabricated_stems=fab, stems=tot, self_check_claims=claim_n, self_check_claims_invalid=claim_bad,
                 errors=sum(1 for r in rs if r.get("error")))
        summary[lab] = s
        rows.append([lab, s["n"], f"{s['valid']}/{s['n']}", f"{s['f1']:.3f}", f"{s['f1_valid']:.3f}", f"{s['slip_f1']:.3f}",
                     f"{s['mcc']:.3f}", f"{fab}/{tot}", f"{claim_bad}/{claim_n}", s["errors"]])
        fam_rows.append([lab] + [f"{mean(r['exact']['f1'] for r in rs if r['family'] == fm):.3f}" for fm in fams])
        oc = Counter(tool_outcome(r, man[r["id"]]["ref_db"]) for r in rs)
        if any(k for k in oc if k):
            summary[lab]["tool_outcomes"] = dict(oc)
            called = [r for r in rs if (r.get("extra") or {}).get("tool_audit", {}).get("status") != "no_tool_call"]
            notc = [r for r in rs if r not in called]
            summary[lab].update(tool_call_rate=len(called) / len(rs), f1_called=mean(r["exact"]["f1"] for r in called),
                                f1_not_called=mean(r["exact"]["f1"] for r in notc))
            tool_rows.append([lab, f"{len(called)}/{len(rs)}", f"{summary[lab]['f1_called']:.3f}",
                              f"{summary[lab]['f1_not_called']:.3f}" if notc else "-"]
                             + [oc.get(k, 0) for k in ("verbatim", "improved", "worsened", "altered_same_f1",
                                                       "tool_called_on_other_seq", "no_final_structure")])
    md = ["# Pilot analysis (extra metrics)", "",
          "F1 counts invalid answers as 0. MCC is the approximate base-pair MCC sqrt(PPV x sensitivity). "
          "Fabricated stem: a predicted stem (>= 2 stacked pairs) with no pair within +-1 of a reference pair. "
          "Self-check: answers whose text claims a length or balance check; first number is how many of those were invalid.", "",
          table(["method", "n", "valid", "F1", "F1 valid only", "F1 +-1", "MCC", "fabricated stems", "self-check claim but invalid",
                 "call errors"], rows), "", "## F1 per family", "",
          table(["method"] + [f"{fm} (n={sum(m['family'] == fm for m in man.values())})" for fm in fams], fam_rows), ""]
    if tool_rows:
        md += ["## Method B: what the model did with the RNAfold output", "",
               table(["method", "tool call rate", "F1 when called", "F1 when not called", "verbatim", "improved", "worsened",
                      "altered, same F1", "tool on other seq", "no final structure"], tool_rows), ""]
    (ROOT / a.results / "analysis.md").write_text("\n".join(md))
    (ROOT / a.results / "analysis.json").write_text(json.dumps(summary, indent=1))
    print("\n".join(md))


if __name__ == "__main__":
    main()
