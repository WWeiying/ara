#!/usr/bin/env python3
"""Audit a preserved model run with two proven UART/TCG framing collisions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
RUN = OUT / 'enablement_model_m4_20261111_01'
LOG_SHA = '98f0eac6601bf45a6e812d04e1f9ddbf1b789f02ad4f25c074b25416a2c28a24'
PREFIX = ('Explain how a vector processor uses parallel arithmetic and memory bandwidth '
          'to perform quantized matrix multiplication when generating text with a language model. To')
TRACE = re.compile(r'Trace 0: ((?:0x)?[0-9a-f]+) \[[0-9a-f]+/([0-9a-f]+)/[0-9a-f]+/[0-9a-f]+\].*')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_checker(path):
    spec = importlib.util.spec_from_file_location('frozen_model_m4_checker', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(lines, symbols, repairs):
    """Split only the proven prompt/token prefix; retain every original Trace."""
    for line_number, raw in enumerate(lines, 1):
        text = raw.rstrip('\r\n')
        marker = text.find('Trace 0:')
        if marker > 0:
            prefix, trace = text[:marker], text[marker:]
            matched = TRACE.fullmatch(trace)
            require(prefix == PREFIX and matched is not None and
                    int(matched[2], 16) == symbols['qbs'], 'Unrecognized trace framing collision')
            repairs.append(dict(line=line_number, raw_line_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                                prefix=prefix, trace=trace))
            yield prefix + '\n'
            yield trace + '\n'
        else:
            yield raw


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and
            out.name.startswith('enablement_model_m4_audit_') and not out.exists(), 'Fresh signoff output required')
    out.mkdir()
    result = dict(state='FAIL', original_worker_state='FAIL', model_rerun=False,
                  performance_measured=False, fpga_acceptance=False, instruction_retirement_claim=False)
    try:
        original = read(RUN / 'result.json')
        require(original['state'] == 'FAIL' and
                original['error'] == "ValueError('Native QBS entries differ from summary')" and
                original['guest_log_sha256'] == LOG_SHA and sha(RUN / 'guest.log') == LOG_SHA,
                'Unexpected original failure or log identity')
        pins = read(RUN / 'source-pins.json')
        require(sha(RUN / 'source-pins.json') == original['source_pins_sha256'], 'Original pins drift')
        require(all(sha(path) == digest for path, digest in pins.items()), 'Original source/image drift')
        checker_path = RUN / 'inputs/model_m4_run.py'
        require(pins[str(checker_path)] == sha(checker_path), 'Unpinned original checker')
        checker = load_checker(checker_path)
        repairs = []
        with (RUN / 'guest.log').open() as stream:
            proof = checker.check(records(stream, read(RUN / 'symbols.json'), repairs), read(RUN / 'symbols.json'))
        require([r['line'] for r in repairs] == [147130, 328941], 'Not the two proven collisions')
        # Old negative controls still reject after framing repair.
        test = HERE / 'model_m4_audit_v2_test.py'
        with (out / 'tests.log').open('xb') as log:
            run = subprocess.run(['/usr/bin/python3.11', '-B', str(test)], stdout=log,
                                 stderr=subprocess.STDOUT, timeout=60)
        require(run.returncode == 0, 'Framing/strict-checker regression failed')
        require(sha(RUN / 'guest.log') == LOG_SHA and
                all(sha(path) == digest for path, digest in pins.items()), 'Post-audit input drift')
        result.update(state='MODEL_M4_FRAMING_AUDIT_PASS', proof=proof, repairs=repairs,
                      original_result_sha256=sha(RUN / 'result.json'), guest_log_sha256=LOG_SHA,
                      source_pins_sha256=original['source_pins_sha256'], input_identity_match=True,
                      checker_sha256=sha(checker_path), audit_source_sha256=sha(__file__),
                      test_source_sha256=sha(test), tests_log_sha256=sha(out / 'tests.log'))
    except Exception as exc:
        result['error'] = repr(exc)
    with (out / 'result.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result, sort_keys=True))
    return int(result['state'] != 'MODEL_M4_FRAMING_AUDIT_PASS')


if __name__ == '__main__':
    raise SystemExit(main())
