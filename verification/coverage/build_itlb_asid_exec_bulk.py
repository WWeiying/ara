"""Scalar-only bulk ITLB oracle; file-backed zero code pages, no VCS launch."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
from types import FunctionType, SimpleNamespace
from elftools.elf.elffile import ELFFile
import build_itlb_asid_exec_linear as linear

old=linear.old
life,require,ROOT,OUT=old.life,old.require,old.ROOT,old.OUT
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vitlb_asid_exec_matrix_bulk.c'
HEADER=APP.with_name('itlb_bulk_scalar.h')
PRIOR=OUT/'itlb-asid-exec-linear-preflight-771-agent-20261007-01/preflight.json'
PRIOR_SHA='e1ac19e6064d834f4d8b2501d1f3ced7eefc7721571e43c5f86e58691ebe6545'
GUARD,CHECKS,architecture=old.GUARD,old.CHECKS,old.architecture
tables,address,codeword=old.tables,old.address,old.codeword
DECL='volatile unsigned long itm_code[16][512] __attribute__((aligned(4096)));'
NEW_DECL='volatile unsigned long itm_code[16][512] __attribute__((aligned(4096), section(".data.itlb_code"))) = {{0}};'
INIT='''  for (unsigned entry=0;entry<16;entry++)
    for (unsigned word=0;word<512;word++) itm_code[entry][word]=codeword(entry,word);'''
NEW_INIT='''  for (unsigned entry=0;entry<16;entry++)
    itlb_init_page(itm_code[entry],guard,codeword(entry,8),codeword(entry,9));'''
READ='''  for (unsigned entry=0;entry<16;entry++) for (unsigned word=0;word<512;word++)
    check(itm_code[entry][word],codeword(entry,word),&checks);'''
NEW_READ='''  for (unsigned entry=0;entry<16;entry++)
    num_failed += itlb_check_page(itm_code[entry],guard,codeword(entry,8),codeword(entry,9),&checks);'''


def transform(text):
    for a in ('#include <stdint.h>',DECL,INIT,READ):
        require(text.count(a)==1,'Exact linear source contract required')
    return text.replace('#include <stdint.h>','#include <stdint.h>\n#include "itlb_bulk_scalar.h"').replace(
        DECL,NEW_DECL).replace(INIT,NEW_INIT).replace(READ,NEW_READ)


def source_contract():
    prior=life.read_bound(PRIOR,PRIOR_SHA)
    paths=(linear.APP,Path(linear.__file__).resolve())
    for path in paths:
        require(prior['input_pins'][str(path)]==life.digest(path),'Frozen linear predecessor differs')
    require(APP.read_text()==transform(linear.APP.read_text()),'Change outside exact bulk source transform')
    proof,pins=linear.source_contract()
    book=life.read_bound(old.shared.SOURCE,old.shared.SOURCE_SHA)
    loader=ROOT/'hardware/deps/cva6/corev_apu/tb/dpi/elfloader.cc'
    tb=ROOT/'hardware/tb/ara_tb.sv'
    for path in (loader,tb):
        require(life.digest(path)==book[str(path)],'Frozen preload source differs')
        pins=life.merge_pins(pins,{str(path):book[str(path)]})
    cpp=re.sub(r'\s+','',loader.read_text())
    for token in ('if(ph[i].p_type==PT_LOAD&&ph[i].p_memsz)',
        'write(ph[i].p_paddr,ph[i].p_filesz,(uint8_t*)buf+ph[i].p_offset);'):
        require(token in cpp,'Frozen file-backed loader semantics differ')
    start=ROOT/'verification/tests/gap75_start.S'
    require('la t0, __bss_start' in start.read_text() and 'la t1, __bss_end' in start.read_text(),
        'CRT bounded BSS clearing contract differs')
    for path in (*paths,PRIOR,HEADER,start,ROOT/'verification/tests/itlb_bulk_scalar_host.c',
        Path('/usr/bin/gcc'),Path(__file__).with_name('test_build_itlb_asid_exec_bulk.py')):
        pins=life.merge_pins(pins,{str(path):PRIOR_SHA if path==PRIOR else life.digest(path)})
    return dict(proof,bulk_change='exact three source substitutions plus scalar header',
        code_initial_bytes='65536 file-backed PROGBITS zero bytes, not runtime CRT stores',
        code_initialization_writes=8192,code_guard_reads=8192,fail_count='one per mismatching word, summed exactly',
        stimulus_unchanged=True,checks_unchanged=10966,previous_timeout_retained=True),pins


def elf_contract(path):
    with path.open('rb') as f:
        elf=ELFFile(f)
        require(elf.elfclass==64 and elf.little_endian and elf['e_machine']=='EM_RISCV' and
            elf['e_entry']==0x80000000,'Exact ELF64 fixed boot required')
        symtab=elf.get_section_by_name('.symtab')
        def symbol(name):
            matches=symtab.get_symbol_by_name(name) or []
            require(len(matches)==1,'Unique ELF symbol required: '+name)
            return matches[0]
        code=symbol('itm_code');addr=code['st_value'];size=code['st_size']
        require(size==65536 and addr%4096==0 and code['st_info']['type']=='STT_OBJECT',
            'Exact16 aligned code pages required')
        section=elf.get_section(code['st_shndx'])
        require(section['sh_type']=='SHT_PROGBITS' and section['sh_flags']&3==3 and
            not section['sh_flags']&4,'Code data must be file-backed allocated writable PROGBITS')
        offset=addr-section['sh_addr']
        require(0<=offset and offset+size<=section['sh_size'],'Code object outside section')
        data=section.data()[offset:offset+size]
        require(data==bytes(size),'All65536 code initial file bytes must be zero')
        segments=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and
            s['p_vaddr']<=addr and addr+size<=s['p_vaddr']+s['p_filesz']]
        require(len(segments)==1,'Code must be completely file-backed by exactly one PT_LOAD')
        segment=segments[0]
        require(segment['p_paddr']==segment['p_vaddr'] and segment['p_paddr']%16==0 and
            segment['p_offset']+addr-segment['p_vaddr']==section['sh_offset']+offset,
            'VCS physical load/file offset mapping differs')
        lo,hi=symbol('__bss_start')['st_value'],symbol('__bss_end')['st_value']
        require(lo<=hi and (addr+size<=lo or addr>=hi),'Code array must be outside CRT BSS range')
        return dict(address=addr,size=size,section=section.name,type=section['sh_type'],
            file_offset=section['sh_offset']+offset,initial_bytes_sha256=hashlib.sha256(data).hexdigest(),
            PT_LOAD_paddr=segment['p_paddr'],PT_LOAD_filesz=segment['p_filesz'],
            bss_start=lo,bss_end=hi,CRT_excluded_bytes=65536,not_a_runtime_initial_store=True,
            actual_RTL_preload_readback_pending=True)


def reference_interval(commits):
    starts=[i for i,c in enumerate(commits) if c.pc==0x80000000]
    require(len(starts)==1,'Exactly one architectural fixed entry required')
    ends=[i for i,c in enumerate(commits) if (0x80001000,1) in c.memory_accesses]
    require(len(ends)==1 and ends[0]>=starts[0],'Exactly one successful tohost after entry required')
    return commits[starts[0]:ends[0]+1]


def validate(commits,symbols):
    view=SimpleNamespace(validate=_base_validate,tables=old.tables)
    impl=FunctionType(linear.validate.__code__,dict(linear.validate.__globals__,old=view))
    return impl(commits,symbols)


def prepare(output):
    host_source=ROOT/'verification/tests/itlb_bulk_scalar_host.c'
    source_contract()
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'host'
        subprocess.run(['/usr/bin/gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            str(host_source),'-o',str(exe)],check=True,timeout=30)
        host=subprocess.run([str(exe)],check=True,timeout=10,capture_output=True,text=True)
        require(host.stdout=='ITLB_BULK_HOST_EXACT8192_STORE_READ_512_SINGLE_FAULTS_AND_512_MULTI_FAILS_PASS\n',
            'Exact instrumented scalar header evidence required')
    def checked_validate(commits,symbols):
        contract=elf_contract(output/'input.elf')
        require(contract['address']==symbols['itm_code'],'ELF/source symbol mismatch')
        path=output/'elf-preload-proof.json'
        if not path.exists():life.save(path,contract)
        host_path=output/'host-header-proof.json'
        if not host_path.exists():life.save(host_path,dict(status=host.stdout.strip(),
            code_stores=8192,code_reads=8192,single_fault_positions=512,multiple_fault_count=512,
            compiler='/usr/bin/gcc',source=str(host_source),source_sha=life.digest(host_source)))
        return validate(commits,symbols)
    namespace=dict(old.__dict__,APP=APP,SYMBOLS=old.SYMBOLS+('itm_leaf_gold',),
        __file__=str(Path(__file__).resolve()),source_contract=source_contract,validate=checked_validate)
    FunctionType(old.prepare.__code__,namespace,argdefs=old.prepare.__defaults__)(output)
    q=life.read_bound(output/'preflight.json',life.digest(output/'preflight.json'))
    count=q['counts']['matched_instructions']
    require(count<150000,'Measured reference still too expensive; no VCS authorization')
    ref=reference_interval(old.build.parse_spike_commits(output/'spike.trace'))
    require(len(ref)==count,'Complete exact-entry reference count differs')
    life.save(output/'bulk-workload.json',dict(status='SPIKE_BULK_SCALAR_PREFLIGHT_NOT_RTL',
        old_instructions=253120,new_instructions=count,removed_instructions=253120-count,
        target_below100k=count<100000,software_checks=10966,trap_count=48,
        main_code_stores=8192,guard_reads=8192,code_CRT_stores=0,
        reference_boot_commits_excluded_explicitly=True,preflight_seal=life.digest(output/'preflight.json'),
        VCS_launched=False,coverage_admitted=False))
    print('BULK_PREFLIGHT_READY',life.digest(output/'preflight.json'),q['counts'],flush=True)


def _base_validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits),'Unexpected vector/trap fail')
    writes = {}; phases = []; target = []; histories = {}
    allpcs = {(address(p,e)+off)&((1<<64)-1): (p,e,off) for p in range(2) for e in range(16) for off in (0,4,8)}
    # Phases0 and2 share PCs; order is checked below rather than dictionary counts.
    for c in commits:
        if c.pc in allpcs: target.append(c)
        for a,v in c.memory_accesses:
            if v is None: continue
            writes[a] = v
            histories.setdefault(a,[]).append(v)
            if a == symbols['itm_phase']:
                if len(histories[a]) == 1:
                    require(v == 0,'CRT phase initialization differs')
                    continue
                require(v == len(phases) and v < 3,'Phase order differs')
                gold = tables(symbols,v)
                require(all(writes.get(symbols[n]+8*i) == values[i]
                    for n,values in zip(('itm_root','itm_mid','itm_leaf'),gold) for i in range(512)),
                    'Complete phase PTE image differs')
                phases.append(v)
    require(phases == [0,1,2] and len(target) == 144,'Missing/extra exact thunk instructions')
    for index,c in enumerate(target):
        p,e,off = index//48,(index%48)//3,(index%3)*4
        insn = ((0x100+e)<<20)|0x513 if off == 0 else 0x00150513 if off == 4 else 0x73
        require(c.pc == address(p,e)+off and c.instruction == insn and not c.memory_accesses and
                c.gpr_writes == ({10:0x100+e} if off == 0 else {10:0x101+e} if off == 4 else {}),
                'Exact S-mode PC/opcode/result differs')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
             writes.get(symbols['num_failed']),writes.get(symbols['tohost'])] == [CHECKS,0,0,1],
            'Complete selfcheck terminal differs')
    original = [writes.get(symbols['itm_original']+8*i) for i in range(3)]
    require(all(v is not None for v in original) and original[1] == 0,'Original CSR missing/nonbare')
    require([writes.get(symbols['itm_restored']+8*i) for i in range(3)] == original,'CSR restoration differs')
    for p in range(3):
        satp = (8<<60)|((0xaaaa if p == 1 else 0x5555)<<44)|(symbols['itm_root']>>12)
        require([writes.get(symbols['itm_csr']+8*(p*6+i)) for i in range(6)] ==
                [satp,original[0],symbols['itm_handler'],0,0,0],'Phase CSR/guards differ')
        for e in range(16):
            index=p*16+e
            require(writes.get(symbols['itm_observed']+8*index) == 0x101+e and
                [writes.get(symbols['itm_ledger']+8*(3*index+i)) for i in range(3)] ==
                [9,address(p,e)+8,0],'Trap ledger/result differs')
    for e in range(16):
        for w in range(512):
            a=symbols['itm_code']+4096*e+8*w
            require(writes.get(a) == codeword(e,w),'Full executable code/guard image differs')
            require(histories[a] == [codeword(e,w)],'Code missing/redundant/changed runtime initialization after file-backed zero preload')
    # Initial zero bytes are proved by elf_contract; they are not fabricated
    # as retired stores. Main must write each word once, then read every guard.
    # Every guard is actually read after all S-mode execution, not merely initialized.
    reads = {a for c in commits for a,v in c.memory_accesses if v is None}
    require(all(symbols['itm_code']+4096*e+8*w in reads for e in range(16) for w in range(512)),
            'Code guard readback incomplete')
    require(not any(0xd0000000 <= a < 0xd0001000 for a in writes),'Forbidden CTRL write')
    return architecture.reference_counts(commits,symbols)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.absolute())
