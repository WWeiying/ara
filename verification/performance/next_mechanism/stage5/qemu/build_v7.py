#!/usr/bin/env python3
"""Exact Meson lock-metadata successor; preserve prepare03 and failed V6 audit."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V6_SHA = 'eb26921dd5a2be3b8c23e8d67eef90265a987c118fc5a7f026b292a2a82168c0'
if hashlib.sha256((HERE / 'build_v6.py').read_bytes()).hexdigest() != V6_SHA:
    raise ValueError('Sealed V6 validator drift')
spec = importlib.util.spec_from_file_location('lock_frozen_build_v6', HERE / 'build_v6.py')
v6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v6)
v5, v4, sha, require = v6.v5, v6.v4, v6.sha, v6.require
OUT, PREPARED, PREPARE_SHA = v6.OUT, v6.PREPARED, v6.PREPARE_SHA
OLD_BUILD, OLD_SOURCE = v6.OLD_BUILD, v6.OLD_SOURCE
DTC_COMMIT, ASSET, ASSET_BYTES, ASSET_SHA = v6.DTC_COMMIT, v6.ASSET, v6.ASSET_BYTES, v6.ASSET_SHA
OWN = ('build_v7.py', 'test_build_v7.py', 'BUILD_V7.md', *v6.OWN)
LOCK = 'subprojects/.wraplock'
EMPTY_SHA = hashlib.sha256(b'').hexdigest()
ORIGINAL_TREE_SHA = '52cc21b9ed8ef15315f3d4620df5a6faed0cd1549db1b7848fe9d6b125cbff6f'


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, hashlib.sha256(v4.base().canonical(pins)).hexdigest()


# Reuse the frozen parsers and fixed-commit archive checker without changing their globals.
strings = v6.strings
source_reference = v6.source_reference
regeneration_inputs = v6.regeneration_inputs
compare_references = v6.compare_references
archive_assets = v6.archive_assets


def lock_metadata(root, present):
    return {str(root / 'qemu-10.2.0' / LOCK): EMPTY_SHA} if present else {}


def inventory_with_lock(expected, root, present):
    result = dict(expected)
    for path, digest in lock_metadata(root, present).items():
        require(path not in result, 'Generated lock overlaps frozen inventory')
        result[path] = dict(kind='file', sha256=digest)
    return result


def checked_dependencies():
    """All inherited checks, plus exactly the proven empty BUILD03 Meson lock."""
    r = v4.base()
    require(sha(PREPARED / 'prepare.json') == PREPARE_SHA, 'Unaccepted prepared source')
    receipt = r.read(PREPARED / 'prepare.json')
    require(receipt['schema'] == 'stage5-qemu-prepare-v3' and
            receipt['state'] == 'PREPARED_NOT_BUILT' and
            receipt['source_review_sha256'] == v4.REVIEW_SHA and
            receipt['source'] == str(PREPARED / 'qemu-10.2.0') and
            receipt['configure_argv'] == [str(PREPARED / 'qemu-10.2.0/configure'), *r.CONFIGURE],
            'Prepared contract changed')
    require(sha(PREPARED / 'source-pins.json') == receipt['source_pins_sha256'] and
            sha(PREPARED / 'tree-inventory.json') == ORIGINAL_TREE_SHA, 'Original inventory drift')
    r.verify(r.read(PREPARED / 'source-pins.json'))
    expected = inventory_with_lock(r.read(PREPARED / 'tree-inventory.json'), PREPARED, True)
    r.verify_membership(r.tree_inventory(PREPARED / 'qemu-10.2.0') |
                        r.tree_inventory(PREPARED / 'inputs'), expected)
    toolenv = v4.checked_toolenv(v5.TOOLENV, v5.TOOLENV_SHA)
    require(toolenv['configure_argv'] == v4.configure_argv(receipt), 'Inherited configure contract drift')
    return receipt


def copy_without_lock(source, destination):
    def ignore(directory, names):
        return {'.wraplock'} if Path(directory) == source / 'subprojects' else set()
    shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2, ignore=ignore)


def checked_reference_counts(rows, structured_count, combined_count):
    paths = [row['path'] for row in rows]
    structured = sum(any(origin.startswith('intro-') for origin in row['origins']) for row in rows)
    require(len(paths) == len(set(paths)) == combined_count and
            structured_count == structured > 0, 'Reference census disagrees with unique ledger')
    require([row['path'] for row in rows if row['status'] == 'MISSING'] == [ASSET],
            'Reference ledger missing assets changed')


def audit(output):
    r = v4.base()
    output = r.fresh(output, 'stage5_qemu_asset_audit_')
    own, review = identity()
    report = dict(schema='stage5-qemu-asset-audit-v7', state='FAIL', source_review_sha256=review,
                  prepare_sha256=PREPARE_SHA, dtc_commit=DTC_COMMIT, configure_executed=False,
                  qemu_compiled=False, guest_executed=False, full_ninja_graph_closure=False,
                  original_generated_metadata=lock_metadata(PREPARED, True))
    try:
        checked_dependencies()
        source = PREPARED / 'qemu-10.2.0'
        refs, pins = {}, {}
        intros = sorted((OLD_BUILD / 'meson-info').glob('intro-*.json'))
        require(len(intros) == 11, 'Accepted Meson introspection membership changed')
        for path in intros:
            pins[str(path)] = sha(path)
            for pointer, value in strings(r.read(path)):
                found = source_reference(value)
                if found is not None:
                    refs.setdefault(str(found), set()).add(path.name + '#' + pointer)
        structured_count = len(refs)
        require(structured_count > 0, 'Empty structured source-reference census')
        pins[str(OLD_BUILD / 'build.ninja')] = sha(OLD_BUILD / 'build.ninja')
        pins[v4.NINJA] = sha(v4.NINJA)
        env = dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C',
                   GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
        argv = [v4.NINJA, '-t', 'query', 'build.ninja']
        start = time.time_ns()
        result = subprocess.run(argv, cwd=OLD_BUILD, env=env, capture_output=True, timeout=30)
        (output / 'ninja-query.txt').write_bytes(result.stdout)
        (output / 'ninja-query.stderr').write_bytes(result.stderr)
        report['ninja_query'] = dict(argv=argv, cwd=str(OLD_BUILD), timeout=30, returncode=result.returncode,
                                    started_ns=start, ended_ns=time.time_ns())
        require(result.returncode == 0, 'Read-only Ninja regeneration query failed')
        query = regeneration_inputs(result.stdout.decode())
        query_source_count = 0
        for value in query:
            found = source_reference(value)
            if found is not None:
                refs.setdefault(str(found), set()).add('ninja-query:REGENERATE_BUILD')
                query_source_count += 1
        edits = r.read(PREPARED / 'future-copies.json')['edits']
        allowed = {row['path']: (row['before_sha256'], row['after_sha256']) for row in edits}
        rows = compare_references(refs, source, allowed)
        checked_reference_counts(rows, structured_count, len(refs))
        r.write_new(output / 'source-references.json', rows)
        manifest = r.read(r.MANIFEST)
        require(sha(r.MANIFEST) == r.MANIFEST_SHA, 'Inherited manifest drift')
        dtc = OLD_SOURCE / 'subprojects/dtc'
        frozen = {str(Path(p).relative_to(dtc)): h for p, h in manifest['source_sha256'].items()
                  if Path(p).is_relative_to(dtc) and Path(p).suffix in ('.c', '.h')}
        require(len(frozen) == 104, 'Inherited dtc C/H census changed')
        archive = output / 'dtc-commit.tar'
        git = '/usr/bin/git'
        pins[git] = sha(git)
        argv = [git, '-C', str(dtc), 'archive', '--format=tar', DTC_COMMIT]
        with archive.open('xb') as stream:
            result = subprocess.run(argv, env=env, stdout=stream, stderr=subprocess.PIPE, timeout=30)
        (output / 'git-archive.stderr').write_bytes(result.stderr)
        require(result.returncode == 0, 'Fixed dtc commit archive failed')
        data, checked = archive_assets(archive, frozen)
        (output / 'version_gen.h.in').write_bytes(data)
        r.write_new(output / 'dtc-frozen-ch.json', checked)
        pins.update({p: sha(p) for p in refs})
        pins[str(r.MANIFEST)] = r.MANIFEST_SHA
        pins.update({str(HERE / name): digest for name, digest in own.items()})
        r.verify(pins)
        require(identity() == (own, review), 'Audit source changed')
        report.update(state='ASSET_CLOSURE_AUDITED_NOT_BUILT', structured_source_count=structured_count,
                      regeneration_inputs=len(query), regeneration_source_count=query_source_count,
                      combined_source_count=len(refs), missing=[ASSET], asset_sha256=ASSET_SHA,
                      dtc_frozen_ch_count=len(checked), git_archive_argv=argv,
                      pins=pins, artifacts=r.tree_pins(output))
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        r.write_new(output / 'audit.json', report)
    return report


def checked_audit(path, digest):
    r = v4.base()
    path = Path(path).resolve(strict=True)
    require(sha(path / 'audit.json') == digest, 'Unreviewed asset audit')
    report = r.read(path / 'audit.json')
    require(report['schema'] == 'stage5-qemu-asset-audit-v7' and
            report['state'] == 'ASSET_CLOSURE_AUDITED_NOT_BUILT' and
            report['source_review_sha256'] == identity()[1] and report['prepare_sha256'] == PREPARE_SHA and
            report['dtc_commit'] == DTC_COMMIT and report['missing'] == [ASSET] and
            report['asset_sha256'] == ASSET_SHA and
            report['dtc_frozen_ch_count'] == 104 and report['full_ninja_graph_closure'] is False and
            report['original_generated_metadata'] == lock_metadata(PREPARED, True),
            'Asset audit contract drift')
    r.verify(report['pins'])
    r.verify(report['artifacts'])
    checked_reference_counts(r.read(path / 'source-references.json'), report['structured_source_count'],
                             report['combined_source_count'])
    require((path / 'version_gen.h.in').read_bytes() == ASSET_BYTES, 'Asset drift')
    return report


def expected_inventory(destination, after_build=False):
    r = v4.base()
    old = r.read(PREPARED / 'tree-inventory.json')
    result = {str(destination / Path(path).relative_to(PREPARED)): row for path, row in old.items()}
    result[str(destination / 'qemu-10.2.0' / ASSET)] = dict(kind='file', sha256=ASSET_SHA)
    return inventory_with_lock(result, destination, after_build)


def verify_copy(destination, after_build=False):
    r = v4.base()
    expected = expected_inventory(destination, after_build)
    actual = r.tree_inventory(destination / 'qemu-10.2.0') | r.tree_inventory(destination / 'inputs')
    r.verify_membership(actual, expected)
    for name, row in actual.items():
        if row['kind'] != 'file':
            continue
        path = Path(name)
        original = PREPARED / path.relative_to(destination)
        if original.is_file():
            a, b = original.stat(), path.stat()
            require((a.st_dev, a.st_ino) != (b.st_dev, b.st_ino), 'Hardlinked inherited file: ' + name)
    return actual


def prepare(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V7 inputs')
    checked_dependencies()
    checked_audit(args.audit, args.reviewed_audit_sha256)
    output = r.fresh(args.output, 'stage5_qemu_prepare_variant_')
    report = dict(schema='stage5-qemu-prepare-v7', state='FAIL',
                  original_prepared=str(PREPARED), original_prepare_sha256=PREPARE_SHA,
                  source_review_sha256=args.reviewed_inputs_sha256,
                  audit=str(Path(args.audit).resolve()), audit_sha256=args.reviewed_audit_sha256,
                  added_assets={ASSET: ASSET_SHA}, dtc_commit=DTC_COMMIT,
                  configure_executed=False, qemu_compiled=False, guest_executed=False,
                  required_execution_gates=r.GATES,
                  original_generated_metadata=lock_metadata(PREPARED, True),
                  variant_generated_metadata_before={}, variant_generated_metadata_after={})
    try:
        for name in ('qemu-10.2.0', 'inputs'):
            copy_without_lock(PREPARED / name, output / name)
        target = output / 'qemu-10.2.0' / ASSET
        require(not target.exists() and not target.is_symlink(), 'Asset already exists')
        with target.open('xb') as stream:
            stream.write(ASSET_BYTES)
        inventory = verify_copy(output)
        r.write_new(output / 'tree-inventory.json', inventory)
        pins = r.tree_pins(output / 'qemu-10.2.0') | r.tree_pins(output / 'inputs')
        r.write_new(output / 'source-pins.json', pins)
        checked_dependencies()
        checked_audit(args.audit, args.reviewed_audit_sha256)
        require(identity()[1] == args.reviewed_inputs_sha256, 'V7 inputs changed')
        report.update(state='PREPARED_NOT_BUILT', source=str(output / 'qemu-10.2.0'),
                      source_pins_sha256=sha(output / 'source-pins.json'),
                      tree_inventory_sha256=sha(output / 'tree-inventory.json'),
                      inherited_copy_no_hardlinks=True, original_post_pins_match=True,
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
    require(report['schema'] == 'stage5-qemu-prepare-v7' and report['state'] == 'PREPARED_NOT_BUILT' and
            report['original_prepared'] == str(PREPARED) and report['original_prepare_sha256'] == PREPARE_SHA and
            report['source_review_sha256'] == identity()[1] and report['dtc_commit'] == DTC_COMMIT and
            report['added_assets'] == {ASSET: ASSET_SHA} and report['guest_executed'] is False and
            report['inherited_copy_no_hardlinks'] is True and report['original_post_pins_match'] is True and
            report['source'] == str(path / 'qemu-10.2.0') and
            report['configure_argv'] == [str(path / 'qemu-10.2.0/configure'), *r.CONFIGURE] and
            report['required_execution_gates'] == r.GATES and
            report['original_generated_metadata'] == lock_metadata(PREPARED, True) and
            report['variant_generated_metadata_before'] == {} and
            report['variant_generated_metadata_after'] == {}, 'Source variant contract drift')
    checked_dependencies()
    checked_audit(report['audit'], report['audit_sha256'])
    require(sha(path / 'source-pins.json') == report['source_pins_sha256'] and
            sha(path / 'tree-inventory.json') == report['tree_inventory_sha256'], 'Variant inventory drift')
    r.verify(r.read(path / 'source-pins.json'))
    actual = verify_copy(path, after_build=after_build)
    r.verify_membership(actual, inventory_with_lock(r.read(path / 'tree-inventory.json'), path, after_build))
    return report


def checked_build(build_dir, reviewed_build_sha256):
    """Shared read-only runtime admission; requires this copied variant and V5 command rigor."""
    r = v4.base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v7' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['original_prepare_sha256'] == PREPARE_SHA and
            report['preflight'] == str(v5.TOOLENV) and report['preflight_sha256'] == v5.TOOLENV_SHA and
            report['predecessor_validator_sha256'] == V6_SHA and report['fdt_selection'] == 'internal' and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            report['source_review_sha256'] == identity()[1] and report['required_execution_gates'] == r.GATES and
            report['generated_metadata_before'] == {} and
            report['generated_metadata_after'] == lock_metadata(Path(report['prepared']), True),
            'Build not admitted')
    prepared = checked_variant(report['prepared'], report['prepare_sha256'], after_build=True)
    v5.checked_commands(report, path, prepared)
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def build(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V7 inputs')
    owner = r.service_owner(args.service)
    prepared = checked_variant(args.prepared, args.reviewed_prepare_sha256)
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v7', state='FAIL', commands=[], service_owner=owner,
                  prepared=str(Path(args.prepared).resolve()), prepare_sha256=args.reviewed_prepare_sha256,
                  original_prepare_sha256=PREPARE_SHA, preflight=str(v5.TOOLENV), preflight_sha256=v5.TOOLENV_SHA,
                  source_review_sha256=args.reviewed_inputs_sha256, predecessor_validator_sha256=V6_SHA,
                  fdt_selection='internal', guest_executed=False, required_execution_gates=r.GATES,
                  generated_metadata_before={}, generated_metadata_after=None)
    try:
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        env = v4.environment(output)
        report['environment'] = env
        r.bounded(v5.configure_argv(prepared), output, 900, output / 'configure.log', report['commands'], env)
        r.bounded([v4.NINJA, '-j4', 'qemu-system-riscv64'], output, 1800,
                  output / 'build.log', report['commands'], env)
        checked_variant(args.prepared, args.reviewed_prepare_sha256, after_build=True)
        report['generated_metadata_after'] = lock_metadata(Path(args.prepared).resolve(), True)
        require(identity()[1] == args.reviewed_inputs_sha256, 'V7 source changed')
        require(r.service_owner(args.service) == owner, 'Build service ownership changed')
        v5.checked_commands(report, output, prepared)
        report.update(state='BUILT_NOT_EXECUTED', executable=str(output / 'qemu-system-riscv64'),
                      executable_sha256=sha(output / 'qemu-system-riscv64'), post_pins_match=True)
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
    a = sub.add_parser('audit')
    a.add_argument('--output', type=Path, required=True)
    a = sub.add_parser('prepare')
    a.add_argument('--output', type=Path, required=True)
    a.add_argument('--audit', type=Path, required=True)
    a.add_argument('--reviewed-audit-sha256', required=True)
    a.add_argument('--reviewed-inputs-sha256', required=True)
    a = sub.add_parser('build')
    a.add_argument('--output', type=Path, required=True)
    a.add_argument('--prepared', type=Path, required=True)
    a.add_argument('--reviewed-prepare-sha256', required=True)
    a.add_argument('--reviewed-inputs-sha256', required=True)
    a.add_argument('--service', required=True)
    args = p.parse_args()
    if args.command in ('audit', 'prepare'):
        import signal
        def expired(signum, frame):
            raise TimeoutError('V7 bounded ' + args.command + ' expired')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(240 if args.command == 'audit' else 600)
    result = identity() if args.command == 'identity' else (audit(args.output) if args.command == 'audit'
                                                         else globals()[args.command](args))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

