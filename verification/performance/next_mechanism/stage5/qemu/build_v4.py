#!/usr/bin/env python3
"""Build-only successor: accepted prepare03, explicit Python/Ninja, no extraction."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PREPARED = OUT / 'stage5_qemu_prepare_20261110_03'
PREPARE_SHA = 'a947e2ebcaab10fbcb0480275746665e4ddcf2381a8282ebd66b7d239f3e6ea5'
REVIEW_SHA = '0b091570f4af0f07f45791ec25b97a554dcb1ec4fe29d3aa99de60291037ee23'
OLD_BUILD = OUT / 'qemu-context-20261023-01/qemu-10.2.0-build'
OWN = ('build_v4.py', 'test_build_v4.py', 'BUILD_V4.md')
PYTHON = '/usr/bin/python3.11'
NINJA = '/usr/bin/ninja'
PKGDIR = '/usr/lib64/pkgconfig:/usr/share/pkgconfig'
PKG_WRAPPERS = {
    Path('/usr/bin/pkg-config'): ('/usr/bin/sh', '/usr/bin/rpm',
                                  '/usr/bin/x86_64-redhat-linux-gnu-pkg-config'),
    Path('/usr/bin/x86_64-redhat-linux-gnu-pkg-config'): ('/usr/bin/sh', '/usr/bin/pkgconf'),
}
HELPERS = {
    'recipe_v3.py': '4b51be15693edbd7c83c101bd708b9ff4840a31ed44b5972191a2a69af0f84c3',
    'overlay.py': 'c9c9bf3e2d10f6b94c763ef030a601f54116a9aead9b906466214c927f5442dc',
    'archive_policy_v2.py': 'acaa7371df81768543c91fa705910d285cde34664b0c8f4c6b33e7c692d7c37b',
    'reconstruction_policy_v3.py': 'a32110ae98a85610de7159caf1ba66346e3ed2b5a1f47971c9988eb05fdd3bf2',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
        return h.hexdigest()


def base():
    for name, digest in HELPERS.items():
        require(sha(PREPARED / 'inputs' / name) == digest, 'Sealed helper drift: ' + name)
    sys.path.insert(0, str(PREPARED / 'inputs'))
    module = importlib.import_module('recipe_v3')
    for name in ('recipe_v3', 'overlay', 'archive_policy_v2', 'reconstruction_policy_v3'):
        require(sha(sys.modules[name].__file__) == HELPERS[name + '.py'], 'Imported helper drift')
    return module


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked_prepared():
    r = base()
    require(sha(PREPARED / 'prepare.json') == PREPARE_SHA, 'Unaccepted prepared source')
    receipt = r.read(PREPARED / 'prepare.json')
    require(receipt['schema'] == 'stage5-qemu-prepare-v3' and
            receipt['state'] == 'PREPARED_NOT_BUILT' and
            receipt['source_review_sha256'] == REVIEW_SHA and
            receipt['source'] == str(PREPARED / 'qemu-10.2.0') and
            receipt['configure_argv'] == [str(PREPARED / 'qemu-10.2.0/configure'), *r.CONFIGURE],
            'Prepared contract changed')
    require(sha(PREPARED / 'source-pins.json') == receipt['source_pins_sha256'], 'Prepared pins drift')
    pins = r.read(PREPARED / 'source-pins.json')
    r.verify(pins)
    r.verify_membership(r.tree_inventory(Path(receipt['source'])) |
                        r.tree_inventory(PREPARED / 'inputs'), r.read(PREPARED / 'tree-inventory.json'))
    return receipt


def environment(output):
    return dict(PATH='/usr/bin:/bin', HOME=str(output / 'home'), TMPDIR=str(output / 'tmp'),
                LANG='C', LC_ALL='C', CC='/usr/bin/gcc', CXX='/usr/bin/g++',
                PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                PKG_CONFIG='/usr/bin/pkg-config', PKG_CONFIG_LIBDIR=PKGDIR)


def configure_argv(receipt):
    return [*receipt['configure_argv'], '--python=' + PYTHON, '--ninja=' + NINJA]


def query(argv, env, cwd, rows):
    started = time.time_ns()
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=20)
    rows.append(dict(argv=argv, cwd=str(cwd), timeout=20, started_ns=started,
                     ended_ns=time.time_ns(), returncode=result.returncode,
                     stdout=result.stdout, stderr=result.stderr))
    require(result.returncode == 0, 'Prerequisite query failed: ' + repr(argv) + ': ' + result.stderr)
    return result.stdout.strip()


def classify_tools(paths):
    """Expand the two known pkg-config wrappers; only ELF files go to ldd."""
    pending, result = list(map(Path, paths)), {}
    while pending:
        path = pending.pop()
        if str(path) in result:
            continue
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic == b'\x7fELF':
            result[str(path)] = dict(kind='elf', sha256=sha(path))
        else:
            require(path in PKG_WRAPPERS and path.read_text().splitlines()[0] == '#!/usr/bin/sh',
                    'Unreviewed non-ELF tool: ' + str(path))
            result[str(path)] = dict(kind='wrapper', sha256=sha(path), dependencies=list(PKG_WRAPPERS[path]))
            pending.extend(Path(p) for p in PKG_WRAPPERS[path])
    return result


PYTHON_PROBE = r'''
import importlib, importlib.metadata as md, json, pathlib, sys, tomllib
import pip._vendor.distlib.scripts, pip._vendor.packaging.version
import mesonbuild, pycotap
spec = tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
assert spec['meson']['meson']['installed'] == '1.9.0'
assert spec['meson']['pycotap']['installed'] == '1.3.1'
assert md.version('meson') == '1.9.0' and md.version('pycotap') == '1.3.1'
assert sys.version_info[:2] == (3, 11)
files = set()
for name in ('pip', 'setuptools', 'meson', 'pycotap'):
    dist = md.distribution(name)
    for item in dist.files or ():
        p = pathlib.Path(dist.locate_file(item))
        if p.is_file() and p.suffix != '.pyc': files.add(str(p.resolve()))
for module in tuple(sys.modules.values()):
    p = getattr(module, '__file__', None)
    if p and pathlib.Path(p).is_file() and not p.endswith('.pyc'):
        files.add(str(pathlib.Path(p).resolve()))
print(json.dumps(dict(version=sys.version, executable=sys.executable,
    packages={name:md.version(name) for name in ('pip','setuptools','meson','pycotap')},
    tomllib=tomllib.__file__, sys_path=sys.path, files=sorted(files))))
'''


def preflight(output):
    r = base()
    own, review = identity()
    output = r.fresh(output, 'stage5_qemu_toolenv_')
    report = dict(schema='stage5-qemu-toolenv-v4', state='FAIL', commands=[], queries=[],
                  prepare_sha256=PREPARE_SHA, files=own, source_review_sha256=review,
                  configure_executed=False, qemu_compiled=False, guest_executed=False)
    try:
        prepared = checked_prepared()
        source = Path(prepared['source'])
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        env = environment(output)
        report['environment'] = env
        mkvenv = str(source / 'python/scripts/mkvenv.py')
        # Exercise the exact offline bootstrap configure uses, without configure/C probes.
        r.bounded([PYTHON, '-B', mkvenv, 'create', 'pyvenv'], output, 90,
                  output / 'venv.log', report['commands'], env)
        child = str(output / 'pyvenv/bin/python3')
        r.bounded([child, '-B', mkvenv, 'ensuregroup', '--dir', str(source / 'python/wheels'),
                   str(source / 'pythondeps.toml'), 'meson'], output, 90,
                  output / 'wheels.log', report['commands'], env)
        probe = json.loads(query([child, '-B', '-c', PYTHON_PROBE, str(source / 'pythondeps.toml')],
                                 env, output, report['queries']))
        require(probe['executable'] == child, 'Wrong preflight interpreter')
        report['python'] = probe
        inputs = {Path(p) for p in probe['files']}
        inputs.update(source / 'python/wheels' / name for name in
                      ('meson-1.9.0-py3-none-any.whl', 'pycotap-1.3.1-py3-none-any.whl'))
        inputs.update((source / 'pythondeps.toml', source / 'python/scripts/mkvenv.py',
                       OLD_BUILD / 'meson-info/intro-dependencies.json', OLD_BUILD / 'pyvenv/pyvenv.cfg'))
        deps = r.read(OLD_BUILD / 'meson-info/intro-dependencies.json')
        packages = {d['name']: d['version'] for d in deps if d['type'] == 'pkgconfig'}
        require(len(packages) == 15 and packages['glib-2.0'] == '2.68.4' and
                packages['pixman-1'] == '0.40.0' and packages['zlib'] == '1.2.11',
                'Accepted dependency baseline changed')
        packages.update({'gmodule-no-export-2.0': '2.68.4', 'gmodule-export-2.0': '2.68.4'})
        report['pkg_config'] = {}
        pending, seen = set(packages), set()
        while pending:
            name = sorted(pending)[0]
            pending.remove(name)
            seen.add(name)
            args = ['/usr/bin/pkg-config']
            version = query(args + ['--modversion', name], env, output, report['queries'])
            if name in packages:
                require(version == packages[name], 'Accepted dependency version drift: ' + name)
            flags = query(args + ['--cflags', '--libs', name], env, output, report['queries'])
            pcdir = query(args + ['--variable=pcfiledir', name], env, output, report['queries'])
            pc = Path(pcdir) / (name + '.pc')
            require(str(pc.parent) in PKGDIR.split(':'), 'Unreviewed pkg-config prefix')
            inputs.add(pc)
            report['pkg_config'][name] = dict(version=version, flags=flags, pc=str(pc))
            requires = query(args + ['--print-requires', '--print-requires-private', name],
                             env, output, report['queries'])
            pending.update(line.split()[0] for line in requires.splitlines() if line.split()[0] not in seen)
        # Pin actual selected libraries and their runtime closure, not ambient search variables.
        for dep in deps:
            for value in dep.get('link_args', []):
                if value.startswith('/'):
                    inputs.add(Path(value))
        tools = ('python3.11', 'ninja', 'pkg-config', 'gcc', 'g++', 'as', 'ld', 'ar',
                 'nm', 'ranlib', 'readelf', 'strip', 'make', 'sh', 'ldd')
        tool_paths = [Path('/usr/bin') / name for name in tools]
        for path in tool_paths:
            require(path.is_file(), 'Missing build tool: ' + str(path))
            inputs.add(path)
        report['tool_versions'] = {name: query(['/usr/bin/' + name, '--version'], env, output,
                                             report['queries']).splitlines()[0]
                                   for name in ('python3.11', 'ninja', 'pkg-config', 'gcc', 'g++')}
        require(sha(OLD_BUILD / 'qemu-system-riscv64') == r.BINARY_SHA, 'Old accepted binary drift')
        require(query(['/usr/bin/rpm', '--eval', '%{_target_cpu}-%{_vendor}-%{_target_os}%{?_gnu}'],
                      env, output, report['queries']) == 'x86_64-redhat-linux-gnu',
                'pkg-config wrapper selected an unreviewed platform')
        classified = classify_tools([*tool_paths[:5], OLD_BUILD / 'qemu-system-riscv64'])
        report['tool_classification'] = classified
        inputs.update(Path(p) for p in classified)
        for path, item in classified.items():
            if item['kind'] != 'elf':
                continue
            text = query(['/usr/bin/ldd', path], env, output, report['queries'])
            require('not found' not in text, 'Unresolved native dependency')
            inputs.update(Path(p) for p in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', text, re.M))
        for header in ('/usr/include/glib-2.0/glib.h', '/usr/lib64/glib-2.0/include/glibconfig.h',
                       '/usr/include/pixman-1/pixman.h', '/usr/include/zlib.h'):
            inputs.add(Path(header))
        pins = {str(p): sha(p) for p in sorted(inputs)}
        pins.update({str(p.resolve()): sha(p.resolve()) for p in sorted(inputs)})
        r.write_new(output / 'tool-pins.json', pins)
        report.update(tool_pins_sha256=sha(output / 'tool-pins.json'),
                      pkg_config_libdir=PKGDIR, library_paths=sorted(p for p in pins if '.so' in p or p.endswith('.a')),
                      configure_argv=configure_argv(prepared), build_argv=[NINJA, '-j4', 'qemu-system-riscv64'],
                      docs_group='disabled', testdeps_group='not used by qemu-system-riscv64 target',
                      rust_group='not selected: no rustc on minimal PATH', state='TOOLENV_READY_NOT_BUILT')
        checked_prepared()
        require(identity() == (own, review), 'Successor changed during preflight')
        r.verify(pins)
    except BaseException as exc:
        report['state'] = 'FAIL'
        report['error'] = repr(exc)
        raise
    finally:
        report['artifacts'] = r.tree_pins(output)
        r.write_new(output / 'toolenv.json', report)
    return report


def checked_toolenv(path, digest):
    r = base()
    path = Path(path).resolve(strict=True)
    require(sha(path / 'toolenv.json') == digest, 'Unreviewed tool environment')
    report = r.read(path / 'toolenv.json')
    require(report['schema'] == 'stage5-qemu-toolenv-v4' and report['state'] == 'TOOLENV_READY_NOT_BUILT' and
            report['prepare_sha256'] == PREPARE_SHA and identity() == (report['files'], report['source_review_sha256']),
            'Tool environment scope/source drift')
    require(sha(path / 'tool-pins.json') == report['tool_pins_sha256'], 'Tool pin inventory drift')
    r.verify(r.read(path / 'tool-pins.json'))
    r.verify(report['artifacts'])
    return report


def build(args):
    r = base()
    owner = r.service_owner(args.service)
    preflight_report = checked_toolenv(args.toolenv, args.reviewed_toolenv_sha256)
    prepared = checked_prepared()
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v4', state='FAIL', commands=[], service_owner=owner,
                  prepare_sha256=PREPARE_SHA, prepared=str(PREPARED),
                  preflight=str(Path(args.toolenv).resolve()), preflight_sha256=args.reviewed_toolenv_sha256,
                  source_review_sha256=identity()[1], guest_executed=False, required_execution_gates=r.GATES)
    try:
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        env = environment(output)
        report['environment'] = env
        require(configure_argv(prepared) == preflight_report['configure_argv'], 'Configure argv drift')
        r.bounded(configure_argv(prepared), output, 900, output / 'configure.log', report['commands'], env)
        r.bounded([NINJA, '-j4', 'qemu-system-riscv64'], output, 1800,
                  output / 'build.log', report['commands'], env)
        checked_prepared()
        checked_toolenv(args.toolenv, args.reviewed_toolenv_sha256)
        require(r.service_owner(args.service) == owner, 'Build service ownership changed')
        report.update(state='BUILT_NOT_EXECUTED', executable=str(output / 'qemu-system-riscv64'),
                      executable_sha256=sha(output / 'qemu-system-riscv64'), post_pins_match=True)
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        r.write_new(output / 'build.json', report)
    return report


def checked_build(build_dir, reviewed_build_sha256):
    """Shared read-only image admission API for directed and full-call launchers."""
    r = base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v4' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['prepare_sha256'] == PREPARE_SHA and report['prepared'] == str(PREPARED) and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            report['source_review_sha256'] == identity()[1] and report['required_execution_gates'] == r.GATES,
            'Build not admitted')
    prepared = checked_prepared()
    checked_toolenv(report['preflight'], report['preflight_sha256'])
    require(report['environment'] == environment(path), 'Build environment drift')
    commands = report['commands']
    require(len(commands) == 2, 'Missing/extra build commands')
    for row, argv, timeout, name in zip(commands,
            (configure_argv(prepared), [NINJA, '-j4', 'qemu-system-riscv64']),
            (900, 1800), ('configure.log', 'build.log')):
        require(row['argv'] == argv and row['cwd'] == str(path) and row['timeout'] == timeout and
                row['state'] == 'EXITED' and row['returncode'] == 0 and row['pid'] > 0 and
                row['started_ns'] < row['ended_ns'] and row['log_sha256'] == sha(path / name),
                'Build execution receipt mismatch')
    require(commands[0]['ended_ns'] <= commands[1]['started_ns'], 'Overlapping build steps')
    owner = report['service_owner']
    require(re.fullmatch(r'stage5-qemu-build-[A-Za-z0-9_-]+\.service', owner['unit']) and
            owner['main_pid'] > 0 and re.fullmatch('[0-9a-f]{32}', owner['invocation_id']) and
            '/' + owner['unit'] in owner['cgroup'], 'Build service ownership receipt invalid')
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('identity')
    check = sub.add_parser('preflight')
    check.add_argument('--output', type=Path, required=True)
    run = sub.add_parser('build')
    for name in ('toolenv', 'output'):
        run.add_argument('--' + name, type=Path, required=True)
    run.add_argument('--reviewed-toolenv-sha256', required=True)
    run.add_argument('--service', required=True)
    args = p.parse_args()
    value = identity() if args.command == 'identity' else preflight(args.output) if args.command == 'preflight' else build(args)
    print(json.dumps(value, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
