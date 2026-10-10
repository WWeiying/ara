"""One legal RVV alias ring: independent word/VRF/PTE oracle and Spike preflight."""
import argparse
import json
from pathlib import Path
import subprocess
import build_tlb_asid_matrix as old

life,build,require=old.life,old.build,old.require
ROOT,OUT=old.ROOT,old.OUT
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vsv39_rvv_alias_ring.c'
AUDIT=OUT/'toggle-outside-prepared-union770-static-agent-20261007-01.json'
AUDIT_SHA='c6dd804cbee8e8d872c6058da0defb8e1c0facd1ca816caf8326e6b12105f036'
PATTERNS=(0x5555555555555555,0xaaaaaaaaaaaaaaaa,0x5555555555555555)
SEED,GUARD,PAGE=0x5a5a5a5a5a5a5a5a,0x9696969696969696,0x6969696969696969
SYMBOLS=('tohost','num_failed','g75_result','trap_fail','alias_page','alias_root',
         'alias_mid','alias_leaf','alias_vrf','alias_source','alias_csr','alias_store_site','alias_load_site')


def vpn(phase):
    require(phase in (0,1,2),'Exact phase')
    return 0x5aaaaaa if phase==1 else 0x2555555


def address(phase):
    a=vpn(phase)<<12
    return (a|(((1<<64)-(1<<39)) if a&(1<<38) else 0))|64


def vrf_words(phase):
    return [PATTERNS[phase] if 128<=i<136 or 256<=i<264 else SEED for i in range(512)]


def ring_proof():
    mask=(1<<64)-1
    require(address(0)^address(1)==((1<<64)-(1<<12)),'Exact virtual XOR bits12..63')
    result=[]
    for initial in range(16):
        slots=[[] for _ in range(16)];p=initial
        for phase in range(3):
            for _ in range(16):slots[p].append(address(phase));p=(p+1)%16
        require(all(x==[address(i) for i in range(3)] for x in slots),'Complete ring')
        up=(~address(0))&address(1)&mask;down=address(0)&(~address(1))&mask
        up|=(~address(1))&address(2)&mask;down|=address(1)&(~address(2))&mask
        require(up==down==((1<<64)-(1<<12)),'Both virtual directions')
        result.append({'initial_pointer':initial,'all16_written_each_phase':True})
    return result


def validate(commits,symbols):
    stores=loads=vector_bytes=page_reads=0;state={};seen_snapshot=set();writes={};csr_reads=[]
    site_stores=[];site_loads=[]
    for c in commits:
        require(c.pc!=symbols['trap_fail'],'Unexpected trap')
        phase=min(stores//16,2)
        if c.pc==symbols['alias_store_site']:
            require(stores<48 and c.instruction&0x707f==0x7027,'Exact vse64 site')
            expected=tuple((address(stores//16)+8*i,PATTERNS[stores//16]) for i in range(8))
            require(c.memory_accesses==expected,'Exact full target vector store')
            site_stores.append(c.pc);stores+=1
        elif c.pc==symbols['alias_load_site']:
            require(loads<48 and stores==loads+1 and c.instruction&0x707f==0x7007,'Exact ordered vle64 site')
            require(c.memory_accesses==tuple((address(loads//16)+8*i,None) for i in range(8)),
                    'Exact full target vector load')
            site_loads.append(c.pc);loads+=1
        for r,value in c.vector_writes.items():
            if c.vector_sew==8:
                require(r in range(32) and value==int.from_bytes(bytes([0x5a])*128,'little'),
                        'Full initial VRF seed')
            else:
                require(c.vector_sew==64 and r in (8,16),'Unexpected vector destination/SEW')
                p=(loads-1)//16 if c.pc==symbols['alias_load_site'] else stores//16
                require(0<=p<3,'Exact vector phase')
                expect=PATTERNS[p].to_bytes(8,'little')*8+SEED.to_bytes(8,'little')*8
                require(value==int.from_bytes(expect,'little'),'Full vector result/tail')
            state[r]=value;vector_bytes+=128
        for a,value in c.memory_accesses:
            if value is not None:writes[a]=value
            elif symbols['alias_page']<=a<symbols['alias_page']+4096:
                require((a-symbols['alias_page'])%8==0 and len(c.gpr_writes)==1,
                        'Full-page scalar read shape')
                i=(a-symbols['alias_page'])//8;p=(stores-1)//16
                require(0<=p<3,'Page observation phase')
                expected=PATTERNS[p] if 8<=i<16 else PAGE
                require(list(c.gpr_writes.values())==[expected],'Independent page/guard observation')
                page_reads+=1
            if value is not None and symbols['alias_vrf']<=a<symbols['alias_vrf']+3*516*8:
                p,within=divmod(a-symbols['alias_vrf'],516*8)
                if not state and value==0:
                    continue  # CRT .bss initialization precedes all known VRF seeds.
                i=within//8;expected=GUARD if i<2 or i>=514 else vrf_words(p)[i-2]
                if c.instruction&0x7f==0x27:
                    require(c.instruction&0x707f==0x27,'Exact whole-register byte store')
                    require(value==((expected>>(8*(within%8)))&255),'Independent snapshot byte')
                    require((p,within) not in seen_snapshot,'Duplicate snapshot byte')
                    seen_snapshot.add((p,within))
                else:
                    require(within%8==0 and (i<2 or i>=514) and value==GUARD,'Exact scalar guard store')
                    seen_snapshot.update((p,within+b) for b in range(8))
    require(stores==loads==48 and page_reads==1536,'Complete48 pairs and1536 page readbacks')
    require(set(state)==set(range(32)),'Complete32-register known seed/result')
    require(len(seen_snapshot)==12384,'All3 full VRF snapshots and guards')
    require([writes.get(symbols['g75_result']+4*i) for i in range(2)]==[3113,0] and
            writes.get(symbols['num_failed'])==0 and writes.get(symbols['tohost'])==1,'Exact check/terminal')
    original=writes.get(symbols['alias_csr']+5*8);require(original is not None,'Original status evidence')
    satp=(8<<60)|(65535<<44)|(symbols['alias_root']>>12)
    for p in range(3):
        require([writes.get(symbols['alias_csr']+8*(7*p+i)) for i in range(7)]==
                [8,24,0,0,0,original,satp],'Full phase CSR contract')
    pte=lambda a,f:((a>>12)<<10)|f
    expected={symbols['alias_root']+16:pte(0x80000000,0xcf)}
    for p in range(2):
        v=vpn(p)
        expected[symbols['alias_root']+8*(v>>18)]=pte(symbols['alias_mid'],1)
        expected[symbols['alias_mid']+8*((v>>9)&511)]=pte(symbols['alias_leaf'],1)
        expected[symbols['alias_leaf']+8*(v&511)]=pte(symbols['alias_page'],0xc7)
    for name in ('alias_root','alias_mid','alias_leaf'):
        require(symbols[name]%4096==0,'PTE page alignment')
        for i in range(512):require(writes.get(symbols[name]+8*i)==expected.get(symbols[name]+8*i,0),
                                     'Full independent PTE image')
    require(not any(symbols['alias_source']<=a<symbols['alias_source']+40 for a in writes),'Immutable source write')
    return dict(scalar_retirements=sum(not c.vector_writes for c in commits),retirements=len(commits),
        gpr_writes=sum(len(c.gpr_writes) for c in commits),memory_observations=sum(len(c.memory_accesses) for c in commits),
        vector_write_bytes=vector_bytes,full_vrf_snapshot_bytes=12288,page_checked_bytes=12288,
        target_stores=stores,target_loads=loads,checks=3113,unknown_vector_bytes=0)


def prepare(out,existing=False):
    require(out.parent==OUT and (out.is_dir() if existing else not out.exists()),'Fresh output or explicit offline check')
    require(not (out/'preflight.json').exists(),'Never rewrite sealed preflight')
    audit=json.loads(AUDIT.read_bytes());require(life.digest(AUDIT)==AUDIT_SHA and audit['population']==770,'Exact770 audit')
    book=life.read_bound(old.SOURCE,old.SOURCE_SHA);pins={str(old.SOURCE):old.SOURCE_SHA,str(AUDIT):AUDIT_SHA}
    paths=['hardware/src/vlsu/addrgen.sv','hardware/src/vlsu/vstu.sv','hardware/src/ara.sv',
           'hardware/include/ara_pkg.sv','hardware/deps/cva6/core/acc_dispatcher.sv']
    texts=[]
    for rel in paths:
        p=ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen producer source mismatch '+rel)
        pins[str(p)]=book[str(p)];texts.append(p.read_text())
    addr,store,ara,pkg,acc=texts
    for token in ('vaddr        : axi_addrgen_q.addr','burst_length = 256;'):
        require(token in addr,'Address/burst source contract')
    for token in ('.DEPTH(VstuInsnQueueDepth * VaddrgenInsnQueueDepth)',".flush_i(1'b0)",
                  'b_meta_in.vaddr = axi_addrgen_req_i.vaddr;',"b_meta_push = 1'b1;"):
        require(token in store,'Exact store metadata source contract')
    require('VstuInsnQueueDepth = 4' in pkg and 'VaddrgenInsnQueueDepth = 4' in pkg,'Exact16 slots')
    require('acc_req_i.acc_mmu_en' in ara and 'acc_req_o.acc_mmu_en            = acc_mmu_en_i;' in acc,
            'Translation request propagation')
    command=json.loads(old.TEMPLATE.read_bytes())
    command=[str(APP) if s.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf')
             if s.endswith('/input.elf') else s for s in command]
    require(str(APP) in command and not any('ZCC' in s or 'Terapines' in s for s in command),'Non-ZCC compile')
    for p in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_preflight_sv39_rvv_alias770.py'),
              old.TEMPLATE,Path(command[0]),build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',build.SPIKE,
              ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld'):
        pins[str(p)]=life.digest(p)
    for directory in ('apps/riscv-tests/isa/macros','apps/riscv-tests/env','apps/common'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file():pins[str(p)]=life.digest(p)
    life.check(pins);ring=ring_proof()
    if existing:
        require(json.loads((out/'compile-command.json').read_bytes())==command,'Existing exact compiler command')
    else:
        out.mkdir();life.save(out/'compile-command.json',command)
        with (out/'build.log').open('x') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols={name:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',name) for name in SYMBOLS}
    spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
           '-m0x80000000:0x20000000','-l','--log-commits',str(out/'input.elf')]
    if existing:
        require(json.loads((out/'spike-command.json').read_bytes())==spike,'Existing exact Spike command')
    else:
        life.save(out/'spike-command.json',spike)
        with (out/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    require('exception ' not in (out/'spike.trace').read_text(),'Unexpected Spike exception')
    counts=validate(build.parse_spike_commits(out/'spike.trace'),symbols);life.check(pins)
    life.save(out/'symbols.json',symbols)
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
    result=dict(status='INDEPENDENT_SPIKE_FULL_VRF_MEMORY_PTE_CSR_PREFLIGHT_PASS_NOT_DUT',baseline=770,
        input_pins=pins,symbols=symbols,counts=counts,ring_proof=ring,alias_addresses=[address(p) for p in range(3)],
        logical_virtual_bit_directions=list(range(12,64)),hard_budget_seconds=600,VCS_launched=False,EDA_launched=False,
        target_capacity='3232 low64 missing replicated positions is upper bound, not official metric. Require actual accepted48 AW/W/B records and each metadata slot low/high/low before gain claim.',
        scalar_reference='Complete pinned Spike trace retained; no DUT comparison or ISA skip claimed during preflight.')
    life.save(out/'preflight.json',result);print('PREFLIGHT_PASS',life.digest(out/'preflight.json'),counts,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--check-existing',action='store_true');a=p.parse_args();prepare(a.output.resolve(),a.check_existing)
