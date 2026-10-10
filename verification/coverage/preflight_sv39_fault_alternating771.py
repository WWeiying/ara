"""Independent invalid-leaf S-mode fault oracle; no RTL compilation."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import build_tlb_asid_matrix as shared

life,build,require=shared.life,shared.build,shared.require
ROOT,OUT=life.ROOT,life.OUT
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vsv39_fault_address_alternating.c'
BASE=OUT/'sv39-alias-offline-admitted-771-agent-20261007-01'
BASE_SHA='ad9e01dcd0ea3ef442d7f28934bf1695dca61c7b6d1c7580bd2a49f0c2569860'
SYMBOLS=('tohost','num_failed','g75_result','trap_fail','fault_count','fault_returns',
 'fault_page','fault_root','fault_mid','fault_leaf','fault_vrf','fault_records','fault_csr',
 'fault_source','fault_handler','fault_load_pc','fault_store_pc','fault_s_ecall','fault_resume')
ADDRESSES=(0x2555555040,0xffffffdaaaaaa040)
SEED=0x5a5a5a5a5a5a5a5a

def validate(path,s):
    trace=path.read_text()
    traps=re.findall(r'exception (\w+), epc 0x([0-9a-f]+)',trace)
    expected=[]
    for _ in range(4):
        expected.extend([('trap_load_page_fault',s['fault_load_pc']),
          ('trap_store_page_fault',s['fault_store_pc']),('trap_supervisor_ecall',s['fault_s_ecall'])])
    require([(a,int(b,16)) for a,b in traps]==expected,'Exact fault/return PC and count')
    commits=build.parse_spike_commits(path)
    writes={};snap=set();page_reads=0;source_reads=set();recovery=0;original=None
    for c in commits:
        require(c.pc!=s['trap_fail'],'Default trap handler')
        if original is None and c.instruction>>20==0x300 and c.gpr_writes:
            original=list(c.gpr_writes.values())[0]
        for a,v in c.memory_accesses:
            if v is not None:
                writes[a]=v
                if c.instruction&0x7f==0x27 and s['fault_vrf']+16<=a<s['fault_vrf']+4112:
                    require(v==0x5a and a not in snap,'Full fault VRF unchanged byte')
                    snap.add(a)
            elif s['fault_page']<=a<s['fault_page']+4096:
                require(len(c.gpr_writes)==1,'Page scalar observation')
                value=list(c.gpr_writes.values())[0]
                if page_reads<512:require(value==0x6969696969696969,'Fault store changed backing page')
                page_reads+=1
            elif s['fault_source']<=a<s['fault_source']+24 and c.gpr_writes:
                i=(a-s['fault_source'])//8
                require(a==s['fault_source']+8*i and list(c.gpr_writes.values())==
                  [0x5555555555555555 if i==1 else 0x9696969696969696], 'Immutable source readback')
                source_reads.add(i)
        if 8 in c.vector_writes and c.vector_sew==64:
            expected_bytes=(0x5555555555555555).to_bytes(8,'little')+\
              (0x9696969696969696).to_bytes(8,'little')+bytes([0x5a])*112
            require(c.vector_vl==2 and c.vector_writes[8]==int.from_bytes(expected_bytes,'little'),
              'Full legal recovery destination and tail')
            recovery+=1
        if c.pc in (s['fault_load_pc'],s['fault_store_pc']):
            require(not c.memory_accesses and not c.vector_writes,'Fault acquired memory/VRF effects')
    require(len(snap)==4096 and page_reads>=514,'Complete snapshot/page observations')
    require([writes.get(s['g75_result']+4*i) for i in range(2)]==[1091,0]
      and writes.get(s['tohost'])==1 and writes.get(s['num_failed'])==0,'All1091 checks and terminal')
    require(writes.get(s['fault_count'])==8 and writes.get(s['fault_returns'])==4,'Trap counters')
    for i in range(8):
        want=[15 if i&1 else 13,s['fault_store_pc'] if i&1 else s['fault_load_pc'],
          ADDRESSES[(i//2)&1],0,1,24]
        require([writes.get(s['fault_records']+48*i+8*j) for j in range(6)]==want,'Exact cause/PC/tval/vstart/VL/type')
    for name in ('fault_root','fault_mid','fault_leaf'):
        require(s[name]%4096==0,'Aligned page tables')
        expected_pt={}
        if name=='fault_root':expected_pt[2]=0x200000cf
        for vpn in (0x2555555,0x5aaaaaa):
            index={'fault_root':vpn>>18,'fault_mid':(vpn>>9)&511,'fault_leaf':vpn&511}[name]
            next_name={'fault_root':'fault_mid','fault_mid':'fault_leaf','fault_leaf':'fault_page'}[name]
            expected_pt[index]=((s[next_name]>>12)<<10)|(0xc6 if name=='fault_leaf' else 1)
        require(all(writes.get(s[name]+8*i)==expected_pt.get(i,0) for i in range(512)),'Entire invalid-leaf page table image')
    require(source_reads=={0,1,2} and recovery==1,'Complete immutable source and recovery')
    require([writes.get(s['fault_csr']+8*i) for i in range(5)]==[2,24,0,0,0]
      and original is not None and writes.get(s['fault_csr']+40)==original
      and writes.get(s['fault_csr']+48)==0,'Recovery CSR and mstatus restoration')
    require(all(writes.get(s['fault_vrf']+8*i)==0x9696969696969696 for i in (0,1,514,515)),
      'All snapshot guards')
    require(writes.get(s['fault_page']+64)==0x5555555555555555 and
      writes.get(s['fault_page']+72)==0x9696969696969696,'Legal VL2 recovery memory')
    return dict(instructions=len(commits),checks=1091,page_faults=8,ecalls=4,
      full_VRF_bytes=4096,full_page_no_fault_store_effect_bytes=4096,
      exact_fault_records=8,coverage_admitted=False)

def prepare(out,existing=False):
    require(not out.exists() or (existing and not (out/'preflight.json').exists()),'Fresh unsealed output')
    baseline=BASE/'admission-manifest.json';base=life.read_bound(baseline,BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Exact admitted771')
    ledger=BASE/'combined-inputs.txt';ledger_sha=base['output_pins'][str(ledger)]
    require(life.digest(ledger)==ledger_sha and len(ledger.read_text().splitlines())==772,'771 population')
    pins={str(baseline):BASE_SHA,str(ledger):ledger_sha}
    book=life.read_bound(shared.SOURCE,shared.SOURCE_SHA);pins[str(shared.SOURCE)]=shared.SOURCE_SHA
    source={}
    for rel in ('hardware/src/vlsu/addrgen.sv','hardware/src/vlsu/vldu.sv',
      'hardware/src/vlsu/vstu.sv','hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
      'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv','hardware/deps/cva6/core/cva6.sv'):
        p=ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen source '+rel)
        pins[str(p)]=book[str(p)];source[rel]=p.read_text()
    require('enable_translation_csr_ex' in source['hardware/deps/cva6/core/cva6.sv'], 'Actual S-mode translation path')
    command=json.loads(shared.TEMPLATE.read_bytes())
    command=[str(APP) if a.endswith('/vgap99_csr_satp_mprv.c') else
      str(out/'input.elf') if a.endswith('/input.elf') else a for a in command]
    for p in (APP,shared.TEMPLATE,Path(__file__),Path(command[0]),build.SPIKE,
      build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',ROOT/'verification/tests/gap75_start.S',
      ROOT/'verification/tests/gap75.ld'):
        pins[str(p.resolve())]=life.digest(p)
    for directory in ('apps/riscv-tests/isa/macros','apps/riscv-tests/env','apps/common'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file():pins[str(p)]=life.digest(p)
    life.check(pins)
    if not existing:
        out.mkdir();life.save(out/'compile-command.json',command)
        with (out/'build.log').open('x') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    else:require(json.loads((out/'compile-command.json').read_bytes())==command,'Actual compiler command')
    s={n:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
    require(s['tohost']==0x80001000,'Image tohost ABI')
    spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
      '-m0x80000000:0x20000000','-l','--log-commits',str(out/'input.elf')]
    if not existing:
        life.save(out/'spike-command.json',spike)
        with (out/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    else:require(json.loads((out/'spike-command.json').read_bytes())==spike,'Actual Spike command')
    from elftools.elf.elffile import ELFFile
    with (out/'input.elf').open('rb') as f:
        elf=ELFFile(f);segments=[p for p in elf.iter_segments() if p['p_type']=='PT_LOAD']
        require(segments and all(0x80000000<=p['p_paddr'] and p['p_paddr']+p['p_memsz']<=0x80040000
            for p in segments),'Frozen L2 ELF fit')
        region=next(p for p in segments if p['p_vaddr']<=s['fault_source']<p['p_vaddr']+p['p_filesz'])
        offset=s['fault_source']-region['p_vaddr']
        require(region.data()[offset:offset+24]==b''.join(v.to_bytes(8,'little') for v in
          (0x9696969696969696,0x5555555555555555,0x9696969696969696)),'Independent ELF source bytes')
    require(not any('ZCC' in a or 'Terapines' in a for a in command),'No ZCC')
    from admit_stride_metadata768 import dedup
    duplicate=dedup(ledger.read_text().splitlines(),life.digest(out/'input.elf'),base['input_pins'])
    duplicate['baseline']=771
    life.save(out/'elf-dedup.json',duplicate)
    counts=validate(out/'spike.trace',s);life.check(pins)
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
    life.save(out/'preflight.json',dict(status='SPIKE_INVALID_LEAF_FULL_ORACLE_PASS_NOT_DUT',
      symbols=s,counts=counts,input_pins=pins,baseline=771,baseline_seal=BASE_SHA,
      case_kind='RVV unit-stride page fault, not scalar LSU coordinate proof',coverage_admitted=False))
    print('PREFLIGHT_PASS '+life.digest(out/'preflight.json'),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--existing',action='store_true')
    a=p.parse_args();prepare(a.output.resolve(),a.existing)
