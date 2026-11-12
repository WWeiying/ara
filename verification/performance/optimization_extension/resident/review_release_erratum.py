#!/usr/bin/env python3
"""Record an additive documentation correction; do not execute original tests."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
ORIGINAL = OUT / 'extension_resident_deployment_20261111_01'
DOC = ROOT / 'software/llama/platform/RELEASE_CONTRACT_ERRATUM_20261111.md'
PIN_SHA = '3075a080c06ea241e9988fed481b6bfa07420a6967b8859a216beef3def7085a'
RESULT_SHA = '6ed127f74ed095f36df5f90f5eb4d0a85d7f3009515eaa0bb072a649736f1e34'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out == out.resolve() and out.parent == OUT and not out.exists() and
            out.name.startswith('extension_resident_release_erratum_'), 'Fresh direct signoff output required')
    require(sha(ORIGINAL / 'source-pins.json') == PIN_SHA, 'Original inventory drift')
    require(sha(ORIGINAL / 'result.json') == RESULT_SHA, 'Original report drift')
    count = 0
    for inventory in ('source-pins.json', 'artifact-pins.json'):
        for name, digest in json.loads((ORIGINAL / inventory).read_text()).items():
            require(sha(name) == digest, 'Original sealed input/artifact drift: ' + name)
            count += 1
    pins = {str(p.resolve()): sha(p) for p in (DOC, Path(__file__),
            ORIGINAL / 'source-pins.json', ORIGINAL / 'artifact-pins.json', ORIGINAL / 'result.json')}
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    for source in (DOC, Path(__file__)):
        dest = inputs / source.name
        with dest.open('xb') as stream:
            stream.write(source.read_bytes())
        require(sha(dest) == pins[str(source.resolve())], 'Successor copy drift')
        pins[str(dest)] = sha(dest)
    save(out / 'source-pins.json', pins)
    report = dict(state='STATIC_RELEASE_CONTRACT_ERRATUM_RECORDED',
                  scope='Documentation-only successor; no ABI or runtime code change',
                  original_records_rechecked=count, original_pins_sha256=PIN_SHA,
                  original_report_sha256=RESULT_SHA, original_evidence_modified=False,
                  source_pins_sha256=sha(out / 'source-pins.json'),
                  original_tests_rerun=False, kernel_syscall_tested=False,
                  platform_authorization_changed=False, board_acceptance=False,
                  kernel_rtl_fpga_changes=False,
                  correction='Supported release syscall and exact scalar CSR restoration are not forbidden by v1 ABI')
    save(out / 'result.json', report)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
