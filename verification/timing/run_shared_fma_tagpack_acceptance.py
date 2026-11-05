#!/usr/bin/env python3
"""Pinned tag-compaction SoC qualification, followed by matched component DC."""
import argparse
from pathlib import Path
import subprocess
import sys
import run_operand_ext as api


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    for name in ('prior-soc','prior-ppa','component','softfloat'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    def state(**kw):
        api.save(out/'status.json',kw); print(kw,flush=True)
    try:
        state(state='PREPARING')
        paths=[api.HERE/n for n in ('run_shared_fma_tagpack_acceptance.py','run_shared_fma_tagpack_soc.py',
               'run_shared_fma_ppa.py','run_shared_fma_soc.py','run_operand_ext.py','run_shared_alu_soc.py',
               'shared_fma_timing.sv','shared_fma_soc_monitor.sv','shared_alu_ppa.tcl',
               'shared_fma_tagpack_soc_monitor.sv')]
        paths += [api.ROOT/p for p in ('hardware/src/lane/vmfpu.sv','hardware/src/lane/simd_fpnew.sv',
                  'hardware/src/lane/simd_fma_shared.sv',
                  'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env')]
        pins={str(f):api.sha(f) for f in paths}
        for d in (a.prior_soc,a.prior_ppa,a.component,a.softfloat):
            api.verify(d.resolve()); pins.update(api.read(d.resolve()/'source-pins.json'))
            for name in ('report.json','status.json','library-pins.json','source-pins.json'):
                f=d.resolve()/name
                if f.is_file(): pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins); api.verify(out)
        state(state='SOC_RUNNING')
        cmd=[sys.executable,str(api.HERE/'run_shared_fma_tagpack_soc.py'),str(out/'soc')]
        for name in ('prior_soc','component','softfloat'):
            cmd+=['--'+name.replace('_','-'),str(getattr(a,name).resolve())]
        with (out/'soc-worker.log').open('w') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        api.verify(out)
        if api.read(out/'soc/report.json')['state']!='PASS': raise ValueError('SoC incomplete')
        state(state='PPA_RUNNING')
        cmd=[sys.executable,str(api.HERE/'run_shared_fma_ppa.py'),str(out/'ppa'),
             '--soc',str(out/'soc'),'--prior-shared-ppa',str(a.prior_ppa.resolve()),'--compact-tag']
        with (out/'ppa-worker.log').open('w') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        api.verify(out)
        if api.read(out/'ppa/report.json')['state']!='MEASURED': raise ValueError('PPA incomplete')
        state(state='MEASURED',note='Default remains unchanged; review area and all timing groups')
    except Exception as exc:
        state(state='STOPPED',reason=str(exc)); raise


if __name__=='__main__': main()
