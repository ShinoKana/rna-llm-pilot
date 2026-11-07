# Memorisation gap (difficulty-adjusted with RNAfold)

Memorisation gap, difficulty-adjusted: the two sets differ in difficulty (and reference type), so each method is
first compared with RNAfold on the same set:
    gap = (F1_known - RNAfold_known) - (F1_novel - RNAfold_novel)
known = ArchiveII (comparative structures), novel = bpRNA-NF-15.0 (Rfam-derived consensus). Positive gap = the method
does relatively better on known families. Writes results/gap.md.

| method | F1 known | F1 novel | vs RNAfold known | vs RNAfold novel | gap | valid known | valid novel |
|---|---|---|---|---|---|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 0.673 (n=50) | 0.834 (n=50) | +0.017 | +0.000 | +0.017 | 46/50 | 50/50 |
| llm-direct (claude-cli/claude-opus-5-5) | 0.405 (n=50) | 0.225 (n=50) | -0.250 | -0.609 | +0.359 | 28/50 | 20/50 |
| llm-direct (codex-cli/gpt-6.1-terra) | 0.223 (n=50) | 0.226 (n=50) | -0.433 | -0.608 | +0.175 | 48/50 | 48/50 |
| llm-direct (gemini-cli/gemini-4-argon-medium) | 0.392 (n=50) | 0.391 (n=50) | -0.263 | -0.443 | +0.179 | 32/50 | 37/50 |
| llm-direct-pairs (claude-cli/claude-opus-5-5) | 0.652 (n=50) | 0.607 (n=50) | -0.003 | -0.227 | +0.224 | 50/50 | 50/50 |
| rnafm | 0.787 (n=50) | 0.767 (n=50) | +0.132 | -0.067 | +0.199 | 50/50 | 50/50 |
| rnafold | 0.655 (n=50) | 0.834 (n=50) | +0.000 | +0.000 | +0.000 | 50/50 | 50/50 |

Caveat: the two sets also differ in reference type, so part of any gap may come from that, not from memorisation.