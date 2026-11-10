#!/usr/bin/env python3
"""Copy-only build-asset successor; never modifies the accepted prepare03 tree."""
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
V5_SHA = '0132197b2c192f87a899bbe7efa50e9d80fd653334d78a8d7309a5dc367daeee'
if hashlib.sha256((HERE / 'build_v5.py').read_bytes()).hexdigest() != V5_SHA:
    raise ValueError('Sealed V5 validator drift')
spec = importlib.util.spec_from_file_location('asset_frozen_build_v5', HERE / 'build_v5.py')
v5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v5)
v4, sha, require = v5.v4, v5.sha, v5.require
OUT, PREPARED, PREPARE_SHA = v5.OUT, v5.PREPARED, v5.PREPARE_SHA
OLD_BUILD = v4.OLD_BUILD
OLD_SOURCE = OLD_BUILD.parent / 'qemu-10.2.0'
DTC_COMMIT = 'b6910bec11614980a21e46fbccc35934b671bd81'
ASSET = 'subprojects/dtc/version_gen.h.in'
ASSET_BYTES = b'#define DTC_VERSION "DTC @VCS_TAG@"\n'
ASSET_SHA = hashlib.sha256(ASSET_BYTES).hexdigest()
OWN = ('build_v6.py', 'test_build_v6.py', 'BUILD_V6.md', *v5.OWN)


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, hashlib.sha256(v4.base().canonical(pins)).hexdigest()


def strings(value, pointer=''):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings(child, pointer + '/' + str(index))
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))


def source_reference(value, source=OLD_SOURCE, build=OLD_BUILD):
    path = Path(value)
    if not path.is_absolute():
        path = build / path
    path = Path(os.path.abspath(path))
    return path if path.is_relative_to(source) and path.is_file() else None


def regeneration_inputs(text):
    lines = text.splitlines()
    require(lines[:2] == ['build.ninja:', '  input: REGENERATE_BUILD'], 'Unexpected Ninja query header')
    require('  outputs:' in lines, 'Missing Ninja query outputs delimiter')
    end = lines.index('  outputs:')
    result = []
    for line in lines[2:end]:
        require(line.startswith('    ') and line.strip(), 'Unexpected Ninja query input')
        value = line.strip()
        for prefix in ('|| ', '| '):
            if value.startswith(prefix):
                value = value[len(prefix):]
                break
        result.append(value)
    require(result, 'Empty Ninja regeneration inputs')
    return result


def compare_references(references, source, allowed_edits):
    rows, missing = [], []
    for old, origins in sorted(references.items()):
        relative = str(Path(old).relative_to(OLD_SOURCE))
        target = source / relative
        before = sha(old)
        after = sha(target) if target.is_file() else None
        status = 'IDENTICAL'
        if after is None:
            require(not target.is_symlink() and not target.exists(), 'Asset topology conflict')
            missing.append(relative)
            status = 'MISSING'
        elif before != after:
            require(allowed_edits.get(relative) == (before, after), 'Unexplained source difference: ' + relative)
            status = 'REVIEWED_OVERLAY'
        rows.append(dict(path=relative, old_sha256=before, prepared_sha256=after,
                         status=status, origins=sorted(origins)))
    require(missing == [ASSET], 'Unexpected missing source references: ' + repr(missing))
    return rows


def archive_assets(archive_path, frozen):
    """Validate every inherited dtc C/H pin against the fixed commit archive."""
    with tarfile.open(archive_path, 'r:') as archive:
        members = {item.name: item for item in archive.getmembers()}
        require(len(members) == len(archive.getmembers()), 'Duplicate archive members')
        checked = {}
        for path, expected in frozen.items():
            member = members.get(path)
            require(member is not None and member.isfile(), 'Pinned dtc file absent from commit: ' + path)
            actual = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
            require(actual == expected, 'Frozen dtc differs from commit: ' + path)
            checked[path] = actual
        member = members.get('version_gen.h.in')
        require(member is not None and member.isfile(), 'Missing tracked dtc template')
        data = archive.extractfile(member).read()
        require(data == ASSET_BYTES, 'Unexpected dtc template bytes')
        return data, checked


def audit(output):
    r = v4.base()
    output = r.fresh(output, 'stage5_qemu_asset_audit_')
    own, review = identity()
    report = dict(schema='stage5-qemu-asset-audit-v6', state='FAIL', source_review_sha256=review,
                  prepare_sha256=PREPARE_SHA, dtc_commit=DTC_COMMIT, configure_executed=False,
                  qemu_compiled=False, guest_executed=False, full_ninja_graph_closure=False)
    try:
        v5.checked_dependencies()
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
        require(structured_count == 2941, 'Structured source-reference census changed')
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
    require(report['schema'] == 'stage5-qemu-asset-audit-v6' and
            report['state'] == 'ASSET_CLOSURE_AUDITED_NOT_BUILT' and
            report['source_review_sha256'] == identity()[1] and report['prepare_sha256'] == PREPARE_SHA and
            report['dtc_commit'] == DTC_COMMIT and report['missing'] == [ASSET] and
            report['asset_sha256'] == ASSET_SHA and report['structured_source_count'] == 2941 and
            report['dtc_frozen_ch_count'] == 104 and report['full_ninja_graph_closure'] is False,
            'Asset audit contract drift')
    r.verify(report['pins'])
    r.verify(report['artifacts'])
    require((path / 'version_gen.h.in').read_bytes() == ASSET_BYTES, 'Asset drift')
    return report


def expected_inventory(destination):
    r = v4.base()
    old = r.read(PREPARED / 'tree-inventory.json')
    result = {str(destination / Path(path).relative_to(PREPARED)): row for path, row in old.items()}
    result[str(destination / 'qemu-10.2.0' / ASSET)] = dict(kind='file', sha256=ASSET_SHA)
    return result


def verify_copy(destination):
    r = v4.base()
    expected = expected_inventory(destination)
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
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V6 inputs')
    v5.checked_dependencies()
    checked_audit(args.audit, args.reviewed_audit_sha256)
    output = r.fresh(args.output, 'stage5_qemu_prepare_variant_')
    report = dict(schema='stage5-qemu-prepare-v6', state='FAIL',
                  original_prepared=str(PREPARED), original_prepare_sha256=PREPARE_SHA,
                  source_review_sha256=args.reviewed_inputs_sha256,
                  audit=str(Path(args.audit).resolve()), audit_sha256=args.reviewed_audit_sha256,
                  added_assets={ASSET: ASSET_SHA}, dtc_commit=DTC_COMMIT,
                  configure_executed=False, qemu_compiled=False, guest_executed=False,
                  required_execution_gates=r.GATES)
    try:
        for name in ('qemu-10.2.0', 'inputs'):
            shutil.copytree(PREPARED / name, output / name, symlinks=True, copy_function=shutil.copy2)
        target = output / 'qemu-10.2.0' / ASSET
        require(not target.exists() and not target.is_symlink(), 'Asset already exists')
        with target.open('xb') as stream:
            stream.write(ASSET_BYTES)
        inventory = verify_copy(output)
        r.write_new(output / 'tree-inventory.json', inventory)
        pins = r.tree_pins(output / 'qemu-10.2.0') | r.tree_pins(output / 'inputs')
        r.write_new(output / 'source-pins.json', pins)
        v5.checked_dependencies()
        checked_audit(args.audit, args.reviewed_audit_sha256)
        require(identity()[1] == args.reviewed_inputs_sha256, 'V6 inputs changed')
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


def checked_variant(path, digest):
    r = v4.base()
    path = Path(path).resolve(strict=True)
    require(sha(path / 'prepare.json') == digest, 'Unreviewed source variant')
    report = r.read(path / 'prepare.json')
    require(report['schema'] == 'stage5-qemu-prepare-v6' and report['state'] == 'PREPARED_NOT_BUILT' and
            report['original_prepared'] == str(PREPARED) and report['original_prepare_sha256'] == PREPARE_SHA and
            report['source_review_sha256'] == identity()[1] and report['dtc_commit'] == DTC_COMMIT and
            report['added_assets'] == {ASSET: ASSET_SHA} and report['guest_executed'] is False and
            report['inherited_copy_no_hardlinks'] is True and report['original_post_pins_match'] is True and
            report['source'] == str(path / 'qemu-10.2.0') and
            report['configure_argv'] == [str(path / 'qemu-10.2.0/configure'), *r.CONFIGURE] and
            report['required_execution_gates'] == r.GATES, 'Source variant contract drift')
    v5.checked_dependencies()
    checked_audit(report['audit'], report['audit_sha256'])
    require(sha(path / 'source-pins.json') == report['source_pins_sha256'] and
            sha(path / 'tree-inventory.json') == report['tree_inventory_sha256'], 'Variant inventory drift')
    r.verify(r.read(path / 'source-pins.json'))
    actual = verify_copy(path)
    r.verify_membership(actual, r.read(path / 'tree-inventory.json'))
    return report


def checked_build(build_dir, reviewed_build_sha256):
    """Shared read-only runtime admission; requires this copied variant and V5 command rigor."""
    r = v4.base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v6' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['original_prepare_sha256'] == PREPARE_SHA and
            report['preflight'] == str(v5.TOOLENV) and report['preflight_sha256'] == v5.TOOLENV_SHA and
            report['predecessor_validator_sha256'] == V5_SHA and report['fdt_selection'] == 'internal' and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            report['source_review_sha256'] == identity()[1] and report['required_execution_gates'] == r.GATES,
            'Build not admitted')
    prepared = checked_variant(report['prepared'], report['prepare_sha256'])
    v5.checked_commands(report, path, prepared)
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def build(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed V6 inputs')
    owner = r.service_owner(args.service)
    prepared = checked_variant(args.prepared, args.reviewed_prepare_sha256)
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v6', state='FAIL', commands=[], service_owner=owner,
                  prepared=str(Path(args.prepared).resolve()), prepare_sha256=args.reviewed_prepare_sha256,
                  original_prepare_sha256=PREPARE_SHA, preflight=str(v5.TOOLENV), preflight_sha256=v5.TOOLENV_SHA,
                  source_review_sha256=args.reviewed_inputs_sha256, predecessor_validator_sha256=V5_SHA,
                  fdt_selection='internal', guest_executed=False, required_execution_gates=r.GATES)
    try:
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        env = v4.environment(output)
        report['environment'] = env
        r.bounded(v5.configure_argv(prepared), output, 900, output / 'configure.log', report['commands'], env)
        r.bounded([v4.NINJA, '-j4', 'qemu-system-riscv64'], output, 1800,
                  output / 'build.log', report['commands'], env)
        checked_variant(args.prepared, args.reviewed_prepare_sha256)
        require(identity()[1] == args.reviewed_inputs_sha256, 'V6 source changed')
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
    result = identity() if args.command == 'identity' else (audit(args.output) if args.command == 'audit'
                                                         else globals()[args.command](args))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
