"""Base-pair scoring and dot-bracket validation for RNA secondary structures.

Conventions
-----------
* Pairs are 0-based ``(i, j)`` tuples with ``i < j``.
* Dot-bracket may use ``()``, ``[]``, ``{}`` and ``<>``; each bracket type is
  matched with its own stack, so pseudoknots (crossing pairs) parse correctly.
* ``.`` is unpaired. ``-``, ``_``, ``,`` and ``:`` are accepted as unpaired too
  (some tools emit them); anything else is an invalid character.
* Canonical pairs are Watson-Crick plus G-U wobble (AU, UA, GC, CG, GU, UG).
"""
from __future__ import annotations

from dataclasses import dataclass, field

OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}", "<": ">"}
CLOSE_TO_OPEN = {v: k for k, v in OPEN_TO_CLOSE.items()}
UNPAIRED_CHARS = set(".-_,:")
ALLOWED_CHARS = set(OPEN_TO_CLOSE) | set(CLOSE_TO_OPEN) | UNPAIRED_CHARS
CANONICAL = {("A", "U"), ("U", "A"), ("G", "C"), ("C", "G"), ("G", "U"), ("U", "G")}
# Bracket pages used when writing pairs back out, in order of preference.
PAGES = [("(", ")"), ("[", "]"), ("{", "}"), ("<", ">")]


class DotBracketError(ValueError):
    """Raised when a dot-bracket string cannot be parsed into pairs."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # "invalid_chars" | "unbalanced"


def parse_dotbracket(db: str) -> list[tuple[int, int]]:
    """Parse dot-bracket into a sorted list of 0-based pairs (pseudoknot-safe)."""
    bad = sorted({c for c in db if c not in ALLOWED_CHARS})
    if bad:
        raise DotBracketError("invalid_chars", f"invalid characters: {''.join(bad)!r}")
    stacks: dict[str, list[int]] = {o: [] for o in OPEN_TO_CLOSE}
    pairs = []
    for k, c in enumerate(db):
        if c in OPEN_TO_CLOSE:
            stacks[c].append(k)
        elif c in CLOSE_TO_OPEN:
            stack = stacks[CLOSE_TO_OPEN[c]]
            if not stack:
                raise DotBracketError("unbalanced", f"unmatched {c!r} at position {k}")
            pairs.append((stack.pop(), k))
    leftover = [(o, s[-1]) for o, s in stacks.items() if s]
    if leftover:
        o, pos = leftover[0]
        raise DotBracketError("unbalanced", f"unmatched {o!r} at position {pos}")
    return sorted(pairs)


def pairs_to_dotbracket(pairs, length: int) -> str:
    """Write pairs as dot-bracket, putting crossing pairs on higher bracket pages."""
    out = ["."] * length
    pages: list[list[tuple[int, int]]] = []
    for i, j in sorted(pairs):
        for page in pages:
            if not any(a < i < b < j or i < a < j < b for a, b in page):
                page.append((i, j))
                break
        else:
            if len(pages) >= len(PAGES):
                raise ValueError("pseudoknot depth exceeds available bracket types")
            pages.append([(i, j)])
    for (o, c), page in zip(PAGES, pages):
        for i, j in page:
            out[i], out[j] = o, c
    return "".join(out)


@dataclass
class Validation:
    """Result of validating a predicted structure against its sequence."""

    errors: list[str] = field(default_factory=list)  # fatal: cannot be scored
    noncanonical: list[tuple[int, int]] = field(default_factory=list)  # warning only
    pairs: list[tuple[int, int]] = field(default_factory=list)
    message: str = ""

    @property
    def valid(self) -> bool:
        return not self.errors


def validate(db: str | None, seq: str) -> Validation:
    """Check a predicted structure: characters, balance, length, pair types.

    Error codes: ``no_structure``, ``invalid_chars``, ``unbalanced``,
    ``length_mismatch``. Non-canonical pairs are reported but do not make the
    structure invalid (reference structures contain some, too).
    """
    v = Validation()
    if not db:
        v.errors.append("no_structure")
        v.message = "empty or missing structure"
        return v
    if len(db) != len(seq):
        v.errors.append("length_mismatch")
        v.message = f"structure length {len(db)} != sequence length {len(seq)}"
    try:
        v.pairs = parse_dotbracket(db)
    except DotBracketError as e:
        v.errors.append(e.kind)
        v.message = (v.message + "; " if v.message else "") + str(e)
        v.pairs = []
        return v
    s = seq.upper().replace("T", "U")
    v.noncanonical = [(i, j) for i, j in v.pairs
                      if i < len(s) and j < len(s) and (s[i], s[j]) not in CANONICAL]
    return v


def _match_count(a, b, slip: int) -> int:
    """Number of pairs in ``a`` that have a partner in ``b`` within ``slip``.

    With slip=1 a pair (i, j) also matches (i±1, j) or (i, j±1): one index may
    shift by one, as in the common "shift-allowed" evaluation.
    """
    bset = set(b)
    n = 0
    for i, j in a:
        if (i, j) in bset:
            n += 1
        elif slip and any(p in bset for d in range(1, slip + 1)
                          for p in ((i - d, j), (i + d, j), (i, j - d), (i, j + d))):
            n += 1
    return n


def score_pairs(pred, ref, slip: int = 0) -> dict:
    """Base-pair precision, recall and F1.

    Precision counts predicted pairs matched in the reference, recall counts
    reference pairs matched in the prediction (these differ only with slip).
    If both sets are empty all metrics are 1.0; if only one is empty, 0.0.
    """
    pred, ref = list(pred), list(ref)
    if not pred and not ref:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "n_pred": 0, "n_ref": 0}
    tp_p = _match_count(pred, ref, slip)
    tp_r = _match_count(ref, pred, slip)
    p = tp_p / len(pred) if pred else 0.0
    r = tp_r / len(ref) if ref else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1, "n_pred": len(pred), "n_ref": len(ref)}


def score_structure(pred_db: str | None, ref_db: str, seq: str) -> dict:
    """Validate and score a predicted dot-bracket against the reference.

    Invalid predictions get all-zero metrics (``valid`` = False) so that
    aggregate scores penalise unusable output.
    """
    v = validate(pred_db, seq)
    ref = parse_dotbracket(ref_db)
    out = {
        "valid": v.valid,
        "errors": v.errors,
        "message": v.message,
        "n_noncanonical": len(v.noncanonical),
    }
    if v.valid:
        out["exact"] = score_pairs(v.pairs, ref, slip=0)
        out["slip1"] = score_pairs(v.pairs, ref, slip=1)
    else:
        zero = {"precision": 0.0, "recall": 0.0, "f1": 0.0, "n_pred": 0, "n_ref": len(ref)}
        out["exact"], out["slip1"] = dict(zero), dict(zero)
    return out
