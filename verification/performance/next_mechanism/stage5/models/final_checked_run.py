#!/usr/bin/env python3
"""Run an unchanged prepared model with the explicit source-bound checker repair."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
READER = HERE.with_name('prefill_check.py')
READER_SHA = '2d00cd0f6fb7218889fa88e3d8f9ce3c5285867441cf645d3bda237731495267'
WORKER_SHA = '136c906eb33d1edf94b2bae76bed6f9c6897c40ac4e8cca4a2881282431c9859'
OLD_CHECK_SHA = '9dc3f1df4a1b8e6d44dab01b3f5bf465ac79a0bc9b86c46d6b7a67823bef589a'
AUDIT = OUT/'stage5_models_smol_prefill_audit_20261110_02/result.json'
AUDIT_SHA = '0887a6da31d749c4f7cb4d400f3b2b7777d9a7f57c6c25a5f491543baaa61a26'
CASES = {'qwen25_q4kv', 'qwen25_q8kv', 'qwen3_f16', 'gemma_d256'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binding(out, review):
    require(out.parent == OUT and out.name.startswith('stage5_models_execution_final_'), 'Owned model output')
    require(sha(HERE) == review and sha(READER) == READER_SHA and sha(AUDIT) == AUDIT_SHA,
            'Unreviewed checker correction')
    audit = read(AUDIT)
    require(audit['state'] == 'SCOPED_MODEL_SHORT_PREFILL_AUDIT_PASS' and
            audit['original_failure_preserved'] is audit['all_original_pins_match'] is True,
            'Missing successful full-log correction audit')
    original = out/'inputs/run.py'
    require(sha(original) == WORKER_SHA and sha(out/'inputs/check.py') == OLD_CHECK_SHA,
            'Not the frozen final worker/checker')
    base = load(original, 'unchanged_final_model_worker')
    require(base.read(out/'contract.json')['case'] in CASES, 'No Smol retry or extra matrix')
    pins = {str(HERE): review, str(READER): READER_SHA, str(AUDIT): AUDIT_SHA}
    return base, pins


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('service-command', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-worker-sha256', required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--review-prepare-sha256', required=True)
    args = parser.parse_args(); out = args.output.resolve()
    base, pins = binding(out, args.review_worker_sha256)
    if args.action == 'service-command':
        argv = base.service_command(out, args.review_sha256, args.review_prepare_sha256)
        at = argv.index(str(out/'inputs/run.py'))
        argv[at] = str(HERE)
        argv += ['--review-worker-sha256', args.review_worker_sha256]
        print(json.dumps(argv))
        return 0
    require(not (out/'checker-correction.json').exists(), 'Correction worker is one attempt only')
    receipt = dict(schema='source-bound-model-checker-correction-v1', pins=pins,
                   original_worker_sha256=WORKER_SHA, original_checker_sha256=OLD_CHECK_SHA,
                   model_elf_sha256=base.read(out/'prepare.json')['elf_sha256'],
                   original_prepared_inputs_unchanged=True, numerical_checks_relaxed=False)
    path = out/'checker-correction.json'
    with path.open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
    pins[str(path)] = sha(path)
    old_read, old_load = base.read, base.load

    def read_with_correction(path):
        result = old_read(path)
        if Path(path) == out/'source-pins.json':
            base.merge(result, pins)
        return result

    def checked_load(path, name):
        if Path(path) == out/'inputs/check.py':
            base.verify(pins)
            require(sha(path) == OLD_CHECK_SHA, 'Original checker drift')
            return old_load(READER, name)
        return old_load(path, name)

    base.read, base.load = read_with_correction, checked_load
    ok = base.execute(args)
    base.verify(pins)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
