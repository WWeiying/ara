#!/usr/bin/env python3
"""Bounded multi-lane reduction epoch unit; buffered SLDU barrier, not full SoC."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
FROZEN=Path('/home/wangwy/fpga_runs/current_board_integration_final02/frozen/sources')
BEFORE=Path('/home/wangwy/fpga_runs/comparison_nv_producer_20261010/after02/inputs/hardware/src/lane/vmfpu.sv')
MANIFEST=Path('/tmp/ordered-reduction-extended-after-20261010-01/command.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--vmfpu',type=Path,default=BEFORE)
    parser.add_argument('--lanes',type=int,choices=(1,2,4),required=True)
    parser.add_argument('--snapshot',action='store_true')
    args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False); pins={}

    def pin(name,source):
        data=source.read_bytes(); path=out/'inputs'/name
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data); path.chmod(0o444)
        pins[name]=dict(source=str(source),sha256=hashlib.sha256(data).hexdigest())
        return str(path)

    relatives=[s.split('/inputs/')[1] for s in json.loads(MANIFEST.read_text())
               if '/inputs/hardware/' in s and s.endswith(('.sv','.v'))]
    sources=[pin(s,args.vmfpu.resolve() if s=='hardware/src/lane/vmfpu.sv' else FROZEN/s) for s in relatives]
    for directory in ('hardware/include/ara','hardware/deps/common_cells/include/common_cells'):
        for source in sorted((FROZEN/directory).glob('*.svh')): pin(str(source.relative_to(FROZEN)),source)
    sources.append(pin('test/epoch_tb.sv',HERE/'epoch_tb.sv'))
    pin('test/run.py',HERE/'run.py')
    (out/'pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    vcs='/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi='/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    env=dict(os.environ,VCS_HOME=vcs,VERDI_HOME=verdi,SNPSLMD_LICENSE_FILE='27000@t7920')
    env['PATH']=vcs+'/bin:'+env['PATH']
    command=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-debug_access+all','-top','epoch_tb',
             '-pvalue+epoch_tb.N='+str(args.lanes),
             '+incdir+'+str(out/'inputs/hardware/deps/common_cells/include'),
             '+incdir+'+str(out/'inputs/hardware/include'),*sources,'-o',str(out/'simv'),'-l',str(out/'compile.log')]
    if args.snapshot: command.insert(1,'+define+EPOCH_SNAPSHOT')
    run=[str(out/'simv'),'-no_save','+FSDB']
    (out/'command.json').write_text(json.dumps(command,indent=2)+'\n')
    (out/'run_command.json').write_text(json.dumps(run,indent=2)+'\n')
    status=dict(state='STARTED',lanes=args.lanes,case_count=144,vmfpu=pins['hardware/src/lane/vmfpu.sv'],
                scope='real VMFPU/FPnew, modeled neutralized seed/source interface and buffered SLDU tree; no CPU/CSR')
    try:
        with (out/'compile.console.log').open('w') as log:
            subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=True)
        with (out/'run.console.log').open('w') as log:
            subprocess.run(run,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
        log=(out/'run.console.log').read_text()
        with (out/'results.csv').open() as stream: rows=list(csv.DictReader(stream))
        if not re.search(rf'EPOCH_COMPLETE N={args.lanes} cases=144 failed=\d+',log) or re.search(r'(?m)^(Error|Fatal)(-|:)',log):
            raise RuntimeError('Harness failure; inspect retained logs/trace')
        if [int(r['id']) for r in rows]!=list(range(144)): raise RuntimeError('Case accounting')
        failures=[r for r in rows if int(r['data_errors']) or int(r['flag_errors'])]
        status.update(state='FAIL_EPOCH_ORACLE' if failures else 'PASS_EPOCH_UNIT',failures=failures)
        for name,item in pins.items():
            if hashlib.sha256((out/'inputs'/name).read_bytes()).hexdigest()!=item['sha256']:
                raise RuntimeError('Snapshot modified: '+name)
    except Exception as error: status.update(state='ERROR',error=repr(error))
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k!='failures'} | {'failure_count':len(status.get('failures',[]))},indent=2))
    return int(status['state']!='PASS_EPOCH_UNIT')


if __name__=='__main__': raise SystemExit(main())
