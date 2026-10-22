"""Readonly sealed01 successor: exactly one post-qualification stdout JSON line."""
import argparse
import inspect
import json
from pathlib import Path
import hashlib

import verify_trusted_ip797_readonly as old

HERE = Path(__file__).resolve().parent
OLD_SHA = 'a3ab0c2497cc4225f04781d03cb5ac1b050e81ae5ee611cdc2d1db2c106e1072'
OLD_MANIFEST = old.s.OUT / 'trusted-ip797-readonly-parent-20261008-01/manifest.json'
OLD_MANIFEST_SHA = 'fe0f2fb17ad705db9016ba0de74b12ed30d44393789eb1535240231163aeb7f5'
QUAL_SHA = 'd7b929c065495868e6dc4656f8c575168e8b19530acda570b5a9bc1c691c91fc'
SCHEMA = 'TRUSTED797_SEALED01_READONLY_SUPPLEMENT_V2_EXACT_STDOUT_TAIL'
need = old.need


def stdout_tail(data, pinned_sha, qualification):
    final = dict(status=qualification['status'],
                 metrics=qualification['reports']['applied']['ara_tb.dut.i_ara_soc.i_system'])
    tail = (json.dumps(final) + '\n').encode('utf-8')
    need(data.endswith(tail), 'Only exact final status/metrics JSON newline may follow pinned stdout')
    prefix = data[:-len(tail)]
    need(prefix.endswith(b'\n') and hashlib.sha256(prefix).hexdigest() == pinned_sha,
         'Original stdout pinned prefix differs')
    need(data.splitlines().count(tail[:-1]) == 1, 'Exactly one known final JSON line')
    return dict(path=str(old.OUT / 'service-stdout.log'), original_pinned_prefix_sha256=pinned_sha,
                prefix_bytes=len(prefix), appended_bytes=len(tail), appended_json=final,
                appended_sha256=hashlib.sha256(tail).hexdigest(),
                complete_stdout_sha256=hashlib.sha256(data).hexdigest())


def checked_output_pins(qualification, output):
    target = output / 'service-stdout.log'
    need(str(target) in qualification['output_pins'], 'Original stdout pin required')
    result = {}
    for path, sha in qualification['output_pins'].items():
        need(Path(path).resolve().is_relative_to(output.resolve()), 'Native output outside report')
        if path == str(target):
            audit = stdout_tail(target.read_bytes(), sha, qualification)
            result[path] = audit['complete_stdout_sha256']
        else:
            need(old.digest(path) == sha, 'Exact other native output pin: ' + path)
            result[path] = sha
    return result


def context():
    need(old.digest(Path(old.__file__).resolve()) == OLD_SHA, 'Frozen original readonly helper')
    source = inspect.getsource(old.verify)
    replacements = {
        "manifest['schema'] == 'TRUSTED797_SEALED01_READONLY_SUPPLEMENT_V1'": "manifest['schema'] == SCHEMA",
        "qualification_sha = digest(qp)": "qualification_sha = QUAL_SHA",
        "for path, sha in q['output_pins'].items():\n        need(Path(path).resolve().is_relative_to(OUT.resolve()) and digest(path) == sha, 'Native output pin: ' + path)":
            "checked = checked_output_pins(q, OUT)",
        "pins = dict(q['output_pins'], **logs)": "pins = dict(checked, **logs)",
        "status='TRUSTED797_SEALED01_READONLY_SUPPLEMENT_PASS'":
            "status='TRUSTED797_SEALED01_READONLY_SUPPLEMENT_V2_PASS', stdout_tail_proof=stdout_tail((OUT/'service-stdout.log').read_bytes(),q['output_pins'][str(OUT/'service-stdout.log')],q)",
    }
    for before, after in replacements.items():
        need(source.count(before) == 1, 'Exact frozen readonly anchor')
        source = source.replace(before, after)
    namespace = dict(old.verify.__globals__, SCHEMA=SCHEMA, QUAL_SHA=QUAL_SHA,
                     checked_output_pins=checked_output_pins, stdout_tail=stdout_tail)
    exec(compile(source, str(Path(__file__).resolve()) + ':private-readonly', 'exec'), namespace)
    return namespace['verify']


def prepare(directory):
    need(directory.parent == old.s.OUT and not directory.exists(), 'Fresh independent v2 package')
    context()
    manifest = old.bound(OLD_MANIFEST, OLD_MANIFEST_SHA)
    q = old.bound(old.OUT / 'qualification.json', QUAL_SHA)
    pins = checked_output_pins(q, old.OUT)
    failure = None
    try:
        old.verify(OLD_MANIFEST, OLD_MANIFEST_SHA)
    except ValueError as error:
        failure = str(error)
    need(failure == 'Native output pin: ' + str(old.OUT / 'service-stdout.log'),
         'Reproduce precisely original readonly stdout-tail rejection')
    evidence = dict(status='ORIGINAL_READONLY_FAILURE_REPRODUCED_EXACT_STDOUT_TAIL',
                    exception_type='ValueError', exception_message=failure,
                    original_helper_sha256=OLD_SHA, original_manifest_sha256=OLD_MANIFEST_SHA,
                    qualification_sha256=QUAL_SHA,
                    stdout_tail_proof=stdout_tail((old.OUT / 'service-stdout.log').read_bytes(),
                                                q['output_pins'][str(old.OUT / 'service-stdout.log')], q),
                    every_other_native_pin_exact=True, EDA_started=False, report_modified=False)
    directory.mkdir()
    ep = directory / 'original-failure-evidence.json'
    with ep.open('x') as stream:
        stream.write(json.dumps(evidence, indent=2) + '\n')
    manifest = dict(manifest, schema=SCHEMA, qualification_sha256=QUAL_SHA,
                    allowed_tail_path=str(old.OUT / 'service-stdout.log'),
                    original_failure_evidence=str(ep), pins=dict(manifest['pins']))
    for path in (Path(__file__).resolve(), HERE / 'test_verify_trusted_ip797_readonly_v2.py',
                 OLD_MANIFEST, old.OUT / 'qualification.json', old.OUT / 'service-stdout.log', ep):
        manifest['pins'][str(path)] = old.digest(path)
    need(manifest['pins'][str(old.OUT / 'service-stdout.log')] == pins[str(old.OUT / 'service-stdout.log')],
         'Stdout changed during prepare')
    target = directory / 'manifest.json'
    with target.open('x') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(manifest=str(target), seal=old.digest(target),
                         status='PREPARED_V2_EXACT_STDOUT_TAIL_NO_EDA')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify'))
    parser.add_argument('--package', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        need(args.package is not None and args.receipt is None, 'Independent v2 package')
        prepare(args.package.resolve())
    else:
        need(args.manifest is not None and args.seal is not None, 'Frozen v2 manifest/seal')
        result = context()(args.manifest.resolve(), args.seal)
        text = json.dumps(result, indent=2) + '\n'
        if args.receipt:
            target = args.receipt.resolve()
            need(not target.is_relative_to(old.OUT.resolve()), 'Never write into frozen report')
            with target.open('x') as stream:
                stream.write(text)
        print(text, end='')
