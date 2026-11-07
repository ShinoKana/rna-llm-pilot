"""Extra pilot metrics (added 11-04 after the external survey):

* mcc            approximate base-pair MCC = sqrt(PPV * sensitivity) (Gorodkin et al.; standard in RNA SS work)
* stems          maximal runs of stacked pairs (i,j),(i+1,j-1)... of length >= 2
* fabricated     a predicted stem none of whose pairs matches the reference within +-1 slip
* self-check     the answer text claims it was checked (length / balance) but the structure is invalid
* tool outcome   method B: verbatim / improved / worsened / same, comparing final F1 with the raw RNAfold output's F1
"""
from __future__ import annotations

import math
import re

from evals.f1 import DotBracketError, parse_dotbracket, score_pairs


def mcc(precision: float, recall: float) -> float:
    return math.sqrt(max(precision, 0.0) * max(recall, 0.0))


def stems(pairs) -> list[list[tuple[int, int]]]:
    pset, seen, out = set(pairs), set(), []
    for p in sorted(pairs):
        if p in seen:
            continue
        i, j = p
        if (i - 1, j + 1) in pset:  # not the outermost pair of its stem
            continue
        run = []
        while (i, j) in pset:
            run.append((i, j)); seen.add((i, j)); i, j = i + 1, j - 1
        if len(run) >= 2:
            out.append(run)
    return out


def fabricated_stems(pred_pairs, ref_pairs) -> tuple[int, int]:
    """(n_fabricated, n_stems) for the predicted structure."""
    ref = set(ref_pairs)
    near = lambda i, j: any((i + a, j + b) in ref for a in (-1, 0, 1) for b in (-1, 0, 1) if abs(a) + abs(b) <= 1)  # noqa: E731
    st = stems(pred_pairs)
    fab = sum(1 for s in st if not any(near(i, j) for i, j in s))
    return fab, len(st)


CLAIM_RE = re.compile(r"(I (have )?(checked|verified|confirmed)|brackets? (are )?balanced|is exactly \d+ characters|"
                      r"\b\d+ characters long|length (matches|is correct))", re.I)


def claims_self_check(text: str | None) -> bool:
    return bool(CLAIM_RE.search(text or ""))


def tool_outcome(rec: dict, ref_db: str) -> str | None:
    audit = (rec.get("extra") or {}).get("tool_audit")
    if not audit:
        return None
    st = audit["status"]
    if st != "altered":
        return st
    try:
        tool_f1 = score_pairs(parse_dotbracket(audit["tool_db"]), parse_dotbracket(ref_db))["f1"]
    except DotBracketError:
        return "altered"
    final_f1 = rec["exact"]["f1"]
    if final_f1 > tool_f1 + 1e-9:
        return "improved"
    if final_f1 < tool_f1 - 1e-9:
        return "worsened"
    return "altered_same_f1"
