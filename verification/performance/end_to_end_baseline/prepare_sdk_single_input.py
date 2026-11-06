#!/usr/bin/env python3
"""Isolated, fail-closed host differential preparation. No target execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[2]
GRAPH = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_output_graph_20261106_01')
OUTPUT = MAIN / 'verification/out/e2e_sdk_single_input_host_20261106_01'
RUNTIME_SHA = '04d74029e5d2a80cfe70a2d5192e4d0ccfdc18fb1eeb119c0dc9bb3765edb26b'
GRAPH_PINS_SHA = '24c8d29cc5088d2b4d3b27651b3fc4f7ac4e7271b14b0fade10d58c21cead513'
GRAPH_RESULT_SHA = '097d6ef2d5bb973aa0d3318ef84afb54432c37288a4179706c89701c55132cec'
HELPER_SHA = '2574c060f7d4fb57dfd899520947d092dbd7ec78f229b3759996dfdc94fe47ce'
PATCH_SHA = 'd7444c804c6f9616aa8eec8ebd9d55c4165359fd440c24fd6f98c41904f49c15'
SUCCESS = 'SDK_SINGLE_INPUT_HOST_DIFF_PASS'
SOURCES = ('qbs_runtime.c', 'qbs_format.c', 'qbs_native_riscv.c')
FIXTURES = ('tests/qbs_runtime_test.c', 'examples/runtime_adapter.c',
            'tests/qbs_format_test.c', 'tests/qbs_segmented_test.c',
            'examples/planner_traffic.c', 'tests/qbs_context_admission_test.c',
            'tests/qbs_context_cost_test.c')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def inventory(root):
    return {str(p.absolute()): digest(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def public_symbols(output):
    symbols = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or not fields[0].startswith('qbs_'):
            continue
        require(len(fields) >= 2 and fields[1] in ('T', 'W'), 'Non-function public qbs symbol: ' + line)
        require(re.fullmatch(r'qbs_[A-Za-z0-9_]+', fields[0]), 'Bad public symbol')
        symbols.append(fields[0])
    require(symbols and len(symbols) == len(set(symbols)), 'Empty/duplicate public symbols')
    return sorted(symbols)


def dependency_paths(text):
    text = text.replace('\\\n', ' ')
    require(':' in text, 'Missing compiler dependencies')
    target, body = text.split(':', 1)
    require(target.strip() and '\n' not in body.strip(), 'Expected one dependency rule')
    paths = [Path(s).resolve(strict=True) for s in shlex.split(body)]
    require(paths, 'Empty dependency closure')
    return paths


def new_attempt(root):
    root = Path(root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    # mkdir is the ownership gate; never reuse or remove a previous attempt.
    for i in range(1, 10000):
        path = root / f'attempt-{i:02d}'
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise ValueError('Too many attempts')


class Run:
    def __init__(self, attempt):
        self.out = attempt
        self.pins = {}
        self.commands = []
        self.env = {k: v for k, v in os.environ.items()
                    if not (k.startswith('LD_') or k in {
                        'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                        'LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CC', 'CFLAGS', 'LDFLAGS'})}
        self.env.update(PATH='/usr/bin:/bin', LC_ALL='C', LANG='C', TZ='UTC', SOURCE_DATE_EPOCH='0')

    def pin(self, path, expected=None):
        p = Path(path).absolute()
        value = digest(p)
        require(expected is None or expected == value, 'Identity mismatch: ' + str(p))
        require(str(p) not in self.pins or self.pins[str(p)] == value, 'Input drift: ' + str(p))
        self.pins[str(p)] = value
        return value

    def command(self, args):
        args = [str(x) for x in args]
        executable = Path(shutil.which(args[0]) or args[0]).resolve(strict=True)
        args[0] = str(executable)
        self.pin(executable)
        number = len(self.commands) + 1
        log = self.out / f'command-{number:03d}.log'
        entry = dict(number=number, arguments=args, command=shlex.join(args),
                     cwd=str(self.out), log=str(log), state='RUNNING')
        self.commands.append(entry)
        write(self.out / 'commands.json', self.commands)
        start = time.monotonic()
        try:
            result = subprocess.run(args, cwd=self.out, env=self.env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=180, check=False)
            log.write_bytes(result.stdout)
            entry.update(returncode=result.returncode, seconds=time.monotonic() - start, state='DONE')
            write(self.out / 'commands.json', self.commands)
            require(result.returncode == 0, f'Command {number} failed: {log}')
            return result.stdout.decode(errors='replace')
        except subprocess.TimeoutExpired as exc:
            log.write_bytes(exc.stdout or b'')
            entry.update(state='TIMEOUT', seconds=time.monotonic() - start)
            write(self.out / 'commands.json', self.commands)
            raise

    def compile(self, cc, source, obj, includes, flags=()):
        self.pin(source)
        deps = obj.with_suffix('.d')
        self.command([cc, '-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
                      *flags, *['-I' + str(p) for p in includes],
                      '-MD', '-MF', deps, '-c', source, '-o', obj])
        for path in dependency_paths(deps.read_text()):
            self.pin(path)

    def dynamic_inputs(self, binary):
        output = self.command(['/usr/bin/ldd', binary])
        for line in output.splitlines():
            # ldd gives resolved absolute DSOs and the ELF interpreter.
            match = re.search(r'(?:=>\s+)?(/\S+)\s+\(', line)
            if match:
                self.pin(Path(match.group(1)).resolve(strict=True))

    def link(self, cc, inputs, binary, flags=()):
        mapfile = binary.with_suffix('.map')
        self.command([cc, *flags, *inputs, '-Wl,-Map=' + str(mapfile), '-o', binary])
        for line in mapfile.read_text().splitlines():
            if line.startswith('LOAD '):
                path = Path(line[5:].strip())
                if path.is_absolute() and path.is_file():
                    self.pin(path)

    def verify(self):
        for path, sha in self.pins.items():
            require(digest(path) == sha, 'Final input drift: ' + path)


def prepare(r):
    sdk = GRAPH / 'sdk/software/qbs'
    r.pin(GRAPH / 'source-pins.json', GRAPH_PINS_SHA)
    r.pin(GRAPH / 'result.json', GRAPH_RESULT_SHA)
    sealed = json.loads((GRAPH / 'source-pins.json').read_text())
    graph_state = json.loads((GRAPH / 'result.json').read_text())['state']
    verified = {}
    # Validate the complete pinned SDK subset, not the failed guest graph claim.
    for path, sha in sealed.items():
        if Path(path).is_relative_to(sdk):
            verified[path] = r.pin(path, sha)
    require(str(sdk / 'src/qbs_runtime.c') in verified, 'Runtime absent from GRAPH pins')
    require(verified[str(sdk / 'src/qbs_runtime.c')] == RUNTIME_SHA, 'Wrong locked runtime')
    write(r.out / 'sealed-sdk-identities.json', verified)
    write(r.out / 'sealed-graph-provenance.json', dict(state=graph_state,
          use='source identity only; no inherited functional PASS'))
    consumer = r.out / 'consumer-source-snapshot'
    consumer.mkdir()
    for name in ('prepare_sdk_single_input.py', 'sdk_single_input_diff.c', 'test_sdk_single_input.py'):
        r.pin(HERE / name)
        shutil.copyfile(HERE / name, consumer / name)
        r.pin(consumer / name, r.pins[str(HERE / name)])
    worker = GRAPH.parent / 'e2e_trace_context_model_pair_20261106_01/source-pins.json'
    if worker.exists():
        pins = json.loads(worker.read_text())
        conflicts = [str(HERE / n) for n in ('prepare_sdk_single_input.py', 'sdk_single_input_diff.c',
                     'test_sdk_single_input.py') if str(HERE / n) in pins]
        require(not conflicts, 'Owned files already sealed by worker: ' + repr(conflicts))
        write(r.out / 'worker-pin-inventory.json', dict(path=str(worker), sha256=digest(worker),
              entries=len(pins), owned_conflicts=conflicts,
              inherited_documentation={k: v for k, v in pins.items() if k.lower().endswith('.md')}))
    original = inventory(MAIN / 'software/qbs')
    write(r.out / 'original-sdk-before.json', original)
    helper = MAIN / 'software/qbs/experimental/single_input/qbs_single_input_loop.h'
    patch = helper.with_name('runtime-single-input.patch')
    r.pin(helper, HELPER_SHA); r.pin(patch, PATCH_SHA)
    base, candidate = r.out / 'baseline', r.out / 'candidate'
    for sub in ('include', 'src', 'tests', 'examples'):
        for source in sorted((sdk / sub).rglob('*')):
            if not source.is_file():
                continue
            require(not source.is_symlink() and str(source) in verified, 'Unsealed copied source: ' + str(source))
            dest = base / source.relative_to(sdk)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            r.pin(dest, verified[str(source)])
    shutil.copytree(base, candidate)
    copied_patch = r.out / patch.name
    shutil.copyfile(patch, copied_patch); r.pin(copied_patch, PATCH_SHA)
    # Explicit target operand prevents this registered patch touching other files.
    output = r.command(['patch', '--batch', '--forward', '--fuzz=0', '--no-backup-if-mismatch',
                        '-p1', '-d', candidate, candidate / 'src/qbs_runtime.c', '-i', copied_patch])
    require(not re.search(r'offset|fuzz|FAILED|Reversed', output, re.I), 'Patch not exact')
    shutil.copyfile(helper, candidate / 'src/qbs_single_input_loop.h')
    for p in sorted(candidate.rglob('*')):
        if p.is_file():
            r.pin(p)
    require(digest(base / 'src/qbs_runtime.c') == RUNTIME_SHA, 'Baseline altered')
    require(digest(candidate / 'src/qbs_runtime.c') != RUNTIME_SHA, 'Candidate not patched')
    require(inventory(MAIN / 'software/qbs') == original, 'Original SDK changed during preparation')
    return base, candidate, original


def build(r, base, candidate):
    r.command([sys.executable, '-B', HERE / 'test_sdk_single_input.py'])
    # Bypass login-shell ccache shims; compiler identity must be the real tool.
    cc = Path('/usr/bin/gcc').resolve(strict=True)
    clang = Path('/usr/bin/clang').resolve(strict=True)
    for tool in (cc, clang):
        r.command([tool, '--version'])
        r.dynamic_inputs(tool)
        for program in ('cc1', 'collect2', 'as', 'ld') if tool == cc else ('ld',):
            path = r.command([tool, '-print-prog-name=' + program]).strip()
            found = shutil.which(path) if not Path(path).is_absolute() else path
            require(found, 'Missing compiler subprocess: ' + path)
            r.pin(Path(found).resolve(strict=True))
            r.dynamic_inputs(Path(found).resolve(strict=True))
    r.command(['nm', '--version']); r.command(['patch', '--version'])
    renames = None
    reports = []
    fixture_runs = 0
    for name, compiler, sanitizers in (('gcc', cc, ()), ('clang-ubsan', clang,
                    ('-fsanitize=undefined', '-fno-sanitize-recover=all'))):
        builddir = r.out / name; builddir.mkdir()
        symbols = []
        raw = []
        for i, source in enumerate(SOURCES):
            obj = builddir / ('baseline.o' if i == 0 else f'baseline-{i}.o')
            r.compile(compiler, base / 'src' / source, obj, [base / 'include'], sanitizers)
            raw.append(obj)
            symbols += public_symbols(r.command(['nm', '-g', '--defined-only', '-P', obj]))
        require(len(symbols) == len(set(symbols)), 'Duplicate SDK public symbols')
        args = ['-D' + s + '=baseline_' + s for s in sorted(symbols)]
        require('-Dqbs_execute_with_options=baseline_qbs_execute_with_options' in args, 'Missing execute alias')
        if renames is not None:
            require(renames == args, 'Compiler public symbol sets differ')
        renames = args
        old, new = [], []
        for i, source in enumerate(SOURCES):
            a, b = builddir / f'old-{i}.o', builddir / f'candidate-{i}.o'
            r.compile(compiler, base / 'src' / source, a, [base / 'include'], (*sanitizers, *args))
            output = r.command(['nm', '-g', '--defined-only', '-P', a])
            require(not any(line.startswith('qbs_') for line in output.splitlines()), 'Old symbol escaped alias')
            undefined = r.command(['nm', '-u', '-P', a])
            require(not any(line.startswith('qbs_') for line in undefined.splitlines()), 'Old SDK links new SDK')
            r.compile(compiler, candidate / 'src' / source, b, [candidate / 'include'], sanitizers)
            old.append(a); new.append(b)
        diff = builddir / 'diff.o'
        r.compile(compiler, r.out / 'consumer-source-snapshot/sdk_single_input_diff.c',
                  diff, [base / 'include'], sanitizers)
        exe = builddir / 'sdk-single-input-diff'
        r.link(compiler, [diff, *old, *new], exe, sanitizers)
        r.dynamic_inputs(exe)
        summary = json.loads(r.command([exe]).splitlines()[-1])
        reports.append(dict(compiler=name, **summary))
        require(summary['failure_cases'] > 0 and summary['fallback_plan_cases'] > 0, 'Empty differential coverage')
        if name == 'gcc':
            for variant, sdk, objects in (('baseline', base, raw), ('candidate', candidate, new)):
                instrumented = builddir / (variant + '-instrumented.o')
                r.compile(compiler, sdk / 'src/qbs_runtime.c', instrumented,
                          [sdk / 'include'], ['-finstrument-functions'])
                for index, fixture in enumerate(FIXTURES):
                    testobj = builddir / f'{variant}-fixture-{index}.o'
                    r.compile(compiler, sdk / fixture, testobj, [sdk / 'include'])
                    linked = [instrumented, objects[1]] if index == 6 else objects
                    binary = builddir / f'{variant}-fixture-{index}'
                    r.link(compiler, [testobj, *linked], binary)
                    r.command([binary]); fixture_runs += 1
            guardobj = builddir / 'guard.o'
            r.compile(compiler, r.out / 'consumer-source-snapshot/sdk_single_input_diff.c', guardobj,
                      [candidate / 'include', candidate / 'src'],
                      ['-DSDK_GUARD_UNIT', '-finstrument-functions'])
            guardexe = builddir / 'guard-unit'
            r.link(compiler, [guardobj, new[1]], guardexe)
            guard = json.loads(r.command([guardexe]).splitlines()[-1])
    require(reports[0]['cases'] == reports[1]['cases'] and
            reports[0]['executor_calls'] == reports[1]['executor_calls'], 'Independent run count mismatch')
    return dict(renames=renames, differential_runs=reports, guard=guard, fixture_runs=fixture_runs,
                python_unit_tests=6,
                case_count=sum(x['cases'] for x in reports),
                executor_command_count=sum(x['executor_calls'] for x in reports))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    # Dedicated output tree only; never allow construction inside source inputs.
    require(args.output.absolute() == OUTPUT, 'Only the assigned unique verification tree is allowed')
    attempt = new_attempt(args.output)
    r = Run(attempt)
    report = dict(state='SDK_SINGLE_INPUT_HOST_DIFF_FAIL', attempt=str(attempt),
                  host_only=True, performance_measured=False, hardware_context_fault_semantics_validated=False)
    original = inventory(MAIN / 'software/qbs')
    try:
        base, candidate, original = prepare(r)
        report.update(baseline_runtime=str(base / 'src/qbs_runtime.c'),
                      candidate_runtime=str(candidate / 'src/qbs_runtime.c'),
                      include_dir=str(base / 'include'), helper_path=str(candidate / 'src/qbs_single_input_loop.h'))
        report.update(build(r, base, candidate))
        r.verify()
        after = inventory(MAIN / 'software/qbs')
        write(attempt / 'original-sdk-after.json', after)
        require(after == original, 'Original SDK changed')
        report.update(state=SUCCESS, original_sdk_unchanged=True)
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        # Failed attempts retain the exact inputs, command, stdout and first error.
        after = inventory(MAIN / 'software/qbs')
        write(attempt / 'original-sdk-after.json', after)
        report['original_sdk_unchanged'] = after == original
        write(attempt / 'source-pins.json', r.pins)
        write(attempt / 'commands.json', r.commands)
        report['source_pins_sha256'] = digest(attempt / 'source-pins.json')
        report['command_count'] = len(r.commands)
        shutil.copyfile(attempt / 'source-pins.json', args.output / 'source-pins.json')
        report['artifacts'] = {str(p): digest(p) for p in sorted(attempt.rglob('*'))
                               if p.is_file() and p.name != 'result.json'}
        report['artifacts'][str(args.output / 'source-pins.json')] = report['source_pins_sha256']
        report['previous_attempts'] = {str(p): digest(p) for p in sorted(args.output.glob('attempt-*/result.json'))
                                       if p.parent != attempt}
        for p in sorted(args.output.glob('attempt-*/consumer-source-snapshot/*')):
            report['artifacts'][str(p)] = digest(p)
        write(attempt / 'result.json', report)
        write(args.output / 'result.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'artifacts'}, indent=2))
    return 0 if report['state'] == SUCCESS else 1


if __name__ == '__main__':
    sys.exit(main())
