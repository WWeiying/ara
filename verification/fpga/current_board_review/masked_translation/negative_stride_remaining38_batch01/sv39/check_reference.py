#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import checker

if __name__ == '__main__':
    a=argparse.ArgumentParser()
    a.add_argument('group',type=Path);a.add_argument('reference',type=Path)
    p=a.parse_args()
    symbols=json.loads((p.group/'spike.symbols.json').read_text())
    cases=json.loads((p.group/'cases.json').read_text())
    result=checker.analyze(p.reference/'spike.trace',symbols,checker.disassemble((p.group/'spike.dis').read_text()),
                           p.group/'spike.elf',[c['parameters'] for c in cases],8000000)
    with (p.reference/'status.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('status','case_count','scalar_checks','firmware_records_through_htif')}))
