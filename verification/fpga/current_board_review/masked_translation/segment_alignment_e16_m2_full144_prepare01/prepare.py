#!/usr/bin/env python3
"""Fresh software/Host preparation only. Reference execution is separate."""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode = True
import model as m

OUT = m.HERE / 'software01'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
RUNTIME = Path('/tmp/current-board-integration-fast01/prepared')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA = 'rv64gcv_zfh_zvfh_zvl1024b'

def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

def command(cmd, path, timeout=120):
    cmd = list(map(str, cmd))
    start = time.monotonic()
    timed_out = False
    with path.open('x') as f:
        child = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    save(path.with_suffix(path.suffix + '.execution.json'),
         dict(command=cmd, returncode=rc, timeout=timed_out, elapsed_s=time.monotonic()-start))
    m.require(rc == 0 and not timed_out, 'Preparation command failed: ' + str(path))

def code(text):
    return {int(a,16):int(v,16) for a,v in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s', text, re.M)}

def window(c, pc, n):
    out = []
    for _ in range(n):
        m.require(pc in c, 'Missing helper PC')
        out.append(pc)
        pc += 4 if c[pc]&3 == 3 else 2
    return out

def main():
    m.require(not OUT.exists(), 'Fresh preparation only; failures retained')
    manifest = json.loads((m.A/'manifest.json').read_text())
    fixed = {m.R/'segment_alignment_oracle.c': 'dd99ad9ba59c451dc01891b2badcd182a2453ceb6651dd1cb683bd8f6b5a8bb0',
             m.R/'segment_alignment.py': '4ddb4103829436036c57b6943a3bad1b48856426f6b646c66a6cafb173413ab7',
             m.A/'manifest.json': 'c9d7eafaa356ebab465b81ed8330632c98e8b6a0923dc80b576bad3d404066ee'}
    for p in (m.A/'overlay/opt/ara-tests'/m.NAME,
              m.C/'rvv_additions32/binaries'/m.NAME,
              m.C/'rvv_recovery08_37/terminal_scene'/m.NAME):
        fixed[p] = 'cfcdabf6e7a378d789c01dde8864e4beb16a133712090e805841cb24648db1df'
    for p,h in fixed.items(): m.require(m.sha(p)==h, 'Original source/ELF drift '+str(p))
    record = next(c for c in manifest['cases'] if c['name']==m.NAME)
    m.require(record['configurations']==144 and record['fields']==[3,4], 'Original scope')
    asm = (m.A/'e16_m2/operations.S').read_text()
    names = ['capacity']+['op_%d'%i for i in range(8)]
    sections = {}
    for i,name in enumerate(names):
        part = asm.split(name+':\n',1)[1]
        part = part.split('.global ',1)[0]
        sections[name] = [s for s in part.splitlines() if s and not s.startswith('.')]
    annotated = []
    targets = []
    for line in asm.splitlines():
        if re.match(r'v(?:lseg|sseg|lsseg|ssseg)[34]e16\.v',line):
            label = 'target_%d' % len(targets)
            targets.append(label)
            annotated += ['.global '+label,label+':']
        annotated.append(line)
    m.require(len(targets)==8, 'All eight original targets')
    OUT.mkdir()
    p = OUT/'prepared';p.mkdir()
    sources = list(fixed)+[m.A/'e16_m2'/n for n in ('operations.S','operations.h')]
    sources += [m.HERE/n for n in ('model.py','fixture.c','fixture.S','prepare.py','host_tests.py')]
    sources += [RUNTIME/n for n in ('startup.S','runtime.c','replay.ld')]
    sources += [CC.resolve(),CC.with_name('riscv64-unknown-elf-objdump').resolve(),CC.with_name('riscv64-unknown-elf-nm').resolve(),SPIKE]
    sources += [m.HERE.parent/'segment_full144_preparation_contract01.md']
    pins = {str(f):m.sha(f) for f in sources}
    save(OUT/'input_pins.json',pins)
    (p/'rom.h').write_text(m.header())
    (p/'original.S').write_text('\n'.join(annotated)+'\n')
    (p/'targets.S').write_text('.section .rodata\n.balign 8\n.global mx_targets\nmx_targets:\n'+''.join('.quad '+t+'\n' for t in targets))
    for n in ('fixture.c','fixture.S'): shutil.copyfile(m.HERE/n,p/n)
    shutil.copyfile(m.A/'e16_m2/operations.h',p/'operations.h')
    for n in ('startup.S','runtime.c','replay.ld'): shutil.copyfile(RUNTIME/n,p/n)
    command(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared','-DHOST_ORACLE',p/'fixture.c','-o',OUT/'host.so'],OUT/'host.compile.log')
    command([sys.executable,'-B',m.HERE/'host_tests.py',OUT],OUT/'host.stdout')
    original = m.A/'overlay/opt/ara-tests'/m.NAME
    objdump = CC.with_name('riscv64-unknown-elf-objdump')
    command([objdump,'-d',original],OUT/'original.dis')
    old = code((OUT/'original.dis').read_text())
    oldpc = 0x106f0
    old_windows = {}
    for name in names:
        pcs = window(old,oldpc,len(sections[name]));old_windows[name]=pcs
        oldpc = pcs[-1]+(4 if old[pcs[-1]]&3==3 else 2)
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections','-T',p/'replay.ld']
    proofs={}
    for backend in ('soc','spike'):
        elf=OUT/(backend+'.elf')
        command([CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                 *[p/n for n in ('fixture.c','fixture.S','original.S','targets.S','startup.S','runtime.c')],
                 '-lgcc','-o',elf],OUT/(backend+'.compile.log'))
        command([objdump,'-d',elf],OUT/(backend+'.dis'))
        nm=subprocess.check_output([CC.with_name('riscv64-unknown-elf-nm'),'-n',elf],text=True,timeout=30)
        syms={name:int(addr,16) for addr,name in re.findall(r'^([0-9a-f]+)\s+\w\s+(\S+)$',nm,re.M)}
        save(OUT/(backend+'.symbols.json'),syms)
        c=code((OUT/(backend+'.dis')).read_text());helpers={}
        for name in names:
            pcs=window(c,syms[name],len(sections[name]));original_pcs=old_windows[name]
            m.require([c[x] for x in pcs]==[old[x] for x in original_pcs], 'Actual helper bytes differ '+name)
            helpers[name]=dict(pcs=pcs,original_pcs=original_pcs,encodings=[c[x] for x in pcs])
        m.require(syms['__bss_end']<syms['__stack_top']-65536,'Full linked footprint/stack')
        proofs[backend]=dict(elf_sha256=m.sha(elf),helpers=helpers,
                             linked_end=syms['__bss_end'],stack_top=syms['__stack_top'],
                             stack_gap=syms['__stack_top']-syms['__bss_end'])
    m.require(all(m.sha(f)==h for f,h in pins.items()),'Input changed during preparation')
    rows,_=m.tables()
    save(OUT/'source_proof.json',dict(status='HOST_SOFTWARE_PREPARED_NOT_REFERENCE_OR_DUT',
         source_pins=pins,scope=dict(cases=144,capacity=128,full_bytes_each=8192,all_numerical_bytes=144*8192,
         original_helpers=8,capacity_helper_instructions=3,capability_eligible=24,no_active=96),
         unique_oracle_rows=len(rows),rom_data_bytes=(len(rows)+2)*8192,
         original_linux_ELF_byte_identity=False,helper_byte_identity=True,
         linux_clone_COW_signal_reproduced=False,deterministic_per_child_data_reset=True,
         actual_profile=ISA,backends=proofs))
    save(OUT/'status.json',dict(status='HOST_SOFTWARE_PREPARED_NOT_REFERENCE_OR_DUT',
         inputs_unchanged=True,reference_executed=False,DUT_executed=False))
    print(json.dumps(dict(status='HOST_SOFTWARE_PREPARED_NOT_REFERENCE_OR_DUT',unique_oracle_rows=len(rows),
                          rom_bytes=(len(rows)+2)*8192,stack_gaps={k:v['stack_gap'] for k,v in proofs.items()})))

if __name__=='__main__': main()
