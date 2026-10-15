"""Owned SoC lifecycle metadata; never selects the Spike transport spec."""
import json
from pathlib import Path
def require(ok,why):
    if not ok:raise ValueError(why)
def definition():return json.loads((Path(__file__).resolve().parent/'soc_spec.json').read_text())
def width(code,write):
    if code&3!=3:
        q,k=code&3,(code>>13)&7
        if q in (0,2) and k in ((6,7) if write else (2,3)):return 4 if k in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None
