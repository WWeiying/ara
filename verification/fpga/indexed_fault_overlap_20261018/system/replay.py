#!/usr/bin/env python3
"""Replay immutable prepared ELFs in a fresh directory against an explicit image."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('system_fixture_runner',HERE/'run.py')
helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--image',type=Path,required=True)
p.add_argument('--prepared',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--case',choices=helper.CASES,action='append')
p.add_argument('--jobs',type=int,default=1,choices=range(1,9))
a=p.parse_args(); old=a.prepared.resolve(); out=a.out.resolve(); image=a.image.resolve()
assert out.is_relative_to(HERE) and not out.exists()
ledger=json.loads((image/'image.json').read_text())
assert helper.sha(Path(ledger['snapshot'])/'snapshot.json')==ledger['snapshot_sha256']
for path,digest in ledger['files'].items(): assert helper.sha(path)==digest,path
names=a.case or list(helper.CASES)
assert len(set(names))==len(names)
out.mkdir()
shutil.copyfile(old/'capture.tcl',out/'capture.tcl')
helper.save(out/'image-audit.json',dict(image=ledger,scope='Explicit-image replay; no live-source baseline equality requirement'))
provenance={}
for name in names:
    case=out/name; case.mkdir()
    for filename in ('soc.elf','soc.dis','reference.json'):
        source=old/name/filename
        shutil.copyfile(source,case/filename)
        provenance[str(source)]=helper.sha(source)
helper.save(out/'replay-inputs.json',dict(prepared=str(old),image=str(image),cases=names,
            source_files=provenance,runner_sha256=helper.sha(HERE/'run.py'),jobs=a.jobs))
with ThreadPoolExecutor(max_workers=a.jobs) as pool:
    results=list(pool.map(lambda name: helper.execute(out,name),names))
helper.save(out/'results.json',dict(cases=names,passed=results))
raise SystemExit(0 if all(results) else 1)
