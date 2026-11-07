"""Failure-type taxonomy for scored prediction records.

Each record gets one primary class (first match wins) and any number of flags.

Primary classes:
  call_error        the method raised (API/network/tool failure)
  no_structure      no dot-bracket could be extracted from the output
  invalid_chars     structure contains characters outside .()[]{}<>
  unbalanced        brackets do not match
  length_mismatch   structure length != sequence length
  empty_prediction  valid but predicts no pairs while the reference has some
  low_f1            valid, exact F1 < 0.5
  ok                valid, exact F1 >= 0.5

Flags:
  noncanonical_pairs     at least one predicted pair is not AU/GC/GU
  slip_sensitive         F1 gains >= 0.1 with +-1 slip (registration errors)
  fallback_extraction    answer lacked the 'STRUCTURE:' line
  tool:<status>          method B only: no_tool_call / verbatim / altered /
                         tool_called_on_other_seq / no_final_structure
  hit_turn_limit         method B only: loop ended while the model still called tools
"""
from __future__ import annotations

ERROR_ORDER = ["no_structure", "invalid_chars", "unbalanced", "length_mismatch"]
LOW_F1 = 0.5


def classify(rec: dict) -> tuple[str, list[str]]:
    flags = []
    extra = rec.get("extra") or {}
    if extra.get("extraction") == "fallback":
        flags.append("fallback_extraction")
    if "tool_audit" in extra:
        flags.append(f"tool:{extra['tool_audit']['status']}")
    if extra.get("hit_turn_limit"):
        flags.append("hit_turn_limit")
    if rec.get("error"):
        return "call_error", flags
    if rec.get("n_noncanonical", 0) > 0:
        flags.append("noncanonical_pairs")
    errors = rec.get("errors") or []
    for code in ERROR_ORDER:
        if code in errors:
            return code, flags
    ex, sl = rec["exact"], rec["slip1"]
    if sl["f1"] - ex["f1"] >= 0.1:
        flags.append("slip_sensitive")
    if ex["n_pred"] == 0 and ex["n_ref"] > 0:
        return "empty_prediction", flags
    if ex["f1"] < LOW_F1:
        return "low_f1", flags
    return "ok", flags
