"""Paired bootstrap 95% CIs for the key comparisons (same items, resampled with replacement, 10,000 draws).
Writes results/ci.md."""
import json, random
from pathlib import Path
ROOT = Path(__file__).resolve().parent

def f1s(path):
    return {json.loads(l)["id"]: json.loads(l)["exact"]["f1"] for l in (ROOT / path).read_text().splitlines() if l.strip()}

def paired(a, b, n=10000, seed=1):
    ids = sorted(set(a) & set(b)); rnd = random.Random(seed)
    d = [a[i] - b[i] for i in ids]; m = sum(d) / len(d)
    bs = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(n))
    return len(ids), m, bs[int(0.025 * n)], bs[int(0.975 * n)]

R = "results/"
cmp = [
 ("ArchiveII: Claude pairs - Claude direct", R+"llm-direct-pairs__claude-cli__claude-opus-5-5.jsonl", R+"llm-direct__claude-cli__claude-opus-5-5.jsonl"),
 ("ArchiveII: GPT pairs - GPT direct", R+"llm-direct-pairs__codex-cli__gpt-6.1-terra.jsonl", R+"llm-direct__codex-cli__gpt-6.1-terra.jsonl"),
 ("ArchiveII: Claude pairs - RNAfold", R+"llm-direct-pairs__claude-cli__claude-opus-5-5.jsonl", R+"rnafold__local__ViennaRNA-2.7.2.jsonl"),
 ("ArchiveII: Claude agent - RNAfold", R+"llm-agent__claude-cli__claude-opus-5-5.jsonl", R+"rnafold__local__ViennaRNA-2.7.2.jsonl"),
 ("ArchiveII: GPT agent - RNAfold", R+"llm-agent__codex-cli__gpt-6.1-terra.jsonl", R+"rnafold__local__ViennaRNA-2.7.2.jsonl"),
 ("ArchiveII: Gemini agent - RNAfold", R+"llm-agent__gemini-cli__gemini-4-argon-medium.jsonl", R+"rnafold__local__ViennaRNA-2.7.2.jsonl"),
 ("ArchiveII: Gemini direct - RNAfold", R+"llm-direct__gemini-cli__gemini-4-argon-medium.jsonl", R+"rnafold__local__ViennaRNA-2.7.2.jsonl"),
 ("ArchiveII: RNA-FM - RNAfold", R+"rnafm__local__RNA-FM-ResNet_bpRNA.jsonl", R+"rnafold__local__ViennaRNA-2.7.2.jsonl"),
 ("NF: Claude pairs - Claude direct", R+"nf/pairs_claude.jsonl", R+"nf/direct_claude.jsonl"),
 ("NF: Claude pairs - RNAfold", R+"nf/pairs_claude.jsonl", R+"nf/rnafold.jsonl"),
 ("NF: RNA-FM - RNAfold", R+"nf/rnafm.jsonl", R+"nf/rnafold.jsonl"),
]
rows = ["| comparison | n | mean diff | 95% CI |", "|---|---|---|---|"]
for name, a, b in cmp:
    n, m, lo, hi = paired(f1s(a), f1s(b))
    rows.append(f"| {name} | {n} | {m:+.3f} | [{lo:+.3f}, {hi:+.3f}] |")
md = "# Paired bootstrap CIs (F1 difference, 10,000 resamples)\n\n" + "\n".join(rows) + "\n"
(ROOT / "results/ci.md").write_text(md); print(md)
