#!/bin/bash
# 50-item pilot over the vendor CLIs. One background job per vendor; direct then agent.
cd "$(dirname "$0")"
P=.venv/bin/python
$P run.py --method rnafold > logs/runs/rnafold.log 2>&1
run_vendor() {  # provider model workers tag
  $P run.py --method llm-direct --provider $1 --model $2 --workers $3 > logs/runs/direct_$4.log 2>&1
  $P run.py --method llm-agent  --provider $1 --model $2 --workers $3 > logs/runs/agent_$4.log 2>&1
}
run_vendor claude-cli claude-opus-5-5 3 claude &
run_vendor gemini-cli gemini-4-argon-medium 2 gemini &  # argon-high timed out at 300 s
RNAPILOT_CODEX_EFFORT=medium run_vendor codex-cli gpt-6.1-terra 2 codex &
wait
echo ALL_DONE > logs/runs/DONE
