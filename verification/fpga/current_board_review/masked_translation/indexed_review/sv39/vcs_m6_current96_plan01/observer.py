#!/usr/bin/env python3
"""One process/group; unchanged NF7 Checker, no reference execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import csv_oracle


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['pins','check'])
    p.add_argument('--group',type=int);p.add_argument('--csv',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.mode=='pins':
        pins={}
        for m in list(sys.modules.values()):
            f=getattr(m,'__file__',None)
            if f and Path(f).is_file() and str(Path(f).resolve()).startswith('/home/wangwy/'):
                pins[str(Path(f).resolve())]=hashlib.sha256(Path(f).read_bytes()).hexdigest()
        print(json.dumps(pins,sort_keys=True));return 0
    if a.group not in range(24) or not a.csv or not a.out or a.out.exists():
        raise ValueError('Exact group / fresh result required')
    old=HERE.parent/'vcs_plan06';rd=lambda x:json.loads(x.read_text())
    source=Path(rd(old/'programs/programs.json')['programs'][f'nf7_g{a.group:02d}']['path']).parent
    report=csv_oracle.analyze(a.csv,rd(source/'soc.symbols.json'),rd(source/'cases.json'),
        rd(source/'status.json'),rd(old/f'ledgers/g{a.group:02d}.json'))
    with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(report['status']);return int(report['status']!='NF7_CSV_ORACLE_PASS')


if __name__=='__main__':raise SystemExit(main())
