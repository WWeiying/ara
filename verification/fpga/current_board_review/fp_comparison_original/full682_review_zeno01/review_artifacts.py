#!/usr/bin/env python3
"""Independent read-only artifact/ELF/Host equivalence audit; never execute binaries."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'full682_packed_prepare01'
CASE=HERE.parent/'prepared02/prepared/alias_v8_e16m8_prefix682'
ARCHIVE=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,d):
    with p.open('x') as f:json.dump(d,f,indent=2);f.write('\n')
def demand(v,msg):
    if not v:raise ValueError(msg)
def initializer(text,name):
    m=re.search(re.escape(name)+r'\s*=\s*(\{.*?\});',text,re.S)
    demand(m is not None,'Initializer '+name)
    s=re.sub(r'UINT64_C\((0x[0-9a-f]+|[0-9]+)\)',r'\1',m[1])
    return ast.literal_eval(s.replace('{','[').replace('}',']'))
def elf(p):
    raw=Path(p).read_bytes()
    demand(raw[:6]==b'\x7fELF\x02\x01','ELF64 little endian')
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    demand(h[2]==243,'RISC-V ELF')
    segments=[]
    for n in range(h[10]):
        ph=struct.unpack_from('<IIQQQQQQ',raw,h[5]+n*h[9])
        if ph[0]==1:segments.append((ph[3],ph[2],ph[5],ph[6]))
    return raw,segments
def at(image,addr,n):
    raw,segments=image
    for va,offset,filesz,memsz in segments:
        if va<=addr and addr+n<=va+filesz:return raw[offset+addr-va:offset+addr-va+n]
    raise ValueError('ELF address '+hex(addr))
def blocks(path):
    result={};name=None
    for line in Path(path).read_text().splitlines():
        head=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if head:name=head[2];result[name]=[]
        insn=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+',line)
        if insn and name:result[name].append((int(insn[1],16),insn[2]))
    return result
def main():
    ready=read(SOURCE/'READY.json');pins=read(SOURCE/'pins.json')
    checked={};drift=[]
    for path,expected in pins.items():
        actual=sha(path);checked[path]=actual
        if actual!=expected:drift.append(dict(path=path,pinned=expected,actual=actual))
    demand(sha(SOURCE/'pins.json')==ready['pins_sha256'],'READY pins link')
    demand(not drift,'Pinned evidence drift '+str(drift))
    original=(CASE/'original/fixtures.h').read_text()
    inputs=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',original)]
    wanted=initializer(original,'expected[6][16][16]')
    tables=(SOURCE/'run01/tables.h').read_text()
    rows=initializer(tables,'input_rows[][128]')
    cases=initializer(tables,'packed_cases[682]')
    sequence=read(CASE/'call_sequence.json')
    demand(len(inputs)==16 and len(wanted)==6 and len(cases)==len(sequence)==682,'Source dimensions')
    reference_sequence=[dict(seed=s,op=o,vl=v,mask=m,sticky=f,vstart=0) for s,o,v,m,f in itertools.product(range(32),range(10),(0,1,2,3,256,511,512),range(4),range(2))][:682]
    demand(sequence==reference_sequence,'All original first682 order')
    bit_checks=input_checks=flags_checks=byte_alternatives=0
    for n,(record,cfg) in enumerate(zip(cases,reference_sequence)):
        seed,op,vl,mode,sticky,airow,birow,flags,zero,one=record
        demand((seed,op,vl,mode,sticky)==tuple(cfg[k] for k in ('seed','op','vl','mask','sticky')),'Table parameter case '+str(n))
        av=[(w>>(16*j))&65535 for w in rows[airow] for j in range(4)]
        bv=[(w>>(16*j))&65535 for w in rows[birow] for j in range(4)]
        demand(len(av)==len(bv)==512 and len(zero)==len(one)==64,'Exact input/output length')
        allow=[];expected_flags=sticky
        for i in range(512):
            aidx=(i+seed+7*(seed//16))%16
            bidx=(i*3+seed*5+seed//16)%16 if op<4 else seed%16
            demand((av[i],bv[i])==(inputs[aidx],inputs[bidx]),'Input construction case '+str(n))
            input_checks+=2
            bit,fl=wanted[op if op<4 else op-4][aidx][bidx]
            old=(inputs[((i//16)+seed+7*(seed//16))%16]>>(i%16))&1
            allowed={bit} if i<vl else {old} if vl==0 else {old,1,bit}
            if i<vl:expected_flags|=fl
            allow.append(allowed);bit_checks+=1
        demand(flags==expected_flags,'Sticky/active-only flags case '+str(n));flags_checks+=1
        for j in range(64):
            # Independent Cartesian product of the ORIGINAL bit predicates.
            valid={0}
            for b in range(8):valid={x|(v<<b) for x in valid for v in allow[8*j+b]}
            for actual in range(256):
                packed_ok=not((actual&zero[j])|((~actual)&one[j]))
                demand(packed_ok==(actual in valid),'Agnostic/active/VL0 predicate case '+str(n))
                byte_alternatives+=1
    flow=read(SOURCE/'host_flow01/result.json');flow_results=[]
    recordsize=48+1024+1024+128+130
    for mutation in range(7):
        a=(SOURCE/f'host_flow01/original{mutation}.bin').read_bytes()
        b=(SOURCE/f'host_flow01/packed{mutation}.bin').read_bytes()
        demand(a==b and len(a)==682*recordsize,'Actual original/packed full records mutation '+str(mutation))
        for variant in ('original','packed'):
            e=read(SOURCE/f'host_flow01/{variant}{mutation}.exit.json')
            demand(e['returncode']==(0 if mutation==0 else 1),'Actual Host exit')
        flow_results.append(dict(mutation=mutation,sha256=hashlib.sha256(a).hexdigest(),bytes=len(a)))
    raw=(SOURCE/'host_flow01/original0.bin').read_bytes()
    for n,cfg in enumerate(reference_sequence):
        start=n*recordsize
        params=struct.unpack_from('<6Q',raw,start)
        demand(params==(n,cfg['op'],cfg['vl'],512,0,cfg['sticky']),'Actual Host order/arguments')
        seed,op=cfg['seed'],cfg['op']
        av=struct.unpack_from('<512H',raw,start+48)
        bv=struct.unpack_from('<512H',raw,start+48+1024)
        demand(av==tuple(inputs[(i+seed+7*(seed//16))%16] for i in range(512)),'Actual Host A')
        demand(bv==tuple(inputs[(i*3+seed*5+seed//16)%16 if op<4 else seed%16] for i in range(512)),'Actual Host B')
        demand(raw[start+48+2048:start+48+2048+128]==bytes([(255,170,36,0)[cfg['mask']]])*128,'Actual Host full mask')
        demand(raw[start+recordsize-130:start+recordsize]==b'\x5b'*130,'Actual Host full output/guards initialization')
    helpers=['capacity']+['op_'+str(i) for i in range(10)]
    archive_image=elf(ARCHIVE);archive_raw=archive_image[0];helper_proofs={}
    demand(sha(ARCHIVE)==sha(CASE/'original_rebuilt.elf')==ready['original_linux_elf_sha256'],'Actual archived/rebuilt binary identity')
    for backend in ('soc','spike'):
        p=SOURCE/f'run01/{backend}.elf';image=elf(p)
        demand(sha(p)==ready[backend+'_elf_sha256'],'READY ELF pin')
        new=blocks(SOURCE/f'run01/{backend}_dis.log')
        old=blocks(SOURCE/f'run01/{backend}_old_dis.log')
        proof={}
        for h in helpers:
            instructions=new[h];demand([x[1] for x in instructions]==[x[1] for x in old[h]],'Whole helper previous-ELF bytes '+h)
            expected_count=3 if h=='capacity' else 16 if int(h[3:])<4 else 21
            demand(len(instructions)==expected_count,'Complete helper instruction count')
            enc=b''.join(int(w,16).to_bytes(len(w)//2,'little') for _,w in instructions)
            demand(at(image,instructions[0][0],len(enc))==enc,'Disassembly matches actual ELF')
            occurrences=[];from_offset=0
            while True:
                offset=archive_raw.find(enc,from_offset)
                if offset<0:break
                occurrences.append(offset);from_offset=offset+1
            demand(len(occurrences)==1,'Unique complete archived helper '+h)
            proof[h]=dict(pc=hex(instructions[0][0]),instruction_count=len(instructions),bytes_sha256=hashlib.sha256(enc).hexdigest(),archive_file_offset=occurrences[0])
        for name,instructions in new.items():
            if name in helpers:continue
            for pc,w in instructions:
                val=int(w,16);op=val&127;f=(val>>12)&7
                demand(at(image,pc,len(w)//2)==val.to_bytes(len(w)//2,'little'),'Actual non-helper ELF encoding')
                demand(not(len(w)==8 and (op==87 or op in (7,39) and f in (0,5,6,7) or op in (0x43,0x47,0x4b,0x4f,0x53))),'New vector/scalar FP outside helpers')
        helper_proofs[backend]=proof
    h=read(SOURCE/'run01/host.exit.json');cost=read(SOURCE/'run01/spike_cost.exit.json')
    demand(h['returncode']==cost['returncode']==0 and not h['timed_out'] and not cost['timed_out'],'Actual Host/Spike cost numeric receipts')
    log=(SOURCE/'run01/spike_cost.log').read_text();values=[int(x,16) for x in re.findall(r'^0x([0-9a-f]+)$',log,re.M)]
    demand(values[1]-values[0]==2123849 and values[2]==0 and 'cases=682 errors=0' in log,'Actual Spike cost/return evidence')
    demand(ready['DUT_launched'] is False and ready['status']=='PREPARED_SCALAR_OPTIMIZATION_HOST_REFERENCE_COST_NOT_DUT_ENTRY','Explicit preparation-only scope')
    postdrift=[p for p,h in checked.items() if sha(p)!=h]
    demand(not postdrift,'Review pre/post pins changed')
    result=dict(decision='NO_BLOCKER_FOR_SCALAR_TRANSFORMATION_ONLY_NOT_DUT_ENTRY',blocking_findings=[],
      ready_sha256=sha(SOURCE/'READY.json'),checked_pin_count=len(pins),pins_pre_post_unchanged=True,
      original682_order=True,first_call=reference_sequence[0],last_call=reference_sequence[-1],
      input_halfwords_checked=input_checks,output_bits_checked=bit_checks,exhaustive_byte_alternatives=byte_alternatives,flags_checked=flags_checks,
      actual_host_flow_pairs=flow_results,whole_helper_proofs=helper_proofs,
      actual_host_exit=h,actual_spike_cost_exit=cost,reference_retirements=2123849,
      scope_limits=['No new dynamic raw helper/VRF/history reference audit','No relocated-PC DUT worker/oracle audit','Not full17920 parent or original Linux ABI','Per-byte error count differs from per-bit diagnostics, but PASS/fail predicates equivalent'],
      executed_binaries=False,DUT_launched=False,RTL_modified=False)
    save(HERE/'evidence.json',result)
    save(HERE/'review_pins.json',{str(p):sha(p) for p in [SOURCE/'READY.json',SOURCE/'pins.json',CASE/'original/parent.c',CASE/'original/prefix.c',CASE/'prefix.diff',CASE/'wrapper.diff',Path(__file__)]})
    print(json.dumps({k:result[k] for k in ('decision','checked_pin_count','input_halfwords_checked','output_bits_checked','exhaustive_byte_alternatives','flags_checked','last_call')},indent=2))
if __name__=='__main__':main()

