#!/usr/bin/env python3
"""NF7 source-derived real Sv39 host/Spike reference. No VCS entry point."""
import argparse
import importlib.util
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
DONE = 0x6978737633390008
GEOMETRY = HERE.parent / 'geometry01.json'
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery12_indexed_failure01')
ASM = ARCHIVE / 'rvv_fault_replay_segment_nf7_indexed_e32_mf2.S'


def load_geometry():
    doc = json.loads(GEOMETRY.read_text())
    for path, digest in doc['source_identity'].items():
        base.require(base.sha(path) == digest, 'Archived source identity changed: ' + path)
    spec = importlib.util.spec_from_file_location('indexed_geometry', HERE.parent / 'prepare.py')
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    base.require(parent.cases() == doc['cases'], 'Geometry regeneration differs')
    base.require(len(doc['cases']) == 96 and sum(c['expected_cause'] is not None for c in doc['cases']) == 72,
                 'Original trial/fault counts differ')
    return doc


def orig(byte):
    return byte // 4 * 37 + 11


def seed(r, i):
    return 0x6c700000 ^ (r << 16) ^ i


def inp(f, i):
    return 101 + 13 * i + 29 * f


def index(c, i):
    return c['index_offsets'][i] if i < 8 else i * 28


def vg(c, phase, r, i):
    if r == 0:
        return index(c, i) if i < 16 else seed(r, i)
    if r in (1, 9) or i >= 16:
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
                elif c['store'] and byte < 4096:
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
            fields = ['trial', 'unmapped', 'store', 'boundary', 'mode', 'split', 'mask', 'base_offset']
            expected = ['C ' + ' '.join(str(c[k]) for k in fields) + ' ' + str(start)]
            expected += [f'I {t} {i} {index(c,i)}' for i in range(128)]
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
    pages = s['ix_pages']
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
    for name in ('ix_guard_lo', 'ix_guard_hi'):
        for i in range(8):
            put(s[name]+i*8, G, 8)
    for name in ('ix_seed', 'ix_fault', 'ix_result'):
        a = s[name]
        for off in (0, 1344):
            for i in range(8):
                put(a+off+i*8, G, 8)
        used = name == 'ix_fault' and fault or name == 'ix_result' and phase == 2
        for r in range(10):
            for i in range(32):
                v = seed(r, i) if name == 'ix_seed' else vg(c, 1 if name == 'ix_fault' else 2, r, i) \
                    if used else (G >> ((i%2)*32)) & 0xffffffff
                put(a+64+r*128+i*4, v, 4)
    for i in range(896):
        put(s['ix_input']+i*4, inp(i//16,i%16) if i < 112 else 0x5b, 4)
    for i in range(898):
        v = vg(c, 2, 2+(i-1)//16, (i-1)%16) if phase == 2 and 1 <= i <= 112 else 0x5b
        put(s['ix_output']+i*4, v, 4)
    for i in range(128):
        put(s['ix_indices']+i*4, index(c,i), 4)
    for i in range(16):
        put(s['ix_mask']+i, c['mask'], 1)
    for i,v in enumerate((0,16,23,0,117,5)):
        put(s['ix_post']+i*8, v if phase == 2 else (1<<64)-1, 8)
    for n in range(2):
        used = n == 0 or phase == 2 and fault
        f = n == 0 and fault
        record = [c['expected_cause'] if f else 9,
                  s['fault_1_pc' if c['store'] else 'fault_0_pc'] if f else s['ix_ecall'],
                  None if f else 0, None, (8<<60)|((pages+8192)>>12), 8 if f else 16, 23,
                  c['expected_vstart'] if f else 0,117,5,0 if f else 1,
                  denied if f or not fault else pte(pages+4096,0xc7)]
        for j,v in enumerate(record):
            put(s['ix_records']+n*96+j*8, v if used else (1<<64)-1, 8)
    for name,v in [('ix_count', 2 if phase == 2 and fault else 1), ('ix_marker',int(phase==2)),
                   ('ix_errors',0), ('ix_unexpected',0)]:
        put(s[name],v,8)
    for i in range(6):
        put(s['ix_firsterror']+i*8,0,8)
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
    target_codes = {s['fault_0_pc']:0xcd056c07, s['fault_1_pc']:0xcd056c27}
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
            trial = read64(memory,s['ix_current'])
            access = [(int(a,16),int(v,16) if v else None)
                      for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
            if pc in target_codes:
                c = by_trial[trial]
                base.require(mode == 1 and pc == s['fault_1_pc' if c['store'] else 'fault_0_pc'], 'Not expected real S-mode target')
                base.require(insn == target_codes[pc], 'Original NF7 ordered indexed target encoding differs')
                actions[trial].append('target')
                events.append(dict(trial=trial,pc=hex(pc),insn=hex(insn),access=access))
            if pc == s['ix_younger_store']:
                base.require(mode == 1,'Younger not S-mode')
                actions[trial].append('younger')
            if pc == s['ix_repair_sfence']:
                base.require(mode == 3 and regs.get((insn>>15)&31) == VA+4096, 'Wrong repair SFENCE address')
                actions[trial].append('repair')
            if pc == s['ix_retry_mret'] and read64(memory,s['ix_marker']) == 0:
                actions[trial].append('retry')
            if pc == s['ix_checkpoint']:
                c = by_trial[trial]; phase = read64(memory,s['ix_phase'])
                want = expected(s,c,phase)
                compare(memory,want,f'trial{trial} phase{phase}')
                fault = c['expected_cause'] is not None
                for n in range(2 if phase == 2 and fault else 1):
                    a = s['ix_records']+n*96
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
                physical = s['ix_pages']+a-VA if VA <= a < VA+8192 else a
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
        goldtraps.append(('trap_supervisor_ecall',s['ix_ecall']))
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
    base.require(exits==[1] and read64(memory,s['ix_completed'])==DONE and
                 read64(memory,s['ix_errors'])==read64(memory,s['ix_unexpected'])==0 and
                 read64(memory,s['ix_cases_done'])==4,'Incomplete software exit')
    base.require(checks==read64(memory,s['ix_checks']),'Oracle comparison count mismatch')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',trials=list(by_trial),checks=checks,commits=commits,
                checkpoints=points,actions=actions,traps=traps,target_events=events,
                case_checks=[read64(memory,s['ix_case_checks']+i*8) for i in range(4)],
                VCS_launched=False,Linux_replay=False)


def negatives(s, cases):
    c=next(c for c in cases if c['expected_cause'])
    a=s['ix_result']+64+2*128+31*4
    choices=[('full_field_upper_tail',c,2,a),('output_guard',c,2,s['ix_output']),
             ('wrong_vstart',c,1,s['ix_records']+56),('page_table',c,1,s['ix_pages']+16384+8),
             ('index_buffer',c,2,s['ix_indices']),('memory_outside_targets',c,2,s['ix_pages'])]
    for i in c['completed_active_prefix'][:1]:
        choices.append(('prefix_poison_replayed',c,2,s['ix_pages']+c['field_offsets'][i][0]))
    result=[]
    for name,c,p,a in choices:
        want=expected(s,c,p); bad=dict(want); bad[a]^=1
        try:
            compare(bad,want,name)
        except ValueError:
            result.append(name)
        else:
            raise ValueError('Negative oracle accepted: '+name)
    return result


def run(out, groups):
    base.require(out.is_relative_to(HERE) and out != HERE and not out.exists(),'Fresh owned output required')
    base.require(groups and len(set(groups))==len(groups) and all(0<=g<24 for g in groups),'Groups must be distinct 0..23')
    geometry=load_geometry(); base.prepare.check(base.PARENT)
    pins={**geometry['source_identity']}
    files=[Path(__file__),GEOMETRY,HERE.parent/'prepare.py',HERE.parent/'README.md',
           HERE/'fixture.c',HERE/'fixture.h',HERE/'fixture.S',Path(base.__file__),base.BASE/'prepare.py',
           base.CC.resolve(),base.SPIKE,base.PARENT/'provenance.json',
           base.ROOT/'verification/coverage/scoped_rv64c_memory.py']
    files += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld')]
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
              scope='Source-derived real Sv39, exact archived assembly; C not byte-proven original ELF',
              original_linux_execution=False))
    try:
        base.run_logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DIX_HOST',prepared/'fixture.c','-o',out/'host'],out/'host.compile.log')
        base.run_logged([out/'host'],out/'host.stdout')
        rows=host_check(out/'host.stdout',geometry['cases'])
        base.save(out/'host.json',dict(status='HOST_ORACLE_ALL96_PASS_NOT_DUT',rows=rows))
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
                cmd=[base.CC,*flags,f'-DIX_GROUP={group}']+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
                cmd += [prepared/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')]+['-lgcc','-o',elf]
                base.run_logged(cmd,d/(backend+'.compile.log'))
                base.run_logged([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],d/(backend+'.dis'))
                nm=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=15)
                s={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
                base.require(s['__bss_end']<0x800f0000,'ELF exceeds sealed memory/stack interface')
                symbols[backend]=s; base.save(d/(backend+'.symbols.json'),s)
            start=time.monotonic()
            base.run_logged([base.SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                             '-m2','-l','--log-commits',d/'spike.elf'],d/'spike.stdout',d/'spike.trace',timeout=90)
            result=validate(d/'spike.trace',symbols['spike'],cases)
            result.update(elapsed_s=time.monotonic()-start,elf_sha256={b:base.sha(d/(b+'.elf')) for b in ('soc','spike')})
            base.save(d/'negative_oracle.json',negatives(symbols['spike'],cases))
            base.save(d/'status.json',result); completed.append(group)
            print(json.dumps(dict(group=group,trials=result['trials'],status=result['status'],checks=result['checks'],commits=result['commits'])),flush=True)
        for p,h in pins.items():
            base.require(base.sha(p)==h,'Input drift: '+p)
        base.save(out/'status.json',dict(status='HOST_SPIKE_SELECTED_GROUPS_PASS_NOT_DUT',groups=completed,
                  trials=[g*4+i for g in completed for i in range(4)],host_rows=rows,
                  all96_spike=sorted(completed)==list(range(24)),VCS_launched=False,Linux_replay=False))
    except Exception as error:
        base.save(out/'failure.json',dict(status='REFERENCE_FAILED_NOT_DUT',error=str(error)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--groups',type=int,nargs='+',required=True)
    args=parser.parse_args()
    run(args.out.resolve(),args.groups)
