"""Owned sole-O2 full continuous software experiment. Never launches a DUT."""
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

def prepare(resume=False):
    require(not (HERE/'sourceproof.json').exists() and (resume or not (HERE/'soc').exists()),'No retry/overwrite')
    oldpins=read(OLD/'source_pins.json')
    require(oldpins[str(HERE.parent/'prepare.py')]==sha(HERE.parent/'prepare.py'),'Original compiler recipe drift')
    files=['case.c','runtime.c','startup.S','replay.ld','original/whole_oracle.c','original/whole.S','original/operations.h',
           'soc/whole_all_main.c','spike/whole_all_main.c']
    inputs={str(HERE.parent/'prepare.py'):sha(HERE.parent/'prepare.py'),str(CC):sha(CC),str(SPIKE):sha(SPIKE),
            str(OLD/'tuples.json'):sha(OLD/'tuples.json'),str(OLD/'source_pins.json'):sha(OLD/'source_pins.json')}
    for f in files:
        src=OLD/f;dst=HERE/f;dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists():shutil.copyfile(src,dst)
        else:require(resume,'Exclusive copied input')
        require(sha(dst)==sha(src),'Copy mismatch')
        inputs[str(src)]=sha(src);inputs[str(dst)]=sha(dst)
    if (HERE/'tuples.json').exists():require(resume and read(HERE/'tuples.json')==geometry(),'Tuple identity')
    else:save(HERE/'tuples.json',geometry())
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding',
           '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
           '-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror',
           '-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-DDETAIL_BYTES=1']
    # Match the frozen original recipe exactly, excluding its varying path tail.
    oldtext=(HERE.parent/'prepare.py').read_text()
    import ast
    tree=ast.parse(oldtext)
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='flags' for t in n.targets))
    require([ast.literal_eval(x) for x in assignment.value.elts[:len(flags)]]==flags,'Original flags mismatch')
    proof={}
    for backend in ('soc','spike'):
        elf=HERE/backend/'whole_all.elf'
        defines=['-DWHOLE_OP_BEGIN=0','-DWHOLE_OP_END=20']+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
        cmd=[CC,'-O2',*flags[1:],'-T',HERE/'replay.ld','-I'+str(HERE/'original'),*defines,
             HERE/'case.c',HERE/'original/whole.S',HERE/backend/'whole_all_main.c',HERE/'startup.S',HERE/'runtime.c','-lgcc','-o',elf]
        log=HERE/backend/'compile.log'
        if elf.exists():
            require(resume and read(str(log)+'.command.json')['command']==list(map(str,cmd)) and
                    read(str(log)+'.exit.json')['returncode']==0,'Existing successful compile only; never retry')
        else:command(cmd,log,90)
        spec,dis=describe(elf);old,_=describe(OLD/backend/'whole_all.elf')
        for op in range(20):
            require([x['insn'] for x in spec['helpers'][str(op)]]==[x['insn'] for x in old['helpers'][str(op)]], 'Helper machine-byte drift '+str(op))
        pcs={x['pc'] for w in spec['helpers'].values() for x in w}
        for pc,ins in spec['code'].items():
            vector=ins&127==0x57 or ins&127 in (7,39) and (ins>>12)&7 in (0,5,6,7)
            require(not vector or pc in pcs,'Extra RVV verification instruction')
        require(spec['symbols']['__bss_end']<spec['symbols']['__stack_top'] and
                max(spec['code'])<0x80200000,'2MiB footprint')
        with (HERE/backend/'program.dis').open('x') as f:f.write(dis)
        proof[backend]=spec
        inputs[str(OLD/backend/'whole_all.elf')]=sha(OLD/backend/'whole_all.elf')
    save(HERE/'sourceproof.json',dict(status='SOLE_O2_FULL1134_HELPERS_IDENTICAL_NOT_REFERENCE',backends=proof,
        original_calls=1134,original_skips=366,output_bytes_per_call=1088,scalar_algorithm_changed=False,
        compiler_delta='-Os to -O2 only, plus independent paths',original_command_receipt='Frozen prepare.py recipe; original stdout logs do not record argv'))
    for p in HERE.rglob('*'):
        if p.is_file():inputs[str(p)]=sha(p)
    save(HERE/'bound.json',dict(status='AUTHORIZED_SINGLE_REFERENCE_NOT_DUT',pins=inputs,steps=LIMIT,
        seconds=120,raw_bytes=RAW_LIMIT,parser_seconds=600,baseline_minstret=33497309,
        static_basis='Os ELF contains repeated per-byte address generation; no static evidence O2 exceeds40M, hard bounds fail closed',
        predicted_O2_steps=None,scope='1134 continuous source-port calls plus366 original exclusions, not Linux'))
    print('PREPARED',sha(HERE/'bound.json'),flush=True)

def execute(digest):
    require(sha(HERE/'bound.json')==digest,'Bound identity');b=read(HERE/'bound.json');pins_check(b['pins'])
    out=HERE/'reference01';out.mkdir()
    elf=HERE/'spike/whole_all.elf'
    cmd=[SPIKE,'--isa=rv64gcv_zvl1024b','-m2','--instructions='+str(LIMIT),
         '--log-commits','--log='+str(out/'commits.log'),elf]
    # Non-debug idle path enforces instruction_limit. Success still requires HTIF/oracle.
    execution=command(cmd,out/'spike.stdout',120,RAW_LIMIT)
    require((out/'commits.log').stat().st_size<=RAW_LIMIT,'Raw exceeds4GiB')
    command([sys.executable,'-B',HERE/'audit.py','--bound-sha256',digest],out/'audit.log',600)
    pins_check(b['pins']);r=read(out/'reference.json')
    save(HERE/'RESULT.json',dict(status='FULL1134_O2_REFERENCE_PASS_NOT_DUT',reference=r,
         execution=execution,audit_exit=read(str(out/'audit.log')+'.exit.json'),bound_sha256=digest,
         no_DUT=True,no_retries=True))
    print('REFERENCE_PASS',r['firmware_through_htif'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','execute']);p.add_argument('--bound-sha256');p.add_argument('--resume-static',action='store_true');a=p.parse_args()
    if a.mode=='prepare':prepare(a.resume_static)
    else:execute(a.bound_sha256)
