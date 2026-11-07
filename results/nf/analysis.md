# Pilot analysis (extra metrics)

F1 counts invalid answers as 0. MCC is the approximate base-pair MCC sqrt(PPV x sensitivity). Fabricated stem: a predicted stem (>= 2 stacked pairs) with no pair within +-1 of a reference pair. Self-check: answers whose text claims a length or balance check; first number is how many of those were invalid.

| method | n | valid | F1 | F1 valid only | F1 +-1 | MCC | fabricated stems | self-check claim but invalid | call errors |
|---|---|---|---|---|---|---|---|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 50 | 50/50 | 0.834 | 0.834 | 0.857 | 0.838 | 54/277 | 0/32 | 0 |
| llm-direct (claude-cli/claude-opus-5-5) | 50 | 20/50 | 0.225 | 0.563 | 0.252 | 0.226 | 31/90 | 0/0 | 0 |
| llm-direct (codex-cli/gpt-6.1-terra) | 50 | 48/50 | 0.226 | 0.235 | 0.242 | 0.254 | 36/75 | 0/0 | 0 |
| llm-direct (gemini-cli/gemini-4-argon-medium) | 50 | 37/50 | 0.391 | 0.529 | 0.451 | 0.393 | 79/175 | 0/0 | 0 |
| llm-direct-pairs (claude-cli/claude-opus-5-5) | 50 | 50/50 | 0.607 | 0.607 | 0.643 | 0.611 | 86/231 | 0/0 | 0 |
| rnafm | 50 | 50/50 | 0.767 | 0.767 | 0.790 | 0.770 | 34/218 | 0/0 | 0 |
| rnafold | 50 | 50/50 | 0.834 | 0.834 | 0.857 | 0.838 | 54/277 | 0/0 | 0 |

## F1 per family

| method | bpRNA-NF (n=50) |
|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 0.834 |
| llm-direct (claude-cli/claude-opus-5-5) | 0.225 |
| llm-direct (codex-cli/gpt-6.1-terra) | 0.226 |
| llm-direct (gemini-cli/gemini-4-argon-medium) | 0.391 |
| llm-direct-pairs (claude-cli/claude-opus-5-5) | 0.607 |
| rnafm | 0.767 |
| rnafold | 0.834 |

## Method B: what the model did with the RNAfold output

| method | tool call rate | F1 when called | F1 when not called | verbatim | improved | worsened | altered, same F1 | tool on other seq | no final structure |
|---|---|---|---|---|---|---|---|---|---|
| llm-agent (claude-cli/claude-opus-5-5) | 50/50 | 0.834 | - | 50 | 0 | 0 | 0 | 0 | 0 |
