"""Read only accepted software01 artifacts, no generation or execution."""
import hashlib
import json
from pathlib import Path
import re
HERE=Path(__file__).resolve().parent
SOFT=HERE.parent/'software01'
def require(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def emit(p,value):
    with Path(p).open('x') as f:f.write(value)
def artifacts():
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
        (SOFT/'spike/program.dis').read_text(),re.M)}
    return read(SOFT/'spike/symbols.json'),code,read(SOFT/'proof.json')['backends']['spike']['helpers'],read(SOFT/'sequence.json')
def width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):
            return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None
