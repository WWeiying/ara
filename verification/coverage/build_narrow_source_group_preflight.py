"""One source-group illegal encoding + legal recovery. Software only; no VCS."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

import build_readonly_csr_preflight as prior
from inventory_operand_debug import Design, points
from closure_point_inventory import read_xml

life, require, shared = prior.life, prior.require, prior.shared
ROOT, OUT, LLVM, SPIKE = prior.ROOT, prior.OUT, prior.LLVM, prior.SPIKE
BASE = OUT/'readonly-csr-offline-admitted-735-parent-20261006-01'
BASE_SEAL = '4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397'
REFERENCE = OUT/'readonly-csr-preflight-v3-733-agent-20261006-01'
REFERENCE_SEAL = 'cfc86e25e0784f6d41b4a6e8d93b66e19c5e97587a2cd02cd8a35b61e0e9a676'
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vnarrow_source_group_illegal.c'
FAULT = (46<<26)|(1<<25)|(9<<20)|(20<<15)|(24<<7)|0x57
CHECKS = 2130
SYMBOLS = ('_start','_end','tohost','trap_fail','g75_result','num_failed','ng_fault','ng_recovery',
           'ng_handler_begin','ng_handler_end','ng_trap','ng_count','ng_rd','ng_before','ng_after',
           'ng_source','ng_old','ng_dump','ng_recovered')


def expected_buffer(name):
    require(name in ('ng_source','ng_old','ng_dump','ng_recovered'),'Unknown oracle buffer')
    values=[0xa5]*528
    if name=='ng_source':
        values[8:520]=[(i*13+0x27)&255 for i in range(512)]
    elif name=='ng_recovered':
        values[8:16]=[(i*13+0x27+3)&255 for i in range(8)]
    return bytes(values)


def static():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    bits=life.read_bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    require(len(bits['tests'])==len(set(bits['tests']))==735,'Unique formal735 required')
    ref=life.read_bound(REFERENCE/'preflight-manifest.json',REFERENCE_SEAL)
    pins=life.merge_pins(ref['pins'],manifest['output_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,
                             str(REFERENCE/'preflight-manifest.json'):REFERENCE_SEAL})
    source=life.read_bound(prior.SOURCE,prior.SOURCE_SEAL)
    snapshot=OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    require(life.digest(life.IMAGE)==prior.IMAGE_SHA and
            life.digest(snapshot)==source[str(ROOT/'hardware/src/ara_dispatcher.sv')],
            'Frozen image/source identity differs')
    text=snapshot.read_text().splitlines()
    require("LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000)" in text[1965] and
            'VNCLIPU' in '\n'.join(text[1953:1959]),'Frozen source decode/legality path differs')
    design=Design(Path(str(life.IMAGE)+'.vdb')); scope=prior.SCOPE
    require(design.hierarchy[scope].get('chksum')=='1448229316','Compiled module differs')
    targets=[]
    for metric,index,width,checksum in (('cond',224,1140,'1370170966'),('line',407,1718,'1316526434')):
        row=bits['metrics'][metric][scope]
        require((row['width'],row['checksum'])==(width,checksum),'Compiled metric shape differs')
        if metric=='cond':
            nodes=[n for n in read_xml(design.db/'shape/cond.verilog.shape.xml')
                   if n.get('id')==design.hierarchy[scope].get('id') and n.get('chksum')==checksum]
            require(len(nodes)==1,'Unique condition definition required'); definition=nodes[0]
        else: definition=design.definition(scope,metric)
        point=next(p for p in points(metric,definition,width) if p['raw_index']==index)
        require(point['line']=='1966' and point['file_id']=='547','Compiled source coordinate differs')
        require(point['expression']==("((insn.varith_type.rs2 & 5'b00111) != 5'b0)" if metric=='cond'
                else "illegal_insn = 1'b1;"),'Compiled expression differs')
        if metric=='cond':
            require(point['native_id']=='91' and point['vector']=='1' and
                point['attributes']['chksum']=='461516933','Exact condition signature differs')
        require(not (int(row['bits'],16)>>(width-1-index)&1),'Primary target already hit')
        targets.append(dict(scope=scope,metric=metric,width=width,checksum=checksum,
                            module_checksum='1448229316',point=point,before735=False))
    deps=(APP,Path(__file__).resolve(),Path(__file__).with_name('test_narrow_source_group_preflight.py'))
    pins=life.merge_pins(pins,{str(x):life.digest(x) for x in deps})
    life.check(pins)
    return dict(baseline=735,baseline_seal=BASE_SEAL,targets=targets,pins=pins,
        hypothesis='Misaligned vs2=9 for narrowing EMUL8 is rejected before backend allocation',
        rejected_opcode=FAULT,configuration=dict(SEW=8,LMUL=4,VL=8,source_EEW=16,source_EMUL=8),
        legal_arithmetic_gap_claimed=False,requester_gain_claimed=False,branch_native_ID_not_guessed=True,
        excluded_targets=['dispatcher cond493','CSR targets','MaskB/StA source-lifetime010 unproved'],
        coverage_admitted=False,vcs_started=False)


def validate(commits,symbols,trace):
    events=re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)',trace)
    require([(n,int(pc,16)) for n,pc in events]==[('trap_illegal_instruction',symbols['ng_fault'])] and
            trace.count('exception ')==1,'Exact single illegal trap required')
    require(not any(c.pc in (symbols['ng_fault'],symbols['trap_fail']) or c.fpr_writes for c in commits),
            'Illegal normal retirement/fatal trap/implicit FP')
    memory={}; terminal=[]; vectors=[]; handler_stores=[]
    for c in commits:
        for address,value in c.memory_accesses:
            if value is None:continue
            width=shared.store_width(c.instruction)
            require(0<=value<1<<(width*8),'Store width overflow')
            for i in range(width):memory[address+i]=(value>>(i*8))&255
            if address==symbols['tohost']:terminal.append(value)
            if symbols['ng_handler_begin']<=c.pc<symbols['ng_handler_end']:
                handler_stores.append((address,width))
        vectors.extend((c.pc,reg,value) for reg,value in c.vector_writes.items())
    def read(name,offset=0,width=8):
        address=symbols[name]+offset
        require(all(address+i in memory for i in range(width)),'Missing oracle bytes: '+name)
        return int.from_bytes(bytes(memory[address+i] for i in range(width)),'little')
    require(terminal==[1] and read('g75_result',width=4)==CHECKS and
            read('g75_result',4,4)==read('num_failed',width=4)==0,'Incomplete self-check')
    require([read('ng_trap',8*j) for j in range(4)]==[1,2,symbols['ng_fault'],FAULT] and
            read('ng_count')==1 and read('ng_rd')==0x7193a65bc24de80f,'Exact trap/rd ledger differs')
    for name in ('ng_before','ng_after'):
        require([read(name,8*i) for i in range(6)]==[8,2,128,0,2,1],'CSR preservation differs')
    for name in ('ng_source','ng_old','ng_dump','ng_recovered'):
        require(bytes(read(name,i,1) for i in range(528))==expected_buffer(name),'Full memory/guard differs: '+name)
    handler=[c for c in commits if symbols['ng_handler_begin']<=c.pc<symbols['ng_handler_end']]
    require(sum(c.pc==symbols['ng_handler_begin'] for c in handler)==1 and
            all(not c.vector_writes and not c.fpr_writes and set(c.gpr_writes)<={2,5,6,7} and
                set(c.csr_writes)<={0x300,0x341} for c in handler),'Handler footprint differs')
    ledger=Counter((symbols['ng_trap']+8*j,8) for j in range(4));ledger[(symbols['ng_count'],8)]=1
    actual=Counter((a,w) for a,w in handler_stores if not 0x80100000<=a<0x80200000)
    require(actual==ledger and len(handler_stores)==8,'Exact handler stores differ')
    require(sum(c.pc==symbols['ng_recovery'] for c in commits)==1,'Missing recovery')
    latest={reg:value for _,reg,value in vectors}
    require(set(latest)==set(range(20,28)),'Extra/missing vector destination registers')
    for base,name in ((20,'ng_source'),(24,'ng_recovered')):
        expected=expected_buffer(name)[8:520]
        for i in range(4):
            require(latest[base+i]==int.from_bytes(expected[128*i:128*(i+1)],'little'),'Full VRF image differs')
    return dict(status='NARROW_SOURCE_GROUP_SPIKE_PASS_NOT_DUT',checks=CHECKS,illegal_traps=1,
                cause=2,exact_tval_mepc=True,full_memory_bytes=2112,full_VRF_bytes=1024,
                native_cycle_qualified=False,coverage_admitted=False)


def build(out):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh direct output required')
    receipt=static();pins=receipt['pins'];out.mkdir();life.save(out/'target-receipt.json',receipt)
    command=json.loads((REFERENCE/'compile-command.json').read_bytes())
    require(command[-4]==str(prior.ROOT/'verification/tests/readonly_csr_start.S') and command[-2]=='-o',
            'Frozen compiler command contract differs')
    command[-3]=str(APP);command[-1]=str(out/'input.elf')
    command.insert(command.index('-ffreestanding'),'-mno-implicit-float')
    spike=[str(SPIKE),'--isa=rv64gcv_zvl1024b','--priv=msu','--pmpregions=0',
           '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
    try:
        life.save(out/'compile-command.json',command)
        with (out/'compile.log').open('x') as log:
            subprocess.run(command,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
        symbols={n:shared._elf_symbol(out/'input.elf',LLVM/'llvm-readelf',n) for n in SYMBOLS}
        require(symbols['_start']==0x80000000 and symbols['tohost']==0x80001000 and
                0x80000000<symbols['_end']<0x80100000,'ELF load/range differs')
        blob=(out/'input.elf').read_bytes()
        require(prior.elf_word(blob,symbols['ng_fault'])==FAULT and
                prior.elf_word(blob,symbols['ng_recovery'])==0x0341bc57,'Exact fault/recovery words differ')
        dis=subprocess.check_output([str(LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
        rvv=[]
        for line in dis.splitlines():
            match=re.match(r'\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+){2,4})',line)
            if not match:continue
            raw=bytes.fromhex(match[2]);word=int.from_bytes(raw,'little')
            if len(raw)==4 and (word&127==0x57 or word&127 in (7,39) and word>>12&7 in (0,5,6,7)):
                rvv.append((int(match[1],16),word))
        require(len(rvv)==12 and sum(pc==symbols['ng_fault'] for pc,_ in rvv)==1,
                'Exact12 explicit RVV opcodes required; implicit lowering forbidden')
        life.save(out/'linked-proof.json',dict(symbols=symbols,RVV_opcodes=rvv,implicit_vector_forbidden=True))
        life.save(out/'spike-command.json',spike)
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace:
            subprocess.run(spike,check=True,timeout=180,stdout=stdout,stderr=trace)
        result=validate(shared.parse_spike_commits(out/'spike.trace'),symbols,(out/'spike.trace').read_text())
        life.save(out/'spike-validation.json',result);life.check(pins)
        pins=life.merge_pins(pins,{str(x):life.digest(x) for x in out.iterdir() if x.is_file()})
        life.save(out/'preflight-manifest.json',dict(status='SOFTWARE_PREFLIGHT_PASS_NOT_DUT_NOT_ADMITTED',
            baseline=735,baseline_seal=BASE_SEAL,targets=receipt['targets'],pins=pins,validation=result,
            elf_sha256=life.digest(out/'input.elf'),VCS_started=False,coverage_admitted=False))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight-manifest.json'),validation=result)))
    except Exception as error:
        life.save(out/'failure.json',dict(status='SOFTWARE_PREFLIGHT_FAILURE_NOT_DUT',reason=str(error)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output.absolute())
