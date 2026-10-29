#!/usr/bin/env python3
"""Run the unchanged ordinary workload using a separately reviewed SoC image."""
import argparse
import importlib.util
from pathlib import Path
import signal
import subprocess
import hashlib
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
path = ROOT/'verification/akv/canonical_promotion/ordinary_runtime/run.py'
spec = importlib.util.spec_from_file_location('retire_ordinary_runtime', path)
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)


def archive_baseline_integer():
    relative = 'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv'
    expected = '576304613df34547c7d80b04739a4a0164febd719cfcbc463d6465db6d966978'
    data = subprocess.check_output(['git', 'show', 'a38656a06^:' + relative],
                                   cwd=ROOT, timeout=30)
    runtime.s.require(hashlib.sha256(data).hexdigest() == expected, 'Historical RTL differs')
    directory = ROOT/'verification/out/qbs-retire-historical-integer-20261029-01'
    directory.mkdir(exist_ok=True)
    target = directory/'qbs_profile_engine_int.sv'
    if not target.exists():
        with target.open('xb') as stream:
            stream.write(data)
    runtime.s.require(runtime.s.digest(target) == expected, 'Historical archive drift')
    parent = runtime.baseline.Consumer

    class Consumer(parent):
        def translate(self, pins):
            translated = super().translate(pins)
            name = str(ROOT/relative)
            if name in translated:
                runtime.s.require(translated[name] == expected, 'Unexpected historical revision')
                del translated[name]
                translated[str(target)] = expected
            return translated

    runtime.baseline.Consumer = Consumer


def checked_review(directory, expected_sha):
    s = runtime.s
    directory = Path(directory).resolve(strict=True)
    receipt = directory/'reviewed-admission.json'
    s.require(s.digest(receipt) == expected_sha, 'Reviewed receipt identity changed')
    report = s.read_json(receipt)
    s.require(report.get('state') == 'ORDER_REVIEWED_SOC_BUILT_NOT_EXECUTED' and
              report.get('original_state') == 'FAIL' and report.get('post_pins_match') is True
              and report.get('execution') == 'NOT_RUN' and
              report.get('source_root') == str(ROOT), 'Wrong admission type')
    source_file = directory/'source-pins.json'
    s.require(s.digest(source_file) == report['source_pins_sha256'], 'Source receipt drift')
    pins = s.read_json(source_file)
    s.merge_pins(pins, report['artifact_pins'])
    s.merge_pins(pins, s.hashes([receipt, Path(__file__)]))
    s.verify_pins(pins)
    simv = directory/'sim/simv'
    s.require(report['simv'] == str(simv) and
              s.hashes(s.image_files(simv)) == report['image_pins'], 'Image inventory drift')
    runtime.verify_current(report, report['image_pins'], pins)
    return report, pins, report['image_pins']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, required=True)
    parser.add_argument('--expected-soc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=9000)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    # Private module instance only; original source/checkers are unchanged.
    runtime.checked_soc = checked_review
    archive_baseline_integer()
    runtime.ACCEPTANCE = 'ORDER_REVIEWED_ORDINARY_SAME_ELF_PASS'
    result = runtime.run(args)
    sys.exit(0 if result['state'] in ('PASS', 'CANONICAL_ORDINARY_PREFLIGHT_NOT_RUN') else 1)
