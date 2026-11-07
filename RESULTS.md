# Pilot results

Base-pair F1 on 50 sequences per set (invalid answers score 0). Full tables: `results/analysis.md` (ArchiveII),
`results/nf/analysis.md` (new families), `results/gap.md`, `results/ci.md`. Single sample per item unless noted.

## Main table

| method | ArchiveII F1 | valid | new-family F1 | valid |
|---|---|---|---|---|
| RNAfold (MFE) | 0.655 | 50/50 | 0.834 | 50/50 |
| RNA-FM (bpRNA ResNet head) | 0.787 * | 50/50 | 0.767 | 50/50 |
| Claude Opus 5.5, direct (dot-bracket) | 0.405 | 28/50 | 0.225 | 20/50 |
| Claude Opus 5.5, direct (pair list) | 0.652 | 50/50 | 0.607 | 50/50 |
| Claude Opus 5.5, with RNAfold tool | 0.673 | 46/50 | 0.834 | 50/50 |
| GPT gpt-6.1-terra (medium), direct (dot-bracket) | 0.223 | 48/50 | 0.226 | 48/50 |
| GPT gpt-6.1-terra (medium), direct (pair list) | 0.277 | 50/50 | not run | |
| GPT gpt-6.1-terra (medium), with RNAfold tool | 0.619 | 50/50 | not run | |
| Gemini argon-medium, direct (dot-bracket) | 0.392 | 32/50 | 0.391 | 37/50 |
| Gemini argon-medium, with RNAfold tool | 0.697 | 47/50 | not run | |

\* RNA-FM's training families overlap ArchiveII; the new-family set is its fair comparison.

## Findings

1. **Answer format is a large confound for direct answers.** Claude's dot-bracket answers were invalid on 22/50
   ArchiveII items (15 unbalanced, 7 wrong length). Asking for a list of pairs and converting it in code raised F1 by
   +0.25 (paired bootstrap 95% CI [+0.14, +0.36]) to the level of RNAfold (difference -0.003, CI [-0.10, +0.09]).
   A second independent Claude run (`results/rep2/`) gave direct 0.292 (20/50 valid) and pair list 0.616 (50/50
   valid): the format effect held (+0.32), and dot-bracket answers were the less stable of the two (item-level
   correlation between runs 0.63, vs 0.80 for pair lists).
   For GPT the same change made no clear difference (+0.06, CI [-0.02, +0.12]). Benchmarks that score free-text
   dot-bracket mix format failures with structure knowledge, and the size of the mix differs by model.
2. **Tool use.** With RNAfold available, Claude matched RNAfold on ArchiveII (+0.02, CI [-0.06, +0.09]). It skipped
   the tool on 9 items, all tRNA, where its own answers (F1 0.88) beat RNAfold (0.75), and altered the tool output on
   9 items (5 better, 4 worse). On the new-family set it called the tool on all 50 and kept the output verbatim.
   GPT kept the tool output verbatim whenever it called it, and was slightly below RNAfold (-0.04, CI [-0.09, -0.00]).
   Gemini called the tool on all 50 items and edited the output most often: verbatim 26, better 18, worse 6
   (overall +0.04 vs RNAfold, CI [-0.03, +0.11]). The three vendors handle the same tool output very differently.
3. **Known vs new families.** After adjusting for set difficulty with RNAfold (`gap.py`), every learned method does
   relatively better on known families: Claude pair list +0.22, Claude direct +0.36, GPT direct +0.18, Gemini direct +0.18, RNA-FM +0.20.
   Part of this may come from the different reference types (comparative vs Rfam-derived), not only from memorisation.

## Limits

n = 50 per set; one sample per item except the Claude direct runs (two runs, `results/rep2/`); vendors run through
different CLI harnesses and effort levels (Claude CLI default, Gemini medium because high timed out, GPT medium);
the method-B tool protocol is plain text, not native function calling; the new-family references are Rfam-derived.
