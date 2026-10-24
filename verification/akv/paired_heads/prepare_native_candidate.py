#!/usr/bin/env python3
"""Generate a tightly scoped native candidate without editing sealed sources."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT/'software/akv/src/akv_v2_native_riscv.c'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transform(source):
    replacements = [
        ('extern char *getenv(const char *name) __attribute__((weak));',
         'extern char *getenv(const char *name) __attribute__((weak));\n'
         '#include "../experimental/paired_heads/native_selection.h"'),
        ('  const int qk_panel4 = qk_panel4_enabled_for_plan(plan);',
         '  const int qk_panel4 = qk_panel4_enabled_for_plan(plan);\n'
         '  const int paired_heads = akv_pair_candidate_enabled_for_plan(plan);'),
        ('      akv_v2_compute_scores_f16_generic(\n'
         '          query, &workspace->score[0][0], tile_tokens,\n'
         '          query_row_stride_bytes, q_rows, head_dim);',
         '      akv_pair_qk_f16_dispatch(paired_heads,\n'
         '          query, &workspace->score[0][0], tile_tokens,\n'
         '          query_row_stride_bytes, q_rows, head_dim);'),
        ('      akv_v2_update_outputs_f16_generic(\n'
         '          &workspace->score[0][0], &workspace->accumulator[0][0],\n'
         '          workspace->old_scale, tile_tokens, q_rows, head_dim);',
         '      akv_pair_pv_f16_dispatch(paired_heads,\n'
         '          &workspace->score[0][0], &workspace->accumulator[0][0],\n'
         '          workspace->old_scale, tile_tokens, q_rows, head_dim);')]
    for before,after in replacements:
        if source.count(before) != 1:
            raise ValueError('Candidate source anchor missing or ambiguous: '+before.splitlines()[0])
        source = source.replace(before,after,1)
    return source


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    original = SOURCE.read_text()
    before = digest(SOURCE)
    candidate = out/'akv_v2_native_candidate.c'
    candidate.write_text(transform(original))
    (out/'candidate.patch').write_text(''.join(difflib.unified_diff(
        original.splitlines(True),candidate.read_text().splitlines(True),
        fromfile='a/software/akv/src/akv_v2_native_riscv.c',
        tofile='b/software/akv/src/akv_v2_native_riscv.c')))
    flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-O3',
        '-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections',
        '-DAKV_REFILL_OVERLAP=0','-iquote',str(SOURCE.parent),
        '-I'+str(ROOT/'software/akv/include')]
    deps = subprocess.check_output([str(CC),*flags,'-M','-MT','candidate',str(candidate)],text=True)
    paths = [Path(x).resolve(strict=True) for x in shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]
    paths += [SOURCE,Path(__file__).resolve(),CC.resolve()]
    pins = {str(x):digest(x) for x in paths}
    obj = out/'candidate.o'
    with (out/'compile.log').open('x') as log:
        subprocess.run([str(CC),*flags,'-c',str(candidate),'-o',str(obj)],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    nm = CC.with_name('riscv64-unknown-elf-nm')
    symbols = subprocess.check_output([str(nm),str(obj)],text=True)
    (out/'symbols.txt').write_text(symbols)
    for symbol in ('akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair',
                   'akv_attention_execute_v2_native','akv_attention_execute_v2_with_features_native'):
        if not any(line.split()[-1] == symbol for line in symbols.splitlines()):
            raise ValueError('Missing candidate symbol '+symbol)
    if any(name in symbols for name in ('bench_pair_enabled','bench_active')):
        raise ValueError('Benchmark mutable state leaked into candidate')
    if digest(SOURCE) != before or any(digest(Path(x)) != h for x,h in pins.items()):
        raise ValueError('Source drift during preparation')
    report = dict(state='CANDIDATE_COMPILED_NOT_EXECUTED',canonical_modified=False,
        source_sha256=before,source_pins=pins,candidate_sha256=digest(candidate),
        patch_sha256=digest(out/'candidate.patch'),object_sha256=digest(obj),
        numerical_accepted=False,rtl_accepted=False,ggml_deployed=False,
        scope='Four exact source substitutions; local opt-in before FULL; original GQA6/Prefill/D256 paths retained')
    (out/'result.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:report[k] for k in ('state','canonical_modified','rtl_accepted')}))


if __name__ == '__main__':
    main()
