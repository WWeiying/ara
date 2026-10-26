#!/usr/bin/env python3
"""Read-only GNU/Buildroot tool discovery and before/after identity verification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BIN = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
FLAGS = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-static', '-pthread']
ENV = dict(PATH='/usr/bin:/bin', HOME='/', LANG='C', LC_ALL='C', TMPDIR='/tmp',
           BR2_DEBUG_WRAPPER='2', BR2_USE_CCACHE='0', CCACHE_DISABLE='1')
TEMP = re.compile(r'/tmp/cc[A-Za-z0-9_]+\.(?:s|o|res)\b')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def links(path):
    """Include directory symlinks as well as the final executable alias."""
    path = Path(path)
    require(path.is_absolute(), 'Expected absolute path: ' + str(path))
    current, pending, result = Path('/'), list(path.parts[1:]), []
    while pending:
        part = pending.pop(0)
        if part == '..':
            current = current.parent
            continue
        candidate = current / part
        if candidate.is_symlink():
            require(len(result) < 40, 'Symlink cycle/depth limit')
            target = os.readlink(candidate)
            result.append(dict(path=str(candidate), target=target))
            target = Path(target)
            if target.is_absolute():
                current = Path('/')
                pending = list(target.parts[1:]) + pending
            else:
                pending = list(target.parts) + pending
        else:
            current = candidate
    return current, result


def identity(path):
    resolved, chain = links(path)
    before = resolved.stat()
    require(stat.S_ISREG(before.st_mode), 'Not a regular file: ' + str(path))
    value = digest(resolved)
    after = resolved.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
            links(path) == (resolved, chain), 'File changed while hashing: ' + str(path))
    return dict(resolved=str(resolved), symlinks=chain, sha256=value,
                bytes=after.st_size, mode=stat.S_IMODE(after.st_mode))


def verify_files(files):
    require(type(files) is dict and bool(files), 'Empty file inventory')
    for path, expected in files.items():
        require(identity(path) == expected, 'File/symlink identity changed: ' + path)


def absolute_answer(text):
    value = text.strip()
    require(bool(value) and '\n' not in value and Path(value).is_absolute(),
            'GNU did not resolve an absolute path: ' + repr(value))
    return Path(value)


def parse_plan(text, frontend):
    real = re.findall(r'^COLLECT_GCC=(.+)$', text, re.M)
    require(len(real) == 1, 'Missing/duplicate actual GNU driver')
    real = absolute_answer(real[0])
    wrapper = text.split('Toolchain wrapper executing:\n')
    if len(wrapper) == 2:
        first = shlex.split(wrapper[1].splitlines()[0].strip())
        require(first == [str(real)], 'Wrapper did not directly execute reported real driver')
    else:
        require(len(wrapper) == 1, 'Multiple wrapper executions')
    commands = []
    for line in text.splitlines():
        if not line.startswith(' /'):
            continue
        argv = shlex.split(line)
        require(argv and Path(argv[0]).is_absolute(), 'Malformed dry-run command')
        commands.append(argv)
    require([Path(c[0]).name for c in commands] == [frontend, 'as', 'collect2'],
            'Unexpected compiler/assembler/link plan')
    link = commands[-1]
    require('-static' in link and '-o' in link and link[link.index('-o') + 1] == '/dev/null',
            'Dry-run is not the requested static link')
    startup = [x for x in link if x.endswith('.o') and Path(x).is_absolute() and not TEMP.fullmatch(x)]
    require({Path(p).name for p in startup} == {'crt1.o', 'crti.o', 'crtbeginT.o', 'crtend.o', 'crtn.o'},
            'Unexpected static startup selection')
    libraries = sorted({x[2:] for x in link if re.fullmatch(r'-l[A-Za-z0-9_+.-]+', x)})
    require({'c', 'm', 'dl', 'gcc', 'gcc_eh', 'pthread'} <= set(libraries), 'Missing static runtime libraries')
    if frontend == 'cc1plus':
        require('stdc++' in libraries, 'Missing C++ runtime')
    extras = []
    for i, arg in enumerate(link):
        if arg == '-plugin':
            require(i + 1 < len(link), 'Truncated plugin option')
            extras.append(str(absolute_answer(link[i + 1])))
        if arg.startswith('-plugin-opt=') and Path(arg[len('-plugin-opt='):]).is_absolute():
            extras.append(str(absolute_answer(arg[len('-plugin-opt='):])))
    temporaries = {}

    def temporary(match):
        name = match[0]
        if name not in temporaries:
            temporaries[name] = '<gcc-temporary-' + str(len(temporaries)) + Path(name).suffix + '>'
        return temporaries[name]

    return dict(real_driver=str(real), wrapper_reported=len(wrapper) == 2,
                commands=[[TEMP.sub(temporary, arg) for arg in row] for row in commands],
                startup=startup, libraries=libraries, extras=extras)


def discover(gcc, gxx, output):
    files, drivers, queries = {}, {}, []

    def pin(path, executable=False):
        path = str(path)
        value = identity(path)
        require(path not in files or files[path] == value, 'Input changed during discovery')
        require(not executable or value['mode'] & 0o111, 'Not executable: ' + path)
        files[path] = value
        return Path(value['resolved'])

    def query(driver, arguments):
        argv = [str(driver), *FLAGS, *arguments]
        result = subprocess.run(argv, env=ENV, cwd=output, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        queries.append(dict(argv=argv, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        require(result.returncode == 0, 'GNU query failed: ' + shlex.join(argv))
        return result

    pin(Path(__file__).resolve())
    pin(Path(sys.executable).resolve(), True)
    for label, driver, language, frontend in (('gcc', gcc, 'c', 'cc1'), ('gxx', gxx, 'c++', 'cc1plus')):
        driver = Path(driver).absolute()
        pin(driver, True)
        sysroot = absolute_answer(query(driver, ['-print-sysroot']).stdout)
        require(sysroot.is_dir(), 'Missing target sysroot')
        sysroot_real, sysroot_links = links(sysroot)
        target = query(driver, ['-dumpmachine']).stdout.strip()
        require(target.startswith('riscv64-') and 'linux' in target, 'Wrong target triple')
        version = query(driver, ['-dumpfullversion']).stdout.strip()
        require(re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version), 'Unexpected GNU version')
        specs = query(driver, ['-dumpspecs']).stdout
        require('*link:' in specs and '*startfile:' in specs, 'Incomplete GNU specs')
        dry = query(driver, ['-###', '-x', language, '/dev/null', '-lm', '-ldl', '-o', '/dev/null'])
        plan = parse_plan(dry.stderr, frontend)
        pin(plan['real_driver'], True)
        if plan['wrapper_reported']:
            require(plan['real_driver'].endswith('.br_real'), 'Unexpected Buildroot driver spelling')
            sdk_wrapper = Path(plan['real_driver'][:-len('.br_real')])
            require(pin(sdk_wrapper, True) == pin(driver, True), 'SDK and invocation wrappers differ')
        programs = {}
        for name in (frontend, 'as', 'ld', 'collect2', 'lto-wrapper'):
            path = absolute_answer(query(driver, ['-print-prog-name=' + name]).stdout)
            pin(path, True)
            programs[name] = str(path)
        for row in plan['commands']:
            require(Path(row[0]).resolve(strict=True) == Path(programs[Path(row[0]).name]).resolve(strict=True),
                    'Dry-run tool differs from queried tool')
            pin(row[0], True)
        for path in plan['extras']:
            pin(path)
        selected = {}
        for name in [*map(lambda p: Path(p).name, plan['startup']), *('lib' + n + '.a' for n in plan['libraries'])]:
            path = absolute_answer(query(driver, ['-print-file-name=' + name]).stdout)
            resolved = pin(path)
            if name.endswith('.a'):
                with resolved.open('rb') as stream:
                    require(stream.read(8) == b'!<arch>\n', 'Not a self-contained static archive: ' + str(path))
            selected[name] = str(path)
        for path in plan['startup']:
            require(Path(selected[Path(path).name]).resolve(strict=True) == Path(path).resolve(strict=True),
                    'Dry-run startup differs from query')
            pin(path)
        for name in ('libc.a', 'libm.a', 'libpthread.a', 'libdl.a', 'crt1.o'):
            require(Path(selected[name]).resolve(strict=True).is_relative_to(sysroot_real),
                    'Target libc/startup escaped sysroot: ' + name)
        drivers[label] = dict(invoked=str(driver), sysroot=str(sysroot), resolved_sysroot=str(sysroot_real),
            sysroot_symlinks=sysroot_links, target=target, version=version, programs=programs,
            selected_files=selected, specs_sha256=hashlib.sha256(specs.encode()).hexdigest(), plan=plan)
    require(drivers['gcc']['resolved_sysroot'] == drivers['gxx']['resolved_sysroot'] and
            drivers['gcc']['target'] == drivers['gxx']['target'] and drivers['gcc']['version'] == drivers['gxx']['version'],
            'C and C++ SDKs differ')
    verify_files(files)
    return dict(schema='quantkv_gnu_toolchain_inventory_v1', flags=FLAGS, environment=ENV,
                drivers=drivers, files=files, compiler_executed_queries_only=True,
                frontend_assembler_linker_executed=False, qemu_abi_proof=False,
                scope='Fixed RV64 Linux static C/C++ link probe, not a full model/header/dynamic-library manifest'), queries


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def run(output, gcc=None, gxx=None, inventory=None):
    output = Path(output).absolute()
    require(output == output.resolve() and not output.exists(), 'Use a fresh non-aliased output directory')
    previous = None
    if inventory:
        inventory = Path(inventory).resolve(strict=True)
        previous_sha = digest(inventory)
        previous = json.loads(inventory.read_text())
        require(previous.get('schema') == 'quantkv_gnu_toolchain_inventory_v1' and
                previous.get('flags') == FLAGS and previous.get('environment') == ENV, 'Wrong inventory contract')
        verify_files(previous['files'])
        gcc, gxx = (previous['drivers'][key]['invoked'] for key in ('gcc', 'gxx'))
    output.mkdir(parents=True)
    try:
        current, queries = discover(gcc or BIN / 'riscv64-linux-gcc', gxx or BIN / 'riscv64-linux-g++', output)
        write_json(output / 'queries.json', queries)
        write_json(output / 'inventory.json', current)
        if previous is not None:
            require(current == previous, 'Toolchain selection/specs/files changed since capture')
            require(digest(inventory) == previous_sha, 'Prior inventory changed during verification')
        verify_files(current['files'])
        result = dict(state='PASS', mode='verify' if previous else 'capture', file_entries=len(current['files']),
                      inventory_sha256=digest(output / 'inventory.json'), queries_sha256=digest(output / 'queries.json'),
                      source_sha256=digest(Path(__file__).resolve()), pre_post_files_match=True,
                      qemu_abi_proof=False, compilation_or_link_execution=False, eda_invocations=0)
        if previous is not None:
            result.update(previous_inventory=str(inventory), previous_inventory_sha256=previous_sha)
        write_json(output / 'result.json', result)
        return result
    except BaseException as error:
        write_json(output / 'result.json', dict(state='FAIL', error=repr(error), qemu_abi_proof=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_subparsers(dest='mode', required=True)
    capture = mode.add_parser('capture', allow_abbrev=False)
    capture.add_argument('--gcc', type=Path, default=BIN / 'riscv64-linux-gcc')
    capture.add_argument('--gxx', type=Path, default=BIN / 'riscv64-linux-g++')
    capture.add_argument('--output', type=Path, required=True)
    check = mode.add_parser('verify', allow_abbrev=False)
    check.add_argument('--inventory', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    args = vars(parser.parse_args())
    args.pop('mode')
    print(json.dumps(run(**args), sort_keys=True))
