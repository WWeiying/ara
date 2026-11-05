#!/usr/bin/env python3
"""Frozen operand-queue extension miter/oracle, followed by matched component DC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RTL = 'hardware/src/lane/operand_queue.sv'
PACKAGES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv', 'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv', 'hardware/include/rvv_pkg.sv',
    'hardware/include/ara_pkg.sv', 'hardware/deps/common_cells/src/fifo_v3.sv',
    'hardware/deps/common_cells/src/lzc.sv',
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def save(p, value):
    temp=p.with_suffix('.tmp'); temp.write_text(json.dumps(value,indent=2)+'\n'); temp.replace(p)


def verify(out):
    for path,digest in read(out/'source-pins.json').items():
        if sha(Path(path)) != digest: raise ValueError('Input drift: '+path)


def command(cmd, cwd, log, marker, seconds=600):
    with log.open('w') as f:
        rc=subprocess.run(['timeout','--signal=TERM','--kill-after=30s',str(seconds),*cmd],
                          cwd=cwd,stdout=f,stderr=subprocess.STDOUT).returncode
    text=log.read_text(errors='replace')
    if rc or re.search(r'(?m)^(Error-|Error:|Fatal:)',text) or (marker and marker not in text):
        raise RuntimeError('Command failed: '+str(log))
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--worker',choices=('ppa',))
    a=p.parse_args(); out=a.output.resolve()
    status={'state':'PREPARING'}
    status_file=out/('ppa.status.json' if a.worker else 'test.status.json')
    def state(**kw):
        status.update(kw); save(status_file,status); print(json.dumps(status),flush=True)
    if not a.worker:
        out.mkdir(parents=True,exist_ok=False); (out/'src').mkdir()
        ref=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        old=subprocess.check_output(['git','-C',str(ROOT),'show',f'{ref}:{RTL}'],text=True)
        (out/'baseline.sv').write_text(old)
        (out/'src/reference.sv').write_text(re.sub(r'\boperand_queue\b','operand_queue_reference',old))
        for path in PACKAGES+[RTL]: shutil.copy2(ROOT/path,out/'src'/Path(path).name)
        for name in ('operand_ext_pkg.sv','operand_ext_tb.sv','operand_ext_timing.sv'):
            shutil.copy2(HERE/name,out/'src'/name)
        shutil.copytree(ROOT/'hardware/deps/common_cells/include',out/'include')
        shutil.copy2(__file__,out/'worker.py')
        shutil.copy2(HERE/'shared_alu_ppa.tcl',out/'template.tcl')
        shutil.copy2(ROOT/'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env',out/'library_env.tcl')
        save(out/'manifest.json',dict(reference=ref,rtl=RTL,candidate_sha256=sha(out/'src/operand_queue.sv'),
            scope='Integer extension source selection only; FIFO/control/FP/reduction unchanged'))
        save(out/'source-pins.json',{str(f):sha(f) for f in out.rglob('*') if f.is_file()})
    try:
        verify(out)
        sources=[f'src/{Path(x).name}' for x in PACKAGES]+['src/operand_ext_pkg.sv','src/operand_queue.sv']
        if not a.worker:
            state(state='BUILDING')
            cmd=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-top','operand_ext_tb',
                 '-o','simv','+incdir+include',*sources,'src/reference.sv','src/operand_ext_tb.sv']
            save(out/'command.json',dict(command=cmd))
            command(cmd,out,out/'compile.log',None)
            state(state='TESTING')
            text=command(['./simv','-no_save'],out,out/'run.log','OPERAND_EXT_PASS')
            rows=re.findall(r'OPERAND_EXT_CASE_PASS support=(\d+) depth=(\d+) comb=(\d+) transactions=(\d+) transfers=(\d+) aborted=(\d+)',text)
            if len(rows)!=8 or {int(x[0]) for x in rows}!=set(range(8)): raise ValueError('Incomplete test matrix')
            verify(out); state(state='PASS',configurations=rows)
            return 0
        if read(out/'test.status.json')['state']!='PASS': raise ValueError('Functional gate missing')
        tcl=(out/'template.tcl').read_text()
        tcl,n=re.subn(r'set sources \{.*?\}','set sources {'+' '.join(sources+['src/operand_ext_timing.sv'])+'}',tcl,count=1,flags=re.S)
        if n!=1: raise ValueError('Cannot replace source list')
        tcl=tcl.replace('elaborate simd_alu_timing','elaborate operand_ext_timing')
        tcl=tcl.replace('set_app_var search_path [concat ./src $search_path]',
                        'set_app_var search_path [concat ./src ./include $search_path]')
        # Pin actual libraries before either run; not only the library setup file.
        tcl=tcl.replace('set_host_options -max_cores 2', '''set f [open resolved_libraries.txt w]
foreach path $target_library {puts $f [file normalize $path]}
close $f
if {[info exists ::env(OPERAND_EXT_LIBRARY_PROBE)]} {exit}
set_host_options -max_cores 2''')
        dc=out/'ppa'; dc.mkdir()
        for variant in ('baseline','candidate'):
            d=dc/variant; d.mkdir(); shutil.copytree(out/'src',d/'src'); shutil.copytree(out/'include',d/'include')
            if variant=='baseline': shutil.copy2(out/'baseline.sv',d/'src/operand_queue.sv')
            shutil.copy2(out/'library_env.tcl',d/'library_env.tcl'); (d/'run.tcl').write_text(tcl)
        def docker(d,probe=False):
            args=['docker','exec','-u',f'{os.getuid()}:{os.getgid()}','-e',f'HOME={Path.home()}']
            if probe: args+=['-e','OPERAND_EXT_LIBRARY_PROBE=1']
            return args+['-w',str(d),'synopsys_workspace','bash','-lc',
                'exec timeout --signal=TERM --kill-after=30s 7200 dc_shell -f run.tcl']
        state(state='PINNING_LIBRARIES')
        command(docker(dc/'baseline',True),dc/'baseline',dc/'library-probe.log',None)
        libraries=(dc/'baseline/resolved_libraries.txt').read_text().splitlines()
        if not libraries: raise ValueError('No resolved libraries')
        library_pins={name:sha(Path(name)) for name in libraries}
        save(dc/'library-pins.json',library_pins)
        input_pins={str(f):sha(f) for f in dc.rglob('*')
                    if f.is_file() and f.suffix in ('.sv','.svh','.tcl','.txt')}
        save(dc/'source-pins.json',input_pins)
        for variant in ('baseline','candidate'):
            verify(out)
            for name,digest in library_pins.items():
                if sha(Path(name))!=digest: raise ValueError('Library drift: '+name)
            state(state='SYNTHESIZING',active=variant)
            command(docker(dc/variant),dc/variant,dc/variant/'dc.log','SHARED_ALU_PPA_COMPLETE',seconds=7500)
            if (dc/variant/'resolved_libraries.txt').read_text().splitlines()!=libraries:
                raise ValueError('Library selection changed')
        for name,digest in {**input_pins,**library_pins}.items():
            if sha(Path(name))!=digest: raise ValueError('PPA input drift: '+name)
        metrics={v:dict((x.split('\t')[0],float(x.split('\t')[1])) for x in
                 (dc/v/'metrics.tsv').read_text().splitlines()) for v in ('baseline','candidate')}
        save(dc/'report.json',dict(state='MEASURED',metrics=metrics,
            area_reduction_pct=100*(1-metrics['candidate']['area_um2']/metrics['baseline']['area_um2']),
            scope='Complete ALU-B-parameter operand queue, not SoC area',
            acceptance='Review area AND setup/hold/path constraints; measurement is not physical signoff'))
        state(state='MEASURED',active=None); return 0
    except Exception as exc:
        state(state='FAIL',reason=str(exc)); raise


if __name__=='__main__':
    raise SystemExit(main())
