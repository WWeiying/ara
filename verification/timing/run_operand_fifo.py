#!/usr/bin/env python3
"""Freeze input-FIFO reset specialization; check the FIFO and complete operand queue."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import run_operand_ext as common

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    src=out/'src'; src.mkdir()
    ref=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    old=subprocess.check_output(['git','-C',str(ROOT),'show',f'{ref}:{common.RTL}'],text=True)
    (out/'baseline.sv').write_text(old)
    (src/'reference.sv').write_text(re.sub(r'\boperand_queue\b','operand_queue_reference',old))
    for path in common.PACKAGES+[common.RTL]: shutil.copy2(ROOT/path,src/Path(path).name)
    for name in ('operand_ext_pkg.sv','operand_ext_tb.sv','operand_ext_timing.sv','operand_fifo_tb.sv'):
        shutil.copy2(HERE/name,src/name)
    shutil.copytree(ROOT/'hardware/deps/common_cells/include',out/'include')
    shutil.copy2(__file__,out/'worker.py'); shutil.copy2(HERE/'run_operand_ext.py',out/'run_operand_ext.py')
    shutil.copy2(HERE/'shared_alu_ppa.tcl',out/'template.tcl')
    shutil.copy2(ROOT/'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env',out/'library_env.tcl')
    common.save(out/'manifest.json',dict(reference=ref,rtl=common.RTL,candidate_sha256=common.sha(src/'operand_queue.sv'),
        scope='Local non-fall-through input FIFO, payload reset removed; original conversion restored',
        comparison='Same valid/control every cycle; exact four-state payload when nonempty'))
    common.save(out/'source-pins.json',{str(f):common.sha(f) for f in out.rglob('*') if f.is_file()})
    status={'state':'PREPARING'}
    def state(**kw):
        status.update(kw); common.save(out/'test.status.json',status); print(status,flush=True)
    try:
        sources=[str(src/Path(x).name) for x in common.PACKAGES]
        sources += [str(src/x) for x in ('operand_ext_pkg.sv','operand_queue.sv','reference.sv')]
        matrices={}
        for name,top,marker in [('fifo','operand_fifo_tb','OPERAND_FIFO_PASS'),('queue','operand_ext_tb','OPERAND_EXT_PASS')]:
            d=out/name; d.mkdir(); state(state='BUILDING',active=name)
            cmd=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-top',top,'-o','simv',
                 '+incdir+'+str(out/'include'),*sources,str(src/(top+'.sv'))]
            common.save(d/'command.json',dict(command=cmd))
            common.command(cmd,d,d/'compile.log',None)
            state(state='TESTING',active=name)
            text=common.command(['./simv','-no_save'],d,d/'run.log',marker)
            if name=='fifo':
                rows=re.findall(r'OPERAND_FIFO_CASE_PASS depth=(\d+) cycles=(\d+) writes=(\d+) reads=(\d+) resets=(\d+) flushes=(\d+) simultaneous=(\d+) flush_push=(\d+)',text)
                if len(rows)!=4 or {int(x[0]) for x in rows}!={1,2,3,5}: raise ValueError('Incomplete FIFO matrix')
            else:
                rows=re.findall(r'OPERAND_EXT_CASE_PASS support=(\d+) depth=(\d+) comb=(\d+) transactions=(\d+) transfers=(\d+) aborted=(\d+)',text)
                if len(rows)!=8 or {int(x[0]) for x in rows}!=set(range(8)): raise ValueError('Incomplete consumer matrix')
            matrices[name]=rows
        common.verify(out); state(state='PASS',active=None,matrices=matrices); return 0
    except Exception as exc:
        state(state='FAIL',reason=str(exc)); raise


if __name__=='__main__':
    raise SystemExit(main())
