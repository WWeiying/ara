"""Six precise scalar misalignment traps, formal789 software preflight only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import build_csr_cause_wlrl788 as shared_case
import review_scalar_fault_itlb789 as review

shared, require = shared_case.shared, shared_case.require
ROOT, OUT, sha, save = shared_case.ROOT, shared_case.OUT, shared_case.sha, shared_case.save
BASE, BASE_SHA = review.BASE, review.BASE_SHA
APP = ROOT/'apps/riscv-tests/isa/rv64uv/scalar_misalign_tval789.c'
STATIC = OUT/'scalar-fault-itlb789-static-agent-20261008-01.json'
ADDRESSES = [0x0000002555555003,0xffffffdaaaaaa003,0x0000002555555003]
GUARDS = shared_case.GUARDS

def target_binding(pins):
    base=json.loads((BASE/'admission-manifest.json').read_bytes())
    require(sha(BASE/'admission-manifest.json')==BASE_SHA and base['coverage_admitted'] is True,'Formal789 authority')
    pins[str(BASE/'admission-manifest.json')]=BASE_SHA
    report=json.loads(STATIC.read_bytes());require(report['baseline_seal']==BASE_SHA,'Exact reviewed static baseline')
    pins[str(STATIC)]=sha(STATIC)
    for p,h in report['input_pins'].items():require(sha(Path(p))==h,'Static source/raw pin changed');pins[p]=h
    ledger_path=BASE/'combined-inputs.txt';require(sha(ledger_path)==base['output_pins'][str(ledger_path)],'Bound ledger')
    ledger=ledger_path.read_text().splitlines();require(len(ledger)==len(set(ledger))==790,'Exact789 population')
    family=next(f for f in report['families'] if f['name']=='SCALAR_MISALIGN_TVAL_PRODUCER_AND_RETURN')
    objects=family['objects'];require(len(objects)==5,'Exact five LSU fields')
    scopes={o['scope'] for o in objects};db=Path(ledger[0])/'snps/coverage/db'
    files=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in files:
        require(sha(p)==base['input_pins'][str(p)],'Frozen typed shape');pins[str(p)]=sha(p)
    checks,defs=review.toggle.definitions(*(review.toggle.xml(p) for p in files),scopes)
    fields=[]
    for obj in objects:
        scope=obj['scope'];require(obj['checksum']==checks[scope],'Typed scope checksum')
        offset=0;matches=[]
        for node in ET.fromstring(defs[scope]['shape']).find('tglshape'):
            if node.tag=='arrays':continue
            require(node.tag in ('node','vectornode'),'Unknown serialized shape')
            left,right=int(node.get('left','0')),int(node.get('right','0'))
            width=1 if node.tag=='node' else abs(left-right)+1
            if node.get('name')==obj['name']:matches.append((offset,left,right,width))
            offset+=2*width
        require(len(matches)==1,'Exact single field declaration');start,left,right,width=matches[0]
        require(left==63 and right==0 and width==obj['logical_width']==64,'Full64 scalar tval, no guessed MDA')
        require(all(start<=p<start+128 for p in obj['coordinates']),'Coordinates lie in exact field')
        # Serialized pairs follow shape declaration order; no assumption about
        # which pair member is rising/falling. Alternating VAs drive both.
        bits=[(p,63-(p-start)//2,(p-start)%2) for p in obj['coordinates']]
        variable_bits={i for i in range(64) if ((ADDRESSES[0]^ADDRESSES[1])>>i)&1}
        predicted=[p for p,b,_ in bits if b in variable_bits]
        fields.append(dict(obj,serialized_field_offset=start,logical_bit_pairs=bits,
                           alternating_address_potential=predicted,direction_pair_order_not_assumed=True))
    return dict(baseline=789,baseline_seal=BASE_SHA,fields=fields,
        raw_missing=sum(len(f['coordinates']) for f in fields),
        predicted_alternating_capacity=sum(len(f['alternating_address_potential']) for f in fields),
        slot_allocation_NOT_predicted=True,actual_gain=None,official_percentage_claimed=False)

def traps(text,symbols):
    found=[]
    pattern=r'^core\s+0:\s+exception\s+(trap_\w+),\s+epc\s+(0x[0-9a-f]+)\s*$'
    lines=text.splitlines()
    for i,line in enumerate(lines):
        m=re.match(pattern,line)
        if not m:continue
        require(m[1] in ('trap_load_address_misaligned','trap_store_address_misaligned'),'Unexpected Spike trap kind')
        require(i+1<len(lines),'Missing trap tval')
        value=re.search(r'\btval\s+(0x[0-9a-f]+)',lines[i+1]);require(value is not None,'Missing exact Spike tval')
        found.append(dict(cause=4 if m[1]=='trap_load_address_misaligned' else 6,pc=int(m[2],16),tval=int(value[1],16)))
    wanted=[dict(cause=4 if i%2==0 else 6,pc=symbols['mis_ld_pc'] if i%2==0 else symbols['mis_sd_pc'],tval=ADDRESSES[i//2]) for i in range(6)]
    require(found==wanted,'Exact six Spike trap EPC/cause/tval ledger')
    return found

def validate(commits,symbols,ledger):
    memory={};guards=[]
    for c in commits:
        require(not c.vector_writes and not c.fpr_writes and c.pc not in (symbols['trap_fail'],symbols['mis_unexpected']),'Unexpected vector/FP/trap failure')
        for address,value in c.memory_accesses:
            require(0x80000000<=address<0x80200000,'Fault escaped to memory / physical range')
            require(value is None or not symbols['mis_guards']<=address<symbols['mis_guards']+16,'Guard mutation')
            if value is not None:memory[address]=value
            if value is None and address in (symbols['mis_guards'],symbols['mis_guards']+8):
                require(list(c.gpr_writes.values())==[GUARDS[(address-symbols['mis_guards'])//8]],'Independent guard readback')
                guards.append(address)
    require(memory.get(symbols['mis_count'])==6 and len(ledger)==6,'Six handler owners')
    for i,want in enumerate(ledger):
        base=symbols['mis_records']+32*i
        require([memory.get(base+8*j) for j in range(3)]==[want['cause'],want['pc'],want['tval']],'Independent handler frame')
        status=memory.get(base+24);require(type(status) is int and status&0x21808==0x1800,'M-mode trap MIE/MPRV/MPP contract')
    require([memory.get(symbols['mis_dest']+8*i) for i in range(3)]==[0x6969696969696969]*3,'Fault LD destination unchanged')
    require([memory.get(symbols['mis_page']+8*i) for i in range(16)]==[0x5555555555555555 if i==8 else 0x9696969696969696 for i in range(16)],'Complete work memory / recovery')
    before=[memory.get(symbols['mis_csr']+8*i) for i in range(7)]
    after=[memory.get(symbols['mis_csr']+56+8*i) for i in range(7)]
    require(all(type(v) is int for v in before) and before==after and before[0]&0x20008==0 and before[5]==0,'Complete CSR restore/Bare/MIE/MPRV')
    terminal=[v for c in commits for a,v in c.memory_accesses if a==symbols['tohost'] and v is not None]
    require(terminal==[1] and memory.get(symbols['g75_result'])==56 and memory.get(symbols['g75_result']+4)==memory.get(symbols['num_failed'])==0
            and guards==[symbols['mis_guards'],symbols['mis_guards']+8],'Signature and exact guard reads')
    return dict(status='SPIKE_SIX_SCALAR_MISALIGN_GOLD_PASS_NOT_DUT',checks=56,trap_ledger=ledger,
        retired_instructions=len(commits),all_reference_memory_accesses=sum(len(c.memory_accesses) for c in commits),
        normal_memory_bytes=128,guards_bytes=16,CSR_restore_bytes=112,load_destination_bytes=24,trap_frame_bytes=192,
        native_fault_before_AXI_verified=False,RTL_changed=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);out=p.parse_args().output.absolute()
    require(out.parent==OUT and not out.exists(),'Fresh direct output')
    pins={};targets=target_binding(pins)
    paths=[APP,Path(__file__).resolve(),Path(__file__).with_name('test_build_scalar_misalign789.py'),ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',shared.LLVM/'clang',shared.LLVM/'llvm-readelf',shared.SPIKE,Path(shared_case.__file__),Path(shared.__file__),Path(review.__file__),Path(__file__).with_name('scalar_misalign789_probe.tcl')]
    paths+=list((ROOT/'verification/ara_verify').glob('*.py'))
    paths+=[f for f in (ROOT/'apps/riscv-tests/isa/macros').rglob('*') if f.is_file()]
    for rel,seal in shared_case.SOURCE_SHAS.items():
        f=shared_case.SPIKE_SOURCE/rel;require(sha(f)==seal,'Pinned Spike source');pins[str(f)]=seal
    pins=shared.merge_pins(pins,{str(f):sha(f) for f in paths});shared.check(pins);out.mkdir();save(out/'target-before.json',targets)
    template=OUT/'csr-cause-wlrl788-preflight-agent-20261008-02'
    require(sha(template/'preflight-manifest.json')=='953943c09cbd5ff93fad321edc715c957b08b837de7e472deae12da9eed5d2cb','Bound compiler template preflight')
    template_manifest=json.loads((template/'preflight-manifest.json').read_bytes())
    require(sha(template/'compile-command.json')==template_manifest['output_pins'][str(template/'compile-command.json')],'Compiler template command changed')
    command=json.loads((template/'compile-command.json').read_text())
    require(command[-4:-2]==[str(ROOT/'verification/tests/gap75_start.S'),str(shared_case.APP)],'Exact known compiler template')
    command[-3]=str(APP);command[-1]=str(out/'input.elf');save(out/'compile-command.json',command)
    with (out/'compile.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols={k:shared._elf_symbol(out/'input.elf',shared.LLVM/'llvm-readelf',k) for k in ('tohost','trap_fail','g75_result','g75_trap','num_failed','mis_count','mis_records','mis_dest','mis_csr','mis_page','mis_guards','mis_ld_pc','mis_sd_pc','mis_handler','mis_unexpected')}
    command=[str(shared.SPIKE),'--isa='+shared_case.SPIKE_ISA,'--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')];save(out/'spike-command.json',command)
    with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace:subprocess.run(command,stdout=stdout,stderr=trace,check=True,timeout=60)
    ledger=traps((out/'spike.trace').read_text(),symbols)
    commits=list(shared.parse_spike_commits(out/'spike.trace'));start=next(i for i,c in enumerate(commits) if c.pc==0x80000000);end=next(i for i,c in enumerate(commits) if (symbols['tohost'],1) in c.memory_accesses)
    validation=validate(commits[start:end+1],symbols,ledger);save(out/'spike-validation.json',validation);shared.check(pins)
    outputs={str(f):sha(f) for f in out.iterdir() if f.is_file()}
    save(out/'preflight-manifest.json',dict(status='SCALAR_MISALIGN789_SOFTWARE_PREFLIGHT_PASS_NOT_DUT',baseline=789,baseline_seal=BASE_SHA,symbols=symbols,input_elf=str(out/'input.elf'),pins=pins,output_pins=outputs,validation=validation,VCS_authorized=False,coverage_admitted=False,RTL_changed=False))
    print(json.dumps(dict(output=str(out),seal=sha(out/'preflight-manifest.json'),validation=validation)))
if __name__=='__main__':main()
