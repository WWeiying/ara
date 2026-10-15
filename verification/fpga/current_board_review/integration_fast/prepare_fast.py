#!/usr/bin/env python3
"""Remove only audited single-case filter traversal; reuse sealed compilation."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
SOURCE_RECEIPT = '568cbd184f4afadb3eff54cfe870cdb1bb81eb434bc2cb253537de7609e54d1d'
SELECTED = {
    'maskslide': dict(seed=0, op=16, s=0, l=4, mode=0, trial=1),
    'gather_original': dict(seed=0, op=0, s=0, l=2, mode=0, trial=0),
    'reduction_fflags': dict(scenario=3, l=4, mode=3, rm=0, op=0, sticky=0),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sealed_compile():
    receipt = BASE / 'SOURCE_SHA256SUMS'
    if sha(receipt) != SOURCE_RECEIPT:
        raise ValueError('sealed source receipt drift')
    for line in receipt.read_text().splitlines():
        digest, name = line.split('  ', 1)
        if sha(BASE / name) != digest:
            raise ValueError('sealed helper/input drift: ' + name)
    spec = importlib.util.spec_from_file_location('sealed_prepare', BASE / 'prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('audited source pattern changed: ' + before)
    return source.replace(before, after, 1)


def adapt(source, identity):
    chosen = SELECTED[identity]
    condition = ' && '.join(f'{name}=={value}' for name, value in chosen.items())
    if source.count(f'if(!({condition}))continue;') != 1:
        raise ValueError('single-case filter identity changed')
    bounds = (dict(seed='3', op='OP_COUNT', s='8', l='7', mode='4',
                   trial='(RESTART_PERMUTATIONS ? 4U:1U)')
              if identity != 'reduction_fflags' else
              dict(scenario='8', l='7', mode='4', rm='5', op='3', sticky='2'))
    for variable, limit in bounds.items():
        value = chosen[variable]
        before = f'for(unsigned {variable}=0;{variable}<{limit};++{variable})'
        after = f'for(unsigned {variable}={value};{variable}<{value+1};++{variable})'
        source = replace_once(source, before, after)
    if identity == 'reduction_fflags':
        # Keep the original initializer and oracle; account for skipped index++.
        source = replace_once(source, 'unsigned index=0;',
                              'unsigned index=0;\n'
                              '        /* 285 preceding fixture reads incremented index only. */\n'
                              '        index += ((4*4+3)*5+0)*3+0;')
    return source


def prepare(out, compiler):
    parent = BASE / 'prepared'
    provenance = compiler.check(parent)
    shutil.copytree(parent, out)
    audit = {}
    diffs = []
    for identity in SELECTED:
        path = out / identity / 'case.c'
        before = path.read_text()
        after = adapt(before, identity)
        path.write_text(after)
        diffs.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        fromfile='sealed/' + identity + '/case.c',
                                        tofile='fast/' + identity + '/case.c'))
        audit[identity] = dict(tuple=SELECTED[identity], parent_sha256=sha(parent / identity / 'case.c'),
                               derived_sha256=sha(path))
    changed = [name for name, digest in provenance['files'].items() if sha(out / name) != digest]
    if sorted(changed) != sorted(name + '/case.c' for name in SELECTED):
        raise ValueError('unexpected source change')
    compiler.save(out / 'parent_provenance.json', provenance)
    (out / 'sources.diff').write_text(''.join(diffs))
    provenance['derivation'] = dict(
        kind='single-case filter-loop narrowing, not original Linux program acceptance',
        parent_prepared=str(parent), parent_provenance_sha256=sha(parent / 'provenance.json'),
        adapter_sha256=sha(__file__), proof_sha256=sha(HERE / 'PROOF.md'),
        selected=audit, changed_files=changed,
        reduction_index_advance=285, reduction_flat_fixture_index=4905)
    provenance['files'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
                           if p.is_file() and p.name != 'provenance.json'}
    compiler.save(out / 'provenance.json', provenance)
    compiler.check(out)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='fresh output root')
    parser.add_argument('--cc', type=Path,
                        default=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc'))
    args = parser.parse_args()
    out = args.out.resolve()
    compiler = sealed_compile()
    out.mkdir(parents=True, exist_ok=False)
    prepare(out / 'prepared', compiler)
    compiler.compile_programs(out / 'prepared', out / 'soc', args.cc)
    compiler.compile_programs(out / 'prepared', out / 'spike', args.cc, spike_reference=True)
    command = [sys.executable, str(BASE / 'reference.py'), '--programs', str(out / 'spike'),
               '--out', str(out / 'reference')]
    compiler.save(out / 'reference_command.json', command)
    subprocess.run(command, check=True)
    sealed_compile()
    compiler.check(out / 'prepared')
    compiler.save(out / 'result.json', dict(status='PASS', vcs_started=False,
                  soc_programs=str(out / 'soc/programs.json'), spike_programs=str(out / 'spike/programs.json'),
                  reference=str(out / 'reference/reference.json'),
                  files={str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
                         if p.is_file()}))
    print('FAST_PACKAGE_PASS ' + str(out))


if __name__ == '__main__':
    main()
