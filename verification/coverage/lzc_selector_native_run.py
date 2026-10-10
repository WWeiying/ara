#!/usr/bin/env python3
"""Host-only execution of approved independent LZC calibration plans."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / 'verification/out'
PREPARED = OUT / 'lzc_selector_native_prepare-705-20261006-02'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, obj):
    with path.open('x') as stream:
        json.dump(obj, stream, indent=2)
        stream.write('\n')


def check_pins(pins):
    for filename, expected in pins.items():
        require(sha(filename) == expected, 'Pin drift: ' + filename)


def execute(argv, cwd, log):
    begin = time.monotonic()
    with log.open('x') as stream:
        result = subprocess.run(argv, cwd=cwd, env=os.environ.copy(), stdout=stream,
                                stderr=subprocess.STDOUT, timeout=130)
    return dict(argv=argv, cwd=str(cwd), log=str(log), returncode=result.returncode,
                elapsed_seconds=round(time.monotonic() - begin, 3), log_sha256=sha(log))


def calibration(output):
    require(output.parent == OUT and not output.exists(), 'Fresh direct output required')
    binding = json.loads((PREPARED / 'binding.json').read_bytes())
    check_pins(binding['pins'])
    plan = json.loads((PREPARED / 'experiments.json').read_bytes())
    require(len(plan['experiments']) == 8, 'Eight prepared experiments required')
    output.mkdir()
    pins = dict(binding['pins'])
    for path in (PREPARED / 'binding.json', PREPARED / 'experiments.json', Path(__file__).resolve()):
        pins[str(path)] = sha(path)
    for row in plan['experiments']:
        source = Path(row['cwd']) / (row['top'] + '.sv')
        pins[str(source)] = sha(source)
    save(output / 'pre-execution-pins.json', pins)
    results = []
    try:
        for row in plan['experiments']:
            case = Path(row['cwd'])
            require(case.parent == PREPARED and case.name == row['top'], 'Not prepared standalone case')
            require(not (case / 'simv').exists(), 'Calibration image already exists; do not overwrite')
            check_pins(pins)
            record = dict(top=row['top'], width=row['width'], selector=row['selector'], parity=row['parity'])
            record['compile'] = execute(row['compile_argv'], case, case / 'compile.log')
            results.append(record)
            require(record['compile']['returncode'] == 0, 'Standalone VCS compile failed: ' + row['top'])
            record['simulation'] = execute(row['run_argv'], case, case / 'simulation.log')
            require(record['simulation']['returncode'] == 0, 'Standalone VCS run failed: ' + row['top'])
            width = row['width']
            index = row['parity'] if row['selector'] else (1 << ((width - 1).bit_length() - 1)) + row['parity']
            marker = (f"LZC_SELECTOR_NATIVE_OBSERVED width={width} selector={row['selector']} "
                      f"index={index} parity={row['parity']}")
            log = (case / 'simulation.log').read_text()
            require(log.count(marker) == 1 and 'LZC_SELECTOR_NATIVE_SEMANTIC_FAILURE' not in log,
                    'Standalone semantic observation failed')
            record.update(index=index, observation=marker, selfcheck='PASS', simv_sha256=sha(case / 'simv'))
            save(output / (row['top'] + '.json'), record)
            print(marker, flush=True)
        check_pins(pins)
        save(output / 'calibration.json', dict(status='STANDALONE_SELFCHECK_PASS_8',
             results=results, processor_admission=False, old_image_exclusions=False,
             native_semantics_qualified=False))
    except Exception as error:
        save(output / 'calibration-failure.json', dict(status='FAILED_RECORDED_NOT_REPAIRED',
             error=str(error), results=results, processor_admission=False, old_image_exclusions=False))
        raise


def bind(evidence):
    record = json.loads((evidence / 'calibration.json').read_bytes())
    require(record['status'] == 'STANDALONE_SELFCHECK_PASS_8', 'Real selfchecks required')
    results = []
    for row in record['results']:
        case = PREPARED / row['top']
        capture = case / 'lzc_selector_native_capture-01'
        argv = [sys.executable, '-B', str(HERE / 'lzc_selector_native_prepare.py'), 'bind-case',
                '--case', str(case), '--output', str(capture)]
        run = execute(argv, ROOT, evidence / (row['top'] + '-bind.log'))
        results.append(run)
        require(run['returncode'] == 0, 'Bind-case failed; retain evidence')
    save(evidence / 'bind.json', dict(status='BOUND_STANDALONE_DVE_PLANS_PENDING_REVIEW', results=results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('calibration', 'bind'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.stage == 'calibration':
        calibration(args.output.absolute())
    else:
        bind(args.output.absolute())


if __name__ == '__main__':
    main()
