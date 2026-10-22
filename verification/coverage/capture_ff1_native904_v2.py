#!/usr/bin/env python3
"""Freeze the corrected fail-fast Tcl fixture gate without editing the first prepare."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_ff1_native904 as core


def prepare(output):
    core.prepare(output)
    config = json.loads((output / 'config.json').read_bytes())
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_capture_ff1_native904_v2.py')):
        config['pins'][str(path)] = core.sha(path)
    config['test_context_contract'] = 'Real Tcl proc-source/foreign working directory; entire script catch+exit on any error'
    core.check(config)
    core.write(output / 'config.json', config)
    seal = core.sha(output / 'config.json')
    core.write(output / 'status.json', dict(status='PREPARED_NO_DVE', config_sha256=seal, application_approval=False))
    print('FF1_V2_PREPARED seal=' + seal, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'capture', 'first', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--result-seal')
    args = parser.parse_args()
    output = args.output.absolute()
    core.require(output.parent == core.prep.OUT and not output.is_symlink(), 'Unsafe output')
    if args.command == 'prepare':
        prepare(output)
    elif args.command == 'capture':
        core.capture(output, args.seal)
    elif args.command == 'first':
        print('FF1_FIRST_EXACT ' + str(len(core.bind_native((output / 'first.el').read_bytes(), core.read_config(output, args.seal)))))
    else:
        core.require(core.sha(output / 'capture-result.json') == args.result_seal, 'External result seal differs')
        saved = json.loads((output / 'capture-result.json').read_bytes())
        core.require(saved['config_sha256'] == args.seal, 'Result/config differs')
        for path, expected in saved['files'].items():
            core.require(core.sha(path) == expected, 'Captured artifact differs')
        fresh = core.verify(output, core.read_config(output, args.seal))
        core.require(all(saved.get(k) == v for k, v in fresh.items() if k != 'files') and
                     all(saved['files'].get(k) == v for k, v in fresh['files'].items()), 'Regeneration differs')
        print('FF1_NATIVE904_V2_REVERIFIED')
