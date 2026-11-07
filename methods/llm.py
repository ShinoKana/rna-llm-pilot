"""Method A: LLMs answering directly in dot-bracket, plus provider-agnostic callers.

Providers: Anthropic (Messages API), OpenAI (Chat Completions), Google (Gemini
generateContent) and a deterministic ``mock`` for dry runs. Calls use plain
HTTPS via urllib, so no vendor SDK is needed.

Safety:
* API keys are read from the environment only (ANTHROPIC_API_KEY,
  OPENAI_API_KEY, GEMINI_API_KEY / GOOGLE_API_KEY) and never printed or logged.
* Network access is disabled unless ``enable_network()`` is called (run.py
  does so only with ``--live``), so a misconfigured run cannot spend money.

Every call is appended to a JSONL log with model id, settings, raw output,
latency and token usage.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from evals.f1 import ALLOWED_CHARS, CANONICAL, pairs_to_dotbracket, parse_dotbracket

_NETWORK_ENABLED = False


def enable_network() -> None:
    global _NETWORK_ENABLED
    _NETWORK_ENABLED = True


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- data types
@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # input_tokens / output_tokens
    latency_s: float = 0.0
    stop_reason: str | None = None
    raw: dict = field(default_factory=dict)


class CallLogger:
    """Append-only JSONL log of every model call (never contains credentials)."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **rec) -> None:
        if self.path:
            rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **rec}
            with open(self.path, "a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")


def _post_json(url: str, headers: dict, body: dict, timeout: float = 120, retries: int = 3) -> dict:
    if not _NETWORK_ENABLED:
        raise LLMError("network disabled (use --live for real API calls, or --dry-run)")
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt * 5)
                continue
            raise LLMError(f"HTTP {e.code} from {url.split('?')[0]}: {msg}") from None
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 5)
                continue
            raise LLMError(f"network error: {e.reason}") from None
    raise LLMError("unreachable")


def _env_key(*names: str) -> str:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    raise LLMError(f"missing API key: set one of {', '.join(names)} in the environment")


# ---------------------------------------------------------------- providers
class Provider:
    """Base class. A conversation is a provider-native dict that ``step`` mutates."""

    name = "base"

    def __init__(self, model: str, temperature: float = 0.0, max_tokens: int = 4096,
                 logger: CallLogger | None = None):
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.logger = logger or CallLogger(None)

    @property
    def settings(self) -> dict:
        return {"temperature": self.temperature, "max_tokens": self.max_tokens}

    def new_conversation(self, system: str, user: str) -> dict:
        return {"system": system, "messages": [{"role": "user", "content": user}]}

    def step(self, conv: dict, tools: list[dict] | None = None, meta: dict | None = None) -> Turn:
        t0 = time.perf_counter()
        try:
            turn = self._call(conv, tools)
        except Exception as e:
            self.logger.log(provider=self.name, model=self.model, settings=self.settings,
                            meta=meta, error=str(e), latency_s=round(time.perf_counter() - t0, 3))
            raise
        turn.latency_s = round(time.perf_counter() - t0, 3)
        self.logger.log(provider=self.name, model=self.model, settings=self.settings, meta=meta,
                        raw_output=turn.text, tool_calls=[asdict(t) for t in turn.tool_calls],
                        stop_reason=turn.stop_reason, usage=turn.usage, latency_s=turn.latency_s)
        return turn

    def _call(self, conv: dict, tools: list[dict] | None) -> Turn:
        raise NotImplementedError

    def add_tool_results(self, conv: dict, results: list[tuple[ToolCall, str]]) -> None:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"

    @property
    def settings(self):
        return {"temperature": "not sent (deprecated for current models)", "max_tokens": self.max_tokens}
    URL = "https://api.anthropic.com/v1/messages"

    def _call(self, conv, tools):
        # current Claude models reject `temperature` (deprecated), so it is not sent; settings record that.
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "system": conv["system"], "messages": conv["messages"]}
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"],
                              "input_schema": t["parameters"]} for t in tools]
        headers = {"x-api-key": _env_key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}
        r = _post_json(self.URL, headers, body)
        conv["messages"].append({"role": "assistant", "content": r["content"]})
        u = r.get("usage", {})
        return Turn(
            text="".join(b.get("text", "") for b in r["content"] if b["type"] == "text"),
            tool_calls=[ToolCall(b["id"], b["name"], b.get("input", {}))
                        for b in r["content"] if b["type"] == "tool_use"],
            usage={"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens")},
            stop_reason=r.get("stop_reason"), raw=r)

    def add_tool_results(self, conv, results):
        conv["messages"].append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tc.id, "content": out} for tc, out in results]})


class OpenAIProvider(Provider):
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def new_conversation(self, system, user):
        return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}

    def _call(self, conv, tools):
        # Note: some reasoning models reject temperature != 1; pass --temperature accordingly.
        body = {"model": self.model, "temperature": self.temperature,
                "max_completion_tokens": self.max_tokens, "messages": conv["messages"]}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        r = _post_json(self.URL, {"authorization": f"Bearer {_env_key('OPENAI_API_KEY')}"}, body)
        choice = r["choices"][0]
        msg = choice["message"]
        calls = msg.get("tool_calls") or []
        conv["messages"].append({"role": "assistant", "content": msg.get("content"),
                                 **({"tool_calls": calls} if calls else {})})
        u = r.get("usage", {})
        return Turn(
            text=msg.get("content") or "",
            tool_calls=[ToolCall(c["id"], c["function"]["name"],
                                 json.loads(c["function"].get("arguments") or "{}")) for c in calls],
            usage={"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")},
            stop_reason=choice.get("finish_reason"), raw=r)

    def add_tool_results(self, conv, results):
        for tc, out in results:
            conv["messages"].append({"role": "tool", "tool_call_id": tc.id, "content": out})


class GoogleProvider(Provider):
    name = "google"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def new_conversation(self, system, user):
        return {"system": system, "contents": [{"role": "user", "parts": [{"text": user}]}]}

    def _call(self, conv, tools):
        body = {"contents": conv["contents"],
                "systemInstruction": {"parts": [{"text": conv["system"]}]},
                "generationConfig": {"temperature": self.temperature,
                                     "maxOutputTokens": self.max_tokens}}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]
        headers = {"x-goog-api-key": _env_key("GEMINI_API_KEY", "GOOGLE_API_KEY")}
        r = _post_json(self.URL.format(model=self.model), headers, body)
        cand = r["candidates"][0]
        content = cand.get("content", {"role": "model", "parts": []})
        conv["contents"].append(content)  # verbatim, keeps any thought signatures
        parts = content.get("parts", [])
        u = r.get("usageMetadata", {})
        return Turn(
            text="".join(p.get("text", "") for p in parts if not p.get("thought")),
            tool_calls=[ToolCall(p["functionCall"].get("id", f"call_{k}"), p["functionCall"]["name"],
                                 p["functionCall"].get("args", {}))
                        for k, p in enumerate(parts) if "functionCall" in p],
            usage={"input_tokens": u.get("promptTokenCount"),
                   "output_tokens": (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)},
            stop_reason=cand.get("finishReason"), raw=r)

    def add_tool_results(self, conv, results):
        parts = []
        for tc, out in results:
            fr = {"name": tc.name, "response": {"result": out}}
            if not tc.id.startswith("call_"):
                fr["id"] = tc.id
            parts.append({"functionResponse": fr})
        conv["contents"].append({"role": "user", "parts": parts})


class MockProvider(Provider):
    """Deterministic offline provider for dry runs and tests.

    Behaviour is keyed on a hash of the sequence so that every failure path
    (fenced output, length mismatch, unbalanced, no structure, altered tool
    output) is exercised on a handful of items.
    """

    name = "mock"
    SEQ_RE = re.compile(r"Sequence \(\d+ nt\):\s*([ACGU]+)")

    def _call(self, conv, tools):
        msgs = conv["messages"]
        seq = self.SEQ_RE.search(msgs[0]["content"]).group(1)
        h = int(hashlib.sha256(seq.encode()).hexdigest(), 16)
        tool_result = next((m["content"] for m in reversed(msgs) if m["role"] == "tool"), None)
        if tools and tool_result is None:
            call = ToolCall(f"mock_{h % 10_000}", "fold", {"seq": seq})
            text = "I will fold the sequence first."
            msgs.append({"role": "assistant", "content": text, "tool_calls": [asdict(call)]})
            return self._turn(text, msgs, [call], "tool_use")
        if tool_result is not None:
            db = json.loads(tool_result)["structure"]
            pairs = parse_dotbracket(db)
            if h % 4 == 0 and pairs:  # pretend the model "corrects" the tool: drop one pair
                i, j = pairs[0]
                db = db[:i] + "." + db[i + 1:j] + "." + db[j + 1:]
            text = f"Based on the MFE fold:\nSTRUCTURE: {db}"
        else:
            text = self._direct_answer(seq, h)
        msgs.append({"role": "assistant", "content": text})
        return self._turn(text, msgs, [], "end_turn")

    def add_tool_results(self, conv, results):
        for tc, out in results:
            conv["messages"].append({"role": "tool", "tool_call_id": tc.id, "content": out})

    def _turn(self, text, msgs, calls, stop):
        n_in = sum(len(str(m.get("content", ""))) for m in msgs[:-1]) // 4
        return Turn(text=text, tool_calls=calls, stop_reason=stop,
                    usage={"input_tokens": n_in, "output_tokens": len(text) // 4})

    @staticmethod
    def _toy_fold(seq: str) -> str:
        """Longest canonical helix (min loop 3): a deliberately weak baseline."""
        L, best = len(seq), (0, 0, 0)
        for i in range(L):
            for j in range(L - 1, i + 3, -1):
                k = 0
                while i + k < j - k - 3 and (seq[i + k], seq[j - k]) in CANONICAL:
                    k += 1
                if k > best[2]:
                    best = (i, j, k)
        i, j, k = best
        return pairs_to_dotbracket([(i + d, j - d) for d in range(k)], L)

    def _direct_answer(self, seq: str, h: int) -> str:
        db = self._toy_fold(seq)
        mode = h % 10
        if mode == 6:
            return f"Here is the structure:\n```\n{db}\n```"
        if mode == 7:
            return f"STRUCTURE: {db[:-3]}"
        if mode == 8:
            return f"STRUCTURE: ({db[1:]}"
        if mode == 9:
            return "I cannot reliably predict this structure without computational tools."
        return f"The sequence forms a hairpin.\nSTRUCTURE: {db}"


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider,
             "google": GoogleProvider, "mock": MockProvider}


def _register_cli():
    from methods.cli import CLI_PROVIDERS
    PROVIDERS.update(CLI_PROVIDERS)


def make_provider(name: str, model: str | None, **kw) -> Provider:
    if name.endswith("-cli"):
        _register_cli()
    if name not in PROVIDERS:
        raise ValueError(f"unknown provider {name!r}; choose from {sorted(PROVIDERS)}")
    if not model:
        if name != "mock":
            raise ValueError("--model is required for real providers")
        model = "mock-v1"
    return PROVIDERS[name](model, **kw)


# ---------------------------------------------------------------- prompting
SYSTEM_PROMPT = "You are an expert in RNA structural biology."

FORMAT_RULES = (
    "Answer in dot-bracket notation with exactly {n} characters: '(' and ')' for base pairs, "
    "'.' for unpaired bases; use '[]', '{{}}' or '<>' only for pseudoknotted pairs. "
    "End your answer with one line of the form:\nSTRUCTURE: <dot-bracket>"
)

DIRECT_PROMPT = ("Predict the secondary structure of the following RNA sequence.\n\n"
                 "Sequence ({n} nt): {seq}\n\n" + FORMAT_RULES)

LABEL_RE = re.compile(r"STRUCTURE:\s*`*([^\s`]+)")
CANDIDATE_RE = re.compile("[" + re.escape("".join(sorted(ALLOWED_CHARS))) + "]{5,}")


def extract_structure(text: str, n: int) -> tuple[str | None, str]:
    """Pull the dot-bracket answer out of free text. Returns (structure, how)."""
    labelled = LABEL_RE.findall(text or "")
    if labelled:
        return labelled[-1], "label"
    cands = [c for c in CANDIDATE_RE.findall(text or "") if any(ch in c for ch in ".()")]
    if cands:
        return min(cands, key=lambda c: (abs(len(c) - n), -len(c))), "fallback"
    return None, "none"


def predict_direct(provider: Provider, item: dict) -> dict:
    """Method A: one call, no tools."""
    seq, n = item["seq"], len(item["seq"])
    conv = provider.new_conversation(SYSTEM_PROMPT, DIRECT_PROMPT.format(n=n, seq=seq))
    turn = provider.step(conv, tools=None, meta={"item_id": item["id"], "method": "llm-direct"})
    pred, how = extract_structure(turn.text, n)
    return {"pred_db": pred, "raw_output": turn.text, "latency_s": turn.latency_s,
            "usage": turn.usage, "extra": {"extraction": how, "stop_reason": turn.stop_reason}}


# ---------------------------------------------------------------- format ablation (11-04)
PAIRS_PROMPT = ("Predict the secondary structure of the following RNA sequence.\n\n"
                "Sequence ({n} nt): {seq}\n\n"
                "Do not write dot-bracket. List the base pairs as 1-based position pairs (i,j) with i<j, each position "
                "used at most once. End your answer with one line of the form:\n"
                "PAIRS: (i,j) (i,j) ...\n(write `PAIRS: none` if you predict no pairs)")

PAIRS_LINE_RE = re.compile(r"PAIRS:\s*(.*)$", re.M)
PAIR_RE = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")


def pairs_from_text(text: str, n: int) -> tuple[str | None, str]:
    """Convert a 'PAIRS:' answer to dot-bracket. Conflicting or out-of-range pairs make it invalid (returned as None)."""
    lines = PAIRS_LINE_RE.findall(text or "")
    if not lines:
        return None, "none"
    raw = [(int(a) - 1, int(b) - 1) for a, b in PAIR_RE.findall(lines[-1])]
    used, pairs = set(), []
    for i, j in raw:
        i, j = min(i, j), max(i, j)
        if i < 0 or j >= n or i == j or i in used or j in used:
            return None, "pairs_conflict"
        used |= {i, j}; pairs.append((i, j))
    try:
        return pairs_to_dotbracket(pairs, n), "pairs"
    except ValueError:
        return None, "pairs_too_deep"


def predict_direct_pairs(provider: Provider, item: dict) -> dict:
    """Method A, pair-list output format: separates format failures from structure knowledge."""
    seq, n = item["seq"], len(item["seq"])
    conv = provider.new_conversation(SYSTEM_PROMPT, PAIRS_PROMPT.format(n=n, seq=seq))
    turn = provider.step(conv, tools=None, meta={"item_id": item["id"], "method": "llm-direct-pairs"})
    pred, how = pairs_from_text(turn.text, n)
    return {"pred_db": pred, "raw_output": turn.text, "latency_s": turn.latency_s,
            "usage": turn.usage, "extra": {"extraction": how, "stop_reason": turn.stop_reason}}
