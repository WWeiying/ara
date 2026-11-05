#!/usr/bin/env python3
"""Independent Spike SoftFloat reference for the isolated shared ADDMUL path."""
import argparse
import importlib.util
from pathlib import Path
import random
import shutil
import run_operand_ext as api
from run_shared_fma import SOURCES


def vectors(oracle):
    sf = oracle.SoftFloat()
    rng = random.Random(0x534641)
    rows = []
    for width, fmt in ((16, 2), (32, 0), (64, 1)):
        frac, exp = {16: (10, 5), 32: (23, 8), 64: (52, 11)}[width]
        one = ((1 << (exp-1))-1) << frac
        sign = 1 << (width-1)
        inf = ((1 << exp)-1) << frac
        nan = inf | (1 << (frac-1))
        edges = [0, sign, 1, sign|1, (1 << frac)-1, 1 << frac,
                 one-1, one, one+1, one|sign, inf-1, inf, inf|sign, nan, inf|1]
        for rm in range(5):
            for op in range(4):
                for n in range(120):
                    vec = n % 5 != 0
                    mod = n % 2
                    mask = rng.randrange(16)
                    boxes = (1 << 18)-1
                    if not vec and n%3 == 0:
                        boxes &= ~(rng.randrange(1,8) << (3*fmt))
                    operands = [0,0,0]
                    result = (1 << 64)-1
                    flags = 0
                    for lane in range(64//width):
                        values = [edges[(n+k*3+lane)%len(edges)] if n < 60 else rng.getrandbits(width)
                                  for k in range(3)]
                        for k, value in enumerate(values): operands[k] |= value << (lane*width)
                        if lane and not vec: continue
                        a,b,c = [value if vec or boxes & (1 << (3*fmt+k)) else nan
                                 for k,value in enumerate(values)]
                        if op == 3:  # MUL ignores operand C and op_mod.
                            y, ex = sf.evaluate('mul', width, width, rm, a,b)
                        else:
                            if op == 2: a=one  # ADD is B + C.
                            if op == 1: a ^= sign  # FNMSUB negates the product.
                            if mod: c ^= sign
                            y, ex = sf.evaluate('fma', width, width, rm, a,b,c)
                        bitmask = ((1 << width)-1) << (lane*width)
                        result = (result & ~bitmask) | (y << (lane*width))
                        if mask & (1 << (lane*(width//16))): flags |= ex
                    rows.append(f'{fmt} {op} {rm} {mod} {int(vec)} {mask:x} {boxes:x} '
                                + ' '.join(f'{v:016x}' for v in operands)
                                + f' {result:016x} {flags:02x}')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    (out/'src').mkdir()
    oracle_path=api.ROOT/'verification/fpnew_upstream_20261009/oracle.py'
    shutil.copy2(oracle_path,out/'oracle.py')
    spec=importlib.util.spec_from_file_location('frozen_softfloat_oracle',out/'oracle.py')
    oracle=importlib.util.module_from_spec(spec); spec.loader.exec_module(oracle)
    source_paths=SOURCES[:-1]+['verification/timing/shared_fma_softfloat_tb.sv']
    for path in source_paths: shutil.copy2(api.ROOT/path,out/'src'/Path(path).name)
    shutil.copytree(api.ROOT/'hardware/deps/common_cells/include',out/'include')
    shutil.copy2(__file__,out/'worker.py')
    shutil.copy2(Path(api.__file__),out/'run_operand_ext.py')
    rows=vectors(oracle); (out/'vectors.txt').write_text('\n'.join(rows)+'\n')
    pins={str(f):api.sha(f) for f in out.rglob('*') if f.is_file()}
    pins[str(oracle.LIB)]=api.sha(oracle.LIB)
    api.save(out/'source-pins.json',pins)
    status={'state':'BUILDING','vectors':len(rows),'scope':'Independent SoftFloat ADDMUL component checks'}
    def state(**fields):
        status.update(fields); api.save(out/'status.json',status); print(status,flush=True)
    try:
        state()
        cmd=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-top','shared_fma_softfloat_tb',
             '-o','simv','+incdir+include',*['src/'+Path(p).name for p in source_paths]]
        api.save(out/'command.json',{'compile':cmd})
        api.command(cmd,out,out/'compile.log',None)
        api.verify(out); state(state='TESTING')
        text=api.command(['./simv','-no_save','+VECTORS=vectors.txt'],out,out/'run.log',
                         f'SHARED_FMA_SOFTFLOAT_PASS checked={len(rows)}')
        api.verify(out); state(state='PASS')
    except Exception as exc:
        state(state='FAIL',error=str(exc)); raise


if __name__=='__main__': main()
