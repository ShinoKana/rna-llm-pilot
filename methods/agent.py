"""Method B: the same LLMs with one tool, ``fold(seq)`` -> RNAfold, in a minimal loop.

The loop: send prompt (+ tool schema) -> execute any tool calls -> return
results -> repeat until the model answers without calling a tool or
``max_turns`` is reached. The final answer is compared with the last RNAfold
output on the query sequence; any difference is recorded as an alteration and
appended to an alterations log.
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.f1 import DotBracketError, parse_dotbracket
from methods import rnafold
from methods.llm import FORMAT_RULES, SYSTEM_PROMPT, Provider, extract_structure

FOLD_TOOL = {
    "name": "fold",
    "description": ("Predict the minimum free energy secondary structure of an RNA sequence with "
                    "ViennaRNA RNAfold (37 C, Turner 2004). Returns the dot-bracket structure and "
                    "the MFE in kcal/mol."),
    "parameters": {
        "type": "object",
        "properties": {"seq": {"type": "string", "description": "RNA sequence (A/C/G/U)"}},
        "required": ["seq"],
    },
}

AGENT_PROMPT = (
    "Predict the secondary structure of the following RNA sequence.\n\n"
    "Sequence ({n} nt): {seq}\n\n"
    "You have one tool, `fold`, which runs ViennaRNA RNAfold (minimum free energy). You may call it, "
    "and you may accept, modify or ignore its output.\n\n" + FORMAT_RULES
)


def run_fold_tool(args: dict) -> dict:
    seq = str(args.get("seq", "")).strip().upper().replace("T", "U")
    if not seq or set(seq) - set("ACGU"):
        return {"error": "seq must be a non-empty string of A/C/G/U"}
    structure, mfe = rnafold.fold(seq)
    return {"structure": structure, "mfe": mfe}


def audit_tool_use(pred: str | None, tool_log: list[dict], seq: str) -> dict:
    """Compare the final answer with the last tool output on the query sequence."""
    if not tool_log:
        return {"status": "no_tool_call"}
    on_query = [t for t in tool_log if t["seq_matches_query"] and "structure" in t["output"]]
    if not on_query:
        return {"status": "tool_called_on_other_seq"}
    tool_db = on_query[-1]["output"]["structure"]
    if pred is None:
        return {"status": "no_final_structure", "tool_db": tool_db}
    if pred == tool_db:
        return {"status": "verbatim"}
    out = {"status": "altered", "tool_db": tool_db, "final_db": pred}
    if len(pred) == len(tool_db):
        out["n_positions_changed"] = sum(a != b for a, b in zip(pred, tool_db))
    try:
        p, t = set(parse_dotbracket(pred)), set(parse_dotbracket(tool_db))
        out["pairs_added"], out["pairs_removed"] = len(p - t), len(t - p)
    except DotBracketError:
        out["final_parse_error"] = True
    return out


def predict_agent(provider: Provider, item: dict, max_turns: int = 4,
                  alterations_log: str | Path | None = None) -> dict:
    seq, n = item["seq"], len(item["seq"])
    conv = provider.new_conversation(SYSTEM_PROMPT, AGENT_PROMPT.format(n=n, seq=seq))
    tool_log, latency, usage = [], 0.0, {"input_tokens": 0, "output_tokens": 0}
    turn, n_turns = None, 0
    for k in range(max_turns):
        n_turns = k + 1
        turn = provider.step(conv, tools=[FOLD_TOOL],
                             meta={"item_id": item["id"], "method": "llm-agent", "turn": k})
        latency += turn.latency_s
        for key in usage:
            usage[key] += turn.usage.get(key) or 0
        if not turn.tool_calls:
            break
        results = []
        for tc in turn.tool_calls:
            out = run_fold_tool(tc.args) if tc.name == "fold" else {"error": f"unknown tool {tc.name}"}
            arg_seq = str(tc.args.get("seq", "")).strip().upper().replace("T", "U")
            tool_log.append({"turn": k, "name": tc.name, "seq_matches_query": arg_seq == seq,
                             "arg_len": len(arg_seq), "output": out})
            results.append((tc, json.dumps(out)))
        provider.add_tool_results(conv, results)
    hit_limit = bool(turn and turn.tool_calls)
    pred, how = extract_structure(turn.text if turn else "", n)
    audit = audit_tool_use(pred, tool_log, seq)
    if audit["status"] == "altered":
        print(f"[agent] {item['id']}: model altered RNAfold output "
              f"(+{audit.get('pairs_added', '?')}/-{audit.get('pairs_removed', '?')} pairs)")
        if alterations_log:
            Path(alterations_log).parent.mkdir(parents=True, exist_ok=True)
            with open(alterations_log, "a") as fh:
                fh.write(json.dumps({"id": item["id"], "provider": provider.name,
                                     "model": provider.model, **audit}) + "\n")
    return {"pred_db": pred, "raw_output": turn.text if turn else "", "latency_s": round(latency, 3),
            "usage": usage,
            "extra": {"extraction": how, "turns": n_turns,
                      "hit_turn_limit": hit_limit, "tool_calls": tool_log, "tool_audit": audit}}
