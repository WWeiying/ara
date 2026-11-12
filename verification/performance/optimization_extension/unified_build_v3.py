#!/usr/bin/env python3
"""Future unified entry: separate audit reports from successful worker outputs."""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE_SHA = 'f6c154c203ec76e54f476b0909f05d377fbd8a1bae46d282db2100af1a2636b2'
AUDIT_REPORTS = ('compile-source-pins.json', 'compiler-dependencies.json',
                 'math-modes.json', 'compiled-enablement.json')


def base():
    spec = importlib.util.spec_from_file_location('unified_immutable_base', HERE / 'unified_build.py')
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    b.require(b.sha(HERE / 'unified_build.py') == BASE_SHA, 'Immutable base driver changed')
    return b


def future_driver(b):
    text = (HERE / 'unified_build.py').read_text()
    text = b.replace(text,
        "p.startswith(('build-', 'build_', 'cmake-build-')) for p in Path(name).parts)",
        "p.startswith(('build-', 'build_', 'cmake-build-')) for p in Path(name).parts[:-1])")
    marker = "    compile(text, 'unified_build_audit.py', 'exec')"
    rename = ('    for filename in ' + repr(AUDIT_REPORTS) + ':\n'
              '        text = text.replace(repr(filename), repr("independent-" + filename))\n')
    text = b.replace(text, marker, rename + marker)
    text = b.replace(text, "verify(read(out / 'compile-source-pins.json'))",
                    "verify(read(out / 'independent-compile-source-pins.json'))")
    compile(text, 'unified_driver.py', 'exec')
    return text


def saved_outputs(text, function):
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    result = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not call.args:
            continue
        name = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, 'attr', None)
        path = call.args[0]
        if name == 'save' and isinstance(path, ast.BinOp) and isinstance(path.op, ast.Div) and \
                isinstance(path.right, ast.Constant) and isinstance(path.right.value, str):
            result.add(path.right.value)
    return result


def checked_driver(b):
    text = future_driver(b)
    namespace = dict(__name__='unified_future_static', __file__=str(HERE / 'unified_build.py'))
    exec(compile(text, 'unified_driver.py', 'exec'), namespace)
    build_template, audit_template = b.templates()
    worker = namespace['derive_build'](build_template, '0' * 64)
    audit = namespace['derive_audit'](audit_template)
    worker_outputs = saved_outputs(worker, 'execute')
    audit_outputs = saved_outputs(audit, 'main') | saved_outputs(text, 'audit_extensions')
    b.require(not worker_outputs & audit_outputs, 'Worker/audit report collision')
    expected = {'independent-' + name for name in AUDIT_REPORTS}
    b.require(expected <= audit_outputs, 'Missing named independent reports')
    b.require(not set(AUDIT_REPORTS) & audit_outputs, 'Audit still writes a worker report name')
    b.require(set(AUDIT_REPORTS[:3]) <= worker_outputs, 'Worker report names changed')
    old_collisions = worker_outputs & saved_outputs(b.derive_audit(audit_template), 'main')
    b.require(old_collisions == set(AUDIT_REPORTS[:3]), 'Static regression no longer reproduces the known collision')
    driver_ast = ast.parse(text)
    execute = next(n for n in driver_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
    consumers = {n.value for n in ast.walk(execute) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    b.require('independent-compile-source-pins.json' in consumers and 'compile-source-pins.json' not in consumers,
              'Delivery must verify the independent audit closure')
    worker_logs = {label + '.' + channel + '.log' for label in
        ('configure', 'build', 'llama-simple-readelf', 'llama-completion-readelf', 'llama-bench-readelf')
        for channel in ('stdout', 'stderr')}
    audit_logs = {'audit-' + name + '-readelf.log' for name in
                  ('llama-simple', 'llama-completion', 'llama-bench')} | {'cap5-macros.log', 'cap5-preprocessed.log'}
    b.require(not worker_logs & audit_logs, 'Worker/audit log collision')
    b.require(namespace['allowed_source']('cmake/build-info.cmake') and
              namespace['allowed_source']('common/build-info.cpp.in') and
              not namespace['allowed_source']('ggml/build-debug/generated.cpp'), 'Directory exclusion regression')
    return text, namespace, dict(state='STATIC_SELF_CHECK_PASS', worker_reports=sorted(worker_outputs),
        audit_reports=sorted(audit_outputs), old_collisions_reproduced=sorted(old_collisions),
        report_names_disjoint=True, log_names_disjoint=True, audit_consumer_updated=True,
        source_snapshot_created=False, compilers_or_simulators_launched=False)


def prepare(b, out, receipt, digest, launch):
    fixed, namespace, _ = checked_driver(b)
    copyfile = b.shutil.copyfile
    old_derive = b.derive_audit

    def copied(source, destination, *args, **kwargs):
        if Path(source).resolve() == (HERE / 'unified_build.py').resolve() and Path(destination) == out / 'unified_driver.py':
            Path(destination).write_text(fixed)
            return destination
        return copyfile(source, destination, *args, **kwargs)

    b.derive_audit = namespace['derive_audit']
    b.shutil.copyfile = copied
    try:
        b.prepare(out, receipt, digest, False)
    finally:
        b.shutil.copyfile = copyfile
        b.derive_audit = old_derive
    copyfile(__file__, out / 'unified_future_entry.py')
    b.save(out / 'future-successor.json', dict(base_sha256=BASE_SHA,
        corrected_driver_sha256=b.sha(out / 'unified_driver.py'),
        changes=['Directory-only exclusions retained', 'Independent audit report namespace',
                 'Delivery verifies independent audit compile-source pins'],
        old_campaign_files_modified=False))
    pins = b.read(out / 'source-pins.json')
    for path in (Path(__file__).resolve(), out / 'unified_future_entry.py', out / 'future-successor.json'):
        pins[str(path)] = b.sha(path)
    b.verify(pins)
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')
    review = b.sha(out / 'source-pins.json')
    command = b.read(out / 'launch-command.json')
    command[-1] = review
    (out / 'launch-command.json').write_text(json.dumps(command, indent=2) + '\n')
    print(json.dumps(dict(output=str(out), review_sha256=review, command=command)), flush=True)
    if launch:
        subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('self-check', 'prepare'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--ready-receipt', type=Path)
    parser.add_argument('--ready-sha256')
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    b = base()
    if args.action == 'self-check':
        print(json.dumps(checked_driver(b)[2], indent=2), flush=True)
        return
    b.require(args.output is not None and args.ready_receipt is not None, 'Fresh output and parent READY required')
    prepare(b, b.output(args.output), args.ready_receipt, args.ready_sha256, args.launch)


if __name__ == '__main__':
    main()
