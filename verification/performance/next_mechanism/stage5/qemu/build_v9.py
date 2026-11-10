#!/usr/bin/env python3
"""Decoder-pattern and RAM-only probe repairs over the sealed V8 variant."""
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
V8_SHA = '59bef77c38336444f08bce84f8cb3e1f6a2a27dfc5229fff2dcb58809001f4de'
if hashlib.sha256((HERE / 'build_v8.py').read_bytes()).hexdigest() != V8_SHA:
    raise ValueError('Sealed V8 validator drift')
spec = importlib.util.spec_from_file_location('decoder_frozen_build_v8', HERE / 'build_v8.py')
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)
v7, v5, v4, sha, require, OUT = v8.v7, v8.v5, v8.v4, v8.sha, v8.require, v8.OUT
OWN = ('build_v9.py', 'test_build_v9.py', 'BUILD_V9.md', *v8.OWN)
PARENT = OUT / 'stage5_qemu_prepare_variant_20261110_02'
PARENT_SHA = '79d8477622dd33b24d9dd25a0cfc56ca55b01e6ef7c72ba13a80bd0d095bc210'
REPAIR_PATH = 'target/riscv/Xaraakv.decode'
REPAIR_BEFORE = 'ce1bb191f1d845ebc185054d2649ae140dd876d94a6e1ff0ec48161a5b0bcefd'
GENERATOR_SHA = '91e068b1993166ba9bf259573f457342c54de70a117f7db42355a3a50fcc0c68'
FAIL05_SHA = 'e1638165a23208d60511dc546448d92eb79d385ffc0a59deba20326d885d00eb'
RAM_PATH = 'target/riscv/akv_helper.c'
RAM_BEFORE = '3cef79060fdcd4092ff6835b65924d5f4b39ae506acdde32970ed9ef48d663c8'
RAM_AFTER = '974596d663ac492844fbd88b94fb4d5cecf8b4c108bc3134ca2c491a2bba6ab0'
SYNTAX = OUT / 'stage5_qemu_csyntax_probe_20261110_02'
SYNTAX_SHA = '4697f9e5a6dfcda4a3d1fa1ad080abd5f0d291a0c5db77f24da87c6d15fd7ca5'
SCRATCH = 'tests/qemu-iotests/scratch'
RAM_OLD = b'''        /* Never invoke MMIO/ROM callbacks for descriptor or payload reads. */
        if ((flags & TLB_MMIO) || !host) {
            akv_raise_access(call, address, chunk);
        }
'''
RAM_NEW = b'''        /* Never invoke MMIO/ROM callbacks for descriptor or payload reads. */
        if ((flags & TLB_MMIO) || !host) {
            akv_raise_access(call, address, chunk);
        }
        ram_addr_t offset;
        bool ram_ok;
        rcu_read_lock();
        MemoryRegion *mr = memory_region_from_host(host, &offset);
        ram_ok = mr && memory_region_is_ram(mr) && !memory_region_is_rom(mr);
        if (ram_ok) {
            uint64_t size = memory_region_size(mr);
            ram_ok = offset <= size && chunk <= size - offset;
        }
        rcu_read_unlock();
        if (!ram_ok) {
            akv_raise_access(call, address, chunk);
        }
'''


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, hashlib.sha256(v4.base().canonical(pins)).hexdigest()


def repaired(data):
    require(hashlib.sha256(data).hexdigest() == REPAIR_BEFORE, 'Decoder input differs')
    for funct3 in ('010', '011', '101', '110', '111'):
        old = ('akvexec    ....... ..... ..... ' + funct3 + ' ..... 1011011 @akv_exec').encode()
        require(data.count(old) == 1, 'Decoder pattern membership differs')
        data = data.replace(old, old.replace(b'.......', b'-------', 1))
    return data


def repair_record():
    before = (PARENT / 'qemu-10.2.0' / REPAIR_PATH).read_bytes()
    after = repaired(before)
    patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                       'a/' + REPAIR_PATH, 'b/' + REPAIR_PATH))
    return dict(path=REPAIR_PATH, before_sha256=REPAIR_BEFORE,
                after_sha256=hashlib.sha256(after).hexdigest(), patterns=5,
                scope='Ignore top7 in decoder only; raw opcode reserved checks unchanged'), after, patch


def checked_parent():
    require(sha(OUT / 'stage5_qemu_build_20261110_05/build.json') == FAIL05_SHA, 'BUILD05 evidence drift')
    r = v4.base()
    require(sha(PARENT / 'prepare.json') == PARENT_SHA, 'Frozen V8 prepare receipt drift')
    report = r.read(PARENT / 'prepare.json')
    require(report['source_review_sha256'] == v8.identity()[1] and
            report['state'] == 'PREPARED_NOT_BUILT', 'Frozen V8 preparation identity differs')
    v8.checked_parent()
    for name, key in (('source-pins.json', 'source_pins_sha256'), ('tree-inventory.json', 'tree_inventory_sha256'),
                      ('asset-manifest.json', 'asset_manifest_sha256'), ('git-tree.raw', 'git_tree_sha256'),
                      ('adapter-repair.patch', 'adapter_patch_sha256'), ('adapter-repair.json', 'adapter_receipt_sha256')):
        require(sha(PARENT / name) == report[key], 'V8 receipt artifact drift: ' + name)
    members, payload = v8.archive_payload(v8.ARCHIVE, (PARENT / 'git-tree.raw').read_bytes())
    manifest = v8.asset_plan(v8.PARENT, members, payload)
    repair, _, patch = v8.repair_record(v8.PARENT)
    require(r.read(PARENT / 'asset-manifest.json') == manifest and
            report['adapter_repair'] == r.read(PARENT / 'adapter-repair.json') == repair and
            (PARENT / 'adapter-repair.patch').read_text() == patch, 'V8 fixed assets/repair differ')
    r.verify(r.read(PARENT / 'source-pins.json'))
    actual = r.tree_inventory(PARENT / 'qemu-10.2.0') | r.tree_inventory(PARENT / 'inputs')
    expected = v8.expected_inventory(PARENT, manifest, repair, after_build=True)
    generated = scratch_metadata(PARENT)
    require(not set(expected) & set(generated), 'Generated scratch overlaps frozen source')
    r.verify_membership(actual, expected | generated)
    frozen = v7.inventory_with_lock(r.read(PARENT / 'tree-inventory.json'), PARENT, True)
    r.verify_membership(actual, frozen | generated)
    for name, row in actual.items():
        if row['kind'] == 'file':
            original = v8.PARENT / Path(name).relative_to(PARENT)
            if original.is_file():
                a, b = original.stat(), Path(name).stat()
                require((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino), 'Hardlinked V8 parent file')
    for row in manifest['tracked']:
        mode = row['mode'] if row['action'] == 'ADD_MISSING' else row['existing_mode']
        require((PARENT / 'qemu-10.2.0' / v8.DTC / row['path']).stat().st_mode & 0o777 == mode,
                'V8 dtc mode drift')
    return report


def scratch_metadata(root):
    path = root / 'qemu-10.2.0' / SCRATCH
    require(not path.is_symlink() and path.is_dir() and not any(path.iterdir()),
            'Generated iotests scratch must be exactly an empty directory')
    return {str(path): dict(kind='directory')}


def ram_repaired(data):
    require(hashlib.sha256(data).hexdigest() == RAM_BEFORE and data.count(RAM_OLD) == 1 and
            data.count(b'#include "fpu/softfloat.h"\n') == 1, 'RAM probe input differs')
    result = data.replace(b'#include "fpu/softfloat.h"\n',
                          b'#include "fpu/softfloat.h"\n#include "system/memory.h"\n#include "qemu/rcu.h"\n').replace(RAM_OLD, RAM_NEW)
    require(hashlib.sha256(result).hexdigest() == RAM_AFTER, 'Syntax-reviewed RAM patch differs')
    return result


def ram_record():
    before = (PARENT / 'qemu-10.2.0' / RAM_PATH).read_bytes()
    after = ram_repaired(before)
    patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                       'a/' + RAM_PATH, 'b/' + RAM_PATH))
    return dict(path=RAM_PATH, before_sha256=RAM_BEFORE,
                after_sha256=hashlib.sha256(after).hexdigest(),
                scope='Reject physical ROM/ROMD; preserve translated read-only DRAM; unlock before access trap'), after, patch


def expected_inventory(destination, after_build=False):
    r = v4.base()
    result = {str(destination / Path(path).relative_to(PARENT)): row
              for path, row in r.read(PARENT / 'tree-inventory.json').items()}
    repair, _, _ = repair_record()
    key = str(destination / 'qemu-10.2.0' / REPAIR_PATH)
    require(result[key] == dict(kind='file', sha256=REPAIR_BEFORE), 'Parent decoder inventory differs')
    result[key] = dict(kind='file', sha256=repair['after_sha256'])
    repair, _, _ = ram_record()
    key = str(destination / 'qemu-10.2.0' / RAM_PATH)
    require(result[key] == dict(kind='file', sha256=RAM_BEFORE), 'Parent RAM helper inventory differs')
    result[key] = dict(kind='file', sha256=repair['after_sha256'])
    result[str(destination / 'qemu-10.2.0' / SCRATCH)] = dict(kind='directory')
    return v7.inventory_with_lock(result, destination, after_build)


def verify_copy(destination, after_build=False):
    r = v4.base()
    scratch_metadata(destination)
    actual = r.tree_inventory(destination / 'qemu-10.2.0') | r.tree_inventory(destination / 'inputs')
    r.verify_membership(actual, expected_inventory(destination, after_build))
    for name, row in actual.items():
        if row['kind'] != 'file' or name in v7.lock_metadata(destination, after_build):
            continue
        target = Path(name)
        original = PARENT / target.relative_to(destination)
        a, b = original.stat(), target.stat()
        require((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino), 'Hardlinked parent file')
        require(a.st_mode & 0o777 == b.st_mode & 0o777, 'Copied source mode differs')
    return actual


def checked_host(path, digest):
    r = v4.base()
    path = Path(path).resolve(strict=True)
    require(sha(path / 'result.json') == digest, 'Unreviewed decoder host receipt')
    report = r.read(path / 'result.json')
    require(report['state'] == 'BUILD_V9_STATIC_HOST_PASS_NOT_BUILT' and
            report['source_review_sha256'] == identity()[1] and report['failures'] == report['errors'] == 0 and
            report['tests'] == 12 and report['generator_sha256'] == GENERATOR_SHA and
            report['guest_executed'] is False, 'Decoder host checks not admitted')
    r.verify(report['artifacts'])
    require(sha(SYNTAX / 'result.json') == SYNTAX_SHA, 'RAM syntax receipt drift')
    syntax = r.read(SYNTAX / 'result.json')
    require(syntax['state'] == 'RAM_GUARD_C_SYNTAX_PASS' and syntax['returncode'] == 0 and
            syntax['candidate_sha256'] == RAM_AFTER and syntax['original_sha256'] == RAM_BEFORE and
            syntax['source_edited'] is syntax['base_build_edited'] is syntax['target_executed'] is False,
            'RAM C syntax not admitted')
    r.verify(syntax['artifacts'])
    r.verify(r.read(SYNTAX / 'source-pins.json'))
    return report


def prepare(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V9 sources')
    checked_host(args.host, args.reviewed_host_sha256)
    checked_parent()
    output = r.fresh(args.output, 'stage5_qemu_prepare_variant_')
    report = dict(schema='stage5-qemu-prepare-v9', state='FAIL', source_review_sha256=args.reviewed_inputs_sha256,
                  parent=str(PARENT), parent_prepare_sha256=PARENT_SHA, original_prepare_sha256=v7.PREPARE_SHA,
                  host=str(args.host.resolve()), host_sha256=args.reviewed_host_sha256,
                  syntax=str(SYNTAX), syntax_sha256=SYNTAX_SHA,
                  parent_generated_metadata=v7.lock_metadata(PARENT, True),
                  parent_generated_directories=scratch_metadata(PARENT),
                  variant_generated_metadata_before={}, variant_generated_metadata_after={},
                  configure_executed=False, qemu_compiled=False, guest_executed=False,
                  required_execution_gates=r.GATES)
    try:
        repair, after, patch = repair_record()
        r.write_new(output / 'decoder-repair.json', repair)
        (output / 'decoder-repair.patch').write_text(patch)
        ram, ram_after, ram_patch = ram_record()
        r.write_new(output / 'ram-repair.json', ram)
        (output / 'ram-repair.patch').write_text(ram_patch)
        for name in ('qemu-10.2.0', 'inputs'):
            v7.copy_without_lock(PARENT / name, output / name)
        target = output / 'qemu-10.2.0' / REPAIR_PATH
        require(sha(target) == REPAIR_BEFORE, 'Copied decoder input differs')
        target.write_bytes(after)
        target = output / 'qemu-10.2.0' / RAM_PATH
        require(sha(target) == RAM_BEFORE, 'Copied RAM helper input differs')
        target.write_bytes(ram_after)
        r.write_new(output / 'tree-inventory.json', verify_copy(output))
        r.write_new(output / 'source-pins.json', r.tree_pins(output / 'qemu-10.2.0') | r.tree_pins(output / 'inputs'))
        checked_parent()
        checked_host(args.host, args.reviewed_host_sha256)
        require(identity()[1] == args.reviewed_inputs_sha256, 'V9 sources changed')
        report.update(state='PREPARED_NOT_BUILT', source=str(output / 'qemu-10.2.0'),
                      source_pins_sha256=sha(output / 'source-pins.json'),
                      tree_inventory_sha256=sha(output / 'tree-inventory.json'), decoder_repair=repair,
                      decoder_patch_sha256=sha(output / 'decoder-repair.patch'),
                      decoder_receipt_sha256=sha(output / 'decoder-repair.json'),
                      ram_repair=ram, ram_patch_sha256=sha(output / 'ram-repair.patch'),
                      ram_receipt_sha256=sha(output / 'ram-repair.json'),
                      variant_generated_directories=scratch_metadata(output),
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
    require(sha(path / 'prepare.json') == digest, 'Unreviewed V9 variant')
    report = r.read(path / 'prepare.json')
    require(report['schema'] == 'stage5-qemu-prepare-v9' and report['state'] == 'PREPARED_NOT_BUILT' and
            report['source_review_sha256'] == identity()[1] and report['parent'] == str(PARENT) and
            report['parent_prepare_sha256'] == PARENT_SHA and report['original_prepare_sha256'] == v7.PREPARE_SHA and
            report['syntax'] == str(SYNTAX) and report['syntax_sha256'] == SYNTAX_SHA and
            report['parent_generated_metadata'] == v7.lock_metadata(PARENT, True) and
            report['parent_generated_directories'] == scratch_metadata(PARENT) and
            report['variant_generated_directories'] == scratch_metadata(path) and
            report['variant_generated_metadata_before'] == report['variant_generated_metadata_after'] == {} and
            report['configure_executed'] is report['qemu_compiled'] is report['guest_executed'] is False and
            report['parent_post_pins_match'] is report['inherited_copy_no_hardlinks'] is True and
            report['required_execution_gates'] == r.GATES and report['source'] == str(path / 'qemu-10.2.0') and
            report['configure_argv'] == [str(path / 'qemu-10.2.0/configure'), *r.CONFIGURE], 'V9 variant differs')
    checked_parent()
    checked_host(report['host'], report['host_sha256'])
    for name, key in (('source-pins.json', 'source_pins_sha256'), ('tree-inventory.json', 'tree_inventory_sha256'),
                      ('decoder-repair.patch', 'decoder_patch_sha256'), ('decoder-repair.json', 'decoder_receipt_sha256'),
                      ('ram-repair.patch', 'ram_patch_sha256'), ('ram-repair.json', 'ram_receipt_sha256')):
        require(sha(path / name) == report[key], 'Variant artifact differs: ' + name)
    repair, _, patch = repair_record()
    require(report['decoder_repair'] == r.read(path / 'decoder-repair.json') == repair and
            (path / 'decoder-repair.patch').read_text() == patch, 'Unapproved decoder repair')
    repair, _, patch = ram_record()
    require(report['ram_repair'] == r.read(path / 'ram-repair.json') == repair and
            (path / 'ram-repair.patch').read_text() == patch, 'Unapproved RAM probe repair')
    r.verify(r.read(path / 'source-pins.json'))
    actual = verify_copy(path, after_build)
    r.verify_membership(actual, v7.inventory_with_lock(r.read(path / 'tree-inventory.json'), path, after_build))
    return report


def checked_build(build_dir, reviewed_build_sha256):
    r = v4.base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v9' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['source_review_sha256'] == identity()[1] and report['predecessor_validator_sha256'] == V8_SHA and
            report['original_prepare_sha256'] == v7.PREPARE_SHA and report['preflight'] == str(v5.TOOLENV) and
            report['preflight_sha256'] == v5.TOOLENV_SHA and report['fdt_selection'] == 'internal' and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            report['required_execution_gates'] == r.GATES and report['generated_metadata_before'] == {} and
            report['generated_metadata_after'] == v7.lock_metadata(Path(report['prepared']), True), 'Build not admitted')
    require(report['generated_directories_before'] == report['generated_directories_after'] ==
            scratch_metadata(Path(report['prepared'])), 'Build generated directory differs')
    prepared = checked_variant(report['prepared'], report['prepare_sha256'], after_build=True)
    v5.checked_commands(report, path, prepared)
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def build(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V9 sources')
    owner = r.service_owner(args.service)
    prepared = checked_variant(args.prepared, args.reviewed_prepare_sha256)
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v9', state='FAIL', commands=[], service_owner=owner,
                  source_review_sha256=args.reviewed_inputs_sha256, predecessor_validator_sha256=V8_SHA,
                  prepared=str(Path(args.prepared).resolve()), prepare_sha256=args.reviewed_prepare_sha256,
                  original_prepare_sha256=v7.PREPARE_SHA, preflight=str(v5.TOOLENV), preflight_sha256=v5.TOOLENV_SHA,
                  fdt_selection='internal', guest_executed=False, required_execution_gates=r.GATES,
                  generated_metadata_before={}, generated_metadata_after=None)
    report.update(generated_directories_before=scratch_metadata(Path(args.prepared).resolve()),
                  generated_directories_after=None)
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
                      generated_directories_after=scratch_metadata(Path(args.prepared).resolve()),
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
        def expired(signum, frame):
            raise TimeoutError('900-second copy/closure preparation bound')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(900)
    print(json.dumps(identity() if args.command == 'identity' else globals()[args.command](args), indent=2))


if __name__ == '__main__':
    main()
