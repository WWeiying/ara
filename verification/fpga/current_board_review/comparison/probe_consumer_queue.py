#!/usr/bin/env python3
"""Two fixed discriminators, reusing consumer03 without any RTL/build change."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'integration'))
from run import environment


def main():
    image = HERE / 'consumer_after03'
    out = HERE / 'consumer_queue_probe01'
    out.mkdir(exist_ok=False)
    pins = json.loads((image / 'pins.json').read_text())
    for name, digest in pins.items():
        if hashlib.sha256((image / name).read_bytes()).hexdigest() != digest:
            raise ValueError('snapshot drift')
    records = []
    for name, options in (
        ('active_unstalled', ['+VL=273', '+NV=261', '+PATTERN=1']),
        ('quiet_stalled', ['+VL=273', '+NV=-1', '+PATTERN=1', '+STALLS=1'])):
        command = [str(image / 'simv'), '-no_save', *options]
        with (out / (name + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=out, env=environment(), stdout=log,
                                    stderr=subprocess.STDOUT, timeout=30)
        lines = (out / (name + '.log')).read_text().splitlines()
        passed = result.returncode == 0 and any(x.startswith('CONSUMER_PASS ') for x in lines)
        record = dict(name=name, command=command, status='PASS' if passed else 'FAIL',
                      returncode=result.returncode,
                      evidence=[x for x in lines if x.startswith(('WRITE ', 'CONSUMER_PASS ', 'wrong write footprint'))])
        records.append(record)
        (out / 'status.json').write_text(json.dumps(dict(
            image=str(image), simv_sha256=hashlib.sha256((image / 'simv').read_bytes()).hexdigest(),
            cases=records), indent=2) + '\n')
        print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
