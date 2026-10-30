#!/usr/bin/env python3
"""Compile the actual installed production TU; require the exact reviewed delta."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from compile_float_gap_candidate import SOURCE,ROOT,DATABASE,candidate
import sys
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,hashes,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--before',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();before=a.before.resolve(strict=True)
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    if SOURCE.read_text()!=candidate(before.read_text()):raise ValueError('Unexpected production delta')
    pins=hashes([SOURCE,before,DATABASE,Path(__file__),Path(__file__).with_name('compile_float_gap_candidate.py')])
    out.mkdir(parents=True,exist_ok=False)
    records=[r for r in json.loads(DATABASE.read_text()) if Path(r['file']).resolve()==SOURCE]
    if len(records)!=1:raise ValueError('Production compile record mismatch')
    cmd=shlex.split(records[0]['command']);cmd[cmd.index('-o')+1]=str(out/'qbs.cpp.o')
    atomic_json(out/'command.json',cmd)
    with (out/'compile.log').open('x') as log:
        subprocess.run(cmd,cwd=records[0]['directory'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    if hashes(map(Path,pins))!=pins:raise ValueError('Compile input drift')
    pins.update(hashes([out/'qbs.cpp.o']))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'result.json',dict(state='PRODUCTION_TU_COMPILE_PASS',
        source_sha256=digest(SOURCE),object_sha256=digest(out/'qbs.cpp.o'),
        scope='Actual installed source, production flags; remaining linked objects unchanged'))


if __name__=='__main__':main()
