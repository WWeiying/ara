#!/usr/bin/env python3
"""Independent host/Spike Sv39 proof. No RTL build and no implicit SoC run."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare
sys.path.insert(0, str(ROOT / 'verification/coverage'))
from scoped_rv64c_memory import decode as compressed_memory

PARENT = Path('/tmp/current-board-integration-fast01/prepared')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
NAMES = ('alloff_fault', 'active_fault_retry', 'alloff_valid')
GUARD = 0xe370697c
DONE = 0x6d74737633390001
SYMBOLS = ('mt_pages', 'mt_guard_lo', 'mt_guard_hi', 'mt_seed', 'mt_fault',
           'mt_result', 'mt_out', 'mt_mask', 'mt_records', 'mt_post',
           'mt_trap_count', 'mt_marker', 'mt_repair_pte', 'mt_expected_satp',
           'mt_unexpected', 'mt_completed', 'mt_checks', 'mt_errors',
           'mt_target', 'mt_ecall', 'mt_recovery_load', 'mt_younger_store',
           'mt_handler', 'trap_entry', 'tohost')
SITES = dict(mt_target=0x00055c07, mt_recovery_load=0x0203d407,
             mt_younger_store=0x0062b023, mt_repair_store=0x006e3023,
             mt_repair_sfence=0x120e0073, mt_retry_mret=0x30200073)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def inside(path):
    path = path.resolve()
    require(path.is_relative_to(HERE) and path != HERE, 'Output must be under masked_translation/')
    return path


def data(page, i):
    return ((i-2044)*37+11 if page == 0 and i >= 2044 else 0x3100+page*0x4000+i*37) & 65535


def word(r, w, variant, result=False):
    v = 0x005b005b if r == 1 else 0x6c700000 ^ (r << 16) ^ w
    halves = [v & 65535, v >> 16]
    if result:
        for h in range(2):
            i = w*2+h
            if r == 1 and variant == 1 and i == 0:
                halves[h] = data(1,i)
            elif r == 3 and i < 8:
                halves[h] = data(0,i)
    return halves[0] | halves[1] << 16


def check_host(text, variant):
    gold = ['R %d %d %08x %08x' % (r,w,word(r,w,variant),word(r,w,variant,True))
            for r in range(4) for w in range(32)]
    gold += ['D %d %d %04x' % (p,i,data(p,i)) for p in range(2) for i in range(2048)]
    require(text.splitlines() == gold, 'Independent Python vs host C oracle mismatch')
    return dict(rows=len(gold), full_vector_bytes=512, data_bytes=8192)


def expected_memory(s, variant):
    memory = {}

    def add(a, value, width):
        for i,b in enumerate(value.to_bytes(width,'little')):
            require(a+i not in memory, 'Overlapping expected memory')
            memory[a+i] = b

    pages = s['mt_pages']
    require(pages % 4096 == 0 and s['mt_guard_lo']+64 == pages and
            s['mt_guard_hi'] == pages+20480, 'Page guard layout mismatch')
    satp = (8 << 60) | ((pages+8192) >> 12)
    repair = ((pages+4096) >> 12 << 10) | 0xc7
    for p in range(2):
        for i in range(2048):
            add(pages+p*4096+i*2, data(p,i), 2)
    ptes = {1025: ((pages+12288) >> 12 << 10) | 1,
            1026: 0x200000cf, 1536: ((pages+16384) >> 12 << 10) | 1,
            2048: (pages >> 12 << 10) | 0xc7,
            2049: repair if variant in (1,2) else 0}
    for i in range(1024,2560):
        add(pages+i*8,ptes.get(i,0),8)
    for name in ('mt_guard_lo','mt_guard_hi'):
        for w in range(16):
            add(s[name]+w*4,GUARD,4)
    for name in ('mt_seed','mt_fault','mt_result'):
        require(s[name] % 64 == 0, 'Snapshot alignment differs')
        for offset in (0,576):
            for w in range(16):
                add(s[name]+offset+w*4,GUARD,4)
        for r in range(4):
            for w in range(32):
                v = GUARD if name == 'mt_fault' and variant != 1 else word(r,w,variant,name == 'mt_result')
                add(s[name]+64+r*128+w*4,v,4)
    for i in range(130):
        add(s['mt_out']+i*2,data(1,0) if variant == 1 and i == 1 else 0x5b,2)
    for i in range(16):
        add(s['mt_mask']+i,int(variant == 1 and i == 0),1)
    for n in range(2):
        used, fault = n == 0 or variant == 1, variant == 1 and n == 0
        vals = [13 if fault else 9,s['mt_target'] if fault else s['mt_ecall'],
                0x40001000 if fault else 0,None,satp,8,8,0,117,5,0 if fault else 1,
                0 if fault or variant == 0 else repair]
        for j,v in enumerate(vals):
            if not used:
                v = (1 << 64)-1
            if v is not None:
                add(s['mt_records']+n*96+j*8,v,8)
    for i,v in enumerate((8,8,0,117,5)):
        add(s['mt_post']+i*8,v,8)
    for name,v,width in (('mt_trap_count',2 if variant == 1 else 1,8),
                         ('mt_marker',1,8),('mt_repair_pte',repair,8),
                         ('mt_expected_satp',satp,8),('mt_unexpected',0,8),
                         ('mt_completed',DONE,8),('mt_errors',0,4),('mt_checks',709,4)):
        add(s[name],v,width)
    return memory


def validate_trace(text, s, variant):
    expected = expected_memory(s,variant)
    traps = re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)',text)
    gold_traps = ([('trap_load_page_fault','%016x' % s['mt_target'])] if variant == 1 else [])
    gold_traps += [('trap_supervisor_ecall','%016x' % s['mt_ecall'])]
    require(traps == gold_traps, 'Exact exception ledger differs: '+repr(traps))
    sites = {s[n]:n for n in SITES if n in s}
    actual, regs, actions, tohost = {}, {0:0}, [], []
    retired, partials, awaiting = 0, 0, False
    for line in text.splitlines():
        require(not re.match(r'^core\s+[1-9][0-9]*:',line),'Unexpected hart')
        m = re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not m:
            continue
        mode,pc,insn,tail = int(m[1]),int(m[2],16),int(m[3],16),m[4]
        require(pc != s['trap_entry'],'Default trap path executed')
        access = [(int(a,16),int(v,16) if v else None)
                  for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc in sites:
            name = sites[pc]
            require(insn == SITES[name],'Exact site opcode differs: '+name)
            require(mode == (3 if name.startswith('mt_repair') or name == 'mt_retry_mret' else 1),
                    'Site not at expected real privilege: '+name)
        if pc == s['mt_target'] and variant == 1 and not access and not re.search(r'\bv24\s',tail):
            require(re.fullmatch(r'\s+e16 m1 l8 c8_vstart 0x0+\s*',tail),
                    'Unexpected faulting partial-vector event')
            partials += 1
            actions.append('fault_partial')
            awaiting = True
            continue
        retired += 1
        if awaiting and insn & 127 == 0x73 and insn >> 20 == 0x341:
            require((insn >> 12) & 7 in (2,3,6,7) and (insn >> 15) & 31 == 0,
                    'Original fault mepc overwritten before retry')
        if pc in sites:
            name = sites[pc]
            actions.append(name)
            if name in ('mt_target','mt_recovery_load'):
                r,vr = (1,24) if name == 'mt_target' else (3,8)
                want = sum(word(r,w,variant,True) << (32*w) for w in range(32))
                writes = re.findall(r'\bv%d\s+0x([0-9a-f]+)' % vr,tail)
                if name == 'mt_target' and variant != 1:
                    # Spike emits no destination write for zero active elements.
                    # The complete post-target snapshot is still checked below.
                    require(not writes and re.fullmatch(r'\s+e16 m1 l8 c8_vstart 0x0+\s*',tail),
                            'Unexpected all-off register/CSR event')
                else:
                    require(len(writes) == 1 and int(writes[0],16) == want and 'e16 m1 l8' in tail,
                            'Complete destination/undisturbed tail differs: '+name)
                addresses = ([(0x40001000,None)] if variant == 1 else []) if name == 'mt_target' else [
                    (0x40000000+2*i,None) for i in range(8)]
                require(access == addresses,'Exact predicate-qualified memory addresses differ')
            elif name == 'mt_repair_store':
                require(access == [(s['mt_pages']+16392,((s['mt_pages']+4096) >> 12 << 10) | 0xc7)],
                        'Wrong exact PTE repair store')
            elif name == 'mt_repair_sfence':
                require(regs.get(28) == 0x40001000,'Wrong addressed SFENCE')
            elif name == 'mt_retry_mret':
                require(awaiting,'Unpaired retry')
                awaiting = False
        for a,v in access:
            if v is None:
                continue
            opcode,funct = insn & 127,(insn >> 12) & 7
            if insn & 3 != 3:
                d = compressed_memory(insn)
                require(d is not None and d['kind'] == 'write','Unknown compressed store')
                require(a == (regs.get(d['base'],-1)+d['offset']) & ((1 << 64)-1),
                        'Compressed store address differs from source GPR')
                width = d['size']
                if d['register'] in regs:
                    require(v & ((1 << (width*8))-1) == regs[d['register']] & ((1 << (width*8))-1),
                            'Compressed store value differs from source GPR')
                else:
                    require(not any(a+i in expected for i in range(width)), 'Unproven oracle write')
            else:
                require(opcode in (0x23,0x27),'Unknown memory store opcode')
                width = (1 << funct) if opcode == 0x23 else {0:1,5:2,6:4,7:8}.get(funct)
            require(width in (1,2,4,8),'Unsupported store width')
            for i,b in enumerate((v & ((1 << (8*width))-1)).to_bytes(width,'little')):
                actual[a+i] = b
            if a == s['tohost']:
                tohost.append(v)
        regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    gold_actions = (['fault_partial','mt_repair_store','mt_repair_sfence','mt_retry_mret']
                    if variant == 1 else []) + ['mt_target','mt_recovery_load','mt_younger_store']
    require(actions == gold_actions and not awaiting and partials == int(variant == 1),
            'Exact fault/retry/younger ordering differs: '+repr(actions))
    # Full scalar initialization and all-byte verification cost about 275k commits.
    require(tohost == [1] and retired < 350000,'Nonzero/duplicate/missing completion or execution bound')
    bad = [(hex(a),b,actual.get(a)) for a,b in expected.items() if actual.get(a) != b]
    require(not bad,'Full memory oracle mismatch: '+repr(bad[:10]))
    for n in range(2 if variant == 1 else 1):
        value = int.from_bytes(bytes(actual.get(s['mt_records']+n*96+24+i,255) for i in range(8)),'little')
        require(value & 0x8000031888 == 0x800,'S-mode trap mstatus differs')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',variant=NAMES[variant],retired=retired,
                verified_memory_bytes=len(expected),traps=traps,actions=actions,checks=709,
                full_oldvd_bytes=128,neighbor_guard_bytes=256,recovery_register_bytes=128,
                original_linux_replay=False,coverage_admitted=False)


def run_logged(command, stdout, stderr=None, timeout=60):
    save(stdout.with_suffix(stdout.suffix+'.command.json'),[str(x) for x in command])
    with stdout.open('x') as out:
        if stderr is None:
            subprocess.run(list(map(str,command)),stdout=out,stderr=subprocess.STDOUT,check=True,timeout=timeout)
        else:
            with stderr.open('x') as err:
                subprocess.run(list(map(str,command)),stdout=out,stderr=err,check=True,timeout=timeout)


def build(out):
    require(not out.exists(),'Fresh output required')
    parent = prepare.check(PARENT)
    linux = json.loads((HERE/'measurement04/linux_provenance.json').read_text())
    pins = dict(linux['files'])
    inputs = [Path(__file__),HERE/'sv39_fixture.c',HERE/'sv39_fixture.S',BASE/'prepare.py',BASE/'run.py',
              ROOT/'verification/coverage/scoped_rv64c_memory.py',
              ROOT/'verification/coverage/build_sv39_masked_unit_fault_preflight.py',
              ROOT/'apps/riscv-tests/isa/rv64uv/vsv39_masked_unit_fault_retry.c',
              PARENT/'provenance.json',CC.resolve(),SPIKE,Path('/usr/bin/cc').resolve()]
    for name in ('startup.S','runtime.c','replay.ld'):
        inputs.append(PARENT/name)
    pins.update({str(p):sha(p) for p in inputs})
    for p,digest in pins.items():
        require(sha(p) == digest,'Input drift: '+p)
    out.mkdir(parents=True)
    save(out/'input_pins.json',pins)
    save(out/'linux_provenance.json',linux)
    prepared = out/'prepared'
    prepared.mkdir()
    for name in ('startup.S','runtime.c','replay.ld'):
        shutil.copyfile(PARENT/name,prepared/name)
    for name in ('sv39_fixture.c','sv39_fixture.S'):
        shutil.copyfile(HERE/name,prepared/name)
    provenance = dict(schema_version=1,vlen=1024,nr_lanes=4,cases=list(NAMES),
                      scope='scenario3 semantic Sv39 derivative, not original Linux execution',
                      parent_provenance_sha256=sha(PARENT/'provenance.json'),
                      parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
                      files={p.name:sha(p) for p in prepared.iterdir()})
    save(prepared/'provenance.json',provenance)
    flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding',
             '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
             '-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror',
             '-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-T',str(prepared/'replay.ld')]
    try:
        hosts = {}
        for variant,name in enumerate(NAMES):
            d = out/name
            d.mkdir()
            run_logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DMT_HOST',f'-DVARIANT={variant}',
                        prepared/'sv39_fixture.c','-o',d/'host'],d/'host.compile.log',timeout=30)
            run_logged([d/'host'],d/'host.stdout',timeout=10)
            hosts[name] = check_host((d/'host.stdout').read_text(),variant)
        for backend in ('soc','spike'):
            d = out/backend
            d.mkdir()
            programs = {}
            for variant,name in enumerate(NAMES):
                elf = d/(name+'.elf')
                command = [CC,*flags,f'-DVARIANT={variant}']
                if backend == 'spike':
                    command.append('-DSPIKE_REFERENCE=1')
                command += [prepared/n for n in ('sv39_fixture.c','sv39_fixture.S','startup.S','runtime.c')]
                command += ['-lgcc','-o',elf]
                run_logged(command,d/(name+'.compile.log'))
                run_logged([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],d/(name+'.dis'))
                nm = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=15)
                symbols = {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
                required = [s for s in SYMBOLS if s != 'tohost' or backend == 'spike']
                if variant == 1:
                    required += ['mt_repair_store','mt_repair_sfence','mt_retry_mret']
                require(all(s in symbols for s in required),'Required ELF symbols missing')
                save(d/(name+'.symbols.json'),{s:symbols[s] for s in required})
                programs[name] = dict(path=str(elf),sha256=sha(elf),cases=[name],pass_markers=['MT_SV39_PASS'])
            save(d/'programs.json',dict(schema_version=1,programs=programs,
                 prepared=str(prepared),provenance_sha256=sha(prepared/'provenance.json'),
                 compiler=dict(path=str(CC),sha256=sha(CC)),
                 backend='spike-htif' if backend == 'spike' else 'vcs-soc'))
        results = {}
        for variant,name in enumerate(NAMES):
            d = out/name
            command = [SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                       '-m2','-l','--log-commits',out/'spike'/(name+'.elf')]
            run_logged(command,d/'spike.stdout',d/'spike.trace',timeout=60)
            s = json.loads((out/'spike'/(name+'.symbols.json')).read_text())
            results[name] = validate_trace((d/'spike.trace').read_text(),s,variant)
            save(d/'validation.json',results[name])
        for p,digest in pins.items():
            require(sha(p) == digest,'Input changed during reference: '+p)
        save(out/'status.json',dict(status='HOST_SPIKE_PASS_NOT_DUT',host=hosts,spike=results,
             RTL_changed=False,VCS_launched=False,Linux_launched=False,
             outputs={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))
        print(json.dumps(results,indent=2))
    except Exception as e:
        save(out/'failure.json',dict(status='REFERENCE_FAILED_NOT_DUT',error=str(e)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['reference'])
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    build(inside(args.out))


if __name__ == '__main__':
    main()
