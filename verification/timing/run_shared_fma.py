#!/usr/bin/env python3
"""Freeze and test the standalone shared FMA; no production integration or DC."""
import argparse
from pathlib import Path
import shutil
import run_operand_ext as api

SOURCES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/stream_register.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_classifier.sv',
    'hardware/deps/fpnew/src/fpnew_rounding.sv',
    'hardware/deps/fpnew/src/fpnew_fma.sv',
    'hardware/deps/fpnew/src/fpnew_fma_multi.sv',
    'hardware/src/lane/simd_fma_shared.sv',
    'verification/timing/shared_fma_tb.sv',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'src').mkdir()
    for path in SOURCES:
        shutil.copy2(api.ROOT/path, out/'src'/Path(path).name)
    shutil.copytree(api.ROOT/'hardware/deps/common_cells/include', out/'include')
    shutil.copy2(__file__, out/'worker.py')
    shutil.copy2(Path(api.__file__), out/'run_operand_ext.py')
    api.save(out/'source-pins.json', {
        str(f): api.sha(f) for f in out.rglob('*') if f.is_file()})
    status = {'state': 'BUILDING', 'scope': 'Standalone ADDMUL candidate miter only'}
    def state(**fields):
        status.update(fields)
        api.save(out/'status.json', status)
        print(status, flush=True)
    try:
        state()
        cmd = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-top', 'shared_fma_tb', '-o', 'simv', '+incdir+include',
               *['src/'+Path(p).name for p in SOURCES]]
        api.save(out/'command.json', {'compile': cmd, 'run': ['./simv', '-no_save']})
        api.command(cmd, out, out/'compile.log', None, seconds=600)
        api.verify(out)
        state(state='TESTING')
        text = api.command(['./simv', '-no_save'], out, out/'run.log',
                           'SHARED_FMA_PASS', seconds=600)
        api.verify(out)
        state(state='PASS', result=[s for s in text.splitlines() if s.startswith('SHARED_FMA_PASS')])
    except Exception as exc:
        state(state='FAIL', error=str(exc))
        raise


if __name__ == '__main__':
    main()
