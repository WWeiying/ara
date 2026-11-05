#!/usr/bin/env python3
"""Freeze accepted FPU dependencies and compare opt-in tag packing to old RTL."""
import argparse
from pathlib import Path
import re
import shutil
import run_operand_ext as api


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--prior-soc',type=Path,required=True)
    a=p.parse_args(); prior=a.prior_soc.resolve(); out=a.output.resolve()
    if api.read(prior/'report.json')['state']!='PASS': raise ValueError('Prior SoC missing')
    api.verify(prior)
    out.mkdir(parents=True,exist_ok=False)
    def state(**kw):
        api.save(out/'status.json',kw); print(kw,flush=True)
    try:
        state(state='PREPARING')
        source=prior/'shared/source'; frozen=out/'source'
        # Preserve dependency layout and include paths from the accepted image.
        shutil.copytree(source/'hardware/deps',frozen/'hardware/deps',symlinks=True)
        sources=[]
        for line in (prior/'shared/sources.f').read_text().splitlines():
            if line.startswith('+incdir+') and any(s in line for s in ('common_cells','fpnew','fpu_div_sqrt')):
                sources.append(line.replace(str(source),str(frozen)))
            elif line.startswith('/') and any('/deps/'+d+'/' in line for d in
                    ('common_cells','fpnew','fpu_div_sqrt_mvp')):
                sources.append(line.replace(str(source),str(frozen)))
            elif line.startswith('/') and line.endswith('/tc_clk.sv'):
                sources.append(line.replace(str(source),str(frozen)))
        sources=list(dict.fromkeys(sources))
        (out/'src').mkdir()
        for name in ('simd_fma_shared','simd_fpnew'):
            old=source/f'hardware/src/lane/{name}.sv'
            text=old.read_text()
            for mod in ('simd_fma_shared','simd_fpnew'):
                text=re.sub(r'\b'+mod+r'\b',mod+'_prior',text)
            path=out/'src'/f'{name}_prior.sv'; path.write_text(text); sources.append(str(path))
            path=out/'src'/f'{name}.sv'
            shutil.copy2(api.ROOT/f'hardware/src/lane/{name}.sv',path); sources.append(str(path))
        shutil.copy2(api.ROOT/'hardware/src/lane/vmfpu.sv',out/'src/vmfpu_integration.sv')
        shutil.copy2(api.HERE/'shared_fma_tagpack_tb.sv',out/'src/shared_fma_tagpack_tb.sv')
        sources.append(str(out/'src/shared_fma_tagpack_tb.sv'))
        (out/'sources.f').write_text('\n'.join(sources)+'\n')
        shutil.copy2(__file__,out/'worker.py')
        shutil.copy2(Path(api.__file__),out/'run_operand_ext.py')
        api.save(out/'source-pins.json',{str(f):api.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='status.json'})
        state(state='BUILDING')
        cmd=['vcs','-full64','-sverilog','-timescale=1ns/1ps','+define+COMMON_CELLS_ASSERTS_OFF',
             '-top','shared_fma_tagpack_tb','-o','simv','-f','sources.f']
        api.save(out/'command.json',dict(compile=cmd))
        api.command(cmd,out,out/'compile.log',None,seconds=600)
        state(state='TESTING')
        text=api.command(['./simv','-no_save','+ntb_random_seed=1'],out,out/'run.log','TAGPACK_PASS',seconds=600)
        api.verify(out)
        state(state='PASS',result=[s for s in text.splitlines() if s.startswith('TAGPACK_PASS')],
              scope='Cycle-exact FPU routing/tag qualification; arithmetic unchanged, not an independent numerical oracle')
    except Exception as exc:
        state(state='FAIL',reason=str(exc)); raise


if __name__=='__main__': main()
