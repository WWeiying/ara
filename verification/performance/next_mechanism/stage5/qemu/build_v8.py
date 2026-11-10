#!/usr/bin/env python3
"""Restore the full fixed dtc Git tree and one approved QEMU API type repair."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V7_SHA = 'f38526a341ce4a51e72e6a419f8cbe160ea68797631ea858f2f08f02610bb3e1'
if hashlib.sha256((HERE / 'build_v7.py').read_bytes()).hexdigest() != V7_SHA:
    raise ValueError('Sealed V7 validator drift')
spec = importlib.util.spec_from_file_location('dtc_frozen_build_v7', HERE / 'build_v7.py')
v7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v7)
v5, v4, sha, require, OUT = v7.v5, v7.v4, v7.sha, v7.require, v7.OUT
OWN = ('build_v8.py', 'test_build_v8.py', 'BUILD_V8.md', *v7.OWN)
PARENT = OUT / 'stage5_qemu_prepare_variant_20261110_01'
PARENT_SHA = '34f60faabc1b8d3cdd9e261ac1dceb87bfedbce95cfa385f47cdd839d9986bcc'
ARCHIVE = OUT / 'stage5_qemu_asset_audit_20261110_03/dtc-commit.tar'
ARCHIVE_SHA = '1fb660c56f7c255b930f9763f58e0b3f3c59d1815fa11bc5cb01d01823540ba4'
DTC = 'subprojects/dtc'
DTC_COMMIT = v7.DTC_COMMIT
REPAIR_PATH = 'hw/riscv/ara_stage4.c'
REPAIR_BEFORE = '1fb17c4482b7bc007167cc00b953c69a49f474eecf9c67db02bddf3e5b7137b8'
REPAIR_OLD, REPAIR_NEW = b'CharBackend console;', b'CharFrontend console;'
MESON_FILES = ('meson.build', 'libfdt/meson.build', 'pylibfdt/meson.build', 'tests/meson.build')


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, hashlib.sha256(v4.base().canonical(pins)).hexdigest()


def git_members(raw):
    result = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        metadata, path = record.split(b'\t', 1)
        mode, kind, blob = metadata.decode('ascii').split()
        name = path.decode('ascii')
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and str(p) == name and
                name not in result and mode in ('100644', '100755') and kind == 'blob' and
                len(blob) == 40 and all(c in '0123456789abcdef' for c in blob), 'Unsafe/duplicate Git entry')
        result[name] = dict(mode=int(mode, 8) & 0o777, git_blob=blob)
    require(result, 'Empty Git tree')
    return result


def archive_payload(path, raw_tree):
    members = git_members(raw_tree)
    payload = {}
    with tarfile.open(path, 'r:') as archive:
        for entry in archive.getmembers():
            if entry.isdir():
                continue
            require(entry.isfile() and entry.name in members and entry.name not in payload,
                    'Archive has an untracked/duplicate/nonregular member')
            data = archive.extractfile(entry).read()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            mode = members[entry.name]['mode']
            require(blob == members[entry.name]['git_blob'] and
                    entry.mode & 0o777 in (mode, mode | 0o020), 'Archive/Git blob or executable mode differs')
            members[entry.name]['archive_mode'] = entry.mode & 0o777
            payload[entry.name] = data
    require(set(payload) == set(members), 'Incomplete tracked archive')
    return members, payload


def asset_plan(parent, members, payload):
    root = parent / 'qemu-10.2.0' / DTC
    rows = []
    for name in sorted(members):
        path = root / name
        require(not path.is_symlink(), 'Dtc tracked symlink conflict')
        for ancestor in path.parents:
            if ancestor == root:
                break
            require(not ancestor.is_symlink(), 'Dtc ancestor symlink conflict')
        existing = path.exists()
        require(not existing or path.is_file() and path.read_bytes() == payload[name],
                'Existing dtc bytes differ from fixed Git commit: ' + name)
        rows.append(dict(path=name, sha256=hashlib.sha256(payload[name]).hexdigest(), bytes=len(payload[name]),
                         git_blob=members[name]['git_blob'], mode=members[name]['mode'],
                         archive_mode=members[name]['archive_mode'],
                         action='KEEP_IDENTICAL' if existing else 'ADD_MISSING',
                         existing_mode=(path.stat().st_mode & 0o777) if existing else None))
    extras = sorted(str(path.relative_to(root)) for path in root.rglob('*')
                    if path.is_file() and str(path.relative_to(root)) not in members)
    require(extras == ['.meson-subproject-wrap-hash.txt'], 'Unexpected untracked dtc file')
    return dict(schema='stage5-dtc-full-tracked-v1', commit=DTC_COMMIT,
                tracked=rows, retained_nontracked={extras[0]: sha(root / extras[0])},
                meson_sources={name: payload[name].decode('utf-8') for name in MESON_FILES})


def repaired(data):
    require(hashlib.sha256(data).hexdigest() == REPAIR_BEFORE and data.count(REPAIR_OLD) == 1 and
            REPAIR_NEW not in data, 'Approved type-repair input differs')
    return data.replace(REPAIR_OLD, REPAIR_NEW)


def repair_record(parent):
    before = (parent / 'qemu-10.2.0' / REPAIR_PATH).read_bytes()
    after = repaired(before)
    patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                       'a/' + REPAIR_PATH, 'b/' + REPAIR_PATH))
    return dict(path=REPAIR_PATH, before_sha256=REPAIR_BEFORE,
                after_sha256=hashlib.sha256(after).hexdigest(),
                scope='Approved CharFrontend API type correction; not a dtc asset change'), after, patch


def checked_parent():
    require(sha(ARCHIVE) == ARCHIVE_SHA, 'Fixed dtc archive drift')
    return v7.checked_variant(PARENT, PARENT_SHA, after_build=True)


def expected_inventory(destination, manifest, repair, after_build=False):
    r = v4.base()
    result = {str(destination / Path(path).relative_to(PARENT)): row
              for path, row in r.read(PARENT / 'tree-inventory.json').items()}
    for row in manifest['tracked']:
        if row['action'] != 'ADD_MISSING':
            continue
        path = destination / 'qemu-10.2.0' / DTC / row['path']
        require(str(path) not in result, 'Added asset overlaps frozen file')
        result[str(path)] = dict(kind='file', sha256=row['sha256'])
        parent = path.parent
        while str(parent) not in result:
            require(parent.is_relative_to(destination / 'qemu-10.2.0' / DTC), 'Asset parent escape')
            result[str(parent)] = dict(kind='directory')
            parent = parent.parent
    repaired_path = str(destination / 'qemu-10.2.0' / repair['path'])
    require(result[repaired_path] == dict(kind='file', sha256=repair['before_sha256']), 'Repair inventory differs')
    result[repaired_path] = dict(kind='file', sha256=repair['after_sha256'])
    return v7.inventory_with_lock(result, destination, after_build)


def verify_variant_tree(path, manifest, repair, after_build=False):
    r = v4.base()
    actual = r.tree_inventory(path / 'qemu-10.2.0') | r.tree_inventory(path / 'inputs')
    r.verify_membership(actual, expected_inventory(path, manifest, repair, after_build))
    for name, row in actual.items():
        if row['kind'] != 'file':
            continue
        original = PARENT / Path(name).relative_to(path)
        if original.is_file():
            a, b = original.stat(), Path(name).stat()
            require((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino), 'Hardlinked parent file')
    for row in manifest['tracked']:
        target = path / 'qemu-10.2.0' / DTC / row['path']
        expected_mode = row['mode'] if row['action'] == 'ADD_MISSING' else row['existing_mode']
        require(target.stat().st_mode & 0o777 == expected_mode, 'Dtc file mode drift: ' + row['path'])
    return actual


def prepare(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V8 sources')
    checked_parent()
    output = r.fresh(args.output, 'stage5_qemu_prepare_variant_')
    report = dict(schema='stage5-qemu-prepare-v8', state='FAIL', source_review_sha256=args.reviewed_inputs_sha256,
                  parent=str(PARENT), parent_prepare_sha256=PARENT_SHA, original_prepare_sha256=v7.PREPARE_SHA,
                  dtc_archive=str(ARCHIVE), dtc_archive_sha256=ARCHIVE_SHA, dtc_commit=DTC_COMMIT,
                  parent_generated_metadata=v7.lock_metadata(PARENT, True),
                  variant_generated_metadata_before={}, variant_generated_metadata_after={},
                  configure_executed=False, qemu_compiled=False, guest_executed=False,
                  required_execution_gates=r.GATES)
    try:
        argv = ['/usr/bin/git', '-C', str(v7.OLD_SOURCE / DTC), 'ls-tree', '-rz', '--full-tree', DTC_COMMIT]
        result = subprocess.run(argv, capture_output=True, timeout=30,
                                env=dict(PATH='/usr/bin:/bin', LC_ALL='C', LANG='C',
                                         GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null'))
        (output / 'git-tree.raw').write_bytes(result.stdout)
        (output / 'git-tree.stderr').write_bytes(result.stderr)
        require(result.returncode == 0, 'Fixed Git tree inventory failed')
        members, payload = archive_payload(ARCHIVE, result.stdout)
        manifest = asset_plan(PARENT, members, payload)
        require(len(members) == 310 and sum(row['action'] == 'ADD_MISSING' for row in manifest['tracked']) == 194,
                'Reviewed fixed-tree restoration set changed')
        r.write_new(output / 'asset-manifest.json', manifest)
        repair, after, patch = repair_record(PARENT)
        r.write_new(output / 'adapter-repair.json', repair)
        (output / 'adapter-repair.patch').write_text(patch)
        for name in ('qemu-10.2.0', 'inputs'):
            v7.copy_without_lock(PARENT / name, output / name)
        for row in manifest['tracked']:
            if row['action'] != 'ADD_MISSING':
                continue
            target = output / 'qemu-10.2.0' / DTC / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(payload[row['path']])
                os.fchmod(stream.fileno(), row['mode'])
        target = output / 'qemu-10.2.0' / REPAIR_PATH
        require(sha(target) == REPAIR_BEFORE, 'Copied adapter input changed')
        target.write_bytes(after)
        inventory = verify_variant_tree(output, manifest, repair)
        r.write_new(output / 'tree-inventory.json', inventory)
        r.write_new(output / 'source-pins.json', r.tree_pins(output / 'qemu-10.2.0') | r.tree_pins(output / 'inputs'))
        checked_parent()
        require(identity()[1] == args.reviewed_inputs_sha256, 'V8 source changed')
        report.update(state='PREPARED_NOT_BUILT', source=str(output / 'qemu-10.2.0'),
                      source_pins_sha256=sha(output / 'source-pins.json'),
                      tree_inventory_sha256=sha(output / 'tree-inventory.json'),
                      asset_manifest_sha256=sha(output / 'asset-manifest.json'),
                      adapter_repair=repair, git_tree_sha256=sha(output / 'git-tree.raw'),
                      adapter_patch_sha256=sha(output / 'adapter-repair.patch'),
                      adapter_receipt_sha256=sha(output / 'adapter-repair.json'),
                      added_tracked_files=194, tracked_files=310, parent_post_pins_match=True,
                      inherited_copy_no_hardlinks=True,
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
    require(sha(path / 'prepare.json') == digest, 'Unreviewed source variant')
    report = r.read(path / 'prepare.json')
    require(report['schema'] == 'stage5-qemu-prepare-v8' and report['state'] == 'PREPARED_NOT_BUILT' and
            report['source_review_sha256'] == identity()[1] and report['parent'] == str(PARENT) and
            report['parent_prepare_sha256'] == PARENT_SHA and report['original_prepare_sha256'] == v7.PREPARE_SHA and
            report['dtc_archive'] == str(ARCHIVE) and report['dtc_archive_sha256'] == ARCHIVE_SHA and
            report['dtc_commit'] == DTC_COMMIT and report['parent_generated_metadata'] == v7.lock_metadata(PARENT, True) and
            report['variant_generated_metadata_before'] == report['variant_generated_metadata_after'] == {} and
            report['configure_executed'] is report['qemu_compiled'] is report['guest_executed'] is False and
            report['parent_post_pins_match'] is report['inherited_copy_no_hardlinks'] is True and
            report['tracked_files'] == 310 and report['added_tracked_files'] == 194 and
            report['required_execution_gates'] == r.GATES and report['source'] == str(path / 'qemu-10.2.0') and
            report['configure_argv'] == [str(path / 'qemu-10.2.0/configure'), *r.CONFIGURE], 'Variant contract differs')
    checked_parent()
    for name, key in (('source-pins.json', 'source_pins_sha256'), ('tree-inventory.json', 'tree_inventory_sha256'),
                      ('asset-manifest.json', 'asset_manifest_sha256'), ('git-tree.raw', 'git_tree_sha256'),
                      ('adapter-repair.patch', 'adapter_patch_sha256'), ('adapter-repair.json', 'adapter_receipt_sha256')):
        require(sha(path / name) == report[key], 'Variant receipt artifact drift: ' + name)
    members, payload = archive_payload(ARCHIVE, (path / 'git-tree.raw').read_bytes())
    manifest = asset_plan(PARENT, members, payload)
    require(r.read(path / 'asset-manifest.json') == manifest, 'Full Git asset manifest differs')
    repair, _, patch = repair_record(PARENT)
    require(report['adapter_repair'] == r.read(path / 'adapter-repair.json') == repair and
            (path / 'adapter-repair.patch').read_text() == patch, 'Unapproved adapter repair')
    r.verify(r.read(path / 'source-pins.json'))
    actual = verify_variant_tree(path, manifest, repair, after_build)
    r.verify_membership(actual, v7.inventory_with_lock(r.read(path / 'tree-inventory.json'), path, after_build))
    return report


def checked_build(build_dir, reviewed_build_sha256):
    r = v4.base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v8' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['source_review_sha256'] == identity()[1] and report['predecessor_validator_sha256'] == V7_SHA and
            report['original_prepare_sha256'] == v7.PREPARE_SHA and
            report['preflight'] == str(v5.TOOLENV) and report['preflight_sha256'] == v5.TOOLENV_SHA and
            report['fdt_selection'] == 'internal' and report['guest_executed'] is False and
            report['post_pins_match'] is True and report['required_execution_gates'] == r.GATES and
            report['generated_metadata_before'] == {} and
            report['generated_metadata_after'] == v7.lock_metadata(Path(report['prepared']), True), 'Build not admitted')
    prepared = checked_variant(report['prepared'], report['prepare_sha256'], after_build=True)
    v5.checked_commands(report, path, prepared)
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def build(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V8 sources')
    owner = r.service_owner(args.service)
    prepared = checked_variant(args.prepared, args.reviewed_prepare_sha256)
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v8', state='FAIL', commands=[], service_owner=owner,
                  source_review_sha256=args.reviewed_inputs_sha256, predecessor_validator_sha256=V7_SHA,
                  prepared=str(Path(args.prepared).resolve()), prepare_sha256=args.reviewed_prepare_sha256,
                  original_prepare_sha256=v7.PREPARE_SHA, preflight=str(v5.TOOLENV), preflight_sha256=v5.TOOLENV_SHA,
                  fdt_selection='internal', guest_executed=False, required_execution_gates=r.GATES,
                  generated_metadata_before={}, generated_metadata_after=None)
    try:
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        env = v4.environment(output)
        report['environment'] = env
        r.bounded(v5.configure_argv(prepared), output, 900, output / 'configure.log', report['commands'], env)
        r.bounded([v4.NINJA, '-j4', 'qemu-system-riscv64'], output, 1800, output / 'build.log', report['commands'], env)
        checked_variant(args.prepared, args.reviewed_prepare_sha256, after_build=True)
        require(identity()[1] == args.reviewed_inputs_sha256 and r.service_owner(args.service) == owner,
                'Build sources/service owner changed')
        v5.checked_commands(report, output, prepared)
        report.update(state='BUILT_NOT_EXECUTED', executable=str(output / 'qemu-system-riscv64'),
                      executable_sha256=sha(output / 'qemu-system-riscv64'), post_pins_match=True,
                      generated_metadata_after=v7.lock_metadata(Path(args.prepared).resolve(), True))
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
    a.add_argument('--output', type=Path, required=True)
    a.add_argument('--reviewed-inputs-sha256', required=True)
    a = sub.add_parser('build')
    for name in ('output', 'prepared'):
        a.add_argument('--' + name, type=Path, required=True)
    for name in ('reviewed-prepare-sha256', 'reviewed-inputs-sha256', 'service'):
        a.add_argument('--' + name, required=True)
    args = p.parse_args()
    if args.command == 'prepare':
        def expired(signum, frame):
            raise TimeoutError('900-second copy/closure preparation bound')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(900)
    result = identity() if args.command == 'identity' else globals()[args.command](args)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
