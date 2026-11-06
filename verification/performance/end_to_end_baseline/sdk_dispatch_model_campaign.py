#!/usr/bin/env python3
"""Own SDK model execution and its independent replay in one background service."""
import argparse
from pathlib import Path
import subprocess
import sys

from audit import digest, require, verify_pins
from build_trace_context_library import write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'audit', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    files = ('sdk_dispatch_model_campaign.py', 'run_sdk_dispatch_model.py', 'collect_sdk_dispatch_model.py',
             'sdk_dispatch_model.py', 'test_sdk_dispatch_model.py', 'audit.py', 'trace_context_model.py',
             'build_sdk_dispatch_library.py', 'build_trace_context_library.py')
    pins = {str(here / name): digest(here / name) for name in files}
    write(out / 'source-pins.json', pins)
    result = dict(state='PREPARING', performance_measured=False)
    try:
        stages = (('model', [sys.executable, '-B', here / 'run_sdk_dispatch_model.py', '--output', args.run, '--execute-reviewed']),
                  ('audit', [sys.executable, '-B', here / 'collect_sdk_dispatch_model.py', '--run', args.run, '--output', args.audit]))
        for stage, command in stages:
            verify_pins(pins)
            result['state'] = stage.upper()
            write(out / 'result.json', result)
            with (out / (stage + '.log')).open('xb') as stream:
                child = subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT, timeout=9000)
            require(child.returncode == 0, stage + ' failed')
            verify_pins(pins)
        require(__import__('json').loads((args.audit / 'result.json').read_text())['state'] ==
                'SDK_DISPATCH_QWEN3_MODEL_PAIR_REAUDITED', 'Independent audit missing')
        result.update(state='PASS', run=str(args.run), audit=str(args.audit),
                      audit_result_sha256=digest(args.audit / 'result.json'), source_pins_sha256=digest(out / 'source-pins.json'))
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out / 'result.json', result)


if __name__ == '__main__':
    main()
