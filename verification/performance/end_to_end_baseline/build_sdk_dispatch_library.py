#!/usr/bin/env python3
"""Integrate the accepted M1 runtime in an isolated, one-member GGML archive.

Reproduce the original object exactly before compiling the candidate. Only the
consumed receipt, source, header, and tool closure is checked, not model/QEMU/RTL
inputs. This produces no new execution or performance acceptance.
"""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import sys

from build_trace_context_library import (
    Build, archive_members, dependencies, digest, exports, read, require, sha, write,
)

HERE = Path(__file__).resolve().parent
MAIN = Path('/home/wangwy/openproject/ara_dsa')
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
RUNS = VERIFY / 'verification/out'
GRAPH = RUNS / 'e2e_output_graph_20261106_01'
MODEL = RUNS / 'e2e_output_model_20261106_01'
HOST = MAIN / 'verification/out/e2e_sdk_single_input_host_20261106_01/attempt-02'
OUTPUT = RUNS / 'e2e_sdk_dispatch_library_20261106_01'
EVIDENCE = MAIN / 'verification/performance/evidence'
TOOLCHAIN = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host')
SOURCE = GRAPH / 'sdk/software/qbs/src/qbs_runtime.c'
MEMBER = 'qbs_runtime.c.o'
BASELIB = 'd440c7d2894f5ab0c5165d8ca4bfc9a437df65fcb7d3aeb0771e2718293a803b'
BEFORE = '04d74029e5d2a80cfe70a2d5192e4d0ccfdc18fb1eeb119c0dc9bb3765edb26b'
AFTER = '927a09d63fbbdef5fc372956dbe643f9c33cfc26e08b07d35cb1b44f1674cec3'
PRIVATE = '2574c060f7d4fb57dfd899520947d092dbd7ec78f229b3759996dfdc94fe47ce'
ORIGINAL_OBJECT = '7f00df7b63aa91f0228ce860c2ec509e73439236edd24479a064f5374fc066f6'
HELPER = '1a1e89b937d96c91cfd96917bc979899051d119c945948d2f0acf19b52b0afef'
RECEIPTS = {
    'trace_context_library': '72712723f00bb69dfad41b2178bd2e70d0562be8facc10e53019c7582b5aab3d',
    'trace_context_model': 'c0079fe778bbd4b69de8cfa57dc128add6e06125212222b4837ddc00d5124024',
    'sdk_single_input': '32a2684e5e6c9bfb7b4a0835c7e0cae81d58447fd4af6db85827b87ff9ed40af',
    'output_model': '5473539c53b687dac3fe4d8cc2b56547ae2f1cf3ec9ad012bf29cc3b0e83fd02',
}


def compare_member_archives(before, after, member, replacement):
    """Allow one changed member; duplicate unrelated names remain positional."""
    require([n for n, _ in before] == [n for n, _ in after],
            'Archive inventory/order changed')
    require(sum(n == member for n, _ in before) == 1, 'Missing/duplicate replacement member')
    evidence = []
    for i, ((name, old), (_, new)) in enumerate(zip(before, after)):
        if name == member:
            require(new == replacement and old != new, 'Stale/wrong replacement object')
        else:
            require(old == new, 'Other member changed: ' + str(i) + ': ' + name)
        evidence.append(dict(index=i, name=name, bytes_before=len(old), bytes_after=len(new),
                             before_sha256=sha(old), after_sha256=sha(new), changed=old != new))
    return evidence


def command_entry(entries, source):
    matches = [e for e in entries if e['file'].endswith('/qbs_runtime.c')]
    require(len(matches) == 1, 'Missing/ambiguous runtime compile command')
    entry = matches[0]
    argv = list(entry.get('arguments') or shlex.split(entry['command']))
    require(Path(entry['file']) == source, 'Not the sealed GRAPH runtime')
    require(argv.count('-c') == argv.count('-o') == 1, 'Ambiguous compile operands')
    require(argv[argv.index('-c') + 1] == str(source), 'Wrong compile operand')
    require(Path(argv[0]).is_absolute(), 'Compiler must be absolute')
    for i, arg in enumerate(argv[1:], 1):
        if i in (argv.index('-c') + 1, argv.index('-o') + 1):
            continue
        require(arg not in ('-I', '-include', '-imacros', '-isystem', '-iquote') and
                not arg.startswith(('@', '-M', '-fplugin', '-specs', '--sysroot', '-B', '-Dqbs_')),
                'Hidden input/output or namespace change: ' + arg)
        require(arg.startswith(('-D', '-I', '-m', '-O', '-std=', '-W')) or arg in ('-o', '-c'),
                'Unsupported command token: ' + arg)
    return entry, argv


def compile_command(original, source, obj):
    argv = list(original)
    argv[argv.index('-c') + 1] = str(source)
    argv[argv.index('-o') + 1] = str(obj)
    return argv


def preprocess_command(command, *options):
    omit = {command.index('-c'), command.index('-o'), command.index('-o') + 1}
    return [arg for i, arg in enumerate(command) if i not in omit] + list(options)


def fresh_attempt(root):
    require(root == root.resolve() and root.is_relative_to(RUNS),
            'Output must be under the sole verification output tree')
    root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 10000):
        out = root / ('attempt-%02d' % number)
        try:
            out.mkdir()
        except FileExistsError:
            continue
        return out
    raise ValueError('No fresh attempt available')


def accepted_inputs(b):
    receipts = {}
    for name, expected in RECEIPTS.items():
        path = EVIDENCE / (name + '_20261106_01/result.json')
        b.pin(path, expected)
        receipts[name] = read(path)
    library = receipts['trace_context_library']
    require(library['state'] == 'TRACE_CONTEXT_LIBRARY_BUILT_ARCHIVE_VERIFIED' and
            library['candidate_library_sha256'] == BASELIB, 'Unaccepted baseline library')
    run = Path(library['run'])
    b.pin(run / 'result.json', library['result_sha256'])
    b.pin(run / 'source-pins.json', library['source_pins_sha256'])
    result = read(run / 'result.json')
    path = Path(result['candidate_library'])
    require(path == run / 'lib/libggml-cpu.a' and
            result['candidate_library_sha256'] == BASELIB, 'Baseline library path/identity differs')
    b.pin(path, BASELIB)
    model = receipts['trace_context_model']
    require(model['state'] == 'TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED' and
            model['candidate_library_sha256'] == BASELIB and model['identical_full_logits'] and
            model['identical_tokens_and_csr'] and model['identical_native_work'],
            'Trace-context model acceptance differs')
    b.pin(Path(model['run']) / 'result.json', model['result_sha256'])
    sdk = receipts['sdk_single_input']
    require(sdk['state'] == 'REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_REAUDITED' and
            sdk['commands'] == 112 and sdk['outputs_checked'] == 3584 and
            sdk['m'] == 1 and sdk['full_k'] and sdk['execution_speedup'] > 1,
            'Unaccepted SDK performance evidence')
    audit = Path(sdk['run']) / 'result.json'
    b.pin(audit, sdk['result_sha256'])
    sdk_report = read(audit)['report']
    worker = Path(sdk_report['run'])
    b.pin(worker / 'result.json', sdk['worker_result_sha256'])
    b.pin(worker / 'source-pins.json', sdk['source_pins_sha256'])
    worker_pins = read(worker / 'source-pins.json')
    native_pins = Path(sdk_report['build']) / 'source-pins.json'
    b.pin(native_pins, worker_pins[str(native_pins)])
    native = read(native_pins)
    host_report = HOST / 'result.json'
    b.pin(host_report, native[str(host_report)])
    host = read(host_report)
    require(host['state'] == 'SDK_SINGLE_INPUT_HOST_DIFF_PASS' and host['case_count'] == 49070,
            'Host differential acceptance differs')
    b.pin(HOST / 'source-pins.json', host['source_pins_sha256'])
    for relative, expected in (('baseline/src/qbs_runtime.c', BEFORE),
                               ('candidate/src/qbs_runtime.c', AFTER),
                               ('candidate/src/qbs_single_input_loop.h', PRIVATE)):
        source = HOST / relative
        require(host['artifacts'][str(source)] == expected, 'Host source acceptance differs')
        if relative.startswith('candidate/'):
            require(native[str(source)] == expected, 'Measured SDK candidate differs')
        b.pin(source, expected)
    original_model = receipts['output_model']
    require(original_model['state'] == 'PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED' and
            original_model['run'] == str(MODEL), 'Unaccepted model source pins')
    b.pin(MODEL / 'source-pins.json', original_model['source_pins_sha256'])
    return path, read(MODEL / 'source-pins.json'), host


def tool_closure(b, compiler, old):
    require(compiler.resolve().is_relative_to(TOOLCHAIN), 'Compiler outside accepted toolchain')
    real = compiler.with_name(compiler.name + '.br_real')
    tools = {}
    new_pins = []
    for label, path in (('compiler-wrapper', compiler), ('compiler-real', real)):
        resolved = str(path.resolve(strict=True))
        require(label != 'compiler-wrapper' or resolved in old, 'Missing accepted compiler wrapper pin')
        b.pin(path, old.get(resolved))
        if resolved not in old:
            new_pins.append(resolved)
        b.tool_libraries(path, label)
    for name in ('cc1', 'as', 'collect2', 'ld', 'ar', 'nm', 'objdump', 'readelf'):
        path = Path(b.run([compiler, '-print-prog-name=' + name], 'locate-' + name).strip())
        require(path.is_absolute() and path.resolve().is_relative_to(TOOLCHAIN),
                'Tool outside toolchain: ' + name)
        b.pin(path, old.get(str(path.resolve())))
        if str(path.resolve()) not in old:
            new_pins.append(str(path.resolve()))
        b.tool_libraries(path, name)
        tools[name] = str(path)
    b.run([compiler, '--version'], 'compiler-version')
    return tools, new_pins


def build(out):
    b = Build(out)
    report = dict(state='PREPARING', run=str(out), member=MEMBER, performance_measured=False,
                  target_executed=False, production_changes=False, production_sdk_changed=False,
                  rtl_changed=False, board_validated=False, full_binary_rebuilt=False)
    try:
        snapshot = out / 'consumer-source-snapshot'
        snapshot.mkdir()
        for name in ('build_sdk_dispatch_library.py', 'test_sdk_dispatch_library.py',
                     'build_trace_context_library.py'):
            path = HERE / name
            expected = HELPER if name == 'build_trace_context_library.py' else None
            b.pin(path, expected)
            shutil.copyfile(path, snapshot / name)
            b.pin(snapshot / name, digest(path))
        b.pin(sys.executable)
        b.run([sys.executable, '-B', '-m', 'unittest', '-v', 'test_sdk_dispatch_library'],
              'unit-tests', cwd=snapshot)
        library, old, host = accepted_inputs(b)
        report.update(baseline_library=str(library), baseline_library_sha256=BASELIB)
        database = GRAPH / 'build/compile_commands.json'
        b.pin(database, old[str(database)])
        shutil.copyfile(database, out / 'inputs/compile_commands.json')
        b.pin(out / 'inputs/compile_commands.json', old[str(database)])
        entry, original = command_entry(read(database), SOURCE)
        cwd = Path(entry['directory'])
        require(cwd == GRAPH / 'build/ggml/src', 'Wrong original compile directory')
        original_obj = cwd / original[original.index('-o') + 1]
        b.pin(original_obj, ORIGINAL_OBJECT)
        depfile = Path(str(original_obj) + '.d')
        b.pin(depfile)
        dep_paths = dependencies(depfile.read_text(), cwd)
        require(SOURCE in dep_paths, 'Original source absent from dependencies')
        origins = {}
        for path in sorted(dep_paths):
            require(path.is_relative_to(GRAPH) or path.is_relative_to(TOOLCHAIN),
                    'Dependency outside sealed graph/toolchain: ' + str(path))
            require(not path.is_relative_to(GRAPH) or str(path) in old,
                    'Unpinned graph dependency: ' + str(path))
            b.pin(path, old.get(str(path)))
            if path.is_relative_to(GRAPH):
                dest = out / 'inputs' / path.relative_to(GRAPH)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
                b.pin(dest, digest(path))
                origins[str(dest)] = dict(source=str(path), sha256=digest(path))
            if path.is_relative_to(GRAPH / 'sdk/software/qbs/include'):
                relative = path.relative_to(GRAPH / 'sdk/software/qbs')
                for variant in ('baseline', 'candidate'):
                    public = HOST / variant / relative
                    require(host['artifacts'][str(public)] == digest(path),
                            'Public header differs from host-tested input')
                    b.pin(public, digest(path))
        b.pin(SOURCE, BEFORE)
        flags = cwd / 'CMakeFiles/ggml-cpu.dir/flags.make'
        b.pin(flags)
        settings = dict(line.split(' = ', 1) for line in flags.read_text().splitlines()
                        if ' = ' in line)
        expected = shlex.split(' '.join(settings[k] for k in ('C_DEFINES', 'C_INCLUDES', 'C_FLAGS')))
        require(original[1:original.index('-o')] == expected, 'GRAPH flags/compile database differ')
        for arg in original:
            if arg.startswith('-I'):
                require(Path(arg[2:]).resolve(strict=True).is_relative_to(GRAPH),
                        'Include outside sealed graph')
        before = archive_members(library.read_bytes())
        require(len(before) == 32, 'Expected accepted 32-member archive')
        require([data for name, data in before if name == MEMBER] == [original_obj.read_bytes()],
                'Original GRAPH object does not match baseline archive')
        tools, new_tool_pins = tool_closure(b, Path(original[0]), old)
        baseline_obj = out / 'objects/original' / MEMBER
        baseline_obj.parent.mkdir()
        baseline_command = compile_command(original, SOURCE, baseline_obj)
        actual = dependencies(b.run(preprocess_command(baseline_command, '-M', '-MT', 'object'),
                                    'baseline-dependencies', cwd=cwd), cwd)
        require(actual == dep_paths, 'Original dependency closure changed')
        b.run([*baseline_command, '-###'], 'baseline-compiler-plan', cwd=cwd)
        b.run(baseline_command, 'compile-original', cwd=cwd, bound=300)
        b.pin(baseline_obj)
        if baseline_obj.read_bytes() != original_obj.read_bytes():
            report['original_object_reproduced_exactly'] = False
            b.run(preprocess_command(baseline_command, '-E'), 'original-preprocessed', cwd=cwd)
            b.run(preprocess_command(baseline_command, '-E', '-dM'), 'original-macros', cwd=cwd)
            for label, obj in (('sealed', original_obj), ('rebuilt', baseline_obj)):
                b.run([tools['readelf'], '-aW', obj], label + '-readelf')
                b.run([tools['objdump'], '-dr', obj], label + '-disassembly')
            raise ValueError('Original runtime object not byte-exact; diagnostics retained, no candidate compile')
        report['original_object_reproduced_exactly'] = True
        candidate_dir = out / 'inputs/candidate/src'
        candidate_dir.mkdir(parents=True)
        for name, expected in (('qbs_runtime.c', AFTER), ('qbs_single_input_loop.h', PRIVATE)):
            shutil.copyfile(HOST / 'candidate/src' / name, candidate_dir / name)
            b.pin(candidate_dir / name, expected)
        patch = HOST / 'runtime-single-input.patch'
        b.pin(patch, host['artifacts'][str(patch)])
        shutil.copyfile(patch, out / 'inputs/runtime-single-input.patch')
        b.pin(out / 'inputs/runtime-single-input.patch', digest(patch))
        obj = out / 'objects' / MEMBER
        command = compile_command(original, candidate_dir / 'qbs_runtime.c', obj)
        candidate_deps = dependencies(b.run(preprocess_command(command, '-M', '-MT', 'object'),
                                           'candidate-dependencies', cwd=cwd), cwd)
        expected_deps = (dep_paths - {SOURCE}) | {candidate_dir / 'qbs_runtime.c',
                                                    candidate_dir / 'qbs_single_input_loop.h'}
        require(candidate_deps == expected_deps, 'Candidate dependency closure changed')
        for path in candidate_deps:
            b.pin(path)
        write(out / 'static-analysis.json', dict(
            compile_entry=entry, baseline_command=baseline_command, candidate_command=command,
            original_dependency_paths=sorted(map(str, dep_paths)),
            candidate_dependency_paths=sorted(map(str, candidate_deps)), tools=tools,
            newly_inventoried_tools=new_tool_pins,
            new_tool_pins_are_not_historical_acceptance=True,
            source_origins=origins, original_object_sha256=ORIGINAL_OBJECT,
            original_object_reproduced_exactly=True, original_compile_flags_preserved=True,
            public_headers_match_host_test=True, namespace_renames=False,
            baseline_library_sha256=BASELIB, sdk_source_before_sha256=BEFORE,
            sdk_source_after_sha256=AFTER, private_helper_sha256=PRIVATE,
            excluded_inputs=['model data', 'RTL', 'QEMU source tree']))
        b.run([*command, '-###'], 'candidate-compiler-plan', cwd=cwd)
        b.run(command, 'compile-candidate', cwd=cwd, bound=300)
        b.pin(obj)
        candidate = out / 'lib/libggml-cpu.a'
        shutil.copyfile(library, candidate)
        require(digest(candidate) == BASELIB, 'Baseline copy differs')
        b.run([tools['ar'], 'rD', candidate, obj], 'replace-runtime')
        b.run([tools['ar'], 'sD', candidate], 'index-archive')
        evidence = compare_member_archives(before, archive_members(candidate.read_bytes()),
                                           MEMBER, obj.read_bytes())
        for label, path in (('before', library), ('after', candidate)):
            inventory = b.run([tools['ar'], 't', path], 'inventory-' + label).splitlines()
            require(inventory == [name for name, _ in before], 'ar inventory/order changed')
        definitions = [exports(b.run([tools['nm'], '-g', '--defined-only', '--format=posix', path],
                                     'exports-' + label))
                       for label, path in (('before', library), ('after', candidate))]
        require(definitions[0] == definitions[1], 'Global export names/types/counts changed')
        write(out / 'archive-members.json', evidence)
        write(out / 'public-exports.json', [dict(name=n, type=t, count=c)
              for (n, t), c in sorted(definitions[0].items())])
        b.pin(candidate)
        b.verify()
        report.update(state='SDK_DISPATCH_LIBRARY_BUILT_ARCHIVE_VERIFIED',
                      candidate_library=str(candidate), candidate_library_sha256=digest(candidate),
                      candidate_object=str(obj), candidate_object_sha256=digest(obj),
                      baseline_object=str(baseline_obj), baseline_object_sha256=digest(baseline_obj),
                      original_object_sha256=ORIGINAL_OBJECT, source_before_sha256=BEFORE,
                      source_after_sha256=AFTER, private_helper_sha256=PRIVATE,
                      members=32, unchanged_other_members=31, changed_members=1,
                      inventory_and_order_unchanged=True, original_library_unchanged=True,
                      public_exports_unchanged=True, public_export_definitions=sum(definitions[0].values()),
                      public_export_names=len({n for n, _ in definitions[0]}),
                      compiled_translation_units=2, unit_tests_passed=True,
                      dependency_count=len(candidate_deps),
                      limitations=['Archive validation only; no new target/model/performance acceptance',
                                   'Single-worker admission and standard fallback remain required'])
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out / 'source-pins.json', b.pins)
        write(out / 'path-identities.json', b.identities)
        write(out / 'commands.json', b.commands)
        report['source_pins_sha256'] = digest(out / 'source-pins.json')
        report['artifacts'] = {str(p): digest(p) for p in sorted(out.rglob('*'))
                               if p.is_file() and p.name != 'result.json' and
                               'tmp' not in p.relative_to(out).parts}
        write(out / 'result.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'artifacts'}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT, help='Parent of fresh attempt-XX')
    args = parser.parse_args()
    build(fresh_attempt(args.output.absolute()))


if __name__ == '__main__':
    main()
