#!/usr/bin/env python3
"""Four independent, expected-failure reproductions on the immutable baseline."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CASES={
    'unmasked_alias_v8_e32_mf2_t0_ctx1':(16,0,5),
    'unboxed_unmasked_alias_v16_e16_m4_t0_ctx1':(16,16,48),
    'unboxed_unmasked_alias_v16_e16_m4_t1_ctx1':(17,17,96),
    'unboxed_unmasked_alias_v8_e16_m4_t0_ctx1':(0,16,2),
}


def main():
    out=HERE/'remaining_baseline01';out.mkdir(exist_ok=False)
    def execute(item):
        name,expected=item
        dest=out/name
        command=[sys.executable,str(HERE/'replay.py'),'--image',
            '/home/wangwy/fpga_runs/indexed_fault_overlap_fix_20261018_02/image',
            '--prepared',str(HERE/'scenarios_prepared03'),'--out',str(dest),
            '--case',name,'--jobs','1','--baseline-dispatcher']
        with (out/(name+'.log')).open('x') as log:
            r=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=720)
        results=json.loads((dest/'results.json').read_text())['results']
        assert len(results)==1
        actual=results[0]
        signature=f'expected_flags={expected[0]} actual_flags={expected[1]} errors={expected[2]}'
        matched=any(signature in line for line in actual['diagnostics'])
        result=dict(name=name,worker_returncode=r.returncode,architectural_status=actual['status'],
                    original_board_signature_reproduced=matched,expected_signature=signature,
                    diagnostics=actual['diagnostics'])
        print(json.dumps(result),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(execute,CASES.items()))
    (out/'results.json').write_text(json.dumps(dict(results=results,
        scope='Expected failure evidence, not passing regression or coverage'),indent=2)+'\n')
    return int(not all(r['original_board_signature_reproduced'] for r in results))


if __name__=='__main__':raise SystemExit(main())
