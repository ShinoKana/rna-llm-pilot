import json

import pytest

from methods import agent, llm, rnafm, rnafold

ITEM = {"id": "t1", "seq": "GGGGAAAACCCCAUGCAUGCAUGC"}


def test_rnafold_hairpin():
    db, mfe = rnafold.fold("GGGGAAAACCCC")
    assert db == "((((....))))" and mfe < 0
    out = rnafold.predict({"id": "x", "seq": "GGGGAAAACCCC"})
    assert out["pred_db"] == db and out["extra"]["mfe"] == mfe


def test_extract_structure():
    assert llm.extract_structure("blah\nSTRUCTURE: ((..))", 6) == ("((..))", "label")
    assert llm.extract_structure("STRUCTURE: `((..))`", 6) == ("((..))", "label")
    assert llm.extract_structure("```\n((..))\n```", 6) == ("((..))", "fallback")
    assert llm.extract_structure("no idea", 6) == (None, "none")


def test_network_disabled_by_default(monkeypatch):
    monkeypatch.setattr(llm, "_NETWORK_ENABLED", False)
    with pytest.raises(llm.LLMError, match="network disabled"):
        llm._post_json("https://example.invalid", {}, {})


def test_missing_key_message_does_not_leak(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.LLMError) as e:
        llm._env_key("ANTHROPIC_API_KEY")
    assert "ANTHROPIC_API_KEY" in str(e.value)


def test_real_provider_requires_model():
    with pytest.raises(ValueError):
        llm.make_provider("anthropic", None)


def test_mock_direct_logs_call(tmp_path):
    log = tmp_path / "calls.jsonl"
    p = llm.make_provider("mock", None, logger=llm.CallLogger(log))
    out = llm.predict_direct(p, ITEM)
    assert set(out) >= {"pred_db", "raw_output", "latency_s", "usage"}
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["model"] == "mock-v1" and rec["settings"]["temperature"] == 0.0
    assert "raw_output" in rec and "usage" in rec and "latency_s" in rec


def test_agent_loop_verbatim_or_altered(tmp_path):
    p = llm.make_provider("mock", None)
    alt_log = tmp_path / "alt.jsonl"
    statuses = set()
    for k in range(12):  # enough sequences to hit both mock behaviours
        item = {"id": f"s{k}", "seq": "GGGGAAAACCCC" + "AUGC" * k}
        out = agent.predict_agent(p, item, alterations_log=alt_log)
        audit = out["extra"]["tool_audit"]
        statuses.add(audit["status"])
        tool_db = out["extra"]["tool_calls"][0]["output"]["structure"]
        assert tool_db == rnafold.fold(item["seq"])[0]
        if audit["status"] == "verbatim":
            assert out["pred_db"] == tool_db
    assert statuses == {"verbatim", "altered"}
    lines = [json.loads(x) for x in alt_log.read_text().splitlines()]
    assert lines and all(x["status"] == "altered" and x["pairs_removed"] == 1 for x in lines)


def test_audit_statuses():
    assert agent.audit_tool_use("((..))", [], "GGAACC")["status"] == "no_tool_call"
    log = [{"seq_matches_query": False, "output": {"structure": "......"}}]
    assert agent.audit_tool_use("((..))", log, "GGAACC")["status"] == "tool_called_on_other_seq"


def test_fold_tool_rejects_bad_input():
    assert "error" in agent.run_fold_tool({"seq": "ACGX"})
    assert agent.run_fold_tool({"seq": "ggggaaaacccc"})["structure"] == "((((....))))"


def test_rnafm_decoder_and_stub():
    seq = "GGGAAAACCC"
    L = len(seq)
    probs = [[0.0] * L for _ in range(L)]
    for i, j in [(0, 9), (1, 8), (2, 7)]:
        probs[i][j] = 0.9
    probs[0][8] = 0.6  # conflicts with (0, 9): must lose
    assert rnafm.decode_contact_map(probs, seq) == "(((....)))"
    with pytest.raises(RuntimeError):
        rnafm.predict({"id": "no-such-id", "seq": seq})
