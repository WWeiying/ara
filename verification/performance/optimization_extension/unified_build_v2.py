#!/usr/bin/env python3
"""Correct directory-only exclusions; preserve the original configure failure."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ready-receipt', type=Path, required=True)
    parser.add_argument('--ready-sha256', required=True)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('unified_original', HERE / 'unified_build.py')
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    previous = b.OUT_ROOT / 'optimization_extension_unified_build_20261111_01'
    b.verify(b.read(previous / 'source-pins.json'))
    b.require(b.read(previous / 'result.json')['error'] == "ValueError('Command failed: configure')" and
              'build-info.cmake' in (previous / 'configure.stderr.log').read_text(), 'Unexpected predecessor failure')
    original = (HERE / 'unified_build.py').read_text()
    before = "p.startswith(('build-', 'build_', 'cmake-build-')) for p in Path(name).parts)"
    after = "p.startswith(('build-', 'build_', 'cmake-build-')) for p in Path(name).parts[:-1])"
    fixed = b.replace(original, before, after)
    compile(fixed, 'unified_driver.py', 'exec')
    namespace = dict(__name__='unified_directory_filter_test', __file__=str(HERE / 'unified_build.py'))
    exec(compile(fixed, 'unified_driver.py', 'exec'), namespace)
    for name in ('cmake/build-info.cmake', 'common/build-info.cpp.in'):
        b.require(namespace['allowed_source'](name), 'Required source wrongly excluded')
    b.require(not namespace['allowed_source']('ggml/build-debug/generated.cpp'), 'Build directory must stay excluded')
    out = b.output(args.output)
    copyfile = b.shutil.copyfile

    def copied(source, destination, *a, **kw):
        if Path(source).resolve() == (HERE / 'unified_build.py').resolve() and Path(destination) == out / 'unified_driver.py':
            Path(destination).write_text(fixed)
            return destination
        return copyfile(source, destination, *a, **kw)

    b.shutil.copyfile = copied
    try:
        b.prepare(out, args.ready_receipt, args.ready_sha256, False)
    finally:
        b.shutil.copyfile = copyfile
    copyfile(__file__, out / 'unified_successor.py')
    b.save(out / 'successor.json', dict(original=str(HERE / 'unified_build.py'),
        original_sha256=b.sha(HERE / 'unified_build.py'), corrected_driver_sha256=b.sha(out / 'unified_driver.py'),
        change='Apply build/cache prefix exclusions to directories, not source basenames',
        failed_predecessor=str(previous), original_failure_preserved=True))
    pins = b.read(out / 'source-pins.json')
    for path in (Path(__file__).resolve(), out / 'unified_successor.py', out / 'successor.json',
                 previous / 'result.json', previous / 'delivery.json', previous / 'configure.stderr.log'):
        pins[str(path)] = b.sha(path)
    b.verify(pins)
    (out / 'source-pins.json').write_text(b.json.dumps(pins, indent=2, sort_keys=True) + '\n')
    review = b.sha(out / 'source-pins.json')
    command = b.read(out / 'launch-command.json')
    command[-1] = review
    (out / 'launch-command.json').write_text(b.json.dumps(command, indent=2) + '\n')
    print(b.json.dumps(dict(output=str(out), review_sha256=review, command=command)), flush=True)
    if args.launch:
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
