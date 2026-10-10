"""Twelve independent misalignment landings; software-only formal792 preflight."""
import argparse
import json
import re
import subprocess
from pathlib import Path

from elftools.elf.elffile import ELFFile
import build_scalar_misalign789 as old

ROOT, OUT, sha, save, require = old.ROOT, old.OUT, old.sha, old.save, old.require
shared = old.shared
APP = ROOT/'apps/riscv-tests/isa/rv64uv/scalar_misalign_slot792.c'
BASE = OUT/'scalar-misalign-offline-admitted792-agent-20261008-01'
BASE_SHA = '0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4'
A = 0x2555555003
B = A ^ ((1 << 64)-1)
ADDRESSES = [A,B,A]*4
SLOTS = [k for k in (2,3,6,7) for _ in range(3)]
CHECKS = 89


def traps(text, symbols):
    found=[]; lines=text.splitlines()
    for i,line in enumerate(lines):
        m=re.fullmatch(r'core\s+0:\s+exception\s+(trap_\w+),\s+epc\s+(0x[0-9a-f]+)\s*',line)
        if not m: continue
        require(m[1] in ('trap_load_address_misaligned','trap_store_address_misaligned'), 'Unexpected trap')
        v=re.search(r'\btval\s+(0x[0-9a-f]+)',lines[i+1] if i+1<len(lines) else '')
        require(v is not None, 'Exact trap tval')
        found.append(dict(cause=4 if 'load' in m[1] else 6,pc=int(m[2],16),tval=int(v[1],16)))
    wanted=[dict(cause=6 if i%3==1 else 4,pc=symbols['slot_fault'+str(i)],tval=ADDRESSES[i]) for i in range(12)]
    require(found==wanted, 'Twelve exact fault PCs/causes/full64 tvals')
    return found


def reference(trace, symbols):
    cs=list(shared.parse_spike_commits(trace))
    starts=[i for i,c in enumerate(cs) if c.pc==0x80000000]
    require(len(starts)==1, 'Unique complete entry reference')
    boot=[(0x1000,0x297),(0x1004,0x02028593),(0x1008,0xf1402573),(0x100c,0x0182b283),(0x1010,0x28067)]
    require([(c.pc,c.instruction) for c in cs[:starts[0]]]==boot, 'Exact Spike boot ROM, not omitted program instructions')
    cs=cs[starts[0]:]
    terminal=[i for i,c in enumerate(cs) if any(a==symbols['tohost'] and v is not None for a,v in c.memory_accesses)]
    require(len(terminal)==1 and (symbols['tohost'],1) in cs[terminal[0]].memory_accesses, 'Unique successful tohost')
    for c in cs[terminal[0]+1:]:
        require(c.instruction in (0xa001,0x0000006f) and not c.gpr_writes and not c.memory_accesses
                and not c.vector_writes and not c.fpr_writes, 'Only side-effect-free terminal spin')
    return cs[:terminal[0]+1]


def validate(cs, symbols, ledger):
    memory={}; guard_reads=[]; accesses=[]
    for c in cs:
        require(not c.vector_writes and not c.fpr_writes and c.pc not in (symbols['trap_fail'],symbols['slot_unexpected']), 'No unexpected owner')
        for address,value in c.memory_accesses:
            op=c.instruction&127
            size=1 << ((c.instruction>>12)&3)
            require(op in (3,35) and 0x80000000<=address and address+size<=0x80200000, 'Every runtime access including stack fits frozen 2MiB L2')
            accesses.append((address,size))
            require(value is None or not symbols['slot_guards']<=address<symbols['slot_guards']+16, 'Immutable guards')
            if value is not None: memory[address]=value
            if value is None and address in (symbols['slot_guards'],symbols['slot_guards']+8):
                require(list(c.gpr_writes.values())==[old.GUARDS[(address-symbols['slot_guards'])//8]], 'Independent guard value')
                guard_reads.append(address)
    require(memory.get(symbols['slot_count'])==12 and len(ledger)==12, 'Exact twelve fault owners')
    for i,want in enumerate(ledger):
        p=symbols['slot_records']+40*i
        require([memory.get(p+8*j) for j in range(3)]==[want['cause'],want['pc'],want['tval']], 'Complete independent frame')
        require(type(memory.get(p+24)) is int and memory[p+24]&0x21808==0x1800, 'Trap privilege/MIE/MPRV')
        require(memory.get(p+32)==0x6969696969696969, 'Fault load destination preserved')
    require([memory.get(symbols['slot_page']+8*i) for i in range(16)]==[0x5555555555555555 if i==8 else 0x9696969696969696 for i in range(16)], 'Full page and aligned recovery')
    before=[memory.get(symbols['slot_csr']+8*i) for i in range(7)]
    after=[memory.get(symbols['slot_csr']+56+8*i) for i in range(7)]
    require(all(type(v) is int for v in before) and before==after and before[0]&0x20008==0 and before[5]==0, 'All CSR restoration/Bare')
    require(memory.get(symbols['g75_result'])==CHECKS and memory.get(symbols['g75_result']+4)==memory.get(symbols['num_failed'])==0, 'Exact89 checks, zero failures')
    require(guard_reads==[symbols['slot_guards'],symbols['slot_guards']+8], 'Full guard readback')
    return dict(status='SPIKE_TWELVE_TRAP_GOLD_PASS_NOT_DUT',checks=CHECKS,traps=ledger,
        retired_instructions=len(cs),scalar_memory_accesses=len(accesses),
        runtime_memory_min=min(a for a,_ in accesses),runtime_memory_max_exclusive=max(a+n for a,n in accesses),
        page_bytes=128,frame_bytes=480,CSR_bytes=112,guard_bytes=16,
        predicted_slots=SLOTS,native_slot_allocation_verified=False,coverage_admitted=False)


def elf_shape(path):
    with path.open('rb') as f:
        elf=ELFFile(f); table=elf.get_section_by_name('.symtab')
        names=['tohost','trap_fail','num_failed','g75_result','slot_count','slot_records','slot_csr','slot_page','slot_guards','slot_handler','slot_unexpected','slot_landings','slot_faults','slot_addresses']
        names += ['slot_'+kind+str(i) for kind in ('landing','fault') for i in range(12)]
        symbols={n:table.get_symbol_by_name(n)[0]['st_value'] for n in names}
        segments=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
        require(all(0x80000000<=s['p_paddr'] and s['p_paddr']+s['p_memsz']<0x80200000-4096 for s in segments), 'ELF/BSS separated from stack by at least4KiB')
        def read(addr,n):
            matches=[s for s in segments if s['p_vaddr']<=addr and addr+n<=s['p_vaddr']+s['p_filesz']]
            require(len(matches)==1, 'Unique file-backed machine code')
            s=matches[0]; off=addr-s['p_vaddr']; return s.data()[off:off+n]
        for i,k in enumerate(SLOTS):
            p=symbols['slot_landing'+str(i)]; q=symbols['slot_fault'+str(i)]
            require(q-p==4*k and read(p,4*k)==b'\x13\x00\x00\x00'*k, 'Fixed-width landing NOPs only')
            require(int.from_bytes(read(q,4),'little')==(0x00943023 if i%3==1 else 0x00043e83), 'Exact SD s1 / LD t4 encoding')
        for name,values in [('slot_landings',[symbols['slot_landing'+str(i)] for i in range(12)]),('slot_faults',[symbols['slot_fault'+str(i)] for i in range(12)]),('slot_addresses',ADDRESSES)]:
            require(read(symbols[name],96)==b''.join(v.to_bytes(8,'little') for v in values), 'Exact immutable landing/fault/address table')
        return symbols


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True,type=Path); out=p.parse_args().output.absolute()
    require(out.parent==OUT and not out.exists(), 'Fresh software-only output')
    require(sha(BASE/'admission-manifest.json')==BASE_SHA, 'Exact formal792 seal')
    base=json.loads((BASE/'admission-manifest.json').read_bytes()); require(base['coverage_admitted'] is True, 'Admitted authority')
    status_path=BASE/'status.json'; require(sha(status_path)==base['output_pins'][str(status_path)], 'Status pin')
    require(json.loads(status_path.read_bytes())['aggregate_passed']==792, 'Formal792 population')
    template=OUT/'scalar-misalign789-preflight-agent-20261008-02'
    require(sha(template/'preflight-manifest.json')=='01352b7d72be5c4605faa231ba78d4555ee26788edfedcebb66c326f480ab94f', 'Frozen789 compiler authority')
    tm=json.loads((template/'preflight-manifest.json').read_bytes())
    cp=template/'compile-command.json'; require(sha(cp)==tm['output_pins'][str(cp)], 'Compiler command pin')
    command=json.loads(cp.read_bytes()); require(command[-3]==str(old.APP), 'Exact compiler source substitution')
    command[-3]=str(APP); command[-1]=str(out/'input.elf')
    paths=[APP,Path(__file__).resolve(),Path(old.__file__),Path(__file__).with_name('test_scalar_slot_rotation792.py'),BASE/'admission-manifest.json',status_path,template/'preflight-manifest.json',cp]
    paths += [Path(v) for v in command if Path(v).is_file() and v not in (str(APP),str(out/'input.elf'))]
    book=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    require(sha(book)=='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b', 'Frozen sourcebook')
    frozen=json.loads(book.read_bytes()); source_pins={str(book):sha(book)}
    for name in ('decoder.sv','scoreboard.sv','controller.sv','cva6.sv'):
        f=ROOT/'hardware/deps/cva6/core'/name
        require(sha(f)==frozen[str(f)], 'Frozen allocation/decoder source')
        source_pins[str(f)]=frozen[str(f)]
    decoder=(ROOT/'hardware/deps/cva6/core/decoder.sv').read_text()
    require(re.search(r'riscv::OpcodeOpImm:\s*begin\s*instruction_o.fu\s*=\s*ALU;.*?3\x27b000:\s*instruction_o.op\s*=\s*ariane_pkg::ADD;',decoder,re.S) is not None, '0x13 OpImm ALU/ADD, not FU_NONE')
    pins={str(f):sha(f) for f in paths}; pins=shared.merge_pins(pins,tm['pins']); pins=shared.merge_pins(pins,source_pins); shared.check(pins)
    out.mkdir(); save(out/'compile-command.json',command)
    with (out/'compile.log').open('x') as log: subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols=elf_shape(out/'input.elf')
    require(sha(out/'input.elf') not in set(base['input_pins'].values()), 'New ELF not historical evidence hash')
    command=[str(shared.SPIKE),'--isa='+old.shared_case.SPIKE_ISA,'--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
    save(out/'spike-command.json',command)
    with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace: subprocess.run(command,stdout=stdout,stderr=trace,check=True,timeout=60)
    ledger=traps((out/'spike.trace').read_text(),symbols); validation=validate(reference(out/'spike.trace',symbols),symbols,ledger)
    save(out/'spike-validation.json',validation); shared.check(pins)
    save(out/'preflight-manifest.json',dict(status='SLOT_ROTATION792_PREFLIGHT_PASS_NOT_DUT',baseline=792,baseline_seal=BASE_SHA,symbols=symbols,
        input_elf=str(out/'input.elf'),pins=pins,output_pins={str(f):sha(f) for f in out.iterdir() if f.is_file()},validation=validation,
        allocation_contract=dict(NOP='0x13: OpcodeOpImm ALU/ADD; no FU_NONE assumption',accepted='decoded_valid && ack && !flush_unissued',flush_priority='flush_i overrides pointer_n=0; same-cycle capture required',actual_slots_verified=False),
        VCS_authorized=False,coverage_admitted=False,RTL_changed=False))
    print(json.dumps(dict(output=str(out),seal=sha(out/'preflight-manifest.json'),validation=validation)))


if __name__=='__main__': main()
