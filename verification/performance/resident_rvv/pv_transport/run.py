#!/usr/bin/env python3
"""Bounded host-VCS private payload protocol gate; no SoC/performance claim."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    here = Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / 'inputs'
    inputs.mkdir()
    pins = {}
    for name in ('resident_payload_fanout.sv', 'tb.sv', 'run.py'):
        source = here / name
        content = source.read_bytes()
        pins[str(source)] = hashlib.sha256(content).hexdigest()
        (inputs / name).write_bytes(content)
        pins[str(inputs / name)] = pins[str(source)]
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    result = {'status': 'FAIL', 'scope': 'private_payload_protocol'}
    try:
        vcs = shutil.which('vcs')
        if not vcs:
            raise RuntimeError('Host VCS unavailable')
        compile_cmd = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                       '-top', 'resident_payload_tb',
                       str(inputs/'resident_payload_fanout.sv'), str(inputs/'tb.sv'),
                       '-o', str(out/'simv')]
        result['compile_command'] = compile_cmd
        with (out/'compile.log').open('w') as log:
            subprocess.run(compile_cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        with (out/'sim.log').open('w') as log:
            subprocess.run([str(out/'simv')], cwd=out, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=30)
        log = (out/'sim.log').read_text()
        matches = re.findall(r'^PAYLOAD_PASS (.*)$', log, re.M)
        if len(matches) != 1 or re.search(r'(Fatal|Error|Assertion failed)', log):
            raise RuntimeError('Missing clean protocol completion')
        counts = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', matches[0]))
        if counts['beats'] != counts['delivered'] + counts['cancelled']:
            raise RuntimeError('Unbalanced payload counts')
        if not all(digest(Path(p)) == expected for p, expected in pins.items()):
            raise RuntimeError('Input drift')
        result.update(status='PASS', counts=counts, source_pins_match=True,
                      image_sha256=digest(out/'simv'), log_sha256=digest(out/'sim.log'))
    except Exception as exc:
        result['error'] = repr(exc)
    (out/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return result['status'] == 'PASS'


if __name__ == '__main__':
    sys.exit(0 if run(Path(sys.argv[1]).resolve()) else 1)
