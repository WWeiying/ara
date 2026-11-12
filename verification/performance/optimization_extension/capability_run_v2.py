#!/usr/bin/env python3
"""Successor preparation: use installed Clang UBSan, preserve failed v1 evidence."""
import argparse
import importlib.util
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
V1_SHA = 'b6a763954f541d6888c089d75a8d780255e74d6885f261cf610c28fedaa50a0f'


def load():
    spec = importlib.util.spec_from_file_location('capability_v1', HERE / 'capability_run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def derive(text):
    changes = {
        "run(mode + '-compile', ['/usr/bin/gcc',":
            "run(mode + '-compile', ['/usr/bin/clang' if mode == 'ubsan' else '/usr/bin/gcc',",
        "== out / 'inputs/capability_run.py', 'Use frozen worker only'":
            "== out / 'inputs/capability_worker_v2.py', 'Use frozen worker only'",
        "    require(not any(r['owned_matches'] for r in inventories), 'New owned helper is already sealed')":
            "    for receipt in inventories:\n        verify({p: read(receipt['path'])[p] for p in receipt['owned_matches']})",
    }
    for before, after in changes.items():
        if text.count(before) != 1:
            raise ValueError('Unrecognized exact v1 derivation: ' + before)
        text = text.replace(before, after)
    compile(text, 'capability_worker_v2.py', 'exec')
    return text


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    c = load()
    c.require(c.sha(HERE / 'capability_run.py') == V1_SHA, 'Original v1 worker changed')
    derived = derive((HERE / 'capability_run.py').read_text())
    runtime = Path('/usr/lib/clang/20/lib/x86_64-redhat-linux-gnu/libclang_rt.ubsan_standalone.a')
    c.require(runtime.is_file(), 'Installed Clang UBSan runtime unavailable')
    previous = c.OUT / 'optimization_extension_capability_20261111_01'
    result = c.read(previous / 'result.json')
    c.require(result['state'] == 'FAIL' and result['error'] == "ValueError('ubsan-compile returncode=1')" and
              '/usr/lib64/libubsan.so.1.0.0' in (previous / 'ubsan-compile.log').read_text(),
              'Not the preserved known GCC UBSan environment failure')
    out = c.output(args.output)
    # Reuse the immutable v1 helper only when every inherited helper pin agrees.
    exec(compile(derived, str(HERE / 'capability_run.py'), 'exec'), c.__dict__)
    c.prepare(out)
    inputs = out / 'inputs'
    pins = c.read(out / 'source-pins.json')
    c.copy(pins, HERE / 'capability_run_v2.py', inputs / 'capability_run_v2.py')
    worker = inputs / 'capability_worker_v2.py'
    worker.write_text(derived)
    c.pin(pins, worker)
    for path in (Path('/usr/bin/clang').resolve(), runtime,
                 previous / 'result.json', previous / 'source-pins.json', previous / 'ubsan-compile.log'):
        c.pin(pins, path)
    plan = c.read(out / 'plan.json')
    plan.update(ubsan_compiler='/usr/bin/clang', ubsan_runtime=str(runtime),
        supersedes_failed_attempt=str(previous),
        derivation=dict(source_sha256=V1_SHA, derived_sha256=c.sha(worker),
            changes=['Use installed Clang only for UBSan compile; GCC plain unchanged',
                     'Require the successor frozen worker path; no test/checker/RTL changes',
                     'Allow immutable helper reuse only after checking all prior helper pins']))
    c.save(out / 'plan.json', plan)
    pins[str(out / 'plan.json')] = c.sha(out / 'plan.json')
    c.verify(pins)
    c.save(out / 'source-pins.json', pins)
    review = c.sha(out / 'source-pins.json')
    c.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review))
    command = c.service(out, review)
    index = command.index(str(inputs / 'capability_run.py'))
    command[index] = str(worker)
    c.save(out / 'launch-command.json', command)
    print(dict(output=str(out), review_sha256=review, command=command), flush=True)
    if args.launch:
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
