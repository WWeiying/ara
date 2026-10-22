"""Owned single packed-scalar conversion; no DUT path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'prepared01'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
LIMIT = 40000000
RAW_LIMIT = 4 * 1024**3

def require(ok, why):
    if not ok:
        raise ValueError(why)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1048576), b''):
            h.update(data)
    return h.hexdigest()

def read(p):
    return json.loads(Path(p).read_text())

def save(p, obj):
    with Path(p).open('x') as f:
        json.dump(obj, f, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())

def pins_check(pins):
    for p, digest in pins.items():
        require(sha(p) == digest, 'Input drift ' + p)

def command(cmd, log, seconds, limit=None):
    cmd = list(map(str, cmd))
    save(str(log)+'.command.json', dict(command=cmd, cwd=str(HERE), timeout_s=seconds))
    def limits():
        if limit:
            resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
    began = time.monotonic(); timed = False
    with Path(log).open('x') as output:
        child = subprocess.Popen(cmd, cwd=HERE, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True, preexec_fn=limits)
        try:
            rc = child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed = True; os.killpg(child.pid, signal.SIGKILL); rc = child.wait()
    result = dict(command=cmd, pid=child.pid, returncode=rc, timeout=timed,
                  elapsed_s=time.monotonic()-began, attempts=1)
    save(str(log)+'.exit.json', result)
    require(rc == 0 and not timed, 'Actual child failure: '+str(log))
    return result

def describe(elf):
    nm = subprocess.run([str(CC.with_name(CC.name[:-3]+'nm')), '-n', str(elf)], check=True,
                        text=True, capture_output=True, timeout=30)
    symbols = {n:int(a,16) for a,_,n in (s.split() for s in nm.stdout.splitlines() if len(s.split())==3)}
    obj = subprocess.run([str(CC.with_name(CC.name[:-3]+'objdump')), '-d', str(elf)], check=True,
                         text=True, capture_output=True, timeout=30)
    code = {int(p,16):int(i,16) for p,i in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s', obj.stdout,re.M)}
    sizes = {p:(4 if i&3==3 else 2) for p,i in code.items()}
    helpers = {}
    for op in range(20):
        pc = symbols['op_'+str(op)]; window=[]
        while True:
            require(pc in code, 'Missing helper byte')
            ins = code[pc];window.append(dict(pc=pc,insn=ins))
            if ins == 0x8082:
                break
            pc += sizes[pc]
            require(len(window)<100, 'Helper runaway')
        helpers[str(op)] = window
    return dict(elf=str(elf),sha256=sha(elf),symbols=symbols,code=code,helpers=helpers),obj.stdout

def geometry():
    cases=[];skips=[]
    for seed in range(3):
        for op in range(20):
            for mode in range(5):
                n=1<<(op//4 if op<16 else op-16)
                width=1<<(op%4 if op<16 else mode)
                if mode==4 and op>=16:width=1
                evl=n*128//width
                for index,start in enumerate((0,1,evl//2,evl,evl+1)):
                    row=dict(seed=seed,op=op,mode=mode,index=index,start=start,bytes=width,registers=n,evl=evl)
                    (skips if start>evl or start>=1024 or mode==4 and op>=16 else cases).append(row)
    require((len(cases),len(skips))==(1134,366),'Original scope')
    old=read(OLD/'tuples.json')
    require(cases==old['cases'] and skips==old['skipped'],'Original tuple order/exclusions')
    return dict(cases=cases,skipped=skips)


def create():
    require(not (HERE/'soc').exists(), 'Exclusive one preparation')
    files=['runtime.c','startup.S','replay.ld','original/whole_oracle.c','original/whole.S',
           'original/operations.h','soc/whole_all_main.c','spike/whole_all_main.c']
    for f in files:
        dst=HERE/f;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/f,dst)
        require(sha(dst)==sha(OLD/f),'Unchanged copied input '+f)
    source=(OLD/'case.c').read_text()
    init='''            for(unsigned i=0;i<1024;++i)input[i]=(uint8_t)(i*37+seed*71+3);
            for(unsigned i=0;i<1088;++i)output[i]=0x5b;'''
    begin='''            for(unsigned i=0;i<1088;++i){unsigned active=i>=32+start*bytes && i<32+n*vlenb;'''
    end='''                }}
            ++cases;'''
    require(source.count(init)==source.count(begin)==source.count(end)==1,'Exact source transformation anchors')
    transformed=source.replace('#include "operations.h"','#include "operations.h"\n#include "packed.h"')
    transformed=transformed.replace(init,'            packed_init(input,output,seed);')
    transformed=transformed.replace(begin,'''            for(unsigned word=0;word<1088;word+=8){
                uint64_t expected=packed_expected(input,word,32+start*bytes,32+n*vlenb);
                if(packed_load(output+word)==expected)continue;
                for(unsigned i=word;i<word+8;++i){unsigned active=i>=32+start*bytes && i<32+n*vlenb;''')
    transformed=transformed.replace(end,'''                }}}
            ++cases;''')
    with (HERE/'case.c').open('x') as f:f.write(transformed)
    table=[]
    for seed in range(3):
        words=[sum((((i+j)*37+seed*71+3)&255)<<(8*j) for j in range(8)) for i in range(0,256,8)]
        table.append('  {'+', '.join('UINT64_C(0x%016x)'%w for w in words)+'}')
    with (HERE/'input_table.h').open('x') as f:
        f.write('static const uint64_t input_table[3][32] = {\n'+',\n'.join(table)+'\n};\n')
    save(HERE/'tuples.json',geometry())
    flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding',
           '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
           '-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror',
           '-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-DDETAIL_BYTES=1']
    proof={}
    for backend in ('soc','spike'):
        elf=HERE/backend/'whole_all.elf'
        defines=['-DWHOLE_OP_BEGIN=0','-DWHOLE_OP_END=20']+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
        command([CC,*flags,'-T',HERE/'replay.ld','-I'+str(HERE/'original'),*defines,
                 HERE/'case.c',HERE/'original/whole.S',HERE/backend/'whole_all_main.c',
                 HERE/'startup.S',HERE/'runtime.c','-lgcc','-o',elf],HERE/backend/'compile.log',90)
        spec,dis=describe(elf);old,_=describe(OLD/backend/'whole_all.elf')
        for op in range(20):
            require([x['insn'] for x in spec['helpers'][str(op)]]==
                    [x['insn'] for x in old['helpers'][str(op)]],'Helper byte drift')
        pcs={x['pc'] for w in spec['helpers'].values() for x in w}
        for pc,ins in spec['code'].items():
            vector=ins&127==0x57 or ins&127 in (7,39) and (ins>>12)&7 in (0,5,6,7)
            require(not vector or pc in pcs,'Extra RVV')
        require('memcpy' not in spec['symbols'] and '__memcpy' not in spec['symbols'],'Unexpected memcpy libcall')
        require(spec['symbols']['__bss_end']<spec['symbols']['__stack_top'] and max(spec['code'])<0x80200000,'2MiB bounds')
        with (HERE/backend/'program.dis').open('x') as f:f.write(dis)
        proof[backend]=spec
    save(HERE/'sourceproof.json',dict(status='PACKED_COMPILED_HELPERS_IDENTICAL_NOT_REFERENCE',
        backends=proof,original_calls=1134,original_skips=366,scalar_algorithm_changed=True,
        original_case_sha256=sha(OLD/'case.c'),original_source_sha256=sha(OLD/'original/whole_oracle.c'),
        source_transform='Only full scalar initialization and word oracle with original byte fallback',
        ABI='Existing SoC architectural source port, not Linux ELF ABI'))
    print('COMPILED',sha(HERE/'sourceproof.json'),flush=True)

if __name__=='__main__':
    require(sys.argv[1:]==['compile'],'Explicit compile only')
    create()

