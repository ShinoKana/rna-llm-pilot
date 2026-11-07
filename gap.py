"""Memorisation gap, difficulty-adjusted: the two sets differ in difficulty (and reference type), so each method is
first compared with RNAfold on the same set:
    gap = (F1_known - RNAfold_known) - (F1_novel - RNAfold_novel)
known = ArchiveII (comparative structures), novel = bpRNA-NF-15.0 (Rfam-derived consensus). Positive gap = the method
does relatively better on known families. Writes results/gap.md.
"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
from report import table

def load(d):
    s = json.loads((ROOT / d / "analysis.json").read_text())
    return s

K, N = load("results"), load("results/nf")
rk, rn = K["rnafold"]["f1"], N["rnafold"]["f1"]
rows = []
for lab in sorted(set(K) & set(N)):
    dk, dn = K[lab]["f1"] - rk, N[lab]["f1"] - rn
    rows.append([lab, f"{K[lab]['f1']:.3f} (n={K[lab]['n']})", f"{N[lab]['f1']:.3f} (n={N[lab]['n']})", f"{dk:+.3f}", f"{dn:+.3f}",
                 f"{dk - dn:+.3f}", f"{K[lab]['valid']}/{K[lab]['n']}", f"{N[lab]['valid']}/{N[lab]['n']}"])
md = ["# Memorisation gap (difficulty-adjusted with RNAfold)", "", __doc__.strip(), "",
      table(["method", "F1 known", "F1 novel", "vs RNAfold known", "vs RNAfold novel", "gap", "valid known", "valid novel"], rows), "",
      "Caveat: the two sets also differ in reference type, so part of any gap may come from that, not from memorisation."]
(ROOT / "results/gap.md").write_text("\n".join(md)); print("\n".join(md))
