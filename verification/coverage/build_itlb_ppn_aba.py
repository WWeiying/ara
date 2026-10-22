"""Two physical pages, sixteen accepted ITLB slots; software preflight only."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
import build_itlb_asid_exec as prior
import build_itlb_asid_exec_bulk as bulk

life, build, architecture = prior.life, prior.build, prior.architecture
ROOT, OUT, require = prior.ROOT, prior.OUT, prior.require
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vitlb_ppn_aba.c'
LINK = ROOT/'verification/tests/itlb_ppn_aba.ld'
BASE = OUT/'scalar-misalign-offline-admitted792-agent-20261008-01'
BASE_SHA = '0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4'
PAGES = (0x80055000, 0x801aa000)
CHECKS = 3846
SYMBOLS = tuple(n for n in prior.SYMBOLS if n != 'itm_code') + ('ipa_page_a','ipa_page_b','__bss_start','__bss_end','_end')


def address(phase, entry):
    require(phase in range(3) and entry in range(16), 'Invalid phase/entry')
    return prior.address(0, entry)


def codeword(page, word):
    if word == 8:
        return (0x00150513 << 32) | ((0x2aa if page else 0x155) << 20) | 0x513
    if word == 9:
        return (prior.GUARD & 0xffffffff00000000) | 0x73
    return prior.GUARD


def tables(symbols, phase):
    pte = lambda a, f: ((a >> 12) << 10) | f
    root, mid, leaf = [0]*512, [0]*512, [0]*512
    root[2] = pte(0x80000000, 0xcf)
    for e in range(16):
        v = prior.shared.vpn(0, e)
        root[v >> 18] = pte(symbols['itm_mid'], 1)
        mid[(v >> 9) & 511] = pte(symbols['itm_leaf'], 1)
        leaf[v & 511] = pte(PAGES[phase == 1], 0x4b)
    return root, mid, leaf


def elf_contract(path):
    with path.open('rb') as f:
        e = ELFFile(f)
        require(e.elfclass == 64 and e.little_endian and e['e_entry'] == 0x80000000
                and e['e_machine'] == 'EM_RISCV', 'Fixed ELF64 boot required')
        st = e.get_section_by_name('.symtab')
        symbols = {}
        for n in SYMBOLS:
            found = st.get_symbol_by_name(n) or []
            require(len(found) == 1, 'Missing/duplicate ELF symbol '+n)
            symbols[n] = found[0]['st_value']
        require(symbols['_end'] < PAGES[0] and symbols['tohost'] == 0x80001000,
                'Normal program overlaps reserved page/boot contract')
        pages = []
        for n, addr in zip(('ipa_page_a','ipa_page_b'), PAGES):
            sym = st.get_symbol_by_name(n)[0]; section = e.get_section(sym['st_shndx'])
            require(sym['st_value'] == addr and sym['st_size'] == 4096 and
                    section['sh_type'] == 'SHT_PROGBITS', 'Exact file-backed page required')
            raw = section.data()[addr-section['sh_addr']:addr-section['sh_addr']+4096]
            require(raw == prior.GUARD.to_bytes(8,'little')*512, 'Initial page guard bytes differ')
            for sec in e.iter_sections():
                if sec['sh_flags'] & 2 and sec['sh_size'] and sec.name != section.name:
                    require(sec['sh_addr']+sec['sh_size'] <= addr or sec['sh_addr'] >= addr+4096,
                            'Allocated section overlaps physical code page')
            segments = [s for s in e.iter_segments() if s['p_type']=='PT_LOAD'
                        and s['p_vaddr']<=addr and addr+4096<=s['p_vaddr']+s['p_filesz']]
            require(len(segments)==1 and segments[0]['p_paddr']==segments[0]['p_vaddr'],
                    'Unique identity file-backed physical load required')
            require(addr+4096 < 0x801f0000, 'Stack reserve overlap')
            pages.append(dict(symbol=n, address=addr, size=4096, section=section.name))
        for n in ('itm_root','itm_mid','itm_leaf'):
            require(symbols[n]%4096==0 and symbols[n]+4096<=PAGES[0], 'Page table overlap')
        return symbols, dict(pages=pages, bss=[symbols['__bss_start'],symbols['__bss_end']],
                             stack_reserved=[0x801f0000,0x80200000], physical_load_pending_DUT=True)


def source_contract():
    book = life.read_bound(prior.shared.SOURCE, prior.shared.SOURCE_SHA)
    pins = {str(prior.shared.SOURCE):prior.shared.SOURCE_SHA}
    rels = ('hardware/deps/cva6/core/cva6_mmu/cva6_tlb.sv',
            'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
            'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
            'hardware/tb/ara_tb.sv','hardware/tb/ara_testharness.sv',
            'hardware/deps/cva6/corev_apu/tb/dpi/elfloader.cc')
    for rel in rels: pins[str(ROOT/rel)] = book[str(ROOT/rel)]
    life.check(pins)
    text = re.sub(r'\s+','',(ROOT/rels[0]).read_text())
    for token in ('update_i.valid&replace_en[i]&!lu_hit_o','content_n[i].pte=update_i.content;',
                  "content_q<='{default:0};", "tags_n[i].valid=1'b0;"):
        require(token in text, 'Frozen TLB driver/reset/flush differs')
    app = APP.read_text()
    require(app.count('sfence.vma zero,zero') == 2 and 'fence.i' in app and
            '0x801aa000ul:0x80055000ul' in app, 'A/B/A or complete flush/fence missing')
    return dict(scope=prior.SCOPE, checksum='817233724', physical_pages=PAGES,
                all_ASIDs_and_global_flushed=True, reset_not_used=True, source_pins=pins,
                candidate_low_PPN_bits=list(range(9)), actual_entry_ownership_pending=True), pins


def validate(commits, symbols):
    writes, history, reads, phases, target = {}, {}, set(), [], []
    pcs = {address(0,e)+o for e in range(16) for o in (0,4,8)}
    for c in commits:
        require(not c.vector_writes and c.pc != symbols['trap_fail'], 'Unexpected vector/trap fail')
        if c.pc in pcs: target.append(c)
        for a,v in c.memory_accesses:
            if v is None: reads.add(a); continue
            writes[a]=v; history.setdefault(a,[]).append(v)
            if a==symbols['itm_phase'] and len(history[a])>1:
                require(v==len(phases) and v<3, 'Phase order differs')
                gold=tables(symbols,v)
                require(all(writes.get(symbols[n]+8*i,0)==values[i]
                        for n,values in zip(('itm_root','itm_mid','itm_leaf'),gold) for i in range(512)),
                        'Complete phase PTE image differs')
                phases.append(v)
    require(phases==[0,1,2] and len(target)==144, 'Missing/extra phase or S-mode PC')
    for i,c in enumerate(target):
        p,e,o=i//48,(i%48)//3,(i%3)*4
        value=0x2aa if p==1 else 0x155
        insn=(value<<20)|0x513 if o==0 else 0x00150513 if o==4 else 0x73
        gpr={10:value} if o==0 else {10:value+1} if o==4 else {}
        require((c.pc,c.instruction,c.gpr_writes,c.memory_accesses)==(address(p,e)+o,insn,gpr,()),
                'Physical A/B thunk PC/opcode/return differs')
    require([writes.get(symbols[n]) for n in ('g75_result','num_failed','tohost')]==[CHECKS,0,1]
            and writes.get(symbols['g75_result']+4)==0, 'Selfcheck terminal differs')
    original=[writes.get(symbols['itm_original']+8*i) for i in range(3)]
    require(None not in original and original[1]==0 and
            [writes.get(symbols['itm_restored']+8*i) for i in range(3)]==original, 'CSR restoration differs')
    for p in range(3):
        satp=(8<<60)|((0xaaaa if p==1 else 0x5555)<<44)|(symbols['itm_root']>>12)
        require([writes.get(symbols['itm_csr']+8*(6*p+i)) for i in range(6)]==
                [satp,original[0],symbols['itm_handler'],0,0,0], 'Phase CSR differs')
        for e in range(16):
            i=p*16+e
            require(writes.get(symbols['itm_observed']+8*i)==(0x2ab if p==1 else 0x156)
                    and [writes.get(symbols['itm_ledger']+8*(3*i+j)) for j in range(3)]==
                    [9,address(p,e)+8,0], 'Ordered exact trap ledger differs')
    first_fetch=next(i for i,c in enumerate(commits) if c.pc in pcs)
    for page,base in enumerate(PAGES):
        for w in range(512):
            a=base+8*w
            initial=[c for c in commits[:first_fetch] if (a,None) in c.memory_accesses]
            require(initial and a in reads, 'Actual preload/guard read missing')
            expected=[codeword(page,w)] if w in (8,9) else []
            require(history.get(a,[])==expected, 'Unexpected code write/guard corruption')
    return architecture.reference_counts([c for c in commits if c.instruction!=0x73],symbols)


def reference(path, symbols):
    text=path.read_text()
    expected=[('trap_supervisor_ecall',address(p,e)+8) for p in range(3) for e in range(16)]
    require([(k,int(a,16)) for k,a in re.findall(r'exception (\w+), epc (0x[0-9a-f]+)',text)]==expected,
            'Exact48 raw reference exception kind/PC/order required')
    cs=bulk.reference_interval(build.parse_spike_commits(path));expanded=[];index=0
    for c in cs:
        if c.pc==symbols['itm_handler']:
            require(index<48,'Extra handler')
            p,e=divmod(index,16);index+=1
            expanded.append(architecture.spike_trace.SpikeCommit(pc=address(p,e)+8,instruction=0x73,
                gpr_writes={},fpr_writes={},vector_writes={},csr_writes={},memory_accesses=()))
        expanded.append(c)
    require(index==48,'Missing handler');validate(expanded,symbols)
    return cs


def prepare(output):
    require(not output.exists() and output.parent==OUT,'Fresh preflight only')
    proof,pins=source_contract();m=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(m['coverage_admitted'] is True,'Formal792 required')
    pins[str(BASE/'admission-manifest.json')]=BASE_SHA
    cmd=json.loads(prior.shared.TEMPLATE.read_bytes())
    cmd=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(LINK) if x.endswith('/gap75.ld')
         else str(output/'input.elf') if x.endswith('/input.elf') else x for x in cmd]
    for p in (APP,LINK,prior.shared.TEMPLATE,ROOT/'verification/tests/gap75_start.S',
              Path(cmd[0]),build.SPIKE,Path(__file__),Path(__file__).with_name('test_itlb_ppn_aba.py')):
        pins[str(p.resolve())]=life.digest(p)
    for mod in (prior,bulk,prior.shared,life,build,architecture):
        p=Path(mod.__file__).resolve();pins[str(p)]=life.digest(p)
    for d in ('apps/common','apps/riscv-tests/env','apps/riscv-tests/isa/macros'):
        for p in (ROOT/d).rglob('*'):
            if p.is_file():pins[str(p)]=life.digest(p)
    life.check(pins);output.mkdir();life.save(output/'input-pins.json',pins)
    try:
        life.save(output/'compile-command.json',cmd)
        with (output/'build.log').open('x') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        symbols,layout=elf_contract(output/'input.elf');life.save(output/'elf-layout.json',layout)
        command=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '-m0x80000000:0x200000','-l','--log-commits',str(output/'input.elf')]
        life.save(output/'spike-command.json',command)
        with (output/'spike.trace').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        cs=reference(output/'spike.trace',symbols);counts=architecture.reference_counts(cs,symbols)
        require(counts['matched_instructions']<40000,'Reference exceeds authorized40k bound')
        life.save(output/'source-contract.json',proof);life.check(pins)
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in output.iterdir() if p.is_file()})
        life.save(output/'preflight.json',dict(status='ITLB_PPN_ABA_SPIKE_PASS_NOT_RTL',baseline=792,
            baseline_seal=BASE_SHA,symbols=symbols,counts=counts,software_checks=CHECKS,trap_count=48,
            input_pins=pins,coverage_admitted=False,VCS_launched=False))
        print('PREFLIGHT_PASS',life.digest(output/'preflight.json'),counts,flush=True)
    except Exception as e:
        life.save(output/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.absolute())
