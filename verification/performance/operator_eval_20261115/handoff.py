#!/usr/bin/env python3
"""Bind a freshly built native QBS/AKV/RVV handoff smoke to the central runner."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare','check'))
    p.add_argument('--build', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--log', type=Path)
    a = p.parse_args()
    if a.action == 'check':
        text = a.log.read_text()
        marker = 'QBS/AKV handoff smoke: PASS traps=0'
        if sum(line.strip()==marker for line in text.splitlines()) != 1:
            raise ValueError('No unique enabled zero-trap handoff PASS')
        if re.search(r'(?im)\bSKIP\b|\bdisabled\b|\bFAIL(?:ED)?\b', text):
            raise ValueError('Disabled, skipped or failed handoff')
        a.output.write_text(json.dumps(dict(state='PASS', scope='native QBS/AKV/RVV handoff',
                                            performance_measured=False), indent=2)+'\n')
        return
    a.output.mkdir()
    b = json.loads((a.build / 'build.json').read_text())
    if b['state'] != 'BUILT_NOT_EXECUTED' or not b['post_pins_match']:
        raise ValueError('No fresh smoke build')
    program = b['programs']['qbs_akv_handoff_smoke']
    pins = json.loads((a.build / 'source-pins.json').read_text())
    pins[str(a.build / 'build.json')] = sha(a.build / 'build.json')
    checker = a.output / 'handoff.py'; checker.write_bytes(Path(__file__).read_bytes())
    pins[str(checker)] = sha(checker)
    for name, value in pins.items():
        if sha(name) != value:
            raise ValueError('Build input drift ' + name)
    (a.output / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    case = dict(id='qbs_akv_rvv_handoff', category='resource_coexistence', elf=program['elf'],
        elf_sha256=program['elf_sha256'], source_pins=str(a.output / 'source-pins.json'),
        timeout_seconds=1800, checker=['/usr/bin/python3','-B',str(checker),'check',
        '--log','{log}','--output','{result}'],plusargs=['+QBS_PERF','+AKV_PERF','+AKV_SUMMARY'])
    (a.output / 'cases.json').write_text(json.dumps(dict(cases=[case]), indent=2)+'\n')


if __name__ == '__main__':
    main()
