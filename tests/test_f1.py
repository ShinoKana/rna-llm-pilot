import pytest

from evals.f1 import (DotBracketError, pairs_to_dotbracket, parse_dotbracket, score_pairs,
                      score_structure, validate)
from evals.taxonomy import classify


# ---------------------------------------------------------------- parsing
def test_parse_simple_hairpin():
    assert parse_dotbracket("((..))") == [(0, 5), (1, 4)]


def test_parse_pseudoknot_all_bracket_types():
    # H-type pseudoknot on [] plus extra {} and <> pages
    db = "((..[[..))..]]{<..}>"
    pairs = parse_dotbracket(db)
    assert (0, 9) in pairs and (1, 8) in pairs
    assert (4, 13) in pairs and (5, 12) in pairs
    assert (14, 18) in pairs and (15, 19) in pairs
    assert len(pairs) == 6


def test_parse_unpaired_alternatives():
    assert parse_dotbracket("(-_,:)") == [(0, 5)]


@pytest.mark.parametrize("db,kind", [
    ("((..)", "unbalanced"),
    ("(..))", "unbalanced"),
    ("(..]", "unbalanced"),
    ("((xx))", "invalid_chars"),
    ("((..)) ", "invalid_chars"),
])
def test_parse_errors(db, kind):
    with pytest.raises(DotBracketError) as e:
        parse_dotbracket(db)
    assert e.value.kind == kind


def test_roundtrip_with_pseudoknot():
    db = "((..[[..))..]]"
    pairs = parse_dotbracket(db)
    assert pairs_to_dotbracket(pairs, len(db)) == db


def test_pairs_to_dotbracket_assigns_crossing_pairs_to_new_page():
    assert pairs_to_dotbracket([(0, 4), (2, 6)], 7) == "(.[.).]"


# ---------------------------------------------------------------- validation
def test_validate_ok_and_noncanonical():
    v = validate("((...))", "GAAAAUC")  # G-C ok, A-U ok
    assert v.valid and v.noncanonical == []
    v = validate("((...))", "GAAAAAC")  # A-A non-canonical: warning, still valid
    assert v.valid and v.noncanonical == [(1, 5)]


def test_validate_gu_wobble_is_canonical():
    assert validate("(...)", "GAAAU").noncanonical == []
    assert validate("(...)", "UAAAG").noncanonical == []


@pytest.mark.parametrize("db,code", [
    ("((..)", "unbalanced"),
    ("((..))..", "length_mismatch"),
    ("((ab))", "invalid_chars"),
    ("", "no_structure"),
    (None, "no_structure"),
])
def test_validate_errors(db, code):
    v = validate(db, "GGAACC")
    assert not v.valid and code in v.errors


def test_validate_reports_length_and_balance_together():
    v = validate("((.", "GGAACC")
    assert set(v.errors) == {"length_mismatch", "unbalanced"}


# ---------------------------------------------------------------- scoring
def test_perfect_score():
    s = score_pairs([(0, 9), (1, 8)], [(0, 9), (1, 8)])
    assert s["precision"] == s["recall"] == s["f1"] == 1.0


def test_partial_score():
    s = score_pairs(pred=[(0, 9), (2, 7)], ref=[(0, 9), (1, 8), (3, 6)])
    assert s["precision"] == pytest.approx(0.5)
    assert s["recall"] == pytest.approx(1 / 3)
    assert s["f1"] == pytest.approx(0.4)


def test_slip_tolerance():
    ref = [(0, 20), (1, 19), (2, 18)]
    pred = [(1, 20), (2, 19), (3, 18)]  # every pair shifted by one on the 5' side
    assert score_pairs(pred, ref)["f1"] == 0.0
    assert score_pairs(pred, ref, slip=1)["f1"] == 1.0
    # shifting both ends is not tolerated
    assert score_pairs([(1, 19)], [(0, 20)], slip=1)["f1"] == 0.0


def test_empty_conventions():
    assert score_pairs([], [])["f1"] == 1.0
    assert score_pairs([], [(0, 5)])["f1"] == 0.0
    assert score_pairs([(0, 5)], [])["f1"] == 0.0


def test_score_structure_pseudoknot_reference():
    seq = "GGAAGGAACCAACCAA"
    ref = "((..[[..))..]].."
    out = score_structure(ref, ref, seq)
    assert out["valid"] and out["exact"]["f1"] == 1.0
    nested_only = "((......))......"
    out = score_structure(nested_only, ref, seq)
    assert out["exact"]["precision"] == 1.0 and out["exact"]["recall"] == 0.5


def test_invalid_prediction_scores_zero():
    out = score_structure("((..", "((..))", "GGAACC")
    assert not out["valid"] and out["exact"]["f1"] == 0.0 and out["exact"]["n_ref"] == 2


# ---------------------------------------------------------------- taxonomy
def _rec(pred, ref="((((....))))", seq="GGGGAAAACCCC", **extra):
    r = score_structure(pred, ref, seq)
    r.update(extra)
    return r


def test_taxonomy_primary_classes():
    assert classify(_rec("((((....))))"))[0] == "ok"
    assert classify(_rec("............"))[0] == "empty_prediction"
    assert classify(_rec("(((....)))"))[0] == "length_mismatch"
    assert classify(_rec("((((....))).."))[0] == "unbalanced"
    assert classify(_rec(None))[0] == "no_structure"
    assert classify(_rec(None, error="LLMError: boom"))[0] == "call_error"
    assert classify(_rec("(((......)))", ref="((((....))))"))[0] == "ok"
    assert classify(_rec("(..........)", ref="..((....)).."))[0] == "low_f1"


def test_taxonomy_flags():
    _, flags = classify(_rec("((((....))))", seq="AAAAAAAAAAAA",
                             extra={"extraction": "fallback", "tool_audit": {"status": "altered"}}))
    assert {"noncanonical_pairs", "fallback_extraction", "tool:altered"} <= set(flags)
    _, flags = classify(_rec(".((((...))))", ref="((((....))))"))
    assert "slip_sensitive" in flags
