#!/usr/bin/env python3
"""NF8 original192 source-derived real Sv39 host/Spike reference. No VCS entry point."""
import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import sv39_adapter as base

VA = 0x40000000
G = 0xe370697ce370697c
DONE = 0x6e3866756c6c0004
GEOMETRY = HERE.parent / 'selection01.json'
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
NAME = 'rvv_fault_replay_segment_nf8_strided_e32_mf2'
ASM = CAMPAIGN / 'rvv_strided_fault_reference54/source_nf8_mf2' / (NAME + '.S')
TRIALS = tuple(range(192))


def load_geometry():
    doc = json.loads(GEOMETRY.read_text())
    # Current RTL pins in the static report are not inputs to this software reference.
    source_identity = {p:h for p,h in doc['pins'].items()
                       if '/hardware/src/' not in p}
    for path, digest in source_identity.items():
        base.require(base.sha(path) == digest, 'Source/evidence identity changed: ' + path)
    source = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
    manifest = json.loads((CAMPAIGN / 'rvv_fault_identity_regression57/'
        'source_mf2_False_0_nf8_stridedTrue_reverseFalse/manifest.json').read_text())
    for name in ('fault_replay.py', 'fault_replay_oracle.c'):
        base.require(base.sha(source/name) == manifest['source_sha256'][name], 'Identity57 C/generator mismatch')
    spec = importlib.util.spec_from_file_location('nf8_original_generator', source/'fault_replay.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    base.require(module.assembly(32,lmul='mf2',fields=8,strided=True) == ASM.read_text(),
                 'Archived assembly regeneration mismatch')
    cases = []
    for t,(u,s,b,m,g,split) in enumerate(itertools.product(range(2),range(2),(1,3,5),range(4),(1,3),range(2))):
        mask=(255,170,36,0)[m]; stride=4*(8+g); address=4096-b*stride-16*split
        start=next((i for i in range(b,8) if mask>>i&1),8)
        offsets=[[address+i*stride+f*4 for f in range(8)] for i in range(8)]
        raw=dict(trial=t,unmapped=u,store=s,boundary=b,mode=m,gap=g,split=split,mask=mask,
                 stride_bytes=stride,base_offset=address,expected_vstart=start,expected_fault=start<8,
                 permitted_tval_offsets=[a for a in offsets[start] if a>=4096] if start<8 else [],
                 field_address_offsets=offsets)
        base.require(raw == doc['tuples'][t], 'Independent original tuple regeneration differs')
        if t in TRIALS:
            cases.append(dict(raw,expected_vstart=start if start<8 else None,
                expected_cause=(15 if s else 13) if start<8 else None,
                field_offsets=offsets,allowed_fault_addresses=[dict(offset=a) for a in raw['permitted_tval_offsets']],
                completed_active_prefix=[i for i in range(start) if mask>>i&1]))
    cases.sort(key=lambda c:TRIALS.index(c['trial']))
    base.require([c['trial'] for c in cases] == list(TRIALS), 'Full192 original tuples differ')
    base.require(len(cases)==192 and sum(c['expected_cause'] is not None for c in cases)==144,
                 'Original192/144 counts differ')
    return dict(cases=cases,source_identity=source_identity,
                original_linux_elf_sha256=doc['original_sha256'],
                scope='All192 exact original geometries, source-derived Sv39 not Linux replay',
                original_169_128_root_cause_known=False,original_linux_execution=False)


def orig(byte):
    return byte // 4 * 37 + 11


def seed(r, i):
    return 0x6c800000 ^ (r << 16) ^ i


def inp(f, i):
    return 101 + 13 * i + 29 * f


def vg(c, phase, r, i):
    if r < 2 or i >= 16:
        return seed(r, i)
    if c['store']:
        return inp(r - 2, i)
    if i >= 8 or not (c['mask'] >> i & 1):
        return 0x5b
    if phase == 1 and i >= c['expected_vstart']:
        return None
    return orig(c['field_offsets'][i][r - 2])


def mg(c, phase):
    values = [orig(i * 4) for i in range(2048)]
    for i in range(8):
        if not (c['mask'] >> i & 1):
            continue
        for f, byte in enumerate(c['field_offsets'][i]):
            if phase == 1:
                if c['store'] and i < c['expected_vstart']:
                    values[byte // 4] = inp(f, i)
                elif c['store'] and i == c['expected_vstart'] and byte < 4096:
                    values[byte // 4] = None
            else:
                if c['store']:
                    values[byte // 4] = inp(f, i)
                if c['expected_vstart'] is not None and i < c['expected_vstart']:
                    values[byte // 4] ^= 0x5b
    return values


def host_check(path, cases):
    rows = 0
    with path.open() as stream:
        for c in cases:
            t = c['trial']
            start = c['expected_vstart'] if c['expected_vstart'] is not None else 8
            fields = ['trial', 'unmapped', 'store', 'boundary', 'mode', 'gap', 'split', 'mask', 'base_offset']
            expected = ['C ' + ' '.join(str(c[k]) for k in fields) + ' ' + str(start) + ' ' + str(c['stride_bytes'])]
            for p in (1, 2):
                # Alloff never has phase1 in the device; host formula still must be total.
                for r in range(10):
                    for i in range(32):
                        v = vg(c, p, r, i)
                        expected.append(f'V {t} {p} {r} {i} {int(v is not None)} {v if v is not None else 0}')
                for i, v in enumerate(mg(c, p)):
                    expected.append(f'M {t} {p} {i} {int(v is not None)} {v if v is not None else orig(i*4)}')
            for want in expected:
                got = stream.readline().strip()
                base.require(got == want, f'Host oracle row {rows}: {got} != {want}')
                rows += 1
        base.require(not stream.read(), 'Extra host oracle rows')
    return rows


def expected(s, c, phase):
    want = {}
    def put(a, value, n):
        if value is None:
            return
        for i, b in enumerate(value.to_bytes(n, 'little')):
            base.require(a+i not in want, 'Oracle overlap')
            want[a+i] = b
    pages = s['na_pages']
    pte = lambda p, flags: ((p >> 12) << 10) | flags
    denied = 0 if c['unmapped'] else pte(pages+4096, 0xc9)
    fault = c['expected_cause'] is not None
    for i, value in enumerate(mg(c, phase)):
        put(pages+i*4, value, 4)
    for p in range(2, 5):
        for w in range(512):
            v = 0
            if p == 2:
                v = pte(pages+12288, 1) if w == 1 else 0x200000cf if w == 2 else 0
            if p == 3 and w == 0:
                v = pte(pages+16384, 1)
            if p == 4:
                v = pte(pages, 0xc7) if w == 0 else (
                    pte(pages+4096, 0xc7) if phase == 2 and fault else denied) if w == 1 else 0
            put(pages+p*4096+w*8, v, 8)
    for name in ('na_guard_lo', 'na_guard_hi'):
        for i in range(8):
            put(s[name]+i*8, G, 8)
    for name in ('na_seed', 'na_fault', 'na_result'):
        a = s[name]
        for off in (0, 1344):
            for i in range(8):
                put(a+off+i*8, G, 8)
        used = name == 'na_fault' and fault or name == 'na_result' and phase == 2
        for r in range(10):
            for i in range(32):
                v = seed(r, i) if name == 'na_seed' else vg(c, 1 if name == 'na_fault' else 2, r, i) \
                    if used else (G >> ((i%2)*32)) & 0xffffffff
                put(a+64+r*128+i*4, v, 4)
    for i in range(1024):
        put(s['na_input']+i*4, inp(i//16,i%16) if i < 128 else 0, 4)
    for i in range(1026):
        v = vg(c, 2, 2+(i-1)//16, (i-1)%16) if phase == 2 and 1 <= i <= 128 else 0x5b
        put(s['na_output']+i*4, v, 4)
    put(s['na_stride'], c['stride_bytes'], 8)
    for i in range(16):
        put(s['na_mask']+i, c['mask'], 1)
    for i,v in enumerate((0,16,23,0,117,5)):
        put(s['na_post']+i*8, v if phase == 2 else (1<<64)-1, 8)
    for n in range(2):
        used = n == 0 or phase == 2 and fault
        f = n == 0 and fault
        record = [c['expected_cause'] if f else 9,
                  s['fault_1_pc' if c['store'] else 'fault_0_pc'] if f else s['na_ecall'],
                  None if f else 0, None, (8<<60)|((pages+8192)>>12), 8 if f else 16, 23,
                  c['expected_vstart'] if f else 0,117,5,0 if f else 1,
                  denied if f or not fault else pte(pages+4096,0xc7)]
        for j,v in enumerate(record):
            put(s['na_records']+n*96+j*8, v if used else (1<<64)-1, 8)
    for name,v in [('na_count', 2 if phase == 2 and fault else 1), ('na_marker',int(phase==2)),
                   ('na_errors',0), ('na_unexpected',0)]:
        put(s[name],v,8)
    for i in range(6):
        put(s['na_firsterror']+i*8,0,8)
    return want


def read64(memory, a):
    return int.from_bytes(bytes(memory.get(a+i,255) for i in range(8)), 'little')


def compare(memory, want, label):
    for a,v in want.items():
        base.require(memory.get(a) == v, f'{label}: {a:#x} got={memory.get(a)} want={v}')


def validate(trace, s, cases):
    memory, regs, points, events, traps, exits = {}, {0:0}, [], [], [], []
    actions = {c['trial']:[] for c in cases}
    by_trial = {c['trial']:c for c in cases}
    checks = commits = 0
    target_codes = {s['fault_0_pc']:0xe9c56c07, s['fault_1_pc']:0xe9c56c27}
    with trace.open() as stream:
        for line in stream:
            trap = re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)', line)
            if trap:
                traps.append((trap[1],int(trap[2],16)))
            m = re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m:
                continue
            commits += 1
            mode,pc,insn,tail = int(m[1]),int(m[2],16),int(m[3],16),m[4]
            base.require(pc not in (s['trap_entry'],s['replay_mismatch']), 'Trap/firsterror reached: '+line.strip())
            if pc == s['check']:
                base.require(regs.get(12) == regs.get(13), f'Scalar oracle firsterror {checks}: '+str(regs))
                checks += 1
            trial = read64(memory,s['na_current'])
            access = [(int(a,16),int(v,16) if v else None)
                      for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
            if pc in target_codes:
                c = by_trial[trial]
                base.require(mode == 1 and pc == s['fault_1_pc' if c['store'] else 'fault_0_pc'], 'Not expected real S-mode target')
                base.require(insn == target_codes[pc], 'Original NF8 positive-stride target encoding differs')
                base.require(regs.get(10) == VA+c['base_offset'] and regs.get(28) == c['stride_bytes']
                             and regs.get(14) == 16, 'Original base/stride/cap arguments differ')
                actions[trial].append('target')
                events.append(dict(trial=trial,pc=hex(pc),insn=hex(insn),access=access))
            if pc == s['na_younger_store']:
                base.require(mode == 1,'Younger not S-mode')
                actions[trial].append('younger')
            if pc == s['na_repair_sfence']:
                base.require(mode == 3 and regs.get((insn>>15)&31) == VA+4096, 'Wrong repair SFENCE address')
                actions[trial].append('repair')
            if pc == s['na_retry_mret'] and read64(memory,s['na_marker']) == 0:
                actions[trial].append('retry')
            if pc == s['na_checkpoint']:
                c = by_trial[trial]; phase = read64(memory,s['na_phase'])
                want = expected(s,c,phase)
                check_state(memory,s,c,phase)
                fault = c['expected_cause'] is not None
                for n in range(2 if phase == 2 and fault else 1):
                    a = s['na_records']+n*96
                    base.require(read64(memory,a+24)&0x8000031888 == 0x800,'Trap privilege changed')
                    if n == 0 and fault:
                        base.require(read64(memory,a+16) in [VA+x['offset'] for x in c['allowed_fault_addresses']],
                                     'Fault tval not an allowed protected field')
                actions[trial].append('fault_checkpoint' if phase == 1 else 'final_checkpoint')
                points.append(dict(trial=trial,phase=phase,commits=commits,checks=checks,checked_bytes=len(want)))
            for a,v in access:
                if v is None:
                    continue
                if insn&3 != 3:
                    d = base.compressed_memory(insn)
                    base.require(d is not None and d['kind']=='write','Unknown compressed store')
                    width = d['size']
                    base.require(a == (regs.get(d['base'],-1)+d['offset']) & ((1<<64)-1),'Store address mismatch')
                else:
                    op,funct = insn&127,(insn>>12)&7
                    base.require(op in (0x23,0x27),'Unknown store opcode')
                    width = 1<<funct if op == 0x23 else {0:1,5:2,6:4,7:8}[funct]
                physical = s['na_pages']+a-VA if VA <= a < VA+8192 else a
                for i,b in enumerate((v & ((1<<(width*8))-1)).to_bytes(width,'little')):
                    memory[physical+i] = b
                if a == s['tohost']:
                    exits.append(v)
            regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    goldtraps = []
    for c in cases:
        trial=c['trial']; fault=c['expected_cause'] is not None
        if fault:
            goldtraps.append(('trap_store_page_fault' if c['store'] else 'trap_load_page_fault',
                              s['fault_1_pc' if c['store'] else 'fault_0_pc']))
        goldtraps.append(('trap_supervisor_ecall',s['na_ecall']))
        goldactions = (['target','fault_checkpoint','repair','retry'] if fault else []) + ['target','younger','final_checkpoint']
        base.require(actions[trial] == goldactions, f'Wrong trial{trial} ordering: '+str(actions[trial]))
        selected=[e for e in events if e['trial']==trial]
        for n,e in enumerate(selected):
            # Require complete ordered prefix/retry accesses. Partial fault-element fields
            # are implementation dependent and are recorded, not required to be atomic.
            start=c['expected_vstart'] if fault and n==1 else 0
            stop=c['expected_vstart'] if fault and n==0 else 8
            required=[(VA+off,inp(f,i) if c['store'] else None)
                      for i in range(start,stop) if c['mask']>>i&1
                      for f,off in enumerate(c['field_offsets'][i])]
            got=[tuple(x) for x in e['access']]
            if fault and n==0:
                base.require(got[:len(required)]==required,'Completed access prefix mismatch')
                allowed={(VA+off,inp(f,stop) if c['store'] else None)
                         for f,off in enumerate(c['field_offsets'][stop]) if off<4096}
                base.require(len(set(got[len(required):]))==len(got[len(required):]) and
                             set(got[len(required):])<=allowed,'Unexpected fault-element access')
            else:
                base.require(got==required,'Retry/alloff exact active accesses mismatch')
    base.require(traps==goldtraps,'Exception sequence differs: '+str(traps))
    base.require([(p['trial'],p['phase']) for p in points] ==
                 [(c['trial'],p) for c in cases for p in ((1,2) if c['expected_cause'] else (2,))], 'Checkpoint coverage differs')
    base.require(exits==[1] and read64(memory,s['na_completed'])==DONE and
                 read64(memory,s['na_errors'])==read64(memory,s['na_unexpected'])==0 and
                 read64(memory,s['na_cases_done'])==len(cases),'Incomplete software exit')
    base.require(checks==read64(memory,s['na_checks']),'Oracle comparison count mismatch')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',trials=list(by_trial),checks=checks,commits=commits,
                checkpoints=points,actions=actions,traps=traps,target_events=events,
                case_checks=[read64(memory,s['na_case_checks']+i*8) for i in range(4)],
                VCS_launched=False,Linux_replay=False)


def check_state(memory, s, c, phase):
    compare(memory,expected(s,c,phase),f"trial{c['trial']} phase{phase}")
    fault=c['expected_cause'] is not None
    for n in range(2 if phase==2 and fault else 1):
        a=s['na_records']+96*n
        base.require(read64(memory,a+24)&0x8000031888 == 0x800,'Trap privilege changed')
        if n==0 and fault:
            base.require(read64(memory,a+16) in [VA+x['offset'] for x in c['allowed_fault_addresses']],
                         'Fault tval not an allowed protected field')
    if phase==1 and c['store']:
        for f,off in enumerate(c['field_offsets'][c['expected_vstart']]):
            if off<4096:
                got=int.from_bytes(bytes(memory.get(s['na_pages']+off+i,255) for i in range(4)),'little')
                base.require(got in (orig(off),inp(f,c['expected_vstart'])),
                             'Partial store value is neither original nor stored field value')


def negatives(s, cases):
    def put(m,a,v,n=8):
        for i,b in enumerate(v.to_bytes(n,'little')): m[a+i]=b
    def synthetic(c,p):
        m=expected(s,c,p)
        fault=c['expected_cause'] is not None
        for n in range(2 if p==2 and fault else 1):
            put(m,s['na_records']+96*n+24,0x800)
            if n==0 and fault: put(m,s['na_records']+16,VA+c['permitted_tval_offsets'][0])
        if p==1 and c['store']:
            for off in c['field_offsets'][c['expected_vstart']]:
                if off<4096: put(m,s['na_pages']+off,orig(off),4)
        check_state(m,s,c,p)
        return m
    result=[]; allowed=0
    for c in cases:
        for phase in ((1,2) if c['expected_cause'] else (2,)):
            synthetic(c,phase)
        a=s['na_result']+64+9*128
        choices=[('v31_active_or_old',2,a),('v31_cap_tail',2,a+8*4),
                 ('v31_physical_fractional_tail',2,a+31*4),
                 ('output_guard0',2,s['na_output']),('output_guard129',2,s['na_output']+129*4),
                 ('page_table',2,s['na_pages']+16384+8),
                 ('stride_argument',2,s['na_stride']),('memory_gap',2,s['na_pages']),
                 ('mask',2,s['na_mask']),('CSR_fcsr',2,s['na_post']+32),
                 ('firsterror',2,s['na_firsterror'])]
        if c['expected_cause']:
            choices += [('fault_vstart',1,s['na_records']+56),('fault_pc',1,s['na_records']+8),
                        ('protected_tval',1,s['na_records']+16),
                        ('saved_v31_cap_tail',1,s['na_fault']+64+9*128+8*4)]
            if c['completed_active_prefix']:
                i=c['completed_active_prefix'][0]
                choices += [('saved_v31_prefix',1,s['na_fault']+64+9*128+i*4),
                            ('prefix_replayed',2,s['na_pages']+c['field_offsets'][i][7])]
        else:
            choices += [('alloff_no_fault_snapshot',2,s['na_fault']+64),
                        ('alloff_trap_count',2,s['na_count'])]
        for name,p,a in choices:
            m=synthetic(c,p); m[a]^=1
            try: check_state(m,s,c,p)
            except ValueError: result.append(dict(trial=c['trial'],name=name)); continue
            raise ValueError('Negative oracle accepted: '+name)
        if c['store'] and c['expected_cause']:
            for f,off in enumerate(c['field_offsets'][c['expected_vstart']]):
                if off>=4096: continue
                m=synthetic(c,1); put(m,s['na_pages']+off,inp(f,c['expected_vstart']),4)
                check_state(m,s,c,1); allowed+=1
                put(m,s['na_pages']+off,0xdeadbeef,4)
                try: check_state(m,s,c,1)
                except ValueError: result.append(dict(trial=c['trial'],name='partial_store_third_value_f'+str(f))); continue
                raise ValueError('Invalid partial field value accepted')
        elif c['expected_cause']:
            m=synthetic(c,1)
            for f in range(8):
                put(m,s['na_fault']+64+(2+f)*128+c['expected_vstart']*4,0x12345678,4)
            check_state(m,s,c,1); allowed+=1
    return dict(rejected=result,allowed_partial_states=allowed)


def run(out, groups, host_only=False):
    base.require(out.is_relative_to(HERE) and out != HERE and not out.exists(),'Fresh owned output required')
    base.require(groups and len(set(groups))==len(groups) and all(0<=g<48 for g in groups),'Groups must be distinct 0..47')
    geometry=load_geometry(); base.prepare.check(base.PARENT)
    pins={**geometry['source_identity']}
    files=[Path(__file__),GEOMETRY,HERE.parent/'prepare_selection.py',HERE.parent/'STATIC_SELECTION.md',
           HERE/'fixture.c',HERE/'fixture.h',HERE/'fixture.S',Path(base.__file__),base.BASE/'prepare.py',
           base.CC.resolve(),base.SPIKE,base.PARENT/'provenance.json',
           base.ROOT/'verification/coverage/scoped_rv64c_memory.py']
    files += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld')]
    for lineage in ('segment_review/sv39', 'indexed_review/sv39', 'nf8_strided_review/sv39'):
        files += [HERE.parents[1]/lineage/n for n in ('fixture.c','fixture.h','fixture.S','reference.py')]
    pins.update({str(p):base.sha(p) for p in files})
    out.mkdir(parents=True)
    base.save(out/'input_pins.json',pins)
    base.save(out/'source_provenance.json',geometry)
    prepared=out/'prepared'; prepared.mkdir()
    for n in ('startup.S','runtime.c','replay.ld'):
        shutil.copyfile(base.PARENT/n,prepared/n)
    for n in ('fixture.c','fixture.S','fixture.h'):
        shutil.copyfile(HERE/n,prepared/n)
    shutil.copyfile(ASM,prepared/'original.S')
    base.save(prepared/'provenance.json',dict(files={p.name:base.sha(p) for p in prepared.iterdir()},
              scope='NF8 source-derived real Sv39, exact archived S; identity57 binds C/generator to original ELF',
              original_linux_execution=False))
    try:
        base.run_logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DNA_HOST',prepared/'fixture.c','-o',out/'host'],out/'host.compile.log')
        base.run_logged([out/'host'],out/'host.stdout')
        rows=host_check(out/'host.stdout',geometry['cases'])
        base.save(out/'host.json',dict(status='HOST_ORACLE_ALL192_PASS_NOT_DUT',rows=rows))
        if host_only:
            for path,digest in pins.items(): base.require(base.sha(path)==digest,'Host input drift: '+path)
            base.save(out/'status.json',dict(status='HOST_ALL192_PASS_NOT_DUT',rows=rows,Spike_started=False,VCS_launched=False))
            print('HOST_ALL192_PASS_NOT_DUT',rows,flush=True)
            return
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
               '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
               '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
               '-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld']
        completed=[]
        for group in groups:
            d=out/f'group{group:02d}'; d.mkdir()
            cases=geometry['cases'][group*4:group*4+4]
            base.save(d/'cases.json',cases)
            symbols={}
            for backend in ('soc','spike'):
                elf=d/(backend+'.elf')
                cmd=[base.CC,*flags,f'-DNA_GROUP={group}']+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
                cmd += [prepared/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')]+['-lgcc','-o',elf]
                base.run_logged(cmd,d/(backend+'.compile.log'))
                base.run_logged([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],d/(backend+'.dis'))
                nm=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=15)
                s={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
                base.require(s['__bss_end']<0x800f0000,'ELF exceeds sealed memory/stack interface')
                symbols[backend]=s; base.save(d/(backend+'.symbols.json'),s)
            base.save(d/'negative_oracle.json',negatives(symbols['spike'],cases))
            start=time.monotonic()
            base.run_logged([base.SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                             '-m2','-l','--log-commits',d/'spike.elf'],d/'spike.stdout',d/'spike.trace',timeout=90)
            result=validate(d/'spike.trace',symbols['spike'],cases)
            result.update(elapsed_s=time.monotonic()-start,elf_sha256={b:base.sha(d/(b+'.elf')) for b in ('soc','spike')})
            base.save(d/'status.json',result); completed.append(group)
            print(json.dumps(dict(group=group,trials=result['trials'],status=result['status'],checks=result['checks'],commits=result['commits'])),flush=True)
        for p,h in pins.items():
            base.require(base.sha(p)==h,'Input drift: '+p)
        base.save(out/'status.json',dict(status='HOST_SPIKE_GROUPS_PASS_NOT_DUT',groups=completed,trials=[g*4+i for g in completed for i in range(4)],host_rows=rows,
                  all192_spike=sorted(completed)==list(range(48)),original_169_128_root_cause_known=False,VCS_launched=False,Linux_replay=False))
    except Exception as error:
        base.save(out/'failure.json',dict(status='REFERENCE_FAILED_NOT_DUT',error=str(error)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--groups',type=int,nargs='+',default=list(range(48)))
    parser.add_argument('--host-only',action='store_true')
    args=parser.parse_args()
    run(args.out.resolve(),args.groups,args.host_only)
