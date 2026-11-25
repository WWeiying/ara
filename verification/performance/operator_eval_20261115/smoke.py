#!/usr/bin/env python3
"""Reuse a pinned ISA vadd program to qualify the new image, not performance."""
import argparse
import hashlib
import json
from pathlib import Path
import re

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE = OUT / 'shared_fma_tagpack_acceptance_20261105_02/soc'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, v):
    p.write_text(json.dumps(v, indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare','check'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--log', type=Path)
    a = p.parse_args()
    if a.action == 'check':
        text = a.log.read_text()
        if not re.search(r'^PASSED: .*[/\\]vadd\.c!$', text, re.M):
            raise ValueError('No numeric vadd PASS')
        save(a.output, dict(state='PASS', performance_measured=False,
                            scope='Pinned ISA vadd on current RTL; not operator throughput'))
        return
    out = a.output.resolve()
    if out.parent != OUT or not out.name.startswith('operator_smoke_build_'):
        raise ValueError('Wrong output scope')
    out.mkdir()
    original = BASE / 'inputs/rv64uv-ara-vadd'
    inherited = json.loads((BASE / 'source-pins.json').read_text())
    if inherited[str(original)] != sha(original):
        raise ValueError('ISA executable identity changed')
    target = out / 'smoke.elf'; target.write_bytes(original.read_bytes())
    checker = out / 'smoke.py'; checker.write_bytes(Path(__file__).read_bytes())
    pins = {str(f):sha(f) for f in (original, BASE/'source-pins.json', target, checker)}
    save(out/'source-pins.json', pins)
    save(out/'cases.json', dict(cases=[dict(id='rvv_smoke', category='image_qualification',
        elf=str(target), elf_sha256=sha(target), source_pins=str(out/'source-pins.json'),
        timeout_seconds=1800, checker=['/usr/bin/python3','-B',str(checker),'check',
        '--log','{log}','--output','{result}'])]))


if __name__ == '__main__':
    main()
