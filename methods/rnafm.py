"""Method C (specialist, second model): RNA-FM secondary-structure head (bpRNA-trained ResNet).

To run later on a machine with the HF weights (cuhkaih/rnafm) and a GPU.
Only the decoding step (contact map -> dot-bracket) is implemented here so it
can be unit-tested; model loading and inference are left to ``predict``.

IMPORTANT: RNA-FM's secondary-structure head was trained on bpRNA TR0. Evaluate
it on bpRNA TS0 only (``python -m data.sample --bprna-ts0``), not on ArchiveII,
whose families overlap the training data.
"""
from __future__ import annotations

from evals.f1 import CANONICAL, pairs_to_dotbracket

HF_MODEL_ID = "cuhkaih/rnafm"


def decode_contact_map(probs, seq: str, threshold: float = 0.5, min_loop: int = 3) -> str:
    """Greedy decoding: take highest-probability canonical pairs, one partner per base.

    ``probs`` is an L x L matrix-like (nested lists or array) of pair probabilities.
    """
    L = len(seq)
    s = seq.upper().replace("T", "U")
    cand = [(float(probs[i][j]), i, j) for i in range(L) for j in range(i + min_loop + 1, L)
            if float(probs[i][j]) >= threshold and (s[i], s[j]) in CANONICAL]
    used, pairs = set(), []
    for _, i, j in sorted(cand, reverse=True):
        if i not in used and j not in used:
            used.update((i, j))
            pairs.append((i, j))
    return pairs_to_dotbracket(pairs, L)


OFFICIAL_THRESHOLD = 0.33993712  # RNA-FM redevelop/pretrained/ss_prediction.yml
_MAPS: dict = {}


def _maps():
    """Pair-probability maps computed on a GPU by methods/rnafm_infer_gpu.py (one RTX 3060,
    weights SS/RNA-FM-ResNet_bpRNA.pth from HF cuhkaih/rnafm). Loaded lazily from data/rnafm_maps/*.npz."""
    if not _MAPS:
        import numpy as np
        from pathlib import Path
        for f in sorted((Path(__file__).resolve().parent.parent / "data/rnafm_maps").glob("*.npz")):
            with np.load(f) as z:
                _MAPS.update({k: z[k].astype("float32") for k in z.files})
    return _MAPS


def predict(item: dict) -> dict:
    m = _maps().get(item["id"])
    if m is None:
        raise RuntimeError(f"no RNA-FM map for {item['id']}; run methods/rnafm_infer_gpu.py on a GPU machine first")
    return {"pred_db": decode_contact_map(m, item["seq"], threshold=OFFICIAL_THRESHOLD), "raw_output": None,
            "latency_s": None, "usage": {}, "extra": {"threshold": OFFICIAL_THRESHOLD, "head": "RNA-FM-ResNet_bpRNA"}}
