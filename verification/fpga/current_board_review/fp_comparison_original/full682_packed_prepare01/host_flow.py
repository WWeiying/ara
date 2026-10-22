#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('prep',HERE/'prepare.py')
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
u=p.u


def main():
    run=HERE/'host_flow01';run.mkdir()
    u.save(run/'pins.json',{str(f):u.sha(f) for f in [Path(__file__),HERE/'host_flow.c',
           HERE/'run01/case.c',HERE/'run01/tables.h',p.CASE/'case.c',
           p.CASE/'original/fixtures.h',p.CASE/'original/operations.h']})
    results=[]
    for variant,source in [('original',p.CASE/'case.c'),('packed',HERE/'run01/case.c')]:
        u.command(['gcc','-O2','-Wall','-Wextra','-Werror','-fno-tree-vectorize','-fno-tree-slp-vectorize',
                   '-DSEW=16','-DUNMASKED_COMPARISONS=1','-DDESTINATION_KIND=1',
                   '-I'+str(p.CASE/'original'),source,HERE/'host_flow.c','-o',run/variant],run/(variant+'_compile'),120)
        for mutation in range(7):
            name=variant+str(mutation)
            argv=[str(run/variant),str(mutation),str(run/(name+'.bin'))]
            start=time.monotonic()
            with (run/(name+'.log')).open('xb') as f:
                proc=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT)
                try:rc=proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.kill();rc=proc.wait()
                    u.save(run/(name+'.exit.json'),dict(returncode=rc,timed_out=True))
                    raise
            outcome=dict(returncode=rc,pid=proc.pid,elapsed_s=time.monotonic()-start,mutation=mutation)
            u.save(run/(name+'.exit.json'),outcome)
            assert rc==(0 if mutation==0 else 1),outcome
            results.append(outcome)
    for mutation in range(7):
        assert u.sha(run/('original'+str(mutation)+'.bin'))==u.sha(run/('packed'+str(mutation)+'.bin'))
    u.save(run/'result.json',dict(status='HOST_ACTUAL_SOURCE_CALL_FLOW_EQUIVALENT',calls_each=682,
        positive_pairs=1,negative_pairs=6,full_a_b_mask_output_initialization=True,
        all_call_parameters_and_order=True,byte_identical_call_record_sha256=u.sha(run/'original0.bin'),
        results=results,limits='Host scalar flow proof, not RISC-V ABI or dynamic VRF-state audit'))
    print((run/'result.json').read_text())


if __name__=='__main__':main()
