#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import checker02 as checker

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('group',type=Path);p.add_argument('raw',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    symbols=json.loads((a.group/'spike.symbols.json').read_text())
    cases=json.loads((a.group/'cases.json').read_text())
    result=checker.analyze(a.raw,symbols,checker.disassemble((a.group/'spike.dis').read_text()),a.group/'spike.elf',[c['parameters'] for c in cases],8000000)
    with (a.out/'status.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('status','case_count','scalar_checks','firmware_records_through_htif')}))
