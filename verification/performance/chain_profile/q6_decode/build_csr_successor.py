#!/usr/bin/env python3
"""Explicit CSR successor: fresh archived inputs and compilation, no target execution.

Only the predecessor's main.c compile input is routed to the new measurement C.
HERE/ROOT, quantizer, SDK, host reference, flags, objects and fences stay inherited.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT_SHA256 = '0036348fcc4a733886e159b482291740915200bb8d94af6c1cec9cfeaef99abc'


def load_parent(path=HERE / 'build.py'):
    # Validate before executing any predecessor code; never load an unchecked builder.
    if hashlib.sha256(path.read_bytes()).hexdigest() != PARENT_SHA256:
        raise ValueError('Predecessor build.py identity mismatch')
    spec = importlib.util.spec_from_file_location('q6_csr_parent_build', path)
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    return parent


parent = load_parent()


class Builder(parent.Builder):
    def compile(self, cc, flags, source, obj):
        if Path(source) == parent.HERE / 'main.c':
            source = HERE / 'main_csr_successor.c'
        return super().compile(cc, flags, source, obj)


def build(args):
    parent.require(parent.digest(HERE / 'build.py') == PARENT_SHA256,
                   'Predecessor build.py changed before build')
    # The isolated imported module still owns its original HERE/ROOT and build().
    # Its HERE.iterdir() seals every old/new helper before any compilation.
    parent.Builder = Builder
    parent.build(args)
    spec = importlib.util.spec_from_file_location('q6_csr_checker', HERE / 'check_successor.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    manifest = args.output.resolve() / 'build.json'
    receipt = json.loads(manifest.read_text())
    receipt.update(
        checker_entry=[sys.executable, '-B', str(HERE / 'check_successor.py'),
                       '--build', str(manifest), '--log', '<run.vcs.log>',
                       '--output', '<new authorized output.json>'],
        parent_builder=dict(path=str(HERE / 'build.py'), sha256=PARENT_SHA256),
        measurement_source=str(HERE / 'main_csr_successor.c'),
        csr_contract=checker.CSR_CONTRACT, successor_reason=checker.SUCCESSOR_REASON)
    parent.write_json(manifest, receipt)
    checker.check_build(manifest)
    print(json.dumps(dict(build=str(manifest), checker_entry=receipt['checker_entry'],
                          csr_contract=receipt['csr_contract'], state=receipt['state']), indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--llama', type=Path, default=parent.LLAMA)
    p.add_argument('--toolchain', type=Path, default=parent.TOOLCHAIN)
    p.add_argument('--host-cc', default='/usr/bin/gcc')
    try:
        build(p.parse_args())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        raise SystemExit(str(e)) from e


if __name__ == '__main__':
    main()
