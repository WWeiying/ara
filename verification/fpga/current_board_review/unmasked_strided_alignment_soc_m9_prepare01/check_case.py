import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import dut_check
import reference as r
member,csv,spec,out=sys.argv[1:]
result=dut_check.analyze(Path(csv),json.loads(Path(spec).read_text()),member.startswith('store'),member.endswith('sv39'))
r.save(Path(out),result)
print(json.dumps(result,indent=2))
