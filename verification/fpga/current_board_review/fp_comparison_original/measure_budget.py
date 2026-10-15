#!/usr/bin/env python3
"""Measure same-ELF Spike retire counts and completed VCS calibration traces."""
import csv
import math
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
from recover import HERE, read, save, sha
sys.path.insert(0, str(HERE.parent/'comparison_alias_original'))
import prepare19 as base


def main():
    out=HERE/'budget01'; out.mkdir(exist_ok=False)
    prepared=HERE/'prepared02'
    pins={str(base.SPIKE):sha(base.SPIKE),str(Path(__file__)):sha(Path(__file__))}
    counts=[]
    for name,entry in read(prepared/'spike/programs.json')['programs'].items():
        elf=Path(entry['path']); assert sha(elf)==entry['sha256']
        symbols=read(prepared/'spike'/f'{name}.symbols.json')
        debug=out/f'{name}.cmd'
        debug.write_text('until pc 0 '+symbols['_start']+'\nreg 0 minstret\nuntil pc 0 '+symbols['replay_exit']+
            '\nreg 0 minstret\nreg 0 a0\nstr '+symbols['replay_log']+'\nrs\n')
        log=out/f'{name}.log'; started=time.monotonic()
        base.command([base.SPIKE,'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvfh_zvl1024b','-m2',elf],log,120)
        text=log.read_text(); values=[int(x,16) for x in re.findall(r'^0x([0-9a-f]+)$',text,re.M)]
        assert len(values)==3 and values[1]>values[0] and values[2]==0
        assert all(m in text for m in entry['pass_markers']) and not re.search(r'RVV_FP_COMPARE_(FAIL|DETAIL|CAPACITY_FAIL)',text)
        for p in (elf,debug,log,prepared/'spike/programs.json'):pins[str(p)]=sha(p)
        counts.append(dict(name=name,elf_sha256=sha(elf),start_minstret=values[0],exit_minstret=values[1],
            retired=values[1]-values[0],spike_elapsed_s=time.monotonic()-started,oracle='PASS'))
    calibrations=[]
    sources=[
        (HERE.parent/'comparison_alias_original/candidate04_01/singles/replay/summary.json',None,'M4'),
        (HERE.parent/'comparison_scalar_original/vcs_candidate04_01/first/replay/summary.json',None,'M4'),
        (HERE.parent/'integration/memory_regression_plan02/replay/summary.json',
         {'comparison-matrix__matrix_e16','comparison-matrix__matrix_e32','comparison-matrix__matrix_e64'},'M2'),
    ]
    for summary,names,version in sources:
        pins[str(summary)]=sha(summary)
        for row in read(summary):
            if names is not None and row['name'] not in names:continue
            assert row['status']=='PASS' and row['returncode']==0
            trace=Path(row['artifact_dir'])/'commit_trace.csv'
            retired=0; last_cycle=0
            with trace.open() as f:
                for event in csv.DictReader(f):
                    retired+=event['event']=='retire'
                    last_cycle=int(event['cycle'])
            assert retired>0 and row['elapsed_s']>0
            pins[str(trace)]=sha(trace)
            calibrations.append(dict(name=row['name'],version=version,elapsed_s=row['elapsed_s'],
                retired=retired,last_cycle=last_cycle,retired_per_second=retired/row['elapsed_s'],
                cycles_per_second=last_cycle/row['elapsed_s'],trace=str(trace)))
    # Use the slowest completed sample, including tiny controls with startup cost.
    rate=min(x['retired_per_second'] for x in calibrations)
    for row in counts:
        row['estimate_s']=row['retired']/rate
        row['timeout_s']=max(300,math.ceil((2*row['estimate_s']+120)/300)*300)
    save(out/'finding.json',dict(status='BUDGET_REFERENCE_ONLY_NOT_DUT',counts=counts,calibrations=calibrations,
        conservative_rate=rate,formula='ceil_to_300s(2 * Spike_retired / slowest_completed_retire_rate + 120s), minimum300s',
        limits='Spike scalar retire count is not RTL cycle count; vector stalls, cache and concurrent host load vary. M2 FP calibration is not M4 acceptance.',
        inner_sum_s=sum(x['timeout_s'] for x in counts),jobs=2))
    save(out/'pins.json',pins)
    print(read(out/'finding.json'))


if __name__=='__main__':main()
