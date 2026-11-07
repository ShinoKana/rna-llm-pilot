# rna-llm-pilot

This repository evaluates how well general-purpose LLMs predict RNA secondary structure, with and without a folding tool, compared with specialist predictors. The task is restricted to cellular non-coding RNA.

## Key findings

- **Answer format affects scores.** On ArchiveII, asking Claude for a pair list instead of dot-bracket raised F1 by +0.25, with a paired bootstrap 95% CI of [+0.14, +0.36]. For GPT, the difference was +0.06, CI [-0.02, +0.12].
- **Tool use differs by vendor.** Claude skipped RNAfold on 9 items and altered its output on 9. GPT kept the output verbatim whenever it called the tool. Gemini called the tool on all 50 items and returned it verbatim on 26, improved it on 18 and made it worse on 6.
- **Known vs new families.** After adjustment for set difficulty with RNAfold, every learned method did relatively better on known families, with gaps from +0.18 to +0.36. Different reference types may account for part of the gap.

See [RESULTS.md](RESULTS.md) for the full table.

## Methods compared

| Method | What it is | Status |
|---|---|---|
| C, specialist | ViennaRNA RNAfold (MFE, 37 °C, Turner 2004) | working |
| C, specialist | RNA-FM secondary-structure head (`SS/RNA-FM-ResNet_bpRNA.pth` from `cuhkaih/rnafm`) | run on a GPU; maps in `data/rnafm_maps/` |
| A, LLM direct | LLM answers in dot-bracket, no tools | run (Claude, Gemini, GPT via CLIs) |
| A', LLM direct, pair list | LLM lists 1-based pairs, the program writes dot-bracket (format ablation) | run (Claude, GPT) |
| B, LLM + tool | same LLMs, one tool `fold(seq)` -> RNAfold, up to 4 turns | run (Claude, Gemini, GPT) |

## Evaluation sets

**ArchiveII** (Sloma & Mathews 2016) contains known families. The committed sample is in `data/manifest.jsonl`. The original Mathews-lab tarball (`rna.urmc.rochester.edu/pub/archiveII.tar.gz`) returned 404 in Nov 2026, so `data/fetch.py` downloads the MultiMolecule mirror (`huggingface.co/datasets/multimolecule/archiveii`, parquet, AGPL-3.0). If the mirror disappears, unpack the original .ct/.bpseq files anywhere and run `python -m data.sample --ct-dir <folder>`.

**bpRNA-NF-15.0** contains Rfam families absent from bpRNA-1m. Its source is figshare 28468946, `bpRNA-NF-15.0.csv`, into `data/raw/bprna_nf15/`. Of 8107 sequences of at most 200 nt, 619 pass the allowlist. The 50 drawn with seed `20261104` are in `data/manifest_nf.jsonl`, with the log in `data/manifest_nf_log.json`.

**Sampling:** Each set has 50 sequences of at most 200 nt. Sequences are A/C/G/U only, scope-filtered and de-duplicated by sequence. Families get equal shares capped by availability, and each family's length-sorted list is split into 3 equal bins and sampled evenly, with seed `20261104`.

**Scope:** The cellular ncRNA family and organism allowlist is in [data/scope.py](data/scope.py). Records outside the allowlist are dropped.

Under the scope-v2 allowlist, 441 unique ArchiveII sequences of at most 200 nt remain from 2393. The sample contains 16S rRNA domain fragments (13), 5S rRNA (12), SRP (12), tRNA (12) and tmRNA (1). Group I intron, group II intron, telomerase and 23S rRNA have no entries <= 200 nt in ArchiveII. RNase P has none on the allowlist at this length.

The allowlist covers tRNA, 5S rRNA, SRP, RNase P, tmRNA, rRNA domains, group I/II introns and telomerase, plus named model and other well-characterised free-living species. Names are matched as `Genus_species`, `G.species` or `Genu.spec.`. False exclusions are acceptable, false inclusions are not. To add an organism, add it to `ALLOWED_ORGANISMS`. `data/scope_exclusions.jsonl` records counts by family.

Manifest fields are `id, family, length, seq, ref_db`, plus `source` and `length_bin`. `ref_db` is the reference structure in dot-bracket, with pseudoknots on `[]`/`{}`.

**bpRNA-TS0** is optional for RNA-FM:

```bash
python -m data.fetch --bprna
python -m data.sample --bprna-ts0 --out data/manifest_ts0.jsonl
```

It uses the TS0 rows (`bpRNA_*` ids) of the MultiMolecule `bprna-spot` test split. The mirror has no organism metadata, so every TS0 record is dropped under the allowlist until an `id<TAB>description` metadata file names the organism. The rule is the first line of `data/bprna_ts0_filter_log.jsonl`. The bpRNA-TS0 arm, needed for a fair comparison with RNA-FM, waits for that metadata.

## Quick start

Set up the environment and run the tests:

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest
```

Run RNAfold, exercise the mock provider and generate reports:

```bash
P=.venv/bin/python
$P run.py --method rnafold                          # real, local, ~1 s for 50 sequences
$P run.py --method llm-direct --dry-run --limit 5   # mock provider, no network
$P run.py --method llm-agent  --dry-run --limit 5
$P report.py                                        # all results/*.jsonl
$P report.py results/dryrun/*.jsonl --out results/dryrun/report.md
```

RNAfold on the committed 50-sequence manifest gives mean base-pair F1 0.655 (0.684 with +-1 slip).

### Running LLMs

The reported runs used `claude-cli`, `gemini-cli` and `codex-cli`. No `--live` flag is needed for these providers. See `run_all_cli.sh` and `run_nf.sh`.

```bash
$P run.py --method llm-direct --provider claude-cli --model claude-opus-5-5 --workers 3
$P run.py --method llm-agent  --provider gemini-cli --model gemini-4-argon-medium --workers 2
RNAPILOT_CODEX_EFFORT=medium $P run.py --method llm-direct-pairs --provider codex-cli --model gpt-6.1-terra
$P analysis.py; $P analysis.py --manifest data/manifest_nf.jsonl --results results/nf; $P gap.py
```

REST API runs require the provider's key in the environment and an explicit `--live` flag. Without it, the HTTP layer refuses to open a connection.

```bash
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, GEMINI_API_KEY / GOOGLE_API_KEY
$P run.py --method llm-direct --provider anthropic --model <model-id> --live
$P run.py --method llm-agent  --provider openai    --model <model-id> --live
```

Keys are read from the environment only and never printed or logged. Temperature defaults to 0 and can be changed with `--temperature`, for example for OpenAI reasoning models that only accept 1. Each API call is appended to `logs/llm_calls.jsonl` with model id, settings, raw output, tool calls, latency and token usage. For method B, differences between the model's final answer and RNAfold's output are printed and appended to `logs/agent_alterations.jsonl`, including pairs added or removed and positions changed.

### Notes on the LLM runs

Each CLI call runs in an empty temporary directory and its own process group, which is killed on timeout. Method B uses the shared plain-text protocol `CALL fold(SEQ)` / `TOOL RESULT fold: {...}`, not native function calling.

Claude runs with the system prompt replaced and no tools. The Gemini and Codex CLIs keep their own harness prompts. Effort was Claude CLI default, Gemini argon-medium and GPT medium. Gemini argon-high timed out at 300 s with empty answers.

### Outputs

`results/<method>__<provider>__<model>.jsonl` contains one record per sequence with the prediction, raw output, validation errors, exact and +-1-slip P/R/F1, latency, usage, failure class and flags. `report.py` prints per-method and per-family tables and the failure taxonomy from `evals/taxonomy.py`. Invalid predictions score 0 in the main F1 column, and a valid-only F1 column is also given.

## Repository layout

```text
data/
  fetch.py                    Download ArchiveII and optionally bpRNA-spot into data/raw/
  loaders.py                  Parquet, .ct/.bpseq folder and filtered bpRNA-TS0 loaders
  scope.py                    Cellular ncRNA family and organism allowlist
  sample.py                   Stratified sampler
  manifest.jsonl              50-sequence ArchiveII sample
  manifest_nf.jsonl           50-sequence bpRNA-NF-15.0 sample
  scope_exclusions.jsonl      ArchiveII exclusion counts by family
  bprna_ts0_filter_log.jsonl  bpRNA-TS0 filter rule and dropped ids
  rnafm_maps/                 GPU-computed RNA-FM pair-probability maps
methods/
  rnafold.py                  ViennaRNA Python bindings
  rnafm.py                    Decode RNA-FM pair-probability maps
  rnafm_infer_gpu.py          Compute maps on a CUDA machine (set RNAFM_HOME)
  llm.py                      Direct methods and REST callers
  cli.py                      CLI callers: claude -p, agy (Gemini), codex exec
  agent.py                    Method B tool loop
evals/
  f1.py                       Dot-bracket validation and base-pair P/R/F1
  taxonomy.py                 Failure-type taxonomy
analysis.py                   MCC, fabricated stems, self-checks and tool outcomes
gap.py                        Memorisation gap adjusted with RNAfold
ci.py                         Paired bootstrap CIs
run.py                        Run a method over a manifest
report.py                     Per-method and per-family tables and failure taxonomy
RESULTS.md                    Summary of the reported runs
results/                      Per-sequence results and analysis
tests/                        pytest suite
```

`data/raw/` is git-ignored. REST callers in `methods/llm.py` cover Anthropic, OpenAI, Google and the mock provider.

## Scoring

- Pairs are parsed with one stack per bracket type, so pseudoknots in `[]`, `{}` and `<>` are handled.
- Validators: `no_structure`, `invalid_chars`, `unbalanced`, `length_mismatch` (fatal, scored 0). Non-canonical pairs (not AU/GC/GU) are reported as a warning only, since reference structures contain some too.
- +-1 slip: a predicted pair (i, j) also counts if (i+-1, j) or (i, j+-1) is in the reference. Only one end may shift.

## Limitations

- **RNA-FM leakage.** Its secondary-structure head was trained on bpRNA TR0, whose families overlap ArchiveII, so its ArchiveII numbers are inflated. bpRNA-NF-15.0, whose families are absent from bpRNA-1m, is the fair comparison.
- **Reference types differ between sets.** ArchiveII uses comparative-analysis structures. bpRNA-NF-15.0 uses Rfam-derived consensus structures, on which RNAfold scores much higher (0.83 vs 0.66). Cross-set gaps are adjusted with RNAfold (`gap.py`), but part of any gap may still come from the reference type.
- **The default weight URL returns 403.** `fm.downstream.build_rnafm_resnet` builds its backbone through `proj.cse.cuhk.edu.hk/rnafm/api/download`, which returned HTTP 403 on 2026-11-04. `methods/rnafm_infer_gpu.py` redirects that call to the Hugging Face copy of `RNA-FM_pretrained.pth`.
- **LLM contamination.** ArchiveII, bpRNA and their source databases (Rfam, CRW, tRNAdb, SRPDB) are public, so LLMs may have seen these sequences and structures during training. The new-family set is a first probe, not proof of absence. Rfam 15.0 itself is public.
- **Small sample.** Each set has 50 sequences and unequal family sizes (tmRNA n=1, RNase P n=3). Per-family numbers are anecdotal. Only families with entries <= 200 nt appear.
- **16S entries are domain fragments.** Their references contain only pairs within the fragment.
- **Scope filter is an allowlist.** ArchiveII relies on organism names in record ids. bpRNA-NF-15.0 uses NCBI taxonomy or nuccore summaries of each record's accession. Records whose organism cannot be resolved are dropped.
- **CLI harnesses are not clean API calls.** Vendors differ in harness prompt, effort level and tool protocol. There is one sample per item and no temperature control. The REST callers were exercised only through the mock provider. The Anthropic one returned HTTP 400 for `temperature`, now removed.
- **Mock outputs are synthetic.** They exercise parsing, scoring and the taxonomy and say nothing about real LLM performance.
