#!/usr/bin/env python3
"""V2 archive-policy successor. Preserves sealed recipe.py; never runs a guest."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
import overlay
import archive_policy_v2 as archive_policy

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE = OUT / 'qemu-context-20261023-01'
SOURCE = BASE / 'qemu-10.2.0'
MANIFEST = BASE / 'qemu-10.2.0-build/native-model-manifest.json'
MANIFEST_SHA = '6c4dad29c87d518a59adbe3ba92a24be7e3e1203157f519324b91f2337a7e9f9'
BINARY_SHA = '37e3b4c100c3e8fbb7a248f3a0ab328797285dfe59e285fcf8540a14bd5b8e4c'
ARCHIVE_SHA = '9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a'
MODEL_HOST = OUT / 'stage5_akv_model_host_20261110_02'
MODEL_HOST_SHA = 'e8242012b8fff3dc2faa63935e5dd73bc5985f61233684560d9570ff3971554a'
MODEL_LOGS = {
    'host.log': '3ff0f0491d92ef2ce78a54709286b1ae127c5c7da3b6103f5366398cfa8b6a7a',
    'optimized/run.log': 'bbc6176bba383b0b641686c5a8715969933bd34487979c3bf551bbedc03973c0',
    'ubsan/run.log': 'bbc6176bba383b0b641686c5a8715969933bd34487979c3bf551bbedc03973c0',
}
PREDECESSOR_SHA = 'c960b12b12cbf586abcb0541634bf41c9e548518ff6a19ecd630e9bf117ce588'
OWN = (*overlay.FILES, 'overlay.py', 'recipe.py', 'test_adapter.py', 'README.md',
       'recipe_v2.py', 'archive_policy_v2.py', 'test_archive_policy_v2.py', 'ARCHIVE_V2.md')
CONFIGURE = [
    '--target-list=riscv64-softmmu', '--disable-docs', '--disable-werror',
    '--disable-download', '--disable-plugins', '--disable-linux-user',
    '--disable-guest-agent', '--disable-sdl', '--disable-gtk', '--disable-vnc',
    '--disable-curses', '--disable-opengl', '--disable-slirp',
    '--enable-trace-backends=log',
]
GATES = ['directed-native-lifecycle-fault-flags', 'unchanged-stage4-perf02',
         'unchanged-stage4-functional01', 'native-qbs-successor-smoke']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def write_new(path, value):
    with Path(path).open('x') as target:
        json.dump(value, target, sort_keys=True, indent=2)
        target.write('\n')


def identity():
    pins = {name: sha(HERE / name) for name in sorted(OWN)}
    return pins, hashlib.sha256(canonical(pins)).hexdigest()


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Source identity drift: ' + str(path))


def fresh(path, prefix):
    path = Path(path).absolute()
    require(path.parent.resolve() == OUT.resolve() and
            re.fullmatch(prefix + r'[A-Za-z0-9_]+', path.name) and
            not path.exists() and not path.is_symlink(), 'Fresh owned output required')
    path.mkdir()
    return path


def tree_pins(root):
    return {str(p): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def tree_inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            result[str(p)] = dict(kind='symlink', target=os.readlink(p))
        elif p.is_dir():
            result[str(p)] = dict(kind='directory')
        else:
            require(p.is_file(), 'Unsupported source-tree object: ' + str(p))
            result[str(p)] = dict(kind='file', sha256=sha(p))
    return result


def verify_membership(actual, expected):
    require(actual == expected, 'Prepared source/input membership or bytes changed')


def build_environment(output, tools):
    return dict(PATH='/usr/bin:/bin', HOME=str(output / 'home'),
                TMPDIR=str(output / 'tmp'), LANG='C', LC_ALL='C',
                CC=tools['gcc'], CXX=tools['g++'], PYTHONNOUSERSITE='1',
                PYTHONDONTWRITEBYTECODE='1')


def prepare(args):
    own, own_sha = identity()
    require(sha(HERE / 'recipe.py') == PREDECESSOR_SHA, 'Sealed predecessor drift')
    require(own_sha == args.reviewed_inputs_sha256, 'Review does not bind current inputs')
    require(sha(args.archive) == ARCHIVE_SHA, 'Wrong upstream QEMU archive')
    require(sha(MANIFEST) == MANIFEST_SHA, 'Unaccepted frozen QBS manifest')
    manifest = read(MANIFEST)
    require(manifest['state'] == 'PASS' and
            manifest['executable_sha256'] == BINARY_SHA and
            sha(manifest['executable']) == BINARY_SHA, 'Unaccepted frozen QBS executable')
    inherited = {p: h for p, h in manifest['source_sha256'].items()
                 if Path(p).is_relative_to(SOURCE)}
    require(len(inherited) > 30000, 'Incomplete frozen source inventory')
    verify(inherited)
    require(sha(MODEL_HOST / 'result.json') == MODEL_HOST_SHA, 'Unreviewed model host receipt')
    model_host = read(MODEL_HOST / 'result.json')
    require(model_host['state'] == 'HOST_MODEL_CALLBACK_PASS_NOT_QEMU' and
            model_host['post_pins_match'] is True and
            model_host['arithmetic_acceptance'] is False and
            model_host['configurations'] == 2 and model_host['logical_cases'] == 11,
            'Model host scope changed')
    require(sha(MODEL_HOST / 'source-pins.json') == model_host['source_pins_sha256'],
            'Model host pin inventory drift')
    model_pins = read(MODEL_HOST / 'source-pins.json')
    verify(model_pins)
    verify({str(MODEL_HOST / name): digest for name, digest in MODEL_LOGS.items()})
    for name in ('akv_model.c', 'akv_model.h'):
        require(own[name] == model_pins[str(HERE / name)], 'Model differs from host02')
    output = fresh(args.output, 'stage5_qemu_prepare_')
    report = dict(schema='stage5-qemu-prepare-v2', state='FAIL',
                  predecessor_recipe_sha256=PREDECESSOR_SHA,
                  source_review_sha256=own_sha, archive_sha256=ARCHIVE_SHA,
                  base_manifest_sha256=MANIFEST_SHA, base_binary_sha256=BINARY_SHA,
                  model_host_receipt_sha256=MODEL_HOST_SHA,
                  required_execution_gates=GATES, guest_executed=False)
    try:
        # The archive supplies unpinned upstream files (e.g. .S and build tools).
        # Only manifest-verified files override it; never copy the live SDK.
        with tarfile.open(args.archive, 'r:xz') as archive:
            inventory = archive_policy.inventory(archive.getmembers(), output)
            write_new(output / 'archive-inventory.json', inventory)
            archive_policy.require_known(inventory)
            archive.extractall(output, filter=archive_policy.data_filter)
        source = output / 'qemu-10.2.0'
        for name, digest in inherited.items():
            target = source / Path(name).relative_to(SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not target.is_symlink(), 'Refusing symlink overlay: ' + str(target))
            shutil.copyfile(name, target)
            require(sha(target) == digest, 'Frozen copy changed: ' + name)
        excluded = output / archive_policy.SKIP_NAME
        require(not excluded.exists() and not excluded.is_symlink(), 'Excluded link reintroduced')
        require(sha(args.archive) == ARCHIVE_SHA, 'Archive changed during extraction')
        inputs = output / 'inputs'
        inputs.mkdir()
        for name in own:
            shutil.copyfile(HERE / name, inputs / name)
            require(sha(inputs / name) == own[name], 'Review copy changed: ' + name)
        patch = []
        for relative in overlay.EDITS:
            p = source / relative
            before = p.read_text()
            after = overlay.transform(relative, before)
            patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                             'a/' + relative, 'b/' + relative))
            p.write_text(after)
        trace = source / 'target/riscv/trace-events'
        before = trace.read_text()
        after = before + overlay.TRACE_EVENTS
        patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                         'a/target/riscv/trace-events', 'b/target/riscv/trace-events'))
        trace.write_text(after)
        for name, relative in overlay.FILES.items():
            target = source / relative
            require(not target.exists(), 'Overlay would overwrite an existing file: ' + relative)
            shutil.copyfile(inputs / name, target)
            patch.extend(difflib.unified_diff([], target.read_text().splitlines(True),
                                             '/dev/null', 'b/' + relative))
        (output / 'xaraakv.patch').write_text(''.join(patch))
        # QBS implementation bytes must survive all integration transforms.
        qbs = ('Xaraqbs.decode', 'insn_trans/trans_xaraqbs.c.inc', 'qbs_helper.c',
               'qbs_ref.c', 'qbs_ref.h', 'qbs_abi.h')
        for name in qbs:
            require(sha(source / 'target/riscv' / name) ==
                    inherited[str(SOURCE / 'target/riscv' / name)], 'QBS drift: ' + name)
        verify(inherited)
        require(identity()[1] == own_sha, 'Owned inputs changed during preparation')
        pins = tree_pins(source) | tree_pins(inputs) | model_pins | tree_pins(MODEL_HOST)
        pins[str(output / 'archive-inventory.json')] = sha(output / 'archive-inventory.json')
        pins.update({str(MANIFEST): MANIFEST_SHA, str(Path(args.archive).resolve()): ARCHIVE_SHA,
                     str(output / 'xaraakv.patch'): sha(output / 'xaraakv.patch')})
        write_new(output / 'tree-inventory.json', tree_inventory(source) | tree_inventory(inputs))
        pins[str(output / 'tree-inventory.json')] = sha(output / 'tree-inventory.json')
        write_new(output / 'source-pins.json', pins)
        report.update(state='PREPARED_NOT_BUILT', source=str(source),
                      archive_inventory_sha256=sha(output / 'archive-inventory.json'),
                      excluded_archive_member=archive_policy.SKIP_NAME,
                      inherited_source_count=len(inherited),
                      source_pins_sha256=sha(output / 'source-pins.json'),
                      qbs_implementation_bytes_unchanged=True,
                      configure_argv=[str(source / 'configure'), *CONFIGURE],
                      build_argv=['ninja', '-j4', 'qemu-system-riscv64'])
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        write_new(output / 'prepare.json', report)
    return report


def bounded(argv, cwd, timeout, log, receipts, environment):
    row = dict(argv=[str(x) for x in argv], cwd=str(cwd), timeout=timeout,
               started_ns=time.time_ns(), state='RUNNING')
    receipts.append(row)
    with log.open('xb') as stream:
        process = subprocess.Popen(row['argv'], cwd=cwd, env=environment,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        row['pid'] = process.pid
        try:
            row['returncode'] = process.wait(timeout=timeout)
            row['state'] = 'EXITED'
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            row['state'] = 'INTERRUPTED_OR_TIMEOUT'
            raise
        finally:
            row['ended_ns'] = time.time_ns()
            row['log_sha256'] = sha(log)
    require(row['returncode'] == 0, 'Build command failed; preserve ' + str(log))


def service_owner(unit):
    require(re.fullmatch(r'stage5-qemu-build-[A-Za-z0-9_-]+\.service', unit),
            'Owned transient service name required')
    invocation = os.environ.get('INVOCATION_ID', '')
    require(re.fullmatch(r'[0-9a-f]{32}', invocation), 'Not running in a systemd invocation')
    cgroup = Path('/proc/self/cgroup').read_text()
    require('/' + unit in cgroup, 'Worker is not in the named service cgroup')
    mainpid = subprocess.run(
        ['systemctl', '--user', 'show', unit, '--property=MainPID', '--value'],
        check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    require(mainpid == str(os.getpid()), 'Service must own this build worker directly')
    return dict(unit=unit, main_pid=os.getpid(), invocation_id=invocation, cgroup=cgroup)


def build(args):
    owner = service_owner(args.service)
    prepared = Path(args.prepared).resolve()
    require(sha(prepared / 'prepare.json') == args.reviewed_prepare_sha256,
            'Unreviewed preparation receipt')
    receipt = read(prepared / 'prepare.json')
    require(receipt['schema'] == 'stage5-qemu-prepare-v2' and
            receipt['state'] == 'PREPARED_NOT_BUILT', 'Preparation not accepted')
    require(sha(prepared / 'source-pins.json') == receipt['source_pins_sha256'], 'Pin inventory drift')
    pins = read(prepared / 'source-pins.json')
    verify(pins)
    source = Path(receipt['source'])
    require(source == prepared / 'qemu-10.2.0', 'Prepared source path escaped')
    inventory = read(prepared / 'tree-inventory.json')
    verify_membership(tree_inventory(source) | tree_inventory(prepared / 'inputs'), inventory)
    # The executed recipe/overlay must themselves be the reviewed copies.
    require(sha(__file__) == pins[str(prepared / 'inputs/recipe_v2.py')] and
            sha(overlay.__file__) == pins[str(prepared / 'inputs/overlay.py')] and
            sha(archive_policy.__file__) == pins[str(prepared / 'inputs/archive_policy_v2.py')], 'Build helper drift')
    output = fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v2', state='FAIL', commands=[],
                  predecessor_recipe_sha256=PREDECESSOR_SHA,
                  service_owner=owner,
                  prepare_sha256=args.reviewed_prepare_sha256,
                  guest_executed=False, required_execution_gates=GATES)
    try:
        tools = {name: str(Path(shutil.which(name, path='/usr/bin:/bin') or '/nonexistent').resolve(strict=True))
                 for name in ('gcc', 'g++', 'ninja')}
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        environment = build_environment(output, tools)
        report['environment'] = environment
        report['tool_pins'] = {p: sha(p) for p in tools.values()}
        bounded(receipt['configure_argv'], output, 900, output / 'configure.log',
                report['commands'], environment)
        bounded([tools['ninja'], '-j4', 'qemu-system-riscv64'], output, 1800,
                output / 'build.log', report['commands'], environment)
        verify(pins)
        verify_membership(tree_inventory(source) | tree_inventory(prepared / 'inputs'), inventory)
        verify(report['tool_pins'])
        require(service_owner(args.service) == owner, 'Service ownership changed')
        report.update(state='BUILT_NOT_EXECUTED', executable=str(output / 'qemu-system-riscv64'),
                      executable_sha256=sha(output / 'qemu-system-riscv64'),
                      post_pins_match=True)
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        write_new(output / 'build.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('identity', help='Read-only input identity; no preparation/build')
    prep = commands.add_parser('prepare')
    prep.add_argument('--archive', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--reviewed-inputs-sha256', required=True)
    run = commands.add_parser('build')
    run.add_argument('--prepared', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--reviewed-prepare-sha256', required=True)
    run.add_argument('--service', required=True)
    args = parser.parse_args()
    result = identity() if args.command == 'identity' else globals()[args.command](args)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
