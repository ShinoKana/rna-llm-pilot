"""Subscription-backed providers that call vendor CLIs instead of the REST APIs.

Used while API credit is unavailable. Each call is one stateless CLI invocation in an empty temporary
directory; multi-turn conversations (method B) are replayed as a transcript in the prompt.

  claude-cli : ``claude -p`` with the system prompt REPLACED (--system-prompt), no tools, no settings, no MCP,
               no session persistence. Closest to a clean API call.
  gemini-cli : ``agy -p`` (Antigravity CLI). Its own harness prompt (~15k tokens) cannot be removed, and the
               agent has file/terminal tools; the prompt asks it not to use them and the call runs in an empty
               directory. Recorded as a known contamination.
  codex-cli  : ``codex exec`` in a read-only sandbox, ephemeral, in an empty directory. Codex also keeps its own
               harness prompt and could run shell commands; RNAfold is not on PATH there.

Tool use (method B) is a plain-text protocol shared by all three, not native function calling: the model asks
for the tool with one line ``CALL fold(<SEQUENCE>)`` and receives ``TOOL RESULT fold: {...}`` in the next turn.
This keeps the three vendors on the same footing; it is a deviation from native tool calling and is reported.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from methods.llm import Provider, ToolCall, Turn

CALL_RE = re.compile(r"^\s*CALL\s+fold\(\s*([ACGUTacgut]+)\s*\)\s*$", re.M)

TOOL_PROTOCOL = (
    "\n\nTool protocol: to run the tool, reply with exactly one line `CALL fold(<SEQUENCE>)` and nothing else. "
    "You will then receive a line `TOOL RESULT fold: <json>`. When you are done, give your final answer "
    "(no CALL line) in the required format."
)

NO_TOOLS_NOTE = "\n\nDo not use any tools, files or commands; answer from your own knowledge in one reply."


class CLIProvider(Provider):
    name = "cli"
    timeout_s = 600

    def new_conversation(self, system: str, user: str) -> dict:
        return {"system": system, "turns": [("user", user)]}

    # ---- prompt rendering
    def _render(self, conv: dict, tools) -> str:
        parts = []
        for role, text in conv["turns"]:
            if role == "user" and not parts:
                parts.append(text + (TOOL_PROTOCOL if tools else ""))
            elif role == "assistant":
                parts.append(f"[Your previous reply]\n{text}")
            else:
                parts.append(text)
        return "\n\n".join(parts)

    def _run(self, cmd: list[str], prompt_via_stdin: str | None = None, env: dict | None = None) -> tuple[str, str, float]:
        # Own process group: agy/codex children can hold the pipes open, so on timeout kill the whole group
        # (a plain subprocess.run timeout waited far longer than the limit for agy on 11-03).
        with tempfile.TemporaryDirectory(prefix="rnapilot_") as d:
            t0 = time.perf_counter()
            proc = subprocess.Popen(cmd, cwd=d, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, env=env, start_new_session=True)
            try:
                out, err = proc.communicate(input=prompt_via_stdin or "", timeout=self.timeout_s)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                raise RuntimeError(f"{self.name}: timed out after {self.timeout_s}s")
            return out, err, time.perf_counter() - t0

    def _invoke(self, system: str, prompt: str, tools) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def _call(self, conv, tools):
        prompt = self._render(conv, tools)
        text, usage, raw = self._invoke(conv["system"], prompt, tools)
        conv["turns"].append(("assistant", text))
        calls = []
        if tools:
            m = CALL_RE.search(text or "")
            if m and "STRUCTURE:" not in text:
                calls = [ToolCall(id=f"call{len(conv['turns'])}", name="fold", args={"seq": m.group(1)})]
        return Turn(text=text, tool_calls=calls, usage=usage, stop_reason=raw.get("stop_reason"), raw=raw)

    def add_tool_results(self, conv, results):
        for tc, out in results:
            conv["turns"].append(("user", f"TOOL RESULT fold: {out}"))


class ClaudeCLIProvider(CLIProvider):
    name = "claude-cli"

    @property
    def settings(self):
        return {"via": "claude -p (subscription)", "system_prompt": "replaced", "tools": "none (text protocol for B)",
                "effort": os.environ.get("RNAPILOT_CLAUDE_EFFORT", "default")}

    def _invoke(self, system, prompt, tools):
        env = {k: os.environ[k] for k in ("PATH", "HOME", "USER") if k in os.environ}
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        cmd = ["claude", "-p", "--model", self.model, "--system-prompt", system, "--tools", "",
               "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
               "--output-format", "json"]
        if os.environ.get("RNAPILOT_CLAUDE_EFFORT"):
            cmd += ["--effort", os.environ["RNAPILOT_CLAUDE_EFFORT"]]
        out, err, dt = self._run(cmd + [prompt], prompt_via_stdin="", env=env)
        try:
            d = json.loads(out)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude-cli: non-JSON output: {(out or err)[-300:]}")
        if d.get("is_error"):
            raise RuntimeError(f"claude-cli error: {str(d.get('result'))[:300]}")
        u = d.get("usage", {})
        return d.get("result", ""), {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                                     "notional_cost_usd": d.get("total_cost_usd")}, {"stop_reason": d.get("stop_reason"),
                                                                                    "duration_ms": d.get("duration_ms")}


class GeminiCLIProvider(CLIProvider):
    name = "gemini-cli"
    timeout_s = 330  # agy --print-timeout 300s plus margin
    AGY = str(Path.home() / ".gemini/bin/agy-claude")

    @property
    def settings(self):
        return {"via": "agy -p (Gemini subscription)", "system_prompt": "prepended to user turn; agy harness prompt kept",
                "tools": "agy built-ins present, asked not to use (text protocol for B)"}

    def _invoke(self, system, prompt, tools):
        full = f"{system}\n\n{prompt}" + ("" if tools else NO_TOOLS_NOTE)
        out, err, dt = self._run([self.AGY, "-p", full, "--model", self.model, "--print-timeout", "300s",
                                  "--output-format", "json"])
        try:
            d = json.loads(out.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            raise RuntimeError(f"gemini-cli: non-JSON output: {(out or err)[-300:]}")
        if d.get("status") != "SUCCESS":
            raise RuntimeError(f"gemini-cli status {d.get('status')}: {str(d)[:300]}")
        u = d.get("usage", {})
        return d.get("response", ""), {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                                       "thinking_tokens": u.get("thinking_tokens"), "num_turns": d.get("num_turns")}, {}


class CodexCLIProvider(CLIProvider):
    name = "codex-cli"

    @property
    def settings(self):
        return {"via": "codex exec (subscription)", "effort": os.environ.get("RNAPILOT_CODEX_EFFORT", "medium"),
                "sandbox": "read-only, empty dir", "system_prompt": "prepended to user turn; codex harness prompt kept"}

    def _invoke(self, system, prompt, tools):
        full = f"{system}\n\n{prompt}" + ("" if tools else NO_TOOLS_NOTE)
        effort = os.environ.get("RNAPILOT_CODEX_EFFORT", "medium")
        with tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False) as f:
            last = f.name
        try:
            out, err, dt = self._run(["codex", "exec", "-m", self.model, "-c", f'model_reasoning_effort="{effort}"',
                                      "--ephemeral", "--skip-git-repo-check", "-s", "read-only", "-o", last, full])
            text = Path(last).read_text()
        finally:
            os.unlink(last)
        m = re.search(r"tokens used\s*\n?\s*([\d,]+)", out + err)
        return text, {"total_tokens": int(m.group(1).replace(",", "")) if m else None}, {}


CLI_PROVIDERS = {"claude-cli": ClaudeCLIProvider, "gemini-cli": GeminiCLIProvider, "codex-cli": CodexCLIProvider}
