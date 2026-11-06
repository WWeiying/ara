#!/usr/bin/env python3
"""Rebuild only sealed qbs.cpp and replace its member in a copied model archive.

No RTL, CMake rebuild, target execution, or working-checkout dependency is used.
Trace environment flags must remain fixed within each blocking context; they
are refreshed at the next context, not midway through one.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
MODEL = VERIFY / 'verification/out/e2e_output_model_20261106_01'
GRAPH = VERIFY / 'verification/out/e2e_output_graph_20261106_01'
OUTPUT = VERIFY / 'verification/out/e2e_trace_context_library_20261106_01'
TOOLCHAIN = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host')
SOURCE = 'ggml/src/ggml-cpu/arch/riscv/qbs.cpp'
MEMBER = 'qbs.cpp.o'
BEFORE = '43a86cfd658b3a94817077b8e3cc20eb08f948113bcbc841f449e1279d913f6e'
AFTER = '9aa982ff55414f92d8fc10df8b09cc29eb013dcd2b81deadcbed99216158c8f9'
PATCH = '308ad1ce11ffd899f9835cbf23b243d681b740cbf13996e690a491d743c6e83e'
LIBRARY = 'ddd71e17273789a7f60cc435d392829b5768addea6719b405a04d9d215f9ccc4'
RECEIPT = '5473539c53b687dac3fe4d8cc2b56547ae2f1cf3ec9ad012bf29cc3b0e83fd02'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def dependencies(text, cwd):
    """Parse GCC's single-target make dependency rule (including escaped spaces)."""
    text = text.replace('\\\n', ' ')
    require(':' in text, 'Missing dependency target')
    target, body = text.split(':', 1)
    require(target.strip() and '\n' not in body.strip(), 'Expected one dependency rule')
    paths = [((cwd / p) if not Path(p).is_absolute() else Path(p)).resolve(strict=True)
             for p in shlex.split(body)]
    require(paths, 'Empty dependency closure')
    return set(paths)


def command_entry(entries, source):
    matches = [e for e in entries if e['file'].endswith('/arch/riscv/qbs.cpp')]
    require(len(matches) == 1, 'Missing/ambiguous qbs compile command')
    entry = matches[0]
    require(Path(entry['file']) == source, 'Compile source is not sealed graph input')
    argv = entry.get('arguments') or shlex.split(entry['command'])
    require(argv.count('-c') == argv.count('-o') == 1, 'Ambiguous compile/output options')
    require(argv[argv.index('-c') + 1] == str(source), 'Compile operand differs')
    require(Path(argv[0]).is_absolute(), 'Compiler must be absolute')
    for arg in argv[1:]:
        require(not arg.startswith(('@', '-fplugin', '-specs', '--sysroot', '-B', '-M')),
                'Unsupported side input/output option: ' + arg)
        require(arg not in ('-include', '-imacros', '-isystem', '-I', '-iquote') and
                arg not in (';', '&&', '|', '>', '<'), 'Unsupported command token: ' + arg)
    return entry, list(argv)


def remap_command(argv, graph, inputs, obj):
    result = list(argv)
    for i, arg in enumerate(argv):
        if arg.startswith('-I'):
            path = Path(arg[2:]).resolve(strict=True)
            roots = [graph / 'llama', graph / 'sdk']
            require(any(path.is_relative_to(r) for r in roots),
                    'Include outside sealed llama/SDK: ' + str(path))
            result[i] = '-I' + str(inputs / path.relative_to(graph))
    result[result.index('-c') + 1] = str(inputs / 'llama' / SOURCE)
    result[result.index('-o') + 1] = str(obj)
    return result


def archive_members(data):
    """Read regular GNU ar payloads in order, preserving duplicate names."""
    require(data.startswith(b'!<arch>\n'), 'Expected regular archive, not thin/BSD')
    offset, table, members = 8, b'', []
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:] == b'`\n', 'Malformed archive header')
        name = header[:16].decode('ascii').rstrip()
        size = int(header[48:58])
        require(size >= 0, 'Negative member size')
        start = offset + 60
        payload = data[start:start + size]
        require(len(payload) == size and start + size + size % 2 <= len(data),
                'Truncated archive member')
        offset = start + size + size % 2
        if name == '//':
            table = payload
        elif name not in ('/', '/SYM64/'):
            if name.startswith('/'):
                index = int(name[1:])
                end = table.find(b'/\n', index)
                require(0 <= index < len(table) and end >= index, 'Bad long-name reference')
                name = table[index:end].decode('utf-8')
            else:
                require(name.endswith('/') and not name.startswith('#1/'), 'Unsupported archive name')
                name = name[:-1]
            require(name and '/' not in name, 'Non-basename member')
            members.append((name, payload))
    require(members, 'Empty archive')
    return members


def compare_archives(before, after, replacement):
    require([n for n, _ in before] == [n for n, _ in after], 'Archive inventory/order changed')
    require(sum(n == MEMBER for n, _ in before) == 1, 'Missing/duplicate qbs member')
    evidence = []
    for i, ((name, old), (_, new)) in enumerate(zip(before, after)):
        if name == MEMBER:
            require(new == replacement and old != new, 'Stale/wrong qbs object in archive')
        else:
            require(old == new, 'Other member changed at index ' + str(i) + ': ' + name)
        evidence.append(dict(index=i, name=name, bytes_before=len(old), bytes_after=len(new),
                             before_sha256=sha(old), after_sha256=sha(new), changed=old != new))
    return evidence


def exports(text):
    symbols = Counter()
    for line in text.splitlines():
        if not line.strip() or line.endswith(':'):
            continue
        fields = line.split()
        require(len(fields) >= 2 and len(fields[1]) == 1, 'Malformed nm output: ' + line)
        symbols[(fields[0], fields[1])] += 1
    require(symbols, 'Empty global definition set')
    return symbols


class Build:
    def __init__(self, out):
        self.out, self.pins, self.commands, self.identities = out, {}, [], {}
        self.environment = dict(PATH='/usr/bin:/bin', LC_ALL='C', HOME=str(out / 'home'),
                                TMPDIR=str(out / 'tmp'), PYTHONDONTWRITEBYTECODE='1')
        for name in ('home', 'tmp', 'inputs', 'objects', 'lib'):
            (out / name).mkdir()

    def pin(self, path, expected=None):
        lexical = Path(path).absolute()
        path = lexical.resolve(strict=True)
        value = digest(path)
        require(expected is None or value == expected, 'Pinned identity differs: ' + str(path))
        require(str(path) not in self.pins or self.pins[str(path)] == value,
                'Input drift: ' + str(path))
        self.pins[str(path)] = value
        self.identities[str(lexical)] = str(path)
        return value

    def verify(self):
        for lexical, resolved in self.identities.items():
            require(str(Path(lexical).resolve(strict=True)) == resolved, 'Symlink drift: ' + lexical)
        for path, expected in self.pins.items():
            require(digest(path) == expected, 'Input drift: ' + path)

    def run(self, argv, label, cwd=None, bound=180):
        argv = list(map(str, argv))
        self.pin(argv[0])
        self.verify()
        record = dict(label=label, argv=argv, cwd=str(cwd or self.out),
                      environment=self.environment, timeout=bound)
        self.commands.append(record)
        write(self.out / 'commands.json', self.commands)
        result = subprocess.run(argv, cwd=cwd or self.out, env=self.environment,
                                capture_output=True, timeout=bound)
        (self.out / (label + '.stdout')).write_bytes(result.stdout)
        (self.out / (label + '.stderr')).write_bytes(result.stderr)
        record['returncode'] = result.returncode
        write(self.out / 'commands.json', self.commands)
        require(result.returncode == 0, label + ' failed; see stdout/stderr')
        self.verify()
        return result.stdout.decode()

    def tool_libraries(self, tool, label):
        self.pin(tool)
        text = self.run(['/usr/bin/ldd', tool], 'ldd-' + label)
        for line in text.splitlines():
            require('not found' not in line, 'Missing host library')
            for path in re.findall(r'(?:=>\s+|^\s*)(/\S+)', line):
                self.pin(path)


def build(out):
    b = Build(out)
    report = dict(state='PREPARING', performance_measured=False, board_validated=False,
                  target_executed=False, rtl_changed=False, full_binary_rebuilt=False,
                  flag_policy='Fixed environment within blocking context; refresh at next context',
                  original_build=str(MODEL / 'build'))
    try:
        for path in (Path(__file__), HERE / 'test_trace_context_library.py'):
            b.pin(path)
        b.pin(sys.executable)
        b.run([sys.executable, '-B', '-m', 'unittest', '-v', 'test_trace_context_library'],
              'unit-tests', cwd=HERE)
        receipt_path = HERE.parent / 'evidence/output_model_20261106_01/result.json'
        b.pin(receipt_path, RECEIPT)
        accepted = read(receipt_path)
        require(accepted['state'] == 'PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED' and
                accepted['run'] == str(MODEL), 'Unaccepted model library')
        for name, key in (('result.json', 'worker_result_sha256'),
                          ('source-pins.json', 'source_pins_sha256')):
            b.pin(MODEL / name, accepted[key])
        old = read(MODEL / 'source-pins.json')
        b.pin(MODEL / 'commands.json', accepted['audit_pins'][str(MODEL / 'commands.json')])
        for relative in ('src/libllama.a', 'ggml/src/libggml.a',
                         'ggml/src/libggml-cpu.a', 'ggml/src/libggml-base.a'):
            path = MODEL / 'build' / relative
            b.pin(path, old[str(path)])
        library = MODEL / 'build/ggml/src/libggml-cpu.a'
        require(digest(library) == LIBRARY, 'Wrong baseline archive')
        database = MODEL / 'build/compile_commands.json'
        b.pin(database)
        entry, original = command_entry(read(database), GRAPH / 'llama' / SOURCE)
        require(Path(entry['directory']) == MODEL / 'build/ggml/src', 'Wrong compile directory')
        original_obj = Path(entry['directory']) / original[original.index('-o') + 1]
        b.pin(original_obj)
        depfile = Path(str(original_obj) + '.d')
        b.pin(depfile)
        dep_paths = dependencies(depfile.read_text(), Path(entry['directory']))
        require(GRAPH / 'llama' / SOURCE in dep_paths, 'Source absent from original dependencies')
        # Only the sealed source/header closure is copied, never the command cwd.
        origins = {}
        new_toolchain_headers = []
        for path in sorted(dep_paths):
            sealed = path.is_relative_to(GRAPH / 'llama') or path.is_relative_to(GRAPH / 'sdk')
            require(sealed or path.is_relative_to(TOOLCHAIN), 'Unsealed dependency: ' + str(path))
            require(not sealed or str(path) in old, 'Missing sealed header pin: ' + str(path))
            b.pin(path, old.get(str(path)))
            if sealed:
                destination = out / 'inputs' / path.relative_to(GRAPH)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                origins[str(destination)] = dict(source=str(path), sha256=digest(path))
            elif str(path) not in old:
                new_toolchain_headers.append(str(path))
        source = out / 'inputs/llama' / SOURCE
        require(digest(source) == BEFORE, 'Wrong patch preimage')
        shutil.copyfile(source, out / 'inputs/qbs.preimage.cpp')
        b.pin(out / 'inputs/qbs.preimage.cpp', BEFORE)
        patch = HERE / 'trace-context.patch'
        b.pin(patch, PATCH)
        shutil.copyfile(patch, out / 'inputs/trace-context.patch')
        b.pin(out / 'inputs/trace-context.patch', PATCH)
        b.tool_libraries('/usr/bin/patch', 'patch')
        for label, extra in (('patch-check', ['--dry-run']), ('patch-apply', [])):
            b.run(['/usr/bin/patch', '--batch', '--forward', '--fuzz=0', '-p1', *extra,
                   '-i', out / 'inputs/trace-context.patch'], label, cwd=out / 'inputs/llama')
        require(digest(source) == AFTER, 'Wrong patch postimage')
        for path in origins:
            b.pin(path, AFTER if Path(path) == source else origins[path]['sha256'])
        obj = out / 'objects' / MEMBER
        command = remap_command(original, GRAPH, out / 'inputs', obj)
        for arg in command:
            if arg.startswith('-I'):
                Path(arg[2:]).mkdir(parents=True, exist_ok=True)
        compiler = Path(command[0])
        require(compiler.is_relative_to(TOOLCHAIN / 'bin'), 'Unexpected compiler')
        b.pin(compiler, old[str(compiler.resolve(strict=True))])
        real = compiler.with_name('riscv64-buildroot-linux-gnu-g++.br_real')
        b.tool_libraries(compiler, 'compiler-wrapper')
        b.tool_libraries(real, 'compiler-real')
        tools = {}
        for name in ('cc1plus', 'as', 'ar', 'nm'):
            path = Path(b.run([compiler, '-print-prog-name=' + name], 'locate-' + name).strip())
            require(path.is_absolute() and path.resolve().is_relative_to(TOOLCHAIN), 'Tool outside toolchain')
            b.pin(path, old.get(str(path.resolve())))
            b.tool_libraries(path, name)
            tools[name] = str(path)
        b.run([compiler, '--version'], 'compiler-version')
        b.run([tools['ar'], '--version'], 'ar-version')
        b.run([tools['nm'], '--version'], 'nm-version')
        # Document link runtimes for consumers, but do not relink or execute them.
        runtimes = {}
        for name in ('libstdc++.a', 'libgcc.a', 'libgcc_eh.a', 'libc.a', 'libm.a',
                     'libpthread.a', 'libdl.a', 'crt1.o', 'crti.o', 'crtbeginT.o', 'crtend.o', 'crtn.o'):
            path = Path(b.run([compiler, '-print-file-name=' + name], 'locate-' + name).strip())
            require(path.is_absolute() and path.resolve().is_relative_to(TOOLCHAIN), 'Runtime outside toolchain')
            b.pin(path, old.get(str(path.resolve())))
            runtimes[name] = str(path.resolve())
        base = [a for i, a in enumerate(command) if i not in
                (command.index('-c'), command.index('-o'), command.index('-o') + 1)]
        actual_deps = dependencies(b.run([*base, '-M', '-MT', 'object'], 'dependencies'), out)
        expected_deps = {out / 'inputs' / p.relative_to(GRAPH) if p.is_relative_to(GRAPH)
                         else p for p in dep_paths}
        require(actual_deps == expected_deps, 'Dependency closure changed; no compile authorized')
        for path in actual_deps:
            b.pin(path)
        flags = Path(entry['directory']) / 'CMakeFiles/ggml-cpu.dir/flags.make'
        link = flags.with_name('link.txt')
        for path in (flags, link):
            b.pin(path)
        settings = dict(line.split(' = ', 1) for line in flags.read_text().splitlines() if ' = ' in line)
        expected_flags = shlex.split(' '.join(settings[k] for k in ('CXX_DEFINES', 'CXX_INCLUDES', 'CXX_FLAGS')))
        require(original[1:original.index('-o')] == expected_flags, 'Compile database/flags.make differ')
        before = archive_members(library.read_bytes())
        require([v for n, v in before if n == MEMBER] == [original_obj.read_bytes()],
                'Baseline object not identical to archive member')
        require(b.run([tools['ar'], 't', library], 'inventory-before').splitlines() ==
                [n for n, _ in before], 'Archive parser/ar inventory differ')
        write(out / 'static-analysis.json', dict(
            state='SEALED_INPUTS_AND_DEPENDENCY_CLOSURE_CHECKED_BEFORE_COMPILE',
            compile_entry=entry, compile_command=command, source_origins=origins,
            before_sha256=BEFORE, after_sha256=AFTER, patch_sha256=PATCH,
            new_toolchain_headers=new_toolchain_headers, runtime_libraries=runtimes,
            dependency_count=len(actual_deps), original_object_matches_archive=True,
            compile_directory_copied=False, original_compile_options_preserved=True,
            sdk_source='Sealed graph SDK extracted at f5d36baf77c0252121aac7dacb36c87049db826e',
            flag_policy=report['flag_policy']))
        b.run([*command, '-###'], 'compiler-plan')
        b.run(command, 'compile-qbs', bound=300)
        b.pin(obj)
        # r replaces in place; q would append a duplicate and can leave stale code.
        candidate = out / 'lib/libggml-cpu.a'
        shutil.copyfile(library, candidate)
        require(digest(candidate) == LIBRARY, 'Baseline copy differs')
        b.run([tools['ar'], 'rD', candidate, obj], 'replace-qbs')
        b.run([tools['ar'], 'sD', candidate], 'index-archive')
        after = archive_members(candidate.read_bytes())
        evidence = compare_archives(before, after, obj.read_bytes())
        require(b.run([tools['ar'], 't', candidate], 'inventory-after').splitlines() ==
                [n for n, _ in before], 'Archive inventory/order changed')
        definitions = []
        for label, path in (('before', library), ('after', candidate)):
            text = b.run([tools['nm'], '-g', '--defined-only', '--format=posix', path], 'exports-' + label)
            definitions.append(exports(text))
        require(definitions[0] == definitions[1], 'Global defined exports changed')
        write(out / 'archive-members.json', evidence)
        write(out / 'public-exports.json', [dict(name=n, type=t, count=c)
              for (n, t), c in sorted(definitions[0].items())])
        b.verify()
        b.pin(candidate)
        report.update(state='TRACE_CONTEXT_LIBRARY_BUILT_ARCHIVE_VERIFIED',
                      candidate_library=str(candidate), original_library=str(library),
                      original_library_sha256=LIBRARY, candidate_library_sha256=digest(candidate),
                      object_sha256=digest(obj), source_before_sha256=BEFORE, source_after_sha256=AFTER,
                      members=len(evidence), unchanged_other_members=len(evidence) - 1,
                      inventory_and_order_unchanged=True, original_library_unchanged=True,
                      public_exports_unchanged=True, public_export_definitions=sum(definitions[0].values()),
                      public_export_names=len({n for n, _ in definitions[0]}),
                      compiled_translation_units=1, dependency_count=len(actual_deps),
                      new_toolchain_header_count=len(new_toolchain_headers), unit_tests_passed=True,
                      limitations=['Archive/static validation only; no new target numerical or performance evidence',
                                   'Do not change trace environment mid-context',
                                   'New toolchain headers are inventoried now, not retroactively original-worker pins'])
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out / 'source-pins.json', b.pins)
        write(out / 'path-identities.json', b.identities)
        write(out / 'commands.json', b.commands)
        report['artifacts'] = {str(p.relative_to(out)): digest(p) for p in sorted(out.rglob('*'))
                               if p.is_file() and p.name != 'result.json' and 'tmp' not in p.relative_to(out).parts}
        write(out / 'result.json', report)
        print(report['state'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY / 'verification/out'),
            'Use a fresh directory in the sole verification output tree')
    out.mkdir(exist_ok=False)
    build(out)


if __name__ == '__main__':
    main()
