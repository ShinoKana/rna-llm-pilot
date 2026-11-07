# Pilot analysis (extra metrics)

F1 counts invalid answers as 0. MCC is the approximate base-pair MCC sqrt(PPV x sensitivity). Fabricated stem: a predicted stem (>= 2 stacked pairs) with no pair within +-1 of a reference pair. Self-check: answers whose text claims a length or balance check; first number is how many of those were invalid.

| method | n | valid | F1 | F1 valid only | F1 +-1 | MCC | fabricated stems | self-check claim but invalid | call errors |
|---|---|---|---|---|---|---|---|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 50 | 46/50 | 0.673 | 0.731 | 0.701 | 0.674 | 105/339 | 0/17 | 0 |
| llm-agent (codex-cli/gpt-6.1-terra) | 50 | 50/50 | 0.619 | 0.619 | 0.650 | 0.620 | 161/392 | 0/0 | 0 |
| llm-agent (gemini-cli/gemini-4-argon-medium) | 50 | 47/50 | 0.697 | 0.741 | 0.733 | 0.698 | 93/342 | 0/0 | 0 |
| llm-direct (claude-cli/claude-opus-5-5) | 50 | 28/50 | 0.405 | 0.724 | 0.421 | 0.407 | 43/151 | 0/1 | 0 |
| llm-direct (codex-cli/gpt-6.1-terra) | 50 | 48/50 | 0.223 | 0.232 | 0.242 | 0.253 | 35/83 | 0/0 | 0 |
| llm-direct (gemini-cli/gemini-4-argon-medium) | 50 | 32/50 | 0.392 | 0.612 | 0.425 | 0.392 | 81/203 | 0/0 | 0 |
| llm-direct-pairs (claude-cli/claude-opus-5-5) | 50 | 50/50 | 0.652 | 0.652 | 0.684 | 0.655 | 96/304 | 0/0 | 0 |
| llm-direct-pairs (codex-cli/gpt-6.1-terra) | 50 | 50/50 | 0.277 | 0.277 | 0.296 | 0.292 | 126/192 | 0/0 | 0 |
| rnafm | 50 | 50/50 | 0.787 | 0.787 | 0.800 | 0.800 | 27/268 | 0/0 | 0 |
| rnafold | 50 | 50/50 | 0.655 | 0.655 | 0.684 | 0.657 | 149/386 | 0/0 | 0 |

## F1 per family

| method | 16S_rRNA (n=13) | 5S_rRNA (n=12) | SRP (n=12) | tRNA (n=12) | tmRNA (n=1) |
|---|---|---|---|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 0.617 | 0.731 | 0.440 | 0.880 | 1.000 |
| llm-agent (codex-cli/gpt-6.1-terra) | 0.731 | 0.648 | 0.426 | 0.628 | 1.000 |
| llm-agent (gemini-cli/gemini-4-argon-medium) | 0.653 | 0.739 | 0.395 | 0.979 | 1.000 |
| llm-direct (claude-cli/claude-opus-5-5) | 0.200 | 0.389 | 0.180 | 0.869 | 0.414 |
| llm-direct (codex-cli/gpt-6.1-terra) | 0.026 | 0.176 | 0.160 | 0.559 | 0.057 |
| llm-direct (gemini-cli/gemini-4-argon-medium) | 0.143 | 0.223 | 0.243 | 0.979 | 0.407 |
| llm-direct-pairs (claude-cli/claude-opus-5-5) | 0.650 | 0.736 | 0.284 | 0.942 | 0.618 |
| llm-direct-pairs (codex-cli/gpt-6.1-terra) | 0.051 | 0.308 | 0.143 | 0.625 | 0.292 |
| rnafm | 0.460 | 0.902 | 0.796 | 1.000 | 1.000 |
| rnafold | 0.731 | 0.648 | 0.440 | 0.767 | 1.000 |

## Method B: what the model did with the RNAfold output

| method | tool call rate | F1 when called | F1 when not called | verbatim | improved | worsened | altered, same F1 | tool on other seq | no final structure |
|---|---|---|---|---|---|---|---|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 41/50 | 0.627 | 0.881 | 32 | 5 | 4 | 0 | 0 | 0 |
| llm-agent (codex-cli/gpt-6.1-terra) | 44/50 | 0.675 | 0.204 | 44 | 0 | 0 | 0 | 0 | 0 |
| llm-agent (gemini-cli/gemini-4-argon-medium) | 50/50 | 0.697 | - | 26 | 18 | 6 | 0 | 0 | 0 |
