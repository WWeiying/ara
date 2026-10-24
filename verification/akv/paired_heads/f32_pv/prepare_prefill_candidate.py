#!/usr/bin/env python3
"""Generate/compile an opt-in Prefill PV candidate without canonical edits."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT/'software/akv/src/akv_v2_native_riscv.c'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transform(source):
    replacements = [
        ('extern char *getenv(const char *name) __attribute__((weak));',
         'extern char *getenv(const char *name) __attribute__((weak));\n'
         '#include "../experimental/paired_heads/f32_pv/runtime.h"'),
        ('  const uint32_t q_rows = problem->query_heads / problem->kv_heads;',
         '  const uint32_t q_rows = problem->query_heads / problem->kv_heads;\n'
         '  const int paired_pv = akv_prefill_pair_pv_enabled(device, q_rows, problem->head_dim);'),
        ('              akv_v2_update_outputs_f32_generic(\n'
         '                  &workspace->score[compute_slot][0][0], output,',
         '              akv_prefill_pair_pv_dispatch(paired_pv,\n'
         '                  &workspace->score[compute_slot][0][0], output,')]
    for before,after in replacements:
        if source.count(before) != 1:
            raise ValueError('Missing or ambiguous Prefill source anchor: '+before.splitlines()[0])
        source = source.replace(before,after,1)
    return source


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    original = SOURCE.read_text()
    source_hash = digest(SOURCE)
    candidate = out/'akv_prefill_pv_candidate.c'
    candidate.write_text(transform(original))
    (out/'candidate.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),
        candidate.read_text().splitlines(True),fromfile='a/software/akv/src/akv_v2_native_riscv.c',
        tofile='b/software/akv/src/akv_v2_native_riscv.c')))
    flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-O3',
        '-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections',
        '-DAKV_REFILL_OVERLAP=0','-iquote',str(SOURCE.parent),'-I'+str(ROOT/'software/akv/include')]
    deps = subprocess.check_output([str(CC),*flags,'-M','-MT','candidate',str(candidate)],text=True)
    paths = [Path(x).resolve(strict=True) for x in shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]
    paths += [SOURCE,Path(__file__).resolve(),CC.resolve()]
    pins = {str(p):digest(p) for p in paths}
    obj = out/'candidate.o'
    with (out/'compile.log').open('x') as log:
        subprocess.run([str(CC),*flags,'-c',str(candidate),'-o',str(obj)],
                       stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
    symbols = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),str(obj)],text=True)
    (out/'symbols.txt').write_text(symbols)
    for name in ('akv_attention_execute_v2_prefill_native','akv_experimental_pv_f32_pair',
                 'akv_v2_update_outputs_f32_generic','akv_v2_update_outputs_f32_d128_gqa6'):
        if not any(line.split()[-1] == name for line in symbols.splitlines()):
            raise ValueError('Missing required candidate call graph: '+name)
    if digest(SOURCE) != source_hash or any(digest(p) != h for p,h in pins.items()):
        raise ValueError('Source drift')
    result = dict(state='PREFILL_CANDIDATE_COMPILED_NOT_EXECUTED',source_pins=pins,
        canonical_modified=False,object_sha256=digest(obj),candidate_sha256=digest(candidate),
        patch_sha256=digest(out/'candidate.patch'),native_accepted=False,performance_accepted=False,
        scope='Three exact substitutions, once-before-FULL selection, original GQA6 special and QK/masks/softmax unchanged')
    (out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('state','canonical_modified','native_accepted')}))


if __name__ == '__main__':
    main()
