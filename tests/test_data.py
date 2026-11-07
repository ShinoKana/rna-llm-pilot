from data.loaders import load_ct_bpseq_folder, read_bpseq, read_ct
from data.sample import allocate, stratified_sample
from data.scope import scope_check

CT = """\
8 test hairpin
1 G 0 2 8 1
2 G 1 3 7 2
3 A 2 4 0 3
4 A 3 5 0 4
5 A 4 6 0 5
6 A 5 7 0 6
7 C 6 8 2 7
8 C 7 0 1 8
"""

BPSEQ = """\
# comment
1 G 6
2 A 0
3 A 0
4 A 0
5 A 0
6 C 1
"""


def test_read_ct_and_bpseq(tmp_path):
    (tmp_path / "tRNA_x.ct").write_text(CT)
    (tmp_path / "5s_y.bpseq").write_text(BPSEQ)
    assert read_ct(tmp_path / "tRNA_x.ct") == ("GGAAAACC", [(0, 7), (1, 6)])
    assert read_bpseq(tmp_path / "5s_y.bpseq") == ("GAAAAC", [(0, 5)])
    recs = {r["id"]: r for r in load_ct_bpseq_folder(tmp_path)}
    assert recs["tRNA_x"]["ref_db"] == "((....))" and recs["tRNA_x"]["family"] == "tRNA"
    assert recs["5s_y"]["family"] == "5S_rRNA"


def test_scope_allowlist_keeps_listed_organisms():
    for good, fam in [("16S_rRNA-E.coli_domain4", "16S_rRNA"),
                      ("16S_rRNA-C.reinhardtii.mito_domain4", "16S_rRNA"),
                      ("tRNA-tdbR00000250-Saccharomyces_cerevisiae-4932-Leu-UAG", "tRNA"),
                      ("5S_rRNA-Bacillus-subtilis-1", "5S_rRNA"),
                      ("SRP-Homo.sapi._X01037", "SRP"),
                      ("tmRNA-Jako.libe._TRW-143017_1-102", "tmRNA")]:
        assert scope_check(good, fam)[0], good


def test_scope_allowlist_is_fail_closed():
    # organisms or families that are simply not on the allowlist are dropped, with a uniform reason
    for bad, fam in [("5S_rRNA-Weissella-viridescens-1", "5S_rRNA"),
                     ("tRNA-tdbR00000033-Didelphis_virginiana-9267-Asp-QUC", "tRNA"),
                     ("16S_rRNA-E.coli_domain4", "riboswitch"),
                     ("RNaseP-unknown-organism", "RNaseP")]:
        ok, reason = scope_check(bad, fam)
        assert not ok and reason == "not in allowlist", bad


def test_allocate_waterfilling():
    alloc = allocate({"a": 1, "b": 3, "c": 24, "d": 500, "e": 500, "f": 900}, 50)
    assert sum(alloc.values()) == 50
    assert alloc["a"] == 1 and alloc["b"] == 3
    assert max(alloc.values()) - min(alloc[k] for k in "cdef") <= 1


def test_stratified_sample_is_deterministic_and_spans_lengths():
    recs = [{"id": f"{fam}{i}", "family": fam, "seq": "A" * (20 + i), "ref_db": "." * (20 + i),
             "source": "t"} for fam in "xy" for i in range(60)]
    s1 = stratified_sample(recs, 12, seed=1)
    s2 = stratified_sample(recs, 12, seed=1)
    assert [r["id"] for r in s1] == [r["id"] for r in s2]
    assert len(s1) == 12
    x_lens = sorted(len(r["seq"]) for r in s1 if r["family"] == "x")
    assert x_lens[0] < 40 and x_lens[-1] >= 60  # short and long bins both represented
    assert {r["length_bin"] for r in s1} == {"1/3", "2/3", "3/3"}


def test_extra_metrics():
    from evals.extra import claims_self_check, fabricated_stems, stems
    from evals.f1 import parse_dotbracket
    ref = parse_dotbracket("((((....))))......")
    pred = parse_dotbracket("((((....))))((..))")
    assert len(stems(pred)) == 2
    assert fabricated_stems(pred, ref) == (1, 2)
    assert claims_self_check("I checked that the string is 120 characters long")
    assert not claims_self_check("STRUCTURE: ((..))")


def test_pairs_answer_to_dotbracket():
    from methods.llm import pairs_from_text
    assert pairs_from_text("blah\nPAIRS: (1,8) (2,7)", 8) == ("((....))", "pairs")
    assert pairs_from_text("PAIRS: (1,8) (1,7)", 8)[0] is None
    assert pairs_from_text("PAIRS: none", 5) == (".....", "pairs")
