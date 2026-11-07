#!/bin/bash
# Memorisation-gap set: 50 bpRNA-NF-15.0 items (new Rfam families, allowlisted organisms).
cd "$(dirname "$0")"
P=.venv/bin/python; M=data/manifest_nf.jsonl; O=results/nf
$P run.py --method rnafold --manifest $M --out $O/rnafold.jsonl > logs/runs/nf_rnafold.log 2>&1
( $P run.py --method llm-direct --provider claude-cli --model claude-opus-5-5 --workers 3 --manifest $M --out $O/direct_claude.jsonl > logs/runs/nf_direct_claude.log 2>&1
  $P run.py --method llm-agent  --provider claude-cli --model claude-opus-5-5 --workers 3 --manifest $M --out $O/agent_claude.jsonl > logs/runs/nf_agent_claude.log 2>&1 ) &
RNAPILOT_CODEX_EFFORT=medium $P run.py --method llm-direct --provider codex-cli --model gpt-6.1-terra --workers 2 --manifest $M --out $O/direct_codex.jsonl > logs/runs/nf_direct_codex.log 2>&1 &
wait
