"""Run one method over the manifest and write scored records to JSONL.

Examples:
    python run.py --method rnafold
    python run.py --method llm-direct --dry-run --limit 5
    python run.py --method llm-agent  --dry-run --limit 5
    python run.py --method llm-direct --provider anthropic --model <model-id> --live

Real providers need --live (otherwise network access stays disabled).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

from evals.f1 import score_structure
from evals.taxonomy import classify

ROOT = Path(__file__).resolve().parent
METHODS = ["rnafold", "rnafm", "llm-direct", "llm-direct-pairs", "llm-agent"]


def load_manifest(path, limit=None):
    rows = [json.loads(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]
    return rows[:limit] if limit else rows


def build_predictor(a, logs_dir: Path):
    """Return (predict_fn, provider_name, model_id, settings)."""
    if a.method == "rnafold":
        from methods import rnafold
        return rnafold.predict, "local", "ViennaRNA-" + rnafold.SETTINGS["version"], rnafold.SETTINGS
    if a.method == "rnafm":
        from methods import rnafm
        return rnafm.predict, "local", "RNA-FM-ResNet_bpRNA", {"decode": f"greedy canonical, threshold {rnafm.OFFICIAL_THRESHOLD}"}

    from methods import llm
    if a.provider != "mock" and not a.provider.endswith("-cli") and not a.live:
        sys.exit("refusing real API calls without --live (use --dry-run for the mock provider)")
    if a.live or a.provider.endswith("-cli"):
        llm.enable_network()   # CLI providers use the subscription, not paid API keys
    provider = llm.make_provider(a.provider, a.model, temperature=a.temperature,
                                 max_tokens=a.max_tokens,
                                 logger=llm.CallLogger(logs_dir / "llm_calls.jsonl"))
    if a.method == "llm-direct":
        fn = lambda item: llm.predict_direct(provider, item)  # noqa: E731
    elif a.method == "llm-direct-pairs":
        fn = lambda item: llm.predict_direct_pairs(provider, item)  # noqa: E731
    else:
        from methods import agent
        fn = lambda item: agent.predict_agent(  # noqa: E731
            provider, item, max_turns=a.max_turns,
            alterations_log=logs_dir / "agent_alterations.jsonl")
    settings = {**provider.settings, **({"max_turns": a.max_turns} if a.method == "llm-agent" else {})}
    return fn, provider.name, provider.model, settings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", required=True, choices=METHODS)
    ap.add_argument("--manifest", default=str(ROOT / "data/manifest.jsonl"))
    ap.add_argument("--provider", default="mock", choices=["anthropic", "openai", "google", "mock", "claude-cli", "gemini-cli", "codex-cli"])
    ap.add_argument("--model", help="model id (required for real providers)")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--max-turns", type=int, default=4, help="llm-agent only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true", help="use the offline mock provider")
    ap.add_argument("--live", action="store_true", help="allow real (paid) API calls")
    ap.add_argument("--workers", type=int, default=1, help="parallel items (CLI providers are slow)")
    ap.add_argument("--out", help="output JSONL (default: results/<method>__<provider>__<model>.jsonl)")
    a = ap.parse_args()
    if a.dry_run:
        if a.live:
            sys.exit("--dry-run and --live are mutually exclusive")
        a.provider, a.model = "mock", None

    sub = "dryrun" if a.dry_run else ""
    logs_dir = ROOT / "logs" / sub
    predict, provider, model, settings = build_predictor(a, logs_dir)
    out = Path(a.out) if a.out else ROOT / "results" / sub / f"{a.method}__{provider}__{model}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    items = load_manifest(a.manifest, a.limit)
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]

    f1s = []

    def one(item):
        rec = {"run_id": run_id, "method": a.method, "provider": provider, "model": model,
               "settings": settings, "id": item["id"], "family": item["family"],
               "length": item["length"], "length_bin": item.get("length_bin")}
        try:
            res = predict(item)
        except NotImplementedError:
            raise
        except Exception as e:  # noqa: BLE001 - recorded as a call_error, run continues
            res = {"pred_db": None, "raw_output": None, "error": f"{type(e).__name__}: {e}"}
        rec.update({k: res.get(k) for k in ("pred_db", "raw_output", "latency_s", "usage", "error", "extra")})
        rec.update(score_structure(res.get("pred_db"), item["ref_db"], item["seq"]))
        rec["failure"], rec["flags"] = classify(rec)
        return rec

    from concurrent.futures import ThreadPoolExecutor
    with open(out, "w") as fh, ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for item, rec in zip(items, ex.map(one, items)):
            f1s.append(rec["exact"]["f1"])
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"  {item['id'][:48]:48s} F1={rec['exact']['f1']:.3f} {rec['failure']}"
                  + (f" [{','.join(rec['flags'])}]" if rec["flags"] else ""), flush=True)
    print(f"[run] {a.method} {provider}/{model}: n={len(f1s)} mean F1={sum(f1s) / max(len(f1s), 1):.3f} -> {out}")


if __name__ == "__main__":
    main()
