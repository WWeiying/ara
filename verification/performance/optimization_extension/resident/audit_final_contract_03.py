#!/usr/bin/env python3
"""Final comment consistency and GNU object identity audit; no test execution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = OUT / 'extension_resident_deployment_20261111_02'
PLATFORM = ROOT / 'software/llama/platform'
BASE_PINS = '05712b9bc709b5e50073a81b5f14017b90f1ea4b33640ebca92b508e330836f1'
BASE_REPORT = '97b7fbef5cec94f61e26739c41e6afd8babb5bc554d41bfea1f92604e7367e16'
BASE_COMMANDS = '89a81abddecb36a3ece67c9cdc92def01fa633ecc56d0b64f7620b5e7f9a3fe9'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.absolute()
    require(out == out.resolve() and out.parent == OUT and not out.exists() and
            out.name == 'extension_resident_deployment_20261111_03', 'Fresh final 03 output required')
    for name, expected in (('source-pins.json', BASE_PINS), ('result.json', BASE_REPORT),
                           ('commands.json', BASE_COMMANDS)):
        require(sha(BASE / name) == expected, '02 receipt drift: ' + name)
    changed_docs = {str(PLATFORM / name) for name in ('resident_deployment.h', 'DEPLOYMENT.md')}
    verified = 0
    for inventory in ('source-pins.json', 'artifact-pins.json'):
        for name, digest in json.loads((BASE / inventory).read_text()).items():
            if name in changed_docs:
                continue
            require(sha(name) == digest, '02 input/artifact drift outside authorized live docs: ' + name)
            verified += 1
    out.mkdir()
    inputs = out / 'inputs/platform'
    inputs.mkdir(parents=True)
    pins, commands = {}, []

    def pin(path):
        path = Path(path).resolve()
        digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, '03 input drift: ' + str(path))
        pins[str(path)] = digest

    def run(label, argv):
        argv = list(map(str, argv))
        pin(shutil.which(argv[0]) or argv[0])
        for name, digest in pins.items():
            require(sha(name) == digest, 'Frozen input drift: ' + name)
        done = subprocess.run(argv, cwd=out, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                              env=dict(PATH='/usr/bin:/bin', LC_ALL='C', HOME='/home/wangwy'))
        with (out / (label + '.log')).open('xb') as stream:
            stream.write(done.stdout + done.stderr)
        commands.append(dict(label=label, argv=argv, returncode=done.returncode))
        require(done.returncode == 0, 'Audit command failed: ' + label)
        return done.stdout

    pin(__file__)
    for name in ('source-pins.json', 'artifact-pins.json', 'result.json', 'commands.json'):
        pin(BASE / name)
    for name in ('resident_deployment.h', 'resident_provider.c', 'DEPLOYMENT.md'):
        source = PLATFORM / name
        pin(source)
        dest = inputs / name
        with dest.open('xb') as stream:
            stream.write(source.read_bytes())
        require(sha(dest) == sha(source), 'Snapshot drift')
        pin(dest)
    require(sha(inputs / 'resident_provider.c') == sha(BASE / 'inputs/platform/resident_provider.c'),
            'Runtime implementation changed')
    header = (inputs / 'resident_deployment.h').read_text()
    observe = header.split('void *authority;', 1)[1].split('int (*observe)', 1)[0]
    doc = (inputs / 'DEPLOYMENT.md').read_text()
    require('no syscall' not in observe.lower() and 'reviewed kernel' in observe and
            'nonzero VSTART' in observe and 'do not read/write/probe' in observe and
            'on both allow and deny' in observe and 'unaudited libc/syscall' in observe,
            'Observe contract inconsistent')
    require('observe/acquire/release' in doc and 'no user CSR reads, writes or probes' in doc and
            'including nonzero VSTART' in doc and 'Final 03 also supersedes' in doc and
            'Misuse,' in doc and 'permission to retry partially written output' in doc,
            'Deployment contract inconsistent')

    baseline_commands = json.loads((BASE / 'commands.json').read_text())
    identities = {}
    for mode in ('gnu-default', 'gnu-linked'):
        original = next(c['argv'] for c in baseline_commands if c['label'] == mode + '-compile')
        flags = original[1:original.index('-c')]
        source = inputs / 'resident_provider.c'
        obj = out / (mode + '.o')
        pin(original[0])
        run(mode + '-compile', [original[0], *flags, '-c', source, '-o', obj])
        pin(obj)
        pin(BASE / (mode + '.o'))
        require(sha(obj) == sha(BASE / (mode + '.o')), 'GNU object changed: ' + mode)
        before = run(mode + '-02-preprocess', [original[0], *flags, '-E', '-P', original[-3]])
        after = run(mode + '-03-preprocess', [original[0], *flags, '-E', '-P', source])
        require(before == after, 'Non-comment token change: ' + mode)
        identities[mode] = sha(obj)
    for name, digest in pins.items():
        require(sha(name) == digest, 'Final input drift: ' + name)
    save(out / 'source-pins.json', pins)
    save(out / 'commands.json', commands)
    report = dict(state='FINAL03_COMMENT_AND_OBJECT_IDENTITY_CHECKED',
                  documentation_only=True, abi_changed=False, runtime_source_changed=False,
                  preprocessed_tokens_equal_02=True, gnu_objects_identical_02=identities,
                  baseline_records_rechecked=verified, inherited_behavior_receipt=str(BASE / 'result.json'),
                  inherited_behavior_receipt_sha256=BASE_REPORT,
                  inherited_scope='02 host GNU/UBSan/bundle contract tests and scalar GNU audit only',
                  host_checks_executed_03=0, inherited_host_checks_per_mode_02=918,
                  kernel_syscall_tested=False, board_acceptance=False, driver_implemented=False,
                  default_denial_unchanged=True, original_inputs_reports_modified=False,
                  supersedes='Earlier blanket observe no-syscall/no-OS comments, including release erratum',
                  source_pins_sha256=sha(out / 'source-pins.json'))
    save(out / 'result.json', report)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
