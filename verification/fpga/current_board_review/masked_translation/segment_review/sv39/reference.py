#!/usr/bin/env python3
"""Four NF2 original-trial derivatives: host and real-Sv39 Spike, never VCS."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MT = HERE.parents[1]
sys.path.insert(0, str(MT))
import sv39_adapter as base

ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01')
NAMES = ('b3_sparse_load', 'b3_sparse_store', 'b5_laterfield_load', 'b5_laterfield_store')
OFF = (4082, 4082, 4074, 4074)
VA, G, DONE = 0x40000000, 0xe370697ce370697c, 0x7365677376333904
ISA = 'rv64gcv_zfh_zvfh_zvl1024b'
SITE = ('mx_segment_load', 'mx_segment_store') * 2


def provenance():
    pins, cases = {}, []
    def pin(p, expected=None):
        digest = base.sha(p)
        base.require(expected is None or digest == expected, 'Archived identity changed: '+str(p))
        pins[str(p)] = digest
    original = ARCHIVE/'controls/rvv_trace_fault_original_segment_nf2_e16_m1/scenario.elf'
    trace = ARCHIVE/'controls/rvv_trace_fault_replay_segment_nf2_e16_m1'
    for c in range(4):
        directory = (ARCHIVE/'singles'/f'rvv_small_fault_segment_nf2_e16_m1_u0_s{c%2}_b3_m2_f1'
                     if c<2 else trace)
        meta = json.loads((directory/'case.json').read_text())
        pin(directory/'case.json')
        for name, digest in meta['scenario_sources'].items(): pin(directory/name, digest)
        pin(directory/'scenario.elf', meta['sha256'])
        pin(original, meta['original_elf_sha256'])
        if c<2:
            base.require(meta['measured_trial']['errors']==1, 'Expected genuine failing single')
        cases.append(dict(id=c,name=NAMES[c],source_directory=str(directory),metadata=meta,
            tuple=dict(unmapped=0,store=c%2,boundary=3 if c<2 else 5,mode=2,split=1),
            historical_status='single_FAIL_errors1' if c<2 else 'full_trace_selected_trial_PASS_errors0',
            adapter_semantics='NF2 e16m1 VL8, S-mode invalid-PTE fault, unchanged-PC vstart5 retry; not Linux ELF execution'))
    for name in ('hashes.json','index.json','evidence/controls_board_report.json','evidence/control_symptoms.json'):
        pin(ARCHIVE/name)
    report = json.loads((ARCHIVE/'evidence/controls_board_report.json').read_text())
    output = report['results'][2]['output']
    for store in (0,1):
        begin=f'RVV_FAULT_BEGIN unmapped=0 store={store} boundary=5 mode=2 split=1'
        block=output.split(begin,1)[1].split('RVV_FAULT_BEGIN',1)[0]
        base.require('RVV_FAULT_CHECK errors=0' in block and 'vstart=5 expected_start=5' in block,
                     'Positive archived trial evidence missing')
        cases[2+store]['archived_trial_log']=begin+block
    return dict(files=pins,cases=cases,original_linux_elf=str(original))


def seed(c,r,i):
    return 0x6c00+256*r+i if r in (0,3) else (101+13*i+29*(r-1) if c%2 else 0x5b)


def orig(h):
    return (37*h+11)&65535


def partial_vector(c,p,r,i):
    return p==1 and c%2==0 and r in (1,2) and i==5


def vg(c,p,r,i):
    if c%2==0 and r in (1,2) and i in (2,5) and (p==2 or i==2):
        return orig((OFF[c]+4*i+2*(r-1))//2)
    return seed(c,r,i)


def memory_gold(c,p):
    data=[orig(h) for h in range(4096)]
    for i in (2,5):
        for f in (0,1):
            h=(OFF[c]+4*i+2*f)//2
            if c%2 and (p==2 or i==2): data[h]=seed(c,f+1,i)
            if p==2 and i==2: data[h]=(seed(c,f+1,i) if c%2 else orig(h))^0x5b
    return data


def check_host(text):
    rows=[]
    for c in range(4):
        for p in (1,2):
            rows += ['V %d %d %d %d %d %04x'%(c,p,r,i,partial_vector(c,p,r,i),vg(c,p,r,i))
                     for r in range(4) for i in range(64)]
            rows += ['D %d %d %d %d %04x'%(c,p,h,c==3 and p==1 and h==2047,v)
                     for h,v in enumerate(memory_gold(c,p))]
    base.require(text.splitlines()==rows, 'Independent Python / host C oracle differs')
    return len(rows)


def expected(s,c,p):
    want, choices = {}, []
    def put(a,v,n):
        for i,b in enumerate(v.to_bytes(n,'little')):
            base.require(a+i not in want,'Overlapping oracle regions')
            want[a+i]=b
    pages=s['mx_pages']
    pte=lambda a,f:(a>>12<<10)|f
    for h,v in enumerate(memory_gold(c,p)):
        if c==3 and p==1 and h==2047:
            choices.append((pages+2*h,2,(orig(h),seed(c,1,5))))
        else: put(pages+2*h,v,2)
    for page in range(2,5):
        for w in range(512):
            v=0
            if page==2: v=pte(pages+12288,1) if w==1 else 0x200000cf if w==2 else 0
            if page==3 and w==0: v=pte(pages+16384,1)
            if page==4 and (w==0 or w==1 and p==2): v=pte(pages+w*4096,0xc7)
            put(pages+page*4096+w*8,v,8)
    for name in ('mx_guard_lo','mx_guard_hi'):
        for w in range(8): put(s[name]+w*8,G,8)
    for name in ('mx_seed','mx_fault','mx_result'):
        a=s[name]+640*c
        for off in (0,576):
            for w in range(8): put(a+off+w*8,G,8)
        for r in range(4):
            for i in range(64):
                if name=='mx_fault' and partial_vector(c,1,r,i): continue
                value=seed(c,r,i) if name=='mx_seed' else (
                    vg(c,1 if name=='mx_fault' else 2,r,i)
                    if name=='mx_fault' or p==2 else (G>>((i%4)*16))&65535)
                put(a+64+128*r+2*i,value,2)
    for i in range(130):
        v=vg(c,2,1+(i-1)//64,(i-1)%64) if p==2 and 1<=i<=128 else 0x5b
        put(s['mx_out']+260*c+2*i,v,2)
    for j,v in enumerate((8,8,0,117,5) if p==2 else ((1<<64)-1,)*5):
        put(s['mx_post']+40*c+8*j,v,8)
    for i in range(16): put(s['mx_mask']+16*c+i,0x24,1)
    for n in range(2):
        vals=([15 if c%2 else 13,s[SITE[c]],VA+OFF[c]+20+(2 if c>=2 else 0),None,
               (8<<60)|((pages+8192)>>12),8,8,5,117,5,0,0] if n==0 else
              [9,s['mx_ecall'],0,None,(8<<60)|((pages+8192)>>12),8,8,0,117,5,1,pte(pages+4096,0xc7)])
        if n==1 and p==1: vals=[(1<<64)-1]*12
        for j,v in enumerate(vals):
            a=s['mx_records']+192*c+96*n+8*j
            if n==0 and j==2 and c<2:
                choices.append((a,8,(VA+OFF[c]+20,VA+OFF[c]+22)))
            elif v is not None: put(a,v,8)
    for name,v in (('mx_count',p),('mx_marker',p-1)):
        put(s[name]+8*c,v,8)
    return want,choices


def readint(memory,a,n=8):
    return int.from_bytes(bytes(memory.get(a+i,255) for i in range(n)),'little')


def compare(memory,s,c,p):
    want,choices=expected(s,c,p)
    bad=[(hex(a),v,memory.get(a)) for a,v in want.items() if memory.get(a)!=v]
    base.require(not bad,f'{NAMES[c]} phase{p}: {bad[:8]}')
    for a,n,values in choices:
        base.require(readint(memory,a,n) in values, f'Invalid partial/field-address value at {a:x}')
    for n in range(p):
        base.require(readint(memory,s['mx_records']+192*c+96*n+24)&0x8000031888==0x800,
                     'Trap mstatus not S-mode')
    return len(want)


def validate(trace,s):
    memory,regs,points,exits={}, {0:0}, [], []
    actions=[[] for _ in range(4)]
    events=[[] for _ in range(4)]
    commits=0
    for line in trace.splitlines():
        m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not m: continue
        mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]
        commits+=1
        base.require(pc!=s['trap_entry'],'Default trap handler executed')
        c=readint(memory,s['mx_current'])
        access=[(int(a,16),int(v,16) if v else None)
                for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc in (s['mx_segment_load'],s['mx_segment_store']):
            base.require(c<4 and pc==s[SITE[c]] and mode==1,'Wrong target or privilege')
            base.require(insn==(0x20055c27 if c%2 else 0x20055c07),'Original NF2 masked opcode differs')
            actions[c].append('target')
            events[c].append(dict(opcode=hex(insn),access=access))
        if pc==s['mx_younger_store']:
            base.require(mode==1,'Younger store not S-mode'); actions[c].append('younger')
        if pc==s['mx_repair_sfence']:
            base.require(mode==3 and regs.get((insn>>15)&31)==VA+4096,'Wrong repair SFENCE')
            actions[c].append('repair_sfence')
        if pc==s['mx_trap_mret'] and readint(memory,s['mx_marker']+8*c)==0:
            actions[c].append('retry_mret')
        if pc==s['mx_checkpoint']:
            phase=readint(memory,s['mx_phase'])
            checked=compare(memory,s,c,phase)
            points.append(dict(id=c,name=NAMES[c],phase=phase,checked_bytes=checked,commit=commits))
            actions[c].append('fault_checkpoint' if phase==1 else 'final_checkpoint')
        for a,v in access:
            if v is None: continue
            opcode,funct=insn&127,(insn>>12)&7
            if insn&3!=3:
                d=base.compressed_memory(insn)
                base.require(d is not None and d['kind']=='write','Unknown compressed store')
                width=d['size']
                base.require(a==(regs.get(d['base'],-1)+d['offset'])&((1<<64)-1),'Compressed address differs')
            else:
                base.require(opcode in (0x23,0x27),'Unknown store opcode')
                width=(1<<funct) if opcode==0x23 else {0:1,5:2,6:4,7:8}[funct]
            physical=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')): memory[physical+i]=b
            if a==s['tohost']: exits.append(v)
        regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    traps=re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)
    wanted_traps=[]
    for c in range(4):
        wanted_traps += [('trap_store_page_fault' if c%2 else 'trap_load_page_fault','%016x'%s[SITE[c]]),
                         ('trap_supervisor_ecall','%016x'%s['mx_ecall'])]
        base.require(actions[c]==['target','fault_checkpoint','repair_sfence','retry_mret','target','younger','final_checkpoint'],
                     'Repair/retry/completion order differs: '+str((c,actions[c])))
        base.require(len(events[c])==2,'Missing attempt/retry')
        def accesses(i,fields):
            return [(VA+OFF[c]+4*i+2*f,seed(c,f+1,i) if c%2 else None) for f in fields]
        prefix=accesses(2,(0,1))
        allowed=[prefix] if c<2 else [prefix,prefix+accesses(5,(0,))]
        base.require(events[c][0]['access'] in allowed,'Fault-attempt access list differs '+str(events[c][0]))
        base.require(events[c][1]['access']==accesses(5,(0,1)),'Retry did not access exactly segment5 fields')
    base.require(traps==wanted_traps,'Exception ledger differs '+str(traps))
    base.require([(x['id'],x['phase']) for x in points]==[(c,p) for c in range(4) for p in (1,2)],'Checkpoint coverage differs')
    base.require(exits==[1] and readint(memory,s['mx_errors'])==0 and readint(memory,s['mx_unexpected'])==0,'Software failure')
    base.require(readint(memory,s['mx_completed'])==DONE,'Missing completion magic')
    base.require(commits<2500000,'Reference instruction bound exceeded')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',cases=list(NAMES),checkpoints=points,
                checks=readint(memory,s['mx_checks']),case_checks=[readint(memory,s['mx_case_checks']+8*c) for c in range(4)],
                commits=commits,traps=traps,actions=actions,target_events=events,
                VCS_launched=False,Linux_launched=False)


def negative_oracle(s):
    tests=[]
    def synthetic(c,p):
        m,choices=expected(s,c,p)
        for a,n,values in choices:
            for i,b in enumerate(values[0].to_bytes(n,'little')): m[a+i]=b
        for n in range(p):
            a=s['mx_records']+192*c+96*n+24
            for i,b in enumerate((0x800).to_bytes(8,'little')): m[a+i]=b
        compare(m,s,c,p)
        return m
    mutations=(
        (0,1,'wrong_restart',s['mx_records']+56),
        (0,1,'wrong_fault_pc',s['mx_records']+8),
        (0,1,'inactive_prefix',s['mx_fault']+64+128),
        (0,2,'field1_tail',s['mx_result']+64+256+126),
        (0,2,'neighbor_v23',s['mx_result']+64),
        (0,2,'neighbor_v26',s['mx_result']+64+384),
        (0,2,'output_guard',s['mx_out']+258),
        (1,2,'prefix_store_reexecuted',s['mx_pages']+OFF[1]+8),
        (1,2,'inactive_store_write',s['mx_pages']+OFF[1]),
        (2,1,'bad_laterfield_mtval',s['mx_records']+384+16),
        (2,2,'field1_final_data',s['mx_result']+1280+64+256+10),
        (2,2,'pte_corruption',s['mx_pages']+16384+16),
        (3,1,'partial_store_invalid',s['mx_pages']+4094),
        (3,2,'page_guard',s['mx_guard_hi']),
        (3,2,'mask_buffer',s['mx_mask']+48),
        (3,1,'younger_before_fault',s['mx_marker']+24),
    )
    for c,p,name,a in mutations:
        m=synthetic(c,p); m[a]^=1
        try: compare(m,s,c,p)
        except ValueError: tests.append(dict(name=name,rejected=True)); continue
        raise ValueError('Negative oracle accepted '+name)
    # Permitted field-partial states are deliberate, not DUT-derived gold.
    m=synthetic(2,1)
    for r in (1,2):
        a=s['mx_fault']+2*640+64+r*128+10
        for i,b in enumerate(orig((OFF[2]+20+2*(r-1))//2).to_bytes(2,'little')): m[a+i]=b
    compare(m,s,2,1)
    m=synthetic(3,1)
    for i,b in enumerate(seed(3,1,5).to_bytes(2,'little')): m[s['mx_pages']+4094+i]=b
    compare(m,s,3,1)
    return dict(rejected_mutations=tests,allowed_partial_states=2)


def run(out):
    base.require(out.is_relative_to(HERE) and out!=HERE and not out.exists(),'Fresh output under owned sv39 required')
    parent=base.prepare.check(base.PARENT)
    linux=provenance(); pins=dict(linux['files'])
    inputs=[Path(__file__),HERE/'fixture.c',HERE/'fixture.S',HERE/'fixture.h',
            Path(base.__file__),base.BASE/'prepare.py',base.CC.resolve(),base.SPIKE,
            base.ROOT/'verification/coverage/scoped_rv64c_memory.py',base.PARENT/'provenance.json']
    inputs += [MT/'sv39_extended'/n for n in ('fixture.c','fixture.S','fixture.h','reference.py')]
    inputs += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld')]
    for p in inputs: pins[str(p)]=base.sha(p)
    out.mkdir(parents=True)
    base.save(out/'linux_provenance.json',linux); base.save(out/'input_pins.json',pins)
    prepared=out/'prepared'; prepared.mkdir()
    for n in ('startup.S','runtime.c','replay.ld'): shutil.copyfile(base.PARENT/n,prepared/n)
    for n in ('fixture.c','fixture.S','fixture.h'): shutil.copyfile(HERE/n,prepared/n)
    base.save(prepared/'provenance.json',dict(files={p.name:base.sha(p) for p in prepared.iterdir()},
        parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
        cases=list(NAMES),scope='Four NF2 selected-trial Sv39 derivatives; not Linux execution'))
    try:
        base.run_logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DMX_HOST',prepared/'fixture.c','-o',out/'host'],out/'host.compile.log')
        base.run_logged([out/'host'],out/'host.stdout')
        rows=check_host((out/'host.stdout').read_text())
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
          '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
          '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
          '-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld']
        symbols={}
        for backend in ('soc','spike'):
            elf=out/(backend+'.elf')
            cmd=[base.CC,*flags]+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
            cmd += [prepared/n for n in ('fixture.c','fixture.S','startup.S','runtime.c')]+['-lgcc','-o',elf]
            base.run_logged(cmd,out/(backend+'.compile.log'))
            base.run_logged([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],out/(backend+'.dis'))
            nm=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=15)
            s={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
            base.require(s['__bss_end']<0x800f0000,'ELF exceeds retained memory interface')
            symbols[backend]=s; base.save(out/(backend+'.symbols.json'),s)
        base.save(out/'negative_oracle.json',negative_oracle(symbols['spike']))
        started=time.monotonic()
        base.run_logged([base.SPIKE,'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','-l','--log-commits',out/'spike.elf'],
                        out/'spike.stdout',out/'spike.trace',timeout=90)
        result=validate((out/'spike.trace').read_text(),symbols['spike'])
        result.update(host_rows=rows,elapsed_seconds=time.monotonic()-started,isa=ISA,
                      elf_sha256={b:base.sha(out/(b+'.elf')) for b in ('soc','spike')})
        for p,digest in pins.items(): base.require(base.sha(p)==digest,'Input changed: '+p)
        base.save(out/'status.json',result)
        print(json.dumps({k:result[k] for k in ('status','cases','host_rows','commits','checks','elf_sha256','elapsed_seconds')},indent=2))
    except Exception as e:
        base.save(out/'failure.json',dict(status='REFERENCE_FAILED_NOT_DUT',error=str(e)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out.resolve())
