#!/usr/bin/env python3
"""Copy-only AKV trap restore and precise EOC-width successor; no QBS changes."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V9_SHA = '67b94115f6d9493bb0512d1ad702ad03f65a5554d5ee32b7fb3489fe43281c8e'
if hashlib.sha256((HERE / 'build_v9.py').read_bytes()).hexdigest() != V9_SHA:
    raise ValueError('Sealed V9 validator drift')
spec = importlib.util.spec_from_file_location('trap_frozen_build_v9', HERE / 'build_v9.py')
v9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v9)
v7, v5, v4, sha, require, OUT = v9.v7, v9.v5, v9.v4, v9.sha, v9.require, v9.OUT
OWN = ('build_v10.py', 'test_build_v10.py', 'BUILD_V10.md', *v9.OWN)
PARENT = OUT / 'stage5_qemu_prepare_variant_20261110_03'
PARENT_SHA = '655b1c715559885fa99e9bd353553299330b6e46e27ee744a63a7c62a5a28855'
BUILD06_SHA = '93506639dda6fc22dc66733ca2160c5ba7b799787e8fb8f5e4d067ed37d3c3d6'
SYNTAX03 = OUT / 'stage5_qemu_csyntax_probe_20261110_03'
SYNTAX03_SHA = 'a89b9e512a7e0e8cad0098d18b18c48146e58dd92e252b9cac65af76a31560a9'
SYNTAX04 = OUT / 'stage5_qemu_csyntax_probe_20261110_04'
SYNTAX04_SHA = '17210b48aa0d0ce7091fa3d1624043af6750e19da25004604e0a5c50337700e1'
PATCHES = {
    'target/riscv/akv_helper.c': dict(before='974596d663ac492844fbd88b94fb4d5cecf8b4c108bc3134ca2c491a2bba6ab0',
        after='6459c81f161b91af54a35d49d05185b7811546055fd77146c3efeecbd334bec5',
        candidate=str(SYNTAX03 / 'inputs/akv_helper.c')),
    'hw/riscv/ara_stage4.c': dict(before='f4602629633b8b235741faf9ec3d65237217ef5c293b682e36b3b3523a913cf1',
        after='932d97bc9c6fa9c37ebad33f1ae7f2d1ee3181638704ad8c2bceebe543cf6959',
        candidate=str(SYNTAX04 / 'inputs/ara_stage4.c'))}
QBS_SHA = '5ed80e3807f078b75be6c89dc2825af8268fbe04d581fe4623d450b2fcc2c2fd'


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, hashlib.sha256(v4.base().canonical(pins)).hexdigest()


def repairs():
    records, payload, diffs = {}, {}, []
    for name, row in PATCHES.items():
        before = (PARENT / 'qemu-10.2.0' / name).read_bytes()
        after = Path(row['candidate']).read_bytes()
        require(hashlib.sha256(before).hexdigest() == row['before'] and
                hashlib.sha256(after).hexdigest() == row['after'], 'Unreviewed repair bytes: ' + name)
        records[name] = dict(before_sha256=row['before'], after_sha256=row['after'], candidate=row['candidate'])
        payload[name] = after
        diffs.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                        'a/' + name, 'b/' + name))
    return records, payload, ''.join(diffs)


def checked_syntax():
    r = v4.base()
    for path, digest in ((SYNTAX03, SYNTAX03_SHA), (SYNTAX04, SYNTAX04_SHA)):
        require(sha(path / 'result.json') == digest, 'Unreviewed finite C syntax receipt')
        report = r.read(path / 'result.json')
        require(report['state'] == ('AKV_TRAP_EOC_C_SYNTAX_PASS' if path == SYNTAX03 else
                                   'EOC_ONLY_ACCEPTS_C_SYNTAX_PASS'), 'Wrong finite syntax scope')
        require(report['post_pins_match'] is True and report['target_executed'] is False and
                report['source_edited'] is False and report['base_build_edited'] is False,
                'C syntax provenance differs')
        r.verify(report['artifacts'])
        require(sha(path / 'source-pins.json') == report['source_pins_sha256'], 'C syntax input inventory differs')
        r.verify(r.read(path / 'source-pins.json'))
    repairs()


def checked_parent():
    require(sha(OUT / 'stage5_qemu_build_20261110_06/build.json') == BUILD06_SHA, 'BUILD06 receipt changed')
    return v9.checked_variant(PARENT, PARENT_SHA, after_build=True)


def expected_inventory(destination, after_build=False):
    r = v4.base()
    expected = {str(destination / Path(path).relative_to(PARENT)): row
                for path, row in r.read(PARENT / 'tree-inventory.json').items()}
    for name, row in PATCHES.items():
        key = str(destination / 'qemu-10.2.0' / name)
        require(expected[key] == dict(kind='file', sha256=row['before']), 'Repair is not the exact original file')
        expected[key] = dict(kind='file', sha256=row['after'])
    return v7.inventory_with_lock(expected, destination, after_build)


def verify_copy(destination, after_build=False):
    r = v4.base()
    v9.scratch_metadata(destination)
    actual = r.tree_inventory(destination / 'qemu-10.2.0') | r.tree_inventory(destination / 'inputs')
    r.verify_membership(actual, expected_inventory(destination, after_build))
    for name, row in actual.items():
        if row['kind'] != 'file' or name in v7.lock_metadata(destination, after_build):
            continue
        target = Path(name)
        original = PARENT / target.relative_to(destination)
        a, b = original.stat(), target.stat()
        require((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) and a.st_mode & 0o777 == b.st_mode & 0o777,
                'Copy hardlink or inherited mode change')
    require(sha(destination / 'qemu-10.2.0/target/riscv/qbs_helper.c') == QBS_SHA, 'QBS helper must remain unchanged')
    return actual


def checked_host(path, digest):
    r = v4.base()
    path = Path(path).resolve(strict=True)
    require(sha(path / 'result.json') == digest, 'Unreviewed V10 host receipt')
    report = r.read(path / 'result.json')
    require(report['state'] == 'BUILD_V10_STATIC_HOST_PASS_NOT_BUILT' and report['source_review_sha256'] == identity()[1] and
            report['tests'] == 10 and report['failures'] == report['errors'] == 0 and
            report['guest_executed'] is False, 'V10 host not admitted')
    r.verify(report['artifacts'])
    checked_syntax()


def prepare(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V10 sources')
    checked_host(args.host, args.reviewed_host_sha256)
    checked_parent()
    output = r.fresh(args.output, 'stage5_qemu_prepare_variant_')
    report = dict(schema='stage5-qemu-prepare-v10', state='FAIL', source_review_sha256=args.reviewed_inputs_sha256,
                  parent=str(PARENT), parent_prepare_sha256=PARENT_SHA, original_prepare_sha256=v7.PREPARE_SHA,
                  host=str(args.host.resolve()), host_sha256=args.reviewed_host_sha256,
                  syntax_receipts={str(SYNTAX03): SYNTAX03_SHA, str(SYNTAX04): SYNTAX04_SHA},
                  parent_generated_metadata=v7.lock_metadata(PARENT, True),
                  parent_generated_directories=v9.scratch_metadata(PARENT),
                  variant_generated_metadata_before={}, variant_generated_metadata_after={},
                  configure_executed=False, qemu_compiled=False, guest_executed=False, required_execution_gates=r.GATES)
    try:
        records, payload, patch = repairs()
        r.write_new(output / 'adapter-repairs.json', records)
        (output / 'adapter-repairs.patch').write_text(patch)
        for name in ('qemu-10.2.0', 'inputs'):
            v7.copy_without_lock(PARENT / name, output / name)
        for name, data in payload.items():
            path = output / 'qemu-10.2.0' / name
            require(sha(path) == PATCHES[name]['before'], 'Copied repair input changed')
            path.write_bytes(data)
        r.write_new(output / 'tree-inventory.json', verify_copy(output))
        r.write_new(output / 'source-pins.json', r.tree_pins(output / 'qemu-10.2.0') | r.tree_pins(output / 'inputs'))
        checked_parent()
        checked_host(args.host, args.reviewed_host_sha256)
        require(identity()[1] == args.reviewed_inputs_sha256, 'V10 sources changed')
        report.update(state='PREPARED_NOT_BUILT', source=str(output / 'qemu-10.2.0'),
                      source_pins_sha256=sha(output / 'source-pins.json'), tree_inventory_sha256=sha(output / 'tree-inventory.json'),
                      repairs=records, repairs_sha256=sha(output / 'adapter-repairs.json'),
                      patch_sha256=sha(output / 'adapter-repairs.patch'), qbs_helper_sha256=QBS_SHA,
                      variant_generated_directories=v9.scratch_metadata(output),
                      parent_post_pins_match=True, inherited_copy_no_hardlinks=True,
                      configure_argv=[str(output / 'qemu-10.2.0/configure'), *r.CONFIGURE])
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        r.write_new(output / 'prepare.json', report)
    return report


def checked_variant(path, digest, after_build=False):
    r = v4.base()
    path = Path(path).resolve(strict=True)
    require(sha(path / 'prepare.json') == digest, 'Unreviewed V10 variant')
    report = r.read(path / 'prepare.json')
    require(report['schema'] == 'stage5-qemu-prepare-v10' and report['state'] == 'PREPARED_NOT_BUILT' and
            report['source_review_sha256'] == identity()[1] and report['parent'] == str(PARENT) and
            report['parent_prepare_sha256'] == PARENT_SHA and report['original_prepare_sha256'] == v7.PREPARE_SHA and
            report['syntax_receipts'] == {str(SYNTAX03): SYNTAX03_SHA, str(SYNTAX04): SYNTAX04_SHA} and
            report['parent_generated_metadata'] == v7.lock_metadata(PARENT, True) and
            report['parent_generated_directories'] == v9.scratch_metadata(PARENT) and
            report['variant_generated_directories'] == v9.scratch_metadata(path) and
            report['variant_generated_metadata_before'] == report['variant_generated_metadata_after'] == {} and
            report['configure_executed'] is report['qemu_compiled'] is report['guest_executed'] is False and
            report['parent_post_pins_match'] is report['inherited_copy_no_hardlinks'] is True and
            report['required_execution_gates'] == r.GATES and report['source'] == str(path / 'qemu-10.2.0') and
            report['qbs_helper_sha256'] == QBS_SHA and
            report['configure_argv'] == [str(path / 'qemu-10.2.0/configure'), *r.CONFIGURE], 'V10 variant differs')
    checked_parent()
    checked_host(report['host'], report['host_sha256'])
    for name, key in (('source-pins.json', 'source_pins_sha256'), ('tree-inventory.json', 'tree_inventory_sha256'),
                      ('adapter-repairs.json', 'repairs_sha256'), ('adapter-repairs.patch', 'patch_sha256')):
        require(sha(path / name) == report[key], 'Variant artifact drift')
    records, _, patch = repairs()
    require(report['repairs'] == r.read(path / 'adapter-repairs.json') == records and
            (path / 'adapter-repairs.patch').read_text() == patch, 'Unapproved adapter patch')
    r.verify(r.read(path / 'source-pins.json'))
    actual = verify_copy(path, after_build)
    r.verify_membership(actual, v7.inventory_with_lock(r.read(path / 'tree-inventory.json'), path, after_build))
    return report


def checked_build(build_dir, reviewed_build_sha256):
    r = v4.base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v10' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['source_review_sha256'] == identity()[1] and report['predecessor_validator_sha256'] == V9_SHA and
            report['original_prepare_sha256'] == v7.PREPARE_SHA and report['preflight'] == str(v5.TOOLENV) and
            report['preflight_sha256'] == v5.TOOLENV_SHA and report['fdt_selection'] == 'internal' and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            report['required_execution_gates'] == r.GATES and report['generated_metadata_before'] == {} and
            report['generated_metadata_after'] == v7.lock_metadata(Path(report['prepared']), True) and
            report['generated_directories_before'] == report['generated_directories_after'] ==
            v9.scratch_metadata(Path(report['prepared'])), 'Build not admitted')
    prepared = checked_variant(report['prepared'], report['prepare_sha256'], after_build=True)
    v5.checked_commands(report, path, prepared)
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def build(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V10 sources')
    owner = r.service_owner(args.service)
    prepared = checked_variant(args.prepared, args.reviewed_prepare_sha256)
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v10', state='FAIL', commands=[], service_owner=owner,
                  source_review_sha256=args.reviewed_inputs_sha256, predecessor_validator_sha256=V9_SHA,
                  prepared=str(Path(args.prepared).resolve()), prepare_sha256=args.reviewed_prepare_sha256,
                  original_prepare_sha256=v7.PREPARE_SHA, preflight=str(v5.TOOLENV), preflight_sha256=v5.TOOLENV_SHA,
                  fdt_selection='internal', guest_executed=False, required_execution_gates=r.GATES,
                  generated_metadata_before={}, generated_metadata_after=None,
                  generated_directories_before=v9.scratch_metadata(Path(args.prepared).resolve()),
                  generated_directories_after=None)
    try:
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        report['environment'] = env = v4.environment(output)
        r.bounded(v5.configure_argv(prepared), output, 900, output / 'configure.log', report['commands'], env)
        r.bounded([v4.NINJA, '-j4', 'qemu-system-riscv64'], output, 1800, output / 'build.log', report['commands'], env)
        checked_variant(args.prepared, args.reviewed_prepare_sha256, after_build=True)
        require(identity()[1] == args.reviewed_inputs_sha256 and r.service_owner(args.service) == owner,
                'Build source/service ownership changed')
        v5.checked_commands(report, output, prepared)
        report.update(state='BUILT_NOT_EXECUTED', executable=str(output / 'qemu-system-riscv64'),
                      executable_sha256=sha(output / 'qemu-system-riscv64'), post_pins_match=True,
                      generated_metadata_after=v7.lock_metadata(Path(args.prepared).resolve(), True),
                      generated_directories_after=v9.scratch_metadata(Path(args.prepared).resolve()))
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        r.write_new(output / 'build.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('identity')
    a = sub.add_parser('prepare')
    for name in ('output', 'host'):
        a.add_argument('--' + name, type=Path, required=True)
    for name in ('reviewed-inputs-sha256', 'reviewed-host-sha256'):
        a.add_argument('--' + name, required=True)
    a = sub.add_parser('build')
    for name in ('output', 'prepared'):
        a.add_argument('--' + name, type=Path, required=True)
    for name in ('reviewed-prepare-sha256', 'reviewed-inputs-sha256', 'service'):
        a.add_argument('--' + name, required=True)
    args = p.parse_args()
    if args.command == 'prepare':
        def expired(sig, frame):
            raise TimeoutError('900-second copy/closure preparation bound')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(900)
    print(json.dumps(identity() if args.command == 'identity' else globals()[args.command](args), indent=2))


if __name__ == '__main__':
    main()
