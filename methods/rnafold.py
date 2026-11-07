"""Method C (specialist): ViennaRNA RNAfold MFE prediction via the Python bindings."""
from __future__ import annotations

import time

import RNA

SETTINGS = {
    "tool": "ViennaRNA RNAfold (MFE)",
    "version": RNA.__version__,
    "temperature_C": 37.0,
    "energy_params": "Turner 2004 (ViennaRNA default)",
    "dangles": 2,
    "noLP": False,
}


def fold(seq: str) -> tuple[str, float]:
    """Return (MFE structure in dot-bracket, MFE in kcal/mol)."""
    md = RNA.md()
    md.temperature = SETTINGS["temperature_C"]
    md.dangles = SETTINGS["dangles"]
    md.noLP = int(SETTINGS["noLP"])
    fc = RNA.fold_compound(seq.upper().replace("T", "U"), md)
    structure, mfe = fc.mfe()
    return structure, round(float(mfe), 2)


def predict(item: dict) -> dict:
    """Uniform method interface used by run.py (item = manifest row)."""
    t0 = time.perf_counter()
    structure, mfe = fold(item["seq"])
    return {
        "pred_db": structure,
        "raw_output": f"{structure} ({mfe})",
        "latency_s": round(time.perf_counter() - t0, 4),
        "extra": {"mfe": mfe},
    }
