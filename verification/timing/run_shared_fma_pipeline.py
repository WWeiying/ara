#!/usr/bin/env python3
"""Compare compact FMA against the accepted frozen pipeline cycle by cycle."""
import argparse
from pathlib import Path
import re
import shutil
import run_operand_ext as api
from run_shared_fma import SOURCES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--prior-soc', type=Path, required=True)
    a = p.parse_args()
    prior = a.prior_soc.resolve()
    if api.read(prior/'report.json')['state'] != 'PASS':
        raise ValueError('Prior accepted SoC required')
    api.verify(prior)
    frozen = prior/'shared/source'
    old = frozen/'hardware/src/lane/simd_fma_shared.sv'
    if api.sha(old) != '4cdd123575aab2989ccb6990b108613a113df86494f0d49f0fe9883a3350617e':
        raise ValueError('Unexpected prior FMA identity')
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'src').mkdir()
    for rel in SOURCES:
        if '/deps/' in rel and api.sha(api.ROOT/rel) != api.sha(frozen/rel):
            raise ValueError('Arithmetic/dependency drift: '+rel)
        shutil.copy2(api.ROOT/rel, out/'src'/Path(rel).name)
    renamed, count = re.subn(r'\bmodule simd_fma_shared\b', 'module simd_fma_prior', old.read_text())
    if count != 1:
        raise ValueError('Reference rename boundary')
    (out/'src/simd_fma_prior.sv').write_text(renamed)
    shutil.copytree(frozen/'hardware/deps/common_cells/include', out/'include')
    shutil.copy2(__file__, out/'worker.py')
    shutil.copy2(Path(api.__file__), out/'run_operand_ext.py')
    pins = {str(f): api.sha(f) for f in out.rglob('*') if f.is_file()}
    pins[str(old)] = api.sha(old)
    pins[str(prior/'report.json')] = api.sha(prior/'report.json')
    api.save(out/'source-pins.json', pins)
    def state(**fields):
        api.save(out/'status.json', fields)
        print(fields, flush=True)
    try:
        state(state='BUILDING')
        cmd = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
               '+define+SHARED_FMA_CYCLE_MITER', '-top', 'shared_fma_tb',
               '-o', 'simv', '+incdir+include',
               *['src/'+Path(rel).name for rel in SOURCES[:-1]],
               'src/simd_fma_prior.sv', 'src/shared_fma_tb.sv']
        api.save(out/'command.json', dict(compile=cmd))
        api.command(cmd, out, out/'compile.log', None, seconds=600)
        state(state='TESTING')
        text = api.command(['./simv', '-no_save'], out, out/'run.log', 'SHARED_FMA_PASS')
        checks = re.findall(r'^SHARED_FMA_CYCLE_CHECKS (\d+)$', text, re.M)
        if len(checks) != 1 or int(checks[0]) < 15000:
            raise ValueError('Insufficient cycle-level checking')
        api.verify(out)
        state(state='PASS', cycle_checks=int(checks[0]),
              results=[s for s in text.splitlines() if s.startswith('SHARED_FMA_PASS')])
    except Exception as exc:
        state(state='FAIL', reason=str(exc))
        raise


if __name__ == '__main__':
    main()
