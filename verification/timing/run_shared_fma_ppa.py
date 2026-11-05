#!/usr/bin/env python3
"""Matched ADDMUL DC, gated on the finished paired SoC regression."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import run_operand_ext as api

DEPS=[
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/rr_arb_tree.sv',
    'hardware/deps/common_cells/src/stream_register.sv',
    *['hardware/deps/fpnew/src/'+name for name in (
        'fpnew_pkg.sv','fpnew_classifier.sv','fpnew_rounding.sv','fpnew_fma.sv',
        'fpnew_fma_multi.sv','fpnew_opgroup_fmt_slice.sv','fpnew_opgroup_block.sv')],
    'hardware/src/lane/simd_fma_shared.sv',
]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--soc',type=Path,required=True)
    p.add_argument('--prior-shared-ppa',type=Path)
    a=p.parse_args(); out=a.output.resolve(); soc=a.soc.resolve()
    # No polling and no synthesis if functionality is still pending.
    report=api.read(soc/'report.json')
    plan=api.read(soc/'plan.json')
    if (report['state']!='PASS' or report['paired_cases']!=len(plan['cases']) or
            len(plan['cases'])<31 or 'fma_edges' not in plan['cases']):
        raise ValueError('Complete paired SoC functional prerequisite missing')
    api.verify(soc)
    prior=a.prior_shared_ppa.resolve() if a.prior_shared_ppa else None
    if prior:
        if api.read(prior/'report.json')['state']!='MEASURED': raise ValueError('Prior shared PPA missing')
        api.verify(prior)
    out.mkdir(parents=True,exist_ok=False)
    status={'state':'PREPARING'}
    def state(**kw):
        status.update(kw); api.save(out/'status.json',status); print(json.dumps(status),flush=True)
    source=soc/'shared/source'
    try:
        state()
        tcl=(api.HERE/'shared_alu_ppa.tcl').read_text()
        sources=['src/'+Path(x).name for x in DEPS]+['src/shared_fma_timing.sv']
        tcl,n=re.subn(r'set sources \{.*?\}','set sources {'+' '.join(sources)+'}',tcl,count=1,flags=re.S)
        if n!=1: raise ValueError('DC template source boundary missing')
        tcl=tcl.replace('elaborate simd_alu_timing','elaborate shared_fma_timing')
        tcl=tcl.replace('set_app_var search_path [concat ./src $search_path]',
                        'set_app_var search_path [concat ./src ./include $search_path]')
        tcl=tcl.replace('set_host_options -max_cores 2','''set f [open resolved_libraries.txt w]
foreach path $target_library {puts $f [file normalize $path]}
close $f
if {[info exists ::env(FMA_LIBRARY_PROBE)]} {exit}
set_host_options -max_cores 2''')
        tcl=tcl.replace('SHARED_ALU_PPA_COMPLETE','SHARED_FMA_PPA_COMPLETE')
        for variant in ('baseline','shared'):
            d=out/variant; (d/'src').mkdir(parents=True)
            for rel in DEPS: shutil.copy2(source/rel,d/'src'/Path(rel).name)
            if variant=='baseline' and prior:
                shutil.copy2(prior/'shared/src/simd_fma_shared.sv',d/'src/simd_fma_shared.sv')
                for rel in DEPS:
                    if '/deps/fpnew/' in rel and api.sha(d/'src'/Path(rel).name)!=api.sha(prior/'shared/src'/Path(rel).name):
                        raise ValueError('Prior shared arithmetic differs: '+rel)
            shutil.copy2(api.HERE/'shared_fma_timing.sv',d/'src/shared_fma_timing.sv')
            shutil.copytree(source/'hardware/deps/common_cells/include',d/'include')
            shutil.copy2(api.ROOT/'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env',d/'library_env.tcl')
            (d/'run.tcl').write_text(tcl.replace('set defines {SYNTHESIS}',
                'set defines {SYNTHESIS SHARED_FMA_PPA}' if variant=='shared' or prior else 'set defines {SYNTHESIS}'))
        shutil.copy2(__file__,out/'worker.py')
        shutil.copy2(Path(api.__file__),out/'run_operand_ext.py')
        api.save(out/'manifest.json',dict(soc=str(soc),scope='Per-lane ADDMUL only; excludes DIVSQRT and other SoC area',
                 period_ns=1.0,setup_uncertainty_ns=0.15,tag_bits=80,
                 baseline_latency_fp16_fp32_fp64=[5,5,5] if prior else [3,4,5],
                 shared_latency_fp16_fp32_fp64=[5,5,5],prior_shared_ppa=str(prior) if prior else None))
        pins={str(f):api.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='status.json'}
        pins[str(soc/'report.json')]=api.sha(soc/'report.json')
        api.save(out/'source-pins.json',pins)
        def docker(d,probe=False):
            cmd=['docker','exec','-u',f'{os.getuid()}:{os.getgid()}','-e',f'HOME={Path.home()}']
            if probe: cmd+=['-e','FMA_LIBRARY_PROBE=1']
            return cmd+['-w',str(d),'synopsys_workspace','bash','-lc',
                        'exec timeout --signal=TERM --kill-after=30s 10800 dc_shell -f run.tcl']
        state(state='PINNING_LIBRARIES')
        api.command(docker(out/'baseline',True),out/'baseline',out/'library-probe.log',None)
        libraries=(out/'baseline/resolved_libraries.txt').read_text().splitlines()
        if not libraries: raise ValueError('No libraries selected')
        library_pins={name:api.sha(Path(name)) for name in libraries}
        if prior and library_pins!=api.read(prior/'library-pins.json'):
            raise ValueError('Prior shared and compact measurement libraries differ')
        api.save(out/'library-pins.json',library_pins)
        for variant in ('baseline','shared'):
            api.verify(out)
            for name,h in library_pins.items():
                if api.sha(Path(name))!=h: raise ValueError('Library drift: '+name)
            state(state='SYNTHESIZING',active=variant)
            api.command(docker(out/variant),out/variant,out/variant/'dc.log',
                        'SHARED_FMA_PPA_COMPLETE',seconds=11000)
            if (out/variant/'resolved_libraries.txt').read_text().splitlines()!=libraries:
                raise ValueError('Library selection changed')
        api.verify(out)
        metrics={v:dict((line.split('\t')[0],float(line.split('\t')[1])) for line in
                 (out/v/'metrics.tsv').read_text().splitlines()) for v in ('baseline','shared')}
        api.save(out/'report.json',dict(state='MEASURED',metrics=metrics,
                 area_reduction_pct=100*(1-metrics['shared']['area_um2']/metrics['baseline']['area_um2']),
                 scope='Local matched ADDMUL measurement; inspect all timing groups before adoption'))
        state(state='MEASURED',active=None)
    except Exception as exc: state(state='FAIL',reason=str(exc)); raise


if __name__=='__main__': main()
