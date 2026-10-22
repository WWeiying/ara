#!/usr/bin/env python3
"""Focused real operand-queue/VMFPU/FPnew reduction regression, no full SoC."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
FROZEN = Path('/home/wangwy/fpga_runs/current_board_integration_final01/frozen/sources')
MANIFEST = Path('/tmp/ordered-reduction-extended-after-20261010-01/command.json')


def cases(extended=False):
    result = []

    def add(name, sw=32, dw=64, vl=65, op=0, pattern=1, pos=1, neg=33,
            mask=None, vm=0, seed=None, gap=0, rm=0, prior=0, expected=None, flags=16, queued=0):
        if mask is None:
            mask = (1 << pos if pos >= 0 else 0) | (1 << neg if neg >= 0 else 0)
        if seed is None:
            seed = {64:0x4000000000000000, 32:0x40000000, 16:0x4000}[dw]
        if expected is None:
            expected = {64:0x7ff8000000000000, 32:0x7fc00000, 16:0x7e00}[dw]
        result.append(dict(name=name, sw=sw, dw=dw, vl=vl, op=op, pattern=pattern,
                           pos=pos, neg=neg, mask=mask, vm=vm, seed=seed, gap=gap,
                           rm=rm, prior=prior, expected=expected, flags=flags|prior, queued=queued))

    add('reported_trial9')
    add('ordered_trial4', op=1)
    add('interlane_opposite', pos=1, neg=2)
    add('source_invalid_control', pos=-1, neg=0, seed=0x7ff0000000000000)
    add('all_masked_snan_seed', mask=0, pattern=2, seed=0x7ff0000000000001,
        expected=0x7ff0000000000001, flags=0)
    add('remote_active_snan_seed', mask=2, pattern=0, seed=0x7ff0000000000001)
    add('neutral_fill_bubbles', gap=1)
    add('simd_fp32', sw=32, dw=32, pos=1, neg=5)
    add('simd_fp16_upper_slot', sw=16, dw=16, pos=9, neg=13)
    for op, label in ((2,'min'), (3,'max')):
        add(f'{label}_all_masked_snan_seed', sw=64, op=op, mask=0, pattern=2,
            seed=0x7ff0000000000001, expected=0x7ff0000000000001, flags=0)
        add(f'{label}_remote_active_snan_seed', sw=64, op=op, mask=2, pattern=0,
            seed=0x7ff0000000000001, expected=0x4000000000000000)
        add(f'{label}_finite', sw=64, op=op, mask=2, pattern=0,
            expected=0x4000000000000000, flags=0)
    if extended:
        add('nv_then_queued_finite', queued=1)
        add('empty_snan_then_queued_finite', mask=0, pattern=2, seed=0x7ff0000000000001,
            expected=0x7ff0000000000001, flags=0, queued=1)
        add('nv_then_queued_invalid', queued=2)
        add('finite_after_invalid', mask=2, pattern=0, expected=0x4010000000000000, flags=0)
        add('unmasked_finite', mask=0, vm=1, pattern=0,
            expected=0x4070100000000000, flags=0)  # 2 + sum(1+i%7, i=0..64) = 257
        add('widen_fp16_pair',sw=16,dw=32)
        add('late_remote_snan',mask=1<<33,pattern=0,seed=0x7ff0000000000001,gap=1)
        for sw,dw in ((16,16),(16,32),(32,32),(32,64),(64,64)):
            add(f'tail_only_{sw}_{dw}',sw=sw,dw=dw,mask=1<<65,pattern=2,
                expected={16:0x4000,32:0x40000000,64:0x4000000000000000}[dw],flags=0)
            add(f'masked_snan_poison_{sw}_{dw}',sw=sw,dw=dw,mask=2,pattern=3,
                expected={16:0x4400,32:0x40800000,64:0x4010000000000000}[dw],flags=0)
        for rm in range(5):
            for prior in (0,1):
                for vl in (34,65,129):
                    add(f'pair_vl{vl}_rm{rm}_sticky{prior}', vl=vl, rm=rm, prior=prior)
        for width in (16,32,64):
            nan={16:0x7c01,32:0x7f800001,64:0x7ff0000000000001}[width]
            for op in (0,2,3):
                add(f'alloff_fp{width}_op{op}',sw=width,dw=width,op=op,
                    mask=0,pattern=2,seed=nan,expected=nan,flags=0,gap=1)
                add(f'remote_fp{width}_op{op}',sw=width,dw=width,op=op,
                    mask=2,pattern=0,seed=nan,
                    expected=None if op==0 else {16:0x4000,32:0x40000000,64:0x4000000000000000}[width])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--vmfpu',type=Path,default=FROZEN/'hardware/src/lane/vmfpu.sv')
    p.add_argument('--extended',action='store_true')
    p.add_argument('--deferred-flags',action='store_true',help='Require one unordered flag pulse no later than done')
    a=p.parse_args(); out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    pins={}

    def snapshot(relative, source):
        target=out/'inputs'/relative; target.parent.mkdir(parents=True,exist_ok=True)
        data=source.read_bytes(); target.write_bytes(data); target.chmod(0o444)
        pins[relative]=dict(source=str(source),sha256=hashlib.sha256(data).hexdigest())
        return str(target)

    # Consume the previously verified source ordering without editing its runner.
    command=json.loads(MANIFEST.read_text())
    relatives=[s.split('/inputs/')[1] for s in command if '/inputs/hardware/' in s and s.endswith(('.sv','.v'))]
    sources=[snapshot(s,a.vmfpu.resolve() if s=='hardware/src/lane/vmfpu.sv' else FROZEN/s) for s in relatives]
    for relative in ('hardware/deps/common_cells/src/fifo_v3.sv','hardware/src/lane/operand_queue.sv'):
        sources.append(snapshot(relative,FROZEN/relative))
    for directory in ('hardware/include/ara','hardware/deps/common_cells/include/common_cells'):
        for source in sorted((FROZEN/directory).glob('*.svh')):
            snapshot(str(source.relative_to(FROZEN)),source)
    sources.append(snapshot('test/reduction_tb.sv',HERE/'reduction_tb.sv'))
    for name in ('run.py','README.md'):
        snapshot('test/'+name,HERE/name)
    suite=cases(a.extended)
    (out/'cases.json').write_text(json.dumps(suite,indent=2)+'\n')
    calls=[]
    for i,c in enumerate(suite):
        calls.append(f'run_case({i}, "{c["name"]}", {c["sw"]}, {c["dw"]}, {c["vl"]}, {c["op"]}, '
                     f'{c["pattern"]}, {c["pos"]}, {c["neg"]}, 512\'h{c["mask"]:0128x}, 1\'b{c["vm"]}, '
                     f'64\'h{c["seed"]:016x}, {c["gap"]}, {c["rm"]}, {c["prior"]}, '
                     f'64\'h{c["expected"]:016x}, 5\'h{c["flags"]:02x}, {c["queued"]});')
    (out/'inputs/cases.svh').write_text('\n'.join(calls)+'\n')
    pins['cases.svh']=dict(source='generated cases.json',sha256=hashlib.sha256((out/'inputs/cases.svh').read_bytes()).hexdigest())
    (out/'pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    vcs='/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi='/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    env=dict(os.environ,VCS_HOME=vcs,VERDI_HOME=verdi,SNPSLMD_LICENSE_FILE='27000@t7920')
    env['PATH']=vcs+'/bin:'+env['PATH']
    compile_cmd=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-debug_access+all','-top','reduction_tb',
                 '+incdir+'+str(out/'inputs/hardware/deps/common_cells/include'),
                 '+incdir+'+str(out/'inputs/hardware/include'),'+incdir+'+str(out/'inputs'),
                 *sources,'-o',str(out/'simv'),'-l',str(out/'compile.log')]
    (out/'command.json').write_text(json.dumps(compile_cmd,indent=2)+'\n')
    status=dict(state='STARTED',vmfpu=pins['hardware/src/lane/vmfpu.sv'],case_count=len(suite))
    try:
        with (out/'compile.console.log').open('w') as log:
            subprocess.run(compile_cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=True)
        with (out/'run.console.log').open('w') as log:
            subprocess.run([str(out/'simv'),'-no_save','+FSDB',*(['+DEFERRED_FLAGS'] if a.deferred_flags else [])],cwd=out,env=env,stdout=log,
                           stderr=subprocess.STDOUT,timeout=120,check=True)
        log=(out/'run.console.log').read_text()
        with (out/'results.csv').open() as stream: rows=list(csv.DictReader(stream))
        if f'REDUCTION_COMPLETE cases={len(suite)}' not in log or re.search(r'(?m)^(Error|Fatal)(-|:)',log):
            raise RuntimeError('Harness/simulator failure; inspect preserved trace')
        if [r['name'] for r in rows]!=[c['name'] for c in suite]: raise RuntimeError('Missing cases')
        status['failures']=[r for r in rows if r['result_match']!='1' or r['flags_match']!='1']
        status['state']='FAIL_ARCHITECTURAL_ORACLE' if status['failures'] else 'PASS_REDUCED_RTL'
        for name,pin in pins.items():
            if hashlib.sha256((out/'inputs'/name).read_bytes()).hexdigest()!=pin['sha256']:
                raise RuntimeError('Input snapshot drift: '+name)
    except Exception as error: status.update(state='ERROR',error=repr(error))
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2))
    return int(status['state']!='PASS_REDUCED_RTL')


if __name__=='__main__': raise SystemExit(main())
