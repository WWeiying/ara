"""Live physical vector-register/CSR preservation across Linux signal return."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def assembly():
    lines=['.text','.global context_round','context_round:',
           'mv a6,a1','slli t2,a2,3']
    for reg in (0,8,16,24):lines += [f'vl8re8.v v{reg},(a0)','add a0,a0,t2']
    lines += ['andi t1,a4,3','csrw vxrm,t1','csrwi vxsat,1',
              'beqz a4,config0','li t1,1','beq a4,t1,config1',
              'li t1,2','beq a4,t1,config2',
              'vsetivli t0,0,e64,m1,ta,ma','j configured',
              'config0:','slli t1,a2,3','addi t1,t1,-1','vsetvli t0,t1,e8,m8,tu,mu','j configured',
              'config1:','vsetivli t0,3,e16,mf2,ta,ma','j configured',
              'config2:','vsetivli t0,17,e32,m2,tu,mu',
              'configured:','csrwi vstart,0','lw t5,0(a3)',
              'li t0,1','sd t0,0(a5)','fence rw,rw',
              'wait_signal:','lw t0,0(a3)','beq t0,t5,wait_signal',
              'csrr t0,vl','sd t0,0(a6)',
              'csrr t0,vtype','sd t0,8(a6)','csrr t0,vcsr','sd t0,16(a6)',
              'csrr t0,vstart','sd t0,24(a6)','csrwi vstart,0','addi a6,a6,32']
    for reg in (0,8,16,24):lines += [f'vs8r.v v{reg},(a6)','add a6,a6,t2']
    lines += ['li a0,0','ret']
    return '\n'.join(lines)+'\n'

def run(out,cross,nested=False):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('context_oracle.c')
    asm=out/'context.S';asm.write_text(assembly())
    name='rvv_live_'+('nested_altstack_' if nested else '')+'signal_context';binary=binaries/name
    subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
        '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
        '-Wall','-Wextra','-Werror',f'-DNESTED_CONTEXT={int(nested)}',str(source),str(asm),'-o',str(binary)],check=True)
    manifest=dict(scope=('Linux nested asynchronous signals on alternate stack, both live 32-register contexts; no migration claim' if nested else
                         'Linux live 32-register state, asynchronous signal clobber/return with a forked sender; no migration claim'),
                  cases=[dict(name=name,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                              pass_marker='RVV_CONTEXT_PASS',timeout_seconds=180)],
                  exclusions=['Single-core image cannot test migration','vstart nonzero at ABI call boundary excluded',
                              'Syscall ABI permits vector clobber, so no syscall in live-state window'],
                  source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__))})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('opt\nopt/ara-tests\nopt/ara-tests/'+name+'\n').encode(),
                       stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cross',required=True)
    p.add_argument('--nested',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.nested)
