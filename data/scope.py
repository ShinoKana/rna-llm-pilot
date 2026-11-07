"""Data-scope rule (scope-v2, allowlist): keep only cellular ncRNA from an explicit list of organisms.

A record is kept only if BOTH hold:
  1. its family is one of the cellular ncRNA families in ``ALLOWED_FAMILIES``;
  2. its id/name names an organism in ``ALLOWED_ORGANISMS`` (model organisms and other well-characterised
     free-living species: laboratory bacteria and archaea, yeasts, plants, animals, human).
Everything else is dropped with the single reason "not in allowlist". The rule never needs a list of what
to exclude, and the exclusion log records only ids. This replaces scope-v1 (a keyword blocklist).

Organism names in ArchiveII / bpRNA ids come in several styles, all generated from the allowlist entry:
  * full binomial          ``Escherichia_coli``, ``Bacillus-subtilis``, ``Homo sapiens``
  * initial + epithet      ``E.coli``, ``H.sapiens.mito``
  * 4 + 4 abbreviation     ``Esch.coli._CP000...`` (SRP / tmRNA databases)
"""
from __future__ import annotations

import re

RULE_VERSION = "scope-v2-allowlist"

ALLOWED_FAMILIES = {"tRNA", "5S_rRNA", "SRP", "RNaseP", "tmRNA", "16S_rRNA", "23S_rRNA", "grp1", "grp2", "telomerase",
                    "group_I_intron", "group_II_intron"}

ALLOWED_ORGANISMS: list[tuple[str, str]] = [
    # bacteria (laboratory / environmental model species)
    ("Escherichia", "coli"), ("Bacillus", "subtilis"), ("Thermus", "thermophilus"), ("Thermus", "aquaticus"),
    ("Aquifex", "aeolicus"), ("Aquifex", "pyrophilus"), ("Synechocystis", "sp"), ("Synechococcus", "elongatus"),
    ("Anabaena", "variabilis"), ("Caulobacter", "crescentus"), ("Deinococcus", "radiodurans"),
    ("Thermotoga", "maritima"), ("Lactococcus", "lactis"), ("Streptomyces", "coelicolor"),
    # archaea
    ("Haloferax", "volcanii"), ("Halobacterium", "salinarum"), ("Methanocaldococcus", "jannaschii"),
    ("Sulfolobus", "acidocaldarius"), ("Sulfolobus", "solfataricus"), ("Archaeoglobus", "fulgidus"),
    ("Pyrococcus", "furiosus"), ("Thermococcus", "kodakarensis"),
    # fungi and protists (free-living model species)
    ("Saccharomyces", "cerevisiae"), ("Schizosaccharomyces", "pombe"), ("Neurospora", "crassa"),
    ("Dictyostelium", "discoideum"), ("Tetrahymena", "thermophila"), ("Chlamydomonas", "reinhardtii"),
    ("Jakoba", "libera"),
    # plants
    ("Arabidopsis", "thaliana"), ("Oryza", "sativa"), ("Zea", "mays"), ("Triticum", "aestivum"),
    ("Spinacia", "oleracea"), ("Nicotiana", "tabacum"), ("Fragaria", "ananassa"), ("Physcomitrella", "patens"),
    ("Hordeum", "vulgare"), ("Pisum", "sativum"), ("Glycine", "max"),
    # animals
    ("Homo", "sapiens"), ("Mus", "musculus"), ("Rattus", "norvegicus"), ("Bos", "taurus"), ("Sus", "scrofa"),
    ("Gallus", "gallus"), ("Xenopus", "laevis"), ("Danio", "rerio"), ("Drosophila", "melanogaster"),
    ("Caenorhabditis", "elegans"), ("Bombyx", "mori"), ("Apis", "mellifera"),
]

_SEP = r"[\s_\-.]+"


def _patterns():
    pats = []
    for genus, sp in ALLOWED_ORGANISMS:
        pats.append(re.compile(rf"(?<![A-Za-z]){genus}{_SEP}{sp}(?![a-z])", re.I))          # full binomial
        pats.append(re.compile(rf"(?<![A-Za-z]){genus[0]}\.[\s_\-]?{sp}(?![a-z])"))            # E.coli
        pats.append(re.compile(rf"(?<![A-Za-z]){genus[:4]}\.{sp[:4]}\.", re.I))                 # Esch.coli.
    return pats


_ORG_PATTERNS = _patterns()


def family_ok(family: str) -> bool:
    return family in ALLOWED_FAMILIES


def organism_ok(text: str) -> bool:
    return any(p.search(text) for p in _ORG_PATTERNS)


def scope_check(text: str, family: str | None = None) -> tuple[bool, str]:
    """Return (keep, reason). ``text`` is the id/name string; ``family`` the record's family if known."""
    if family is not None and not family_ok(family):
        return False, "not in allowlist"
    if not organism_ok(text):
        return False, "not in allowlist"
    return True, "ok"
