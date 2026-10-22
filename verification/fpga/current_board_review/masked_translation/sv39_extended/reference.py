#!/usr/bin/env python3
"""Software-only Sv39 reference preparation; deliberately has no VCS entry point."""
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
sys.path.insert(0, str(HERE.parent))
import sv39_adapter as base

CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
NAMES = ('unit_load_retry', 'unit_store_retry', 'positive_load_retry',
         'negative_store_retry', 'zero_load_retry', 'zero_store_alloff',
         'fof_shorten', 'fof_masked_suffix')
# Independent of the C configuration table; byte offsets relative to mapping.
OFF = (4090, 4090, 4072, 4106, 4096, 4096, 4088, 4088)
STRIDE = (2, 2, 8, -4, 0, 0, 2, 2)
MASK = (0x24, 0x24, 0x24, 0x24, 0x24, 0, 255, 15)
START = (5, 5, 5, 5, 2, 8, 4, 8)
CAUSE = (13, 15, 13, 15, 13, 0, 0, 0)
PAGE = (1, 1, 1, 0, 1, 1, 1, 1)
VL = (8, 8, 8, 8, 8, 8, 4, 8)
SITE = ('mx_unit_load', 'mx_unit_store', 'mx_stride_load', 'mx_stride_store',
        'mx_stride_load', 'mx_stride_store', 'mx_fof_load', 'mx_fof_load')
G = 0xe370697ce370697c
VA = 0x40000000
SOURCES = (
 ('rvv_fault_handoff_e16m1_01', 'rvv_small_fault_e16_m1_u0_s0_b3_m2'),
 ('rvv_fault_handoff_e16m1_01', 'rvv_small_fault_e16_m1_u0_s1_b3_m2'),
 ('rvv_strided_fault_handoff01', 'rvv_small_fault_strided_e16_m1_u0_s0_b3_m2_f0_g3'),
 ('rvv_negative_stride_handoff01', 'rvv_small_fault_strided_negative_stride_e16_m1_u0_s1_b3_m2_f0_g1'),
 ('rvv_zero_stride_handoff01', 'rvv_small_fault_strided_zero_stride_e16_m1_u0_s0_b0_m2_f0'),
 ('rvv_zero_stride_handoff01', 'rvv_small_fault_strided_zero_stride_e16_m1_u0_s1_b0_m3_f0'),
 ('rvv_small_exceptions01', 'rvv_small_exceptions_e16_scenario0'),
 ('rvv_small_exceptions01', 'rvv_small_exceptions_e16_scenario2'),
)


def provenance():
    pins, cases = {}, []
    def pin(p, expected=None):
        digest = base.sha(p)
        base.require(expected is None or digest == expected, 'Source/ELF identity differs: '+str(p))
        pins[str(p)] = digest
        return digest
    for c, (bundle, name) in enumerate(SOURCES):
        root = CAMP/bundle
        if c < 6:
            d = root/'singles'/name
            meta = json.loads((d/'case.json').read_text())
            pin(d/'case.json'); pin(root/'index.json'); pin(root/'README.txt')
            elf = d/'scenario.elf'
            orig = root/'controls'/meta['original_name'].replace(
                'rvv_fault_replay', 'rvv_trace_fault_original')/'scenario.elf'
            base.require(meta['measured_trial']['errors'] > 0, 'Not a delivered failing scenario')
        else:
            d = root/name
            manifest = json.loads((root/'manifest.json').read_text())
            meta = next(x for x in manifest['cases'] if x['name'] == name)
            pin(root/'manifest.json')
            elf = root/'binaries'/name
            orig = CAMP/'rvv_recovery08_202/resume/binaries'/meta['original_name']
        for source, digest in meta['scenario_sources'].items():
            pin(d/source, digest)
        pin(elf, meta['sha256']); pin(orig, meta['original_elf_sha256'])
        cases.append(dict(id=c, name=NAMES[c], source_directory=str(d),
            reduced_linux_elf=str(elf), original_linux_elf=str(orig), metadata=meta,
            adapted=dict(offset=OFF[c], stride=STRIDE[c], mask=MASK[c],
                         expected_cause=CAUSE[c], fault_vstart=START[c] if CAUSE[c] else None,
                         final_vl=VL[c], original_linux_execution=False)))
    return dict(cases=cases, files=pins, semantics='NF1 e16/m1 VL8 S-mode derivatives; not OS replay')


def orig(c, half):
    return ((half-2044)*37+11 if c>=6 and 2044<=half<2048 else half*37+11) & 65535


def seed(c, r, i):
    if r != 1:
        return 0x6c00+r*256+i
    return (101+(0 if c==5 else 13*i)) if c in (1,3,5) else 0x5b


def vg(c, phase, r, i):
    stop = START[c] if phase==1 else VL[c]
    if r==1 and c not in (1,3,5) and i<min(8,stop) and MASK[c]>>i&1:
        return orig(c,(OFF[c]+i*STRIDE[c])//2)
    return seed(c,r,i)


def check_host(text):
    gold = []
    for c in range(8):
        gold.extend('V %d %d %d %d %04x' % (c,p,r,i,vg(c,p,r,i))
                    for p in (1,2) for r in range(3) for i in range(64))
        gold.extend('D %d %d %04x' % (c,i,orig(c,i)) for i in range(4096))
    base.require(text.splitlines()==gold, 'Host C / independent Python gold differ')
    return len(gold)


def expected(s, c, phase):
    want = {}
    def put(a, v, n):
        for i,b in enumerate(v.to_bytes(n,'little')):
            base.require(a+i not in want,'Expected regions overlap')
            want[a+i]=b
    pages = s['mx_pages']
    pte = lambda p,flags: ((p>>12)<<10)|flags
    data = [orig(c,i) for i in range(4096)]
    for i in range(8):
        if not MASK[c]>>i&1:
            continue
        half=(OFF[c]+i*STRIDE[c])//2
        if c in (1,3,5) and (phase==2 or i<START[c]):
            data[half]=seed(c,1,i)
        if phase==2 and CAUSE[c] and i<START[c]:
            data[half]=(seed(c,1,i) if c in (1,3,5) else orig(c,half))^0x5b
    for i,v in enumerate(data): put(pages+i*2,v,2)
    for p in range(2,5):
        for w in range(512):
            v=0
            if p==2: v=pte(pages+12288,1) if w==1 else 0x200000cf if w==2 else 0
            if p==3 and w==0: v=pte(pages+16384,1)
            if p==4 and w<2 and (w!=PAGE[c] or phase==2 and CAUSE[c]): v=pte(pages+w*4096,0xc7)
            put(pages+p*4096+w*8,v,8)
    for name in ('mx_guard_lo','mx_guard_hi'):
        for w in range(8): put(s[name]+w*8,G,8)
    for name in ('mx_seed','mx_fault','mx_result'):
        a=s[name]+c*512
        for off in (0,448):
            for w in range(8): put(a+off+w*8,G,8)
        for r in range(3):
            for i in range(64):
                if name=='mx_result' and phase==2 and c==6 and r==1 and 4<=i<8:
                    continue
                value=seed(c,r,i) if name=='mx_seed' else (
                    vg(c,1 if name=='mx_fault' else 2,r,i)
                    if (name=='mx_fault' and CAUSE[c]) or (name=='mx_result' and phase==2)
                    else (G>>((i%4)*16))&65535)
                put(a+64+r*128+i*2,value,2)
    if phase==2:
        for i in range(130):
            if c==6 and 5<=i<9: continue
            put(s['mx_out']+c*260+i*2, vg(c,2,1,i-1) if 1<=i<=(64 if c<6 else 8) else 0x5b,2)
        for j,v in enumerate((VL[c],8,0,117,5)): put(s['mx_post']+c*40+j*8,v,8)
    for i in range(16): put(s['mx_mask']+c*16+i,MASK[c] if c<6 or i==0 else 0,1)
    for n in range(2):
        used=n==0 or phase==2 and CAUSE[c]
        if phase==1 and n==1: used=False
        fault=n==0 and bool(CAUSE[c])
        vals=[CAUSE[c] if fault else 9,s[SITE[c]] if fault else s['mx_ecall'],
              VA+OFF[c]+START[c]*STRIDE[c] if fault else 0,None,
              (8<<60)|((pages+8192)>>12),8,8,START[c] if fault else 0,117,5,
              0 if fault else 1,0 if fault or not CAUSE[c] else pte(pages+PAGE[c]*4096,0xc7)]
        for j,v in enumerate(vals):
            if not used: v=(1<<64)-1
            if v is not None: put(s['mx_records']+c*192+n*96+j*8,v,8)
    for name,v in (('mx_count',1 if phase==1 or not CAUSE[c] else 2),
                   ('mx_marker',int(phase==2))): put(s[name]+c*8,v,8)
    return want


def compare_memory(actual,want,label):
    bad=[(hex(a),b,actual.get(a)) for a,b in want.items() if actual.get(a)!=b]
    base.require(not bad,label+': '+repr(bad[:8]))


def read64(memory,a):
    return int.from_bytes(bytes(memory.get(a+i,255) for i in range(8)),'little')


def validate(trace,s):
    memory,regs,points,actions,exits={}, {0:0}, [], [[] for _ in range(8)], []
    commits=0
    targets={s[n] for n in SITE}
    events=[[] for _ in range(8)]
    for line in trace.splitlines():
        m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not m: continue
        mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]
        commits+=1
        base.require(pc!=s['trap_entry'],'Default trap handler executed')
        c=read64(memory,s['mx_current'])
        access=[(int(a,16),int(v,16) if v else None)
                for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc in targets:
            base.require(c<8 and pc==s[SITE[c]] and mode==1,'Target case/real S-mode mismatch')
            events[c].append(dict(insn=hex(insn),access=access,vector_event=tail))
            actions[c].append('target')
        if pc==s['mx_younger_store']:
            base.require(mode==1,'Younger instruction not in S-mode'); actions[c].append('younger')
        if pc==s['mx_repair_sfence']:
            base.require(mode==3 and regs.get((insn>>15)&31)==VA+PAGE[c]*4096,'Wrong addressed repair SFENCE')
            actions[c].append('repair_sfence')
        if pc==s['mx_trap_mret'] and read64(memory,s['mx_marker']+c*8)==0:
            actions[c].append('retry_mret')
        if pc==s['mx_checkpoint']:
            phase=read64(memory,s['mx_phase'])
            want=expected(s,c,phase)
            compare_memory(memory,want,f'{NAMES[c]} phase{phase}')
            nrecords=1 if phase==1 or not CAUSE[c] else 2
            for n in range(nrecords):
                base.require(read64(memory,s['mx_records']+c*192+n*96+24)&0x8000031888==0x800,
                             'Trap mstatus not exact S-mode')
            points.append(dict(case=NAMES[c],id=c,phase=phase,checked_bytes=len(want),commit=commits))
            actions[c].append('fault_checkpoint' if phase==1 else 'final_checkpoint')
        for a,v in access:
            if v is None: continue
            opcode,funct=insn&127,(insn>>12)&7
            if insn&3!=3:
                d=base.compressed_memory(insn)
                base.require(d is not None and d['kind']=='write','Unknown compressed store')
                width=d['size']
                base.require(a==(regs.get(d['base'],-1)+d['offset'])&((1<<64)-1),'Compressed store address mismatch')
                if d['register'] in regs:
                    base.require(v&((1<<(width*8))-1)==regs[d['register']]&((1<<(width*8))-1),'Compressed value mismatch')
            else:
                base.require(opcode in (0x23,0x27),'Unknown store instruction')
                width=(1<<funct) if opcode==0x23 else {0:1,5:2,6:4,7:8}[funct]
            # Spike logs S-mode virtual addresses; oracle uses the backing physical pages.
            physical=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for i,b in enumerate((v&((1<<(width*8))-1)).to_bytes(width,'little')): memory[physical+i]=b
            if a==s['tohost']: exits.append(v)
        regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    gold_traps=[]
    for c in range(8):
        if CAUSE[c]: gold_traps.append(('trap_load_page_fault' if CAUSE[c]==13 else 'trap_store_page_fault','%016x'%s[SITE[c]]))
        gold_traps.append(('trap_supervisor_ecall','%016x'%s['mx_ecall']))
        gold_actions=(['target','fault_checkpoint','repair_sfence','retry_mret'] if CAUSE[c] else [])+[
            'target','younger','final_checkpoint']
        base.require(actions[c]==gold_actions,'Target/repair/retry/completion order differs '+str((c,actions[c])))
        groups=[list(range(START[c])),list(range(START[c],8))] if CAUSE[c] else [list(range(VL[c]))]
        base.require(len(events[c])==len(groups),'Target event count differs')
        for e,indices in zip(events[c],groups):
            want=[(VA+OFF[c]+i*STRIDE[c],seed(c,1,i) if c in (1,3,5) else None)
                  for i in indices if MASK[c]>>i&1]
            base.require(e['access']==want,'Exact active access list differs: '+str((c,e['access'],want)))
            # Non-x0 stride rs2=t3; masked NF1 e16 encoding.
            insn=int(e['insn'],16)
            base.require(insn>>29==0 and not(insn&(1<<25)) and (insn>>12)&7==5,'Wrong NF/VM/EEW opcode')
            if c in (2,3,4,5): base.require((insn>>20)&31==28,'Stride is not t3')
    traps=re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)
    base.require(traps==gold_traps,'Exact exception ledger differs '+str(traps))
    base.require([(p['id'],p['phase']) for p in points]==[(c,p) for c in range(8) for p in ((1,2) if CAUSE[c] else (2,))],
                 'Checkpoint coverage/order differs')
    base.require(exits==[1] and read64(memory,s['mx_errors'])==0 and read64(memory,s['mx_unexpected'])==0,'Software failure')
    base.require(read64(memory,s['mx_completed'])==0x6d78737633390008,'Missing completion magic')
    base.require(commits<2500000,'Reference instruction bound exceeded')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',cases=list(NAMES),checkpoints=points,
        checks=read64(memory,s['mx_checks']),case_checks=[read64(memory,s['mx_case_checks']+8*c) for c in range(8)],
        commits=commits,traps=traps,actions=actions,target_events=events,
        fof_undefined_halves=dict(case=6,register='v24',elements=[4,5,6,7]),
        coverage_admitted=False,VCS_launched=False,Linux_launched=False)


def negative_oracle(s):
    results=[]
    for c,phase,name,address in (
        (0,2,'full_oldvd_tail',s['mx_result']+64+128+126),
        (0,1,'load_prefix',s['mx_fault']+64+128+4),
        (1,2,'store_prefix_replayed',s['mx_pages']+4094),
        (1,2,'masked_store_side_effect',s['mx_pages']+4090),
        (3,1,'wrong_fault_vstart',s['mx_records']+3*192+56),
        (7,2,'fof_inactive_suffix',s['mx_result']+7*512+64+128+14),
    ):
        want=expected(s,c,phase); bad=dict(want); bad[address]^=1
        try: compare_memory(bad,want,name)
        except ValueError: results.append(dict(name=name,rejected=True)); continue
        raise ValueError('Negative oracle was accepted: '+name)
    return results


def run(out):
    base.require(out.resolve().is_relative_to(HERE) and out.resolve()!=HERE and not out.exists(),'Fresh output inside sv39_extended required')
    parent=base.prepare.check(base.PARENT)
    linux=provenance()
    pins=dict(linux['files'])
    for p in [Path(__file__),HERE/'fixture.c',HERE/'fixture.S',HERE/'fixture.h',
              Path(base.__file__),base.BASE/'prepare.py',base.CC.resolve(),base.SPIKE,
              base.ROOT/'verification/coverage/scoped_rv64c_memory.py',
              base.PARENT/'provenance.json']+[base.PARENT/n for n in ('startup.S','runtime.c','replay.ld')]:
        pins[str(p)]=base.sha(p)
    out.mkdir(parents=True)
    base.save(out/'linux_provenance.json',linux); base.save(out/'input_pins.json',pins)
    prepared=out/'prepared'; prepared.mkdir()
    for n in ('startup.S','runtime.c','replay.ld'): shutil.copyfile(base.PARENT/n,prepared/n)
    for n in ('fixture.c','fixture.S','fixture.h'): shutil.copyfile(HERE/n,prepared/n)
    base.save(prepared/'provenance.json',dict(files={p.name:base.sha(p) for p in prepared.iterdir()},
        parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
        cases=list(NAMES),scope=linux['semantics']))
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
            base.require(s['__bss_end']<0x800f0000,'ELF does not fit sealed L2/stack interface')
            symbols[backend]=s; base.save(out/(backend+'.symbols.json'),s)
        started=time.monotonic()
        base.run_logged([base.SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                         '-m2','-l','--log-commits',out/'spike.elf'],out/'spike.stdout',out/'spike.trace',timeout=90)
        result=validate((out/'spike.trace').read_text(),symbols['spike'])
        result.update(host_rows=rows,elapsed_seconds=time.monotonic()-started,
                      elf_sha256={b:base.sha(out/(b+'.elf')) for b in ('soc','spike')})
        base.save(out/'negative_oracle.json',negative_oracle(symbols['spike']))
        for p,digest in pins.items(): base.require(base.sha(p)==digest,'Input changed: '+p)
        base.save(out/'status.json',result)
        print(json.dumps({k:v for k,v in result.items() if k!='target_events'},indent=2))
    except Exception as e:
        base.save(out/'failure.json',dict(status='REFERENCE_FAILED_NOT_DUT',error=str(e)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out.resolve())
