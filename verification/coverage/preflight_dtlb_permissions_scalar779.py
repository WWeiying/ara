"""Scalar-ISA successor: unchanged DTLB oracle, frozen predecessors, no EDA."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import review_dtlb_permissions779 as audit
from ara_verify.spike_trace import parse_spike_commits

p = audit.prior
APP = p.ROOT / 'apps/riscv-tests/isa/rv64uv/vdtlb_permissions_matrix.c'
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'g75_trap', 'trap_fail',
           'dpa_root', 'dpa_mid', 'dpa_leaf', 'dpa_observed', 'dpa_probe',
           'dpa_traps', 'dpa_count', 'dpa_saved', 'dpa_restored', 'dpa_load', 'dpa_store',
           'dpa_enable', 'dpa_disable', 'dpa_clear_mprv', 'dpa_handler_begin', 'dpa_handler_end', '_end')
SENTINEL = 0xfedcba9876543210
STORE = 0x123456789abcdef0


def validate(commits, symbols):
    require = p.require
    s = symbols
    require(commits and not any(c.vector_writes or c.fpr_writes or c.pc == s['trap_fail']
                               for c in commits), 'Unexpected vector/FP/fatal trap')
    writes, histories, reads = {}, {}, {}
    for c in commits:
        for a, v in c.memory_accesses:
            if v is not None:
                writes[a] = v
                histories.setdefault(a, []).append(v)
            else:
                reads.setdefault(a, []).append(c)
    require([writes.get(s['g75_result']), writes.get(s['g75_result']+4),
             writes.get(s['num_failed']), writes.get(s['tohost'])] == [8378, 0, 0, 1],
            'Exact8378 checks and success terminal')
    original = writes[s['dpa_saved']]
    require(original & 0x20000 == 0 and writes[s['dpa_saved']+8] == 0, 'Bare initial state')
    for i in range(8):
        require(writes[s['dpa_saved']+8*i] == writes[s['dpa_restored']+8*i],
                'Full CSR restoration')
    expected = [p.gold(17*i) for phase in range(3) for i in range(16) for repeat in range(2)]
    require([writes[s['dpa_observed']+8*i] for i in range(96)] == expected, '96 fill load gold')
    rows = audit.cases()
    load_faults, store_faults = 0, 0
    for k, row in enumerate(rows):
        cause, store = row['mcause'], row['operation'] == 'store'
        value = STORE if store else SENTINEL if cause else p.gold(0)
        expected_row = [value, int(bool(cause)), cause,
                        s['dpa_store' if store else 'dpa_load'] if cause else 0,
                        p.address(0) if cause else 0, original,
                        STORE if store and not cause else p.gold(0),
                        p.pte(p.pa(0), row['pte_flags'])]
        require([writes[s['dpa_probe']+64*k+8*i] for i in range(8)] == expected_row,
                f'Probe{k} exact value/cause/site/tval/status/PTE/memory gold')
        if cause:
            idx = load_faults + store_faults
            require([writes[s['dpa_traps']+32*idx+8*i] for i in range(3)] == expected_row[2:5],
                    'Independent trap history')
            status = writes[s['dpa_traps']+32*idx+24]
            require(status & 0x21800 == 0x1800, 'Handler M-mode, MPRV cleared')
            if store: store_faults += 1
            else: load_faults += 1
    require(writes[s['dpa_count']] == 5 and (load_faults,store_faults) == (3,2), 'Five exact traps')
    table = {s['dpa_root']+16:p.pte(0x80000000,0xcf)}
    for i in range(16):
        vpn = p.shared.vpn(0,i)
        table[s['dpa_root']+8*(vpn>>18)] = p.pte(s['dpa_mid'],1)
        table[s['dpa_mid']+8*((vpn>>9)&511)] = p.pte(s['dpa_leaf'],1)
        table[s['dpa_leaf']+8*(vpn&511)] = p.pte(p.pa(17*i),0x47 if i==0 else 0xc7)
    for name in ('dpa_root','dpa_mid','dpa_leaf'):
        require(s[name] % 4096 == 0, 'Aligned page table')
        for i in range(512):
            # Loader-zeroed unused BSS is not spuriously represented as an architectural store.
            require(writes.get(s[name]+8*i,0) == table.get(s[name]+8*i,0), 'Final1536 PTE image')
    for i in range(16):
        flags = [0xc7,0x79,0xc7] + ([r['pte_flags'] for r in rows] if i==0 else [])
        a = s['dpa_leaf']+8*(p.shared.vpn(0,i)&511)
        require(histories[a] == [0]+[p.pte(p.pa(17*i),f) for f in flags], 'Exact leaf write history')
        for j in range(512):
            address = p.pa(17*i)+8*j
            expected_history = [p.word(17*i,j)]
            # The translated store is logged at VA; its PA effect is independently read back.
            if i==0 and j==1: expected_history += [p.gold(0)]
            require(histories.get(address) == expected_history, 'Full physical guard/no fault stores')
            expected_reads = [p.word(17*i,j)]
            if i==0 and j==1:
                expected_reads = [p.gold(0)]*6+[STORE]+[p.gold(0)]*3
            require([list(c.gpr_writes.values()) for c in reads.get(address,[])] ==
                    [[value] for value in expected_reads], 'Full physical guard reread values')
    allowed = {p.pa(17*i)+8*j for i in range(16) for j in range(512)}
    require(not any(0x80080000 <= a < 0x80180000 and a not in allowed for a in writes),
            'Unexpected physical data-window stores')
    require(all(writes.get(s['g75_trap']+8*i)==0 for i in range(3)), 'Fatal trap guards')
    loads = [c for c in commits if c.pc==s['dpa_load']]
    stores = [c for c in commits if c.pc==s['dpa_store']]
    require(len(loads)==107 and len(stores)==1, '107 retired loads plus one retired store')
    ordered = expected[:32] + expected[32:64] + [p.gold(0)] + expected[64:]
    for k,row in enumerate(rows):
        if not row['cold_full_sfence']: ordered.append(p.gold(0))
        if row['operation']=='load' and not row['mcause']: ordered.append(p.gold(0))
    require([list(c.gpr_writes.values()) for c in loads] == [[v] for v in ordered],
            'Exact per-instruction load results')
    require(all(p.shared.is_ld_zero(c.instruction) and len(c.memory_accesses)==1 for c in loads),
            'Labeled load instruction/one memory access')
    fill_va = [p.address(i) for phase in range(3) for i in range(16) for repeat in range(2)]
    fill_va.insert(64,p.address(0))
    require([c.memory_accesses[0][0] for c in loads] == fill_va+[p.address(0)]*10,
            'Exact translated VA owners')
    require(tuple(stores[0].memory_accesses)==((p.address(0),STORE),), 'Exact legal store VA/value')
    def setting(priv, summ, mxr):
        return (original & ~0xe188a) | 0x20000 | (priv<<11) | (summ<<18) | (mxr<<19)
    status_gold=[]
    for phase in range(3):
        status_gold += [setting(1,phase==1,phase==1)]*32
        if phase==1: status_gold.append(setting(1,1,1))
    for row in rows:
        if not row['cold_full_sfence']: status_gold.append(setting(1,1,1))
        status_gold.append(setting(int(row['effective_privilege']=='S'),row['SUM'],row['MXR']))
    require([c.csr_writes.get(0x300) for c in commits if c.pc==s['dpa_enable']] == status_gold and
            [c.csr_writes.get(0x300) for c in commits if c.pc==s['dpa_disable']] == [original]*113,
            'Exact113 enable/disable MPRV/MPP/SUM/MXR settings')
    require(len([c for c in commits if c.pc==s['dpa_clear_mprv']])==5, 'Five handler MPRV clears')
    require([c.csr_writes[0x180] for c in commits if 0x180 in c.csr_writes] ==
            [(8<<60)|(1<<44)|(s['dpa_root']>>12),0], 'Exact ASID1/SATP lifecycle')
    active=False
    translated_owners=[]
    for c in commits:
        if active and c.memory_accesses:
            require(c.pc in (s['dpa_load'],s['dpa_store']), 'Hidden translated stack/data access')
            translated_owners.append(c.pc)
        if 0x300 in c.csr_writes:
            active=bool(c.csr_writes[0x300]&0x20000)
    require(not active and len(translated_owners)==108, 'Exact retired MPRV memory windows')
    return dict(p.shared.architecture.reference_counts(commits,s), software_checks=8378,
                complete_physical_guard_bytes=65536, full_pte_slots=1536,
                attempted_translated_accesses=113, retired_translated_loads=107,
                retired_translated_stores=1, page_fault_loads=3, page_fault_stores=2,
                total_spike_retirements=len(commits), native_replacement_coverage_proven=False)


def scalar_isa_evidence(text):
    decoded=[]
    for match in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)',text,re.M):
        address, encoded, mnemonic=match.groups()
        word=int(encoded,16)
        p.require(len(encoded) in (4,8), 'Exact 16/32-bit instruction decoding')
        p.require(not mnemonic.startswith('v'), 'Vector mnemonic forbidden')
        if word & 3 == 3:
            p.require(len(encoded)==8, 'Truncated 32-bit encoding')
            opcode=word & 0x7f
            p.require(opcode!=0x57, 'OP-V encoding forbidden')
            if opcode in (0x07,0x27):
                p.require((word>>12)&7 in (1,2,3), 'Vector/reserved memory encoding forbidden')
        else:
            p.require(len(encoded)==4, 'Noncanonical compressed encoding')
        decoded.append((int(address,16),word,mnemonic))
    p.require(decoded, 'Empty disassembly is not evidence')
    return dict(decoded_instructions=len(decoded),OP_V_encodings=0,
                vector_memory_encodings=0,vector_mnemonics=0,
                software_march='rv64gc_zfh',abi='lp64d',
                Spike_and_frozen_hardware_ISA_unchanged=True)


def prepare(out):
    p.require(not out.exists() and out.is_relative_to(p.OUT), 'Fresh verification output')
    review = audit.review()
    pins = dict(review['pins'])
    command = json.loads(p.shared.TEMPLATE.read_bytes())
    old = str(p.ROOT / 'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    p.require(command.count(old)==1, 'Exact frozen compile template')
    command = [str(APP) if x==old else str(out/'input.elf') if x.endswith('/input.elf') else x for x in command]
    march = [i for i,x in enumerate(command) if x.startswith('-march=')]
    p.require(len(march)==1 and command[march[0]]=='-march=rv64gcv_zfh_zvfh',
              'Exact predecessor software ISA')
    command[march[0]]='-march=rv64gc_zfh'
    p.require(command.count('-mabi=lp64d')==1 and
              command.count('-fno-vectorize')==1 and command.count('-fno-slp-vectorize')==1,
              'Unchanged ABI and single existing scalar optimization controls')
    for path in (APP,Path(__file__),p.shared.TEMPLATE,Path(command[0]),p.build.SPIKE,
                 p.build.LLVM/'llvm-readelf',p.build.LLVM/'llvm-objdump',
                 p.ROOT/'verification/tests/gap75_start.S',p.ROOT/'verification/tests/gap75.ld',
                 p.ROOT/'verification/coverage/dtlb_ppn_swap_probe.tcl',
                 Path(__file__).with_name('preflight_dtlb_permissions779.py'),
                 Path(__file__).with_name('test_preflight_dtlb_permissions_scalar779.py')):
        pins[str(path)]=p.life.digest(path)
    for directory in ('apps/riscv-tests/isa/macros','apps/riscv-tests/env','apps/common','verification/ara_verify'):
        for path in (p.ROOT/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts: pins[str(path)]=p.life.digest(path)
    p.life.check(pins)
    out.mkdir()
    try:
        p.life.save(out/'source-review.json',review)
        p.life.save(out/'compile-command.json',command)
        with (out/'build.log').open('x') as f:
            subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        s={name:p.build._elf_symbol(out/'input.elf',p.build.LLVM/'llvm-readelf',name) for name in SYMBOLS}
        p.require(s['_end']<0x80080000 and s['tohost']==0x80001000,'Exact ELF physical fit')
        from elftools.elf.elffile import ELFFile
        with (out/'input.elf').open('rb') as f:
            elf=ELFFile(f)
            p.require(elf['e_entry']==0x80000000 and all(
                0x80000000 <= segment['p_paddr'] and
                segment['p_paddr']+segment['p_memsz'] <= 0x80080000
                for segment in elf.iter_segments() if segment['p_type']=='PT_LOAD'),
                'Exact ELF entry/segments below guard window')
        with (out/'disassembly.txt').open('x') as f:
            subprocess.run([str(p.build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],stdout=f,check=True,timeout=30)
        p.require(not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+v\S+',
                                (out/'disassembly.txt').read_text(),re.M),
                  'Software must compile to scalar-only instructions')
        isa_evidence=scalar_isa_evidence((out/'disassembly.txt').read_text())
        p.life.save(out/'scalar-isa-evidence.json',isa_evidence)
        spike=[str(p.build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
               '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
        p.life.save(out/'spike-command.json',spike)
        with (out/'spike.trace').open('x') as f:
            subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        counts=validate(parse_spike_commits(out/'spike.trace'),s)
        p.life.check(pins)
        outputs={str(path):p.life.digest(path) for path in out.iterdir() if path.is_file()}
        p.life.save(out/'preflight.json',dict(status='SPIKE_SOURCE_PTE_CSR_TRAP_GOLD_PASS_NOT_DUT',
                    input_pins=pins,output_pins=outputs,symbols=s,counts=counts,
                    formal779_seal=p.BASE_SHA,ppn780_union_bound=True,
                    scalar_isa_evidence=isa_evidence,
                    EDA_launched=False,coverage_admitted=False))
        print('PREFLIGHT_PASS',out,p.life.digest(out/'preflight.json'),counts,flush=True)
    except Exception as exc:
        p.life.save(out/'failure.json',dict(reason=str(exc),coverage_admitted=False))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.absolute())
