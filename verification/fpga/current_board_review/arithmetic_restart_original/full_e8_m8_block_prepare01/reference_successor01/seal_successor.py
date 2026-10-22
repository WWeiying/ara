import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(1,str(Path(__file__).resolve().parent.parent))
import prepare as p
HERE=Path(__file__).resolve().parent

previous=HERE.parent/'entry.json'
assert p.sha(previous)=='b4d39e48be697aa3d02d95bab31d42fb57ae0aa1df14be8019e1074595b67125'
old=json.loads(previous.read_text());pins=dict(old['pins'])
for path,digest in pins.items():assert p.sha(Path(path))==digest,path
pins[str(previous)]=p.sha(previous)
assert json.loads((HERE/'host_group02.json').read_text())['actual_exit_code']==0
for path in HERE.iterdir():
    if path.is_file():pins[str(path)]=p.sha(path)
entry=dict(status='SUCCESSOR_GROUP8_REFERENCE_ENTRY_PENDING_INDEPENDENT_REVIEW',
    previous_entry_sha256=p.sha(previous),previous_entry_reference_runs=0,
    sole_semantic_delta='group concatenates all8 instead of4 physical vector registers',
    pins=pins,pin_count=len(pins),bounds=old['bounds'],scope=old['scope'],
    independent_review_schema=old['independent_review_schema'],
    preserved_source_pins_sha256=old['source_pins_sha256'],
    invocation='python3 -B reference_successor01/reference.py execute --review ABSOLUTE_JSON --review-sha ACTUAL_SHA')
p.save(HERE/'entry.json',entry)
print(json.dumps(dict(entry=str(HERE/'entry.json'),sha256=p.sha(HERE/'entry.json'),pins=len(pins))))
