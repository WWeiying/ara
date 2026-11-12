#!/usr/bin/env python3
"""Successor: fix both names of the legacy-package comparison copy."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('capability_successor_v2', HERE / 'capability_run_v2.py')
    v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v2)
    c = v2.load()
    previous = c.OUT / 'optimization_extension_capability_20261111_03'
    require_log = previous / 'package_qbs0/compile.log'
    c.require(c.read(previous / 'result.json')['state'] == 'FAIL' and
              'Error-[SVBENM]' in require_log.read_text(), 'Expected original package-shim failure')
    old_derive = v2.derive

    def derive(text):
        text = old_derive(text)
        before = "legacy.replace('package qbs_pkg;', 'package legacy_qbs_pkg;')"
        after = before + ".replace('endpackage : qbs_pkg', 'endpackage : legacy_qbs_pkg')"
        c.require(text.count(before) == 1, 'Unrecognized legacy-package derivation')
        text = text.replace(before, after)
        compile(text, 'capability_worker_v2.py', 'exec')
        return text

    # Prepare only; the final successor closure is reviewed before any service.
    v2.derive = derive
    old_argv = sys.argv
    try:
        sys.argv = [str(HERE / 'capability_run_v2.py'), '--output', str(args.output)]
        v2.main()
    finally:
        sys.argv = old_argv
    out = c.output(args.output)
    pins = c.read(out / 'source-pins.json')
    c.copy(pins, HERE / 'capability_run_v3.py', out / 'inputs/capability_run_v3.py')
    for source in (previous / 'result.json', previous / 'source-pins.json', require_log):
        c.pin(pins, source)
    plan = c.read(out / 'plan.json')
    plan['supersedes_package_shim_failure'] = str(previous)
    plan['derivation']['changes'].append('Rename matching legacy endpackage label in comparison-only copy')
    c.save(out / 'plan.json', plan)
    pins[str(out / 'plan.json')] = c.sha(out / 'plan.json')
    c.verify(pins)
    c.save(out / 'source-pins.json', pins)
    review = c.sha(out / 'source-pins.json')
    c.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review))
    command = c.service(out, review)
    command[command.index(str(out / 'inputs/capability_run.py'))] = str(out / 'inputs/capability_worker_v2.py')
    c.save(out / 'launch-command.json', command)
    print(dict(output=str(out), review_sha256=review, command=command), flush=True)
    if args.launch:
        subprocess.run(command, check=True)


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    main()
