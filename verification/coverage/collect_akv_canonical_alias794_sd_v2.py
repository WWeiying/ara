"""Offline successor: derived SD and exact scalar ECALL records, no skips."""
import argparse
import json
import inspect
from pathlib import Path
from types import FunctionType

import collect_akv_canonical_alias794 as original

life,require=original.life,original.require
OLD_SHA='56dcaa27b430a39458d33de379b3b9867d3087e2a53153174397cd03e16aa7d6'
CSR=life.ROOT/'hardware/deps/cva6/core/csr_regfile.sv'
BOOK=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'


def derived_status(value):
    require(type(value) is int and 0<=value<1<<64,'Exact status bit pattern')
    require(value>>15&3==0,'XS remains outside scoped contract')
    dirty=any(value>>shift&3==3 for shift in (9,13))
    return (value&~(1<<63))|(int(dirty)<<63)


class Model(original.Model):
    def csr_write(self,address,value):
        # First retain the original allowed bits/CSR/address contract. SD is
        # read-only derived state, not the value of the software's write bit.
        super().csr_write(address,value)
        if address==0x300:self.csr[address]=derived_status(self.csr[address])


def ecall_retirement(effect,actual,next_row,expected_pc,handler):
    require(effect==dict(pc=expected_pc,insn=0x73,rd=0,mem_addr=0,mem_rmask=0,mem_wmask=0,trap=1),
        'Exact independently derived S-ecall effect')
    original.old.isa.base.compare_retirement(effect,actual,actual['order'])
    require(actual['rd_wdata']==actual['mem_wdata']==0 and next_row['pc']==handler
        and next_row['insn']==0x342022f3 and next_row['trap']==0 and next_row['rd']==5
        and next_row['rd_wdata']==9,'Precise scalar ECALL no effects and immediately observed mcause9 handler')


def make_replay():
    source=inspect.getsource(original.replay)
    old="""            if e['trap']:
                require(index<len(retires) and retires[index]['pc']==model.pc, 'Precise S exception handler entry');continue
"""
    new="""            if e['trap']:
                require(index+1<len(retires), 'Complete scalar S exception retirement/handler')
                ecall_retirement(e,retires[index],retires[index+1],symbols['akva_ecall'],model.pc)
                index+=1
                continue
"""
    require(source.count(old)==1,'Exact one frozen exception comparison replacement')
    g=dict(original.replay.__globals__,Model=Model,ecall_retirement=ecall_retirement)
    exec(compile(source.replace(old,new),str(Path(__file__).resolve())+':exact_replay','exec'),g)
    return g['replay']


replay=make_replay()


def source():
    require(life.digest(Path(original.__file__))==OLD_SHA,'Frozen original checker drift')
    book=life.read_bound(BOOK,BOOK_SHA);require(life.digest(CSR)==book[str(CSR)],'Frozen CSR source drift')
    original.old.isa.base.source_anchors(CSR.read_text(),[
        'if (CVA6Cfg.RVS || CVA6Cfg.RVF || CVA6Cfg.RVV) begin mstatus_d.sd = (mstatus_d.xs == riscv::Dirty) | (mstatus_d.fs == riscv::Dirty) | (mstatus_d.vs == riscv::Dirty);',
        'assign mstatus_extended = CVA6Cfg.IS_XLEN64 ? mstatus_q[CVA6Cfg.XLEN-1:0]'])
    return {str(Path(original.__file__).resolve()):OLD_SHA,str(CSR):book[str(CSR)],str(BOOK):BOOK_SHA}


def diagnose(run,out):
    run,out=Path(run).absolute(),Path(out).absolute()
    require(out.parent==life.OUT and not out.exists(),'Fresh diagnosis only')
    pins=source();m=json.loads((run/'manifest.json').read_bytes());pre=m['preflight']
    elf=Path(pre['input_elf']);require(life.digest(elf)==m['pins'][str(elf)],'Actual native ELF identity')
    trace=run/'commit_trace.csv';rr=[r for r in original.old.isa.base.native.commit_rows(trace) if r['event']=='retire']
    model=original.Model(elf.read_bytes(),pre['symbols']);history=[];i=0
    while not model.terminal:
        prior=dict(pc=model.pc,priv=model.priv,mstatus=model.csr[0x300],csrs=dict(model.csr))
        e=model.step()
        if e['trap']:continue
        try:original.old.isa.base.compare_retirement(e,rr[i],i)
        except ValueError as exc:
            require(i==32191 and e['pc']==0x8000255c and e['insn']==0x30002573
                and e['rd_wdata']==0xa00006600 and rr[i]['rd_wdata']==derived_status(e['rd_wdata']), 'Exact original first SD mismatch')
            record=dict(status='SOURCE_BOUND_CHECKER_SD_WRITE_DERIVATION_ERROR_NOT_RTL_BUG',
                first_error=str(exc),retirement=i,expected=e,actual=rr[i],before=prior,preceding_CSRs=history,
                corrected_exact_read=derived_status(e['rd_wdata']),source_lines=[1996,1997,1998],
                original_failure_preserved=True,no_EDA=True,coverage_admitted=False)
            break
        if e['insn']&127==0x73:history.append(dict(retirement=i,before=prior,effect=e,after=dict(model.csr)))
        i+=1
    else:raise ValueError('Expected original mismatch absent')
    for p in (run/'manifest.json',trace,elf):pins[str(p)]=life.digest(p)
    reference=original.case.OUT/'akv-canonical-alias794-preflight-agent-20261008-02/spike.stderr'
    import re
    lines=[l for l in reference.read_text().splitlines() if re.search(r'\(0x30002573\)\s+x10\s+0x8000000a00006600$',l)]
    require(lines,'Independent software Spike derived SD read')
    record['software_Spike_corresponding_status_reads']=lines
    record['software_Spike_is_not_custom_reference']=True
    pins[str(reference)]=life.digest(reference)
    vcd=life.OUT/'akv-canonical-alias794-qualified-parent-20261008-01/akv-alias.vcd'
    require(vcd.is_file(),'Original converted wave retained')
    pins[str(vcd)]=life.digest(vcd)
    record['VCD_CSR_boundary']='Focused AKV wave has no CVA6 mstatus object; CSR first difference is exact native retirement, not an inferred waveform CSR value'
    ecalls=[r for r in rr if r['insn']==0x73]
    require(len(ecalls)==2,'Exactly two native scalar ECALL records')
    record['scalar_ECALL_native_records']=ecalls
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_akv_canonical_alias794_sd_v2.py').resolve()):pins[str(p)]=life.digest(p)
    record['input_pins']=pins;life.check(pins);out.mkdir();life.save(out/'diagnosis.json',record)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'diagnosis.json'),status=record['status'])))


def collect(run,seal,out,diagnosis,diagnosis_seal):
    out=Path(out).absolute();require(not out.exists(),'Fresh successor qualification')
    pins=source()
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_akv_canonical_alias794_sd_v2.py').resolve()):pins[str(p)]=life.digest(p)
    diagnosis=Path(diagnosis).absolute();d=life.read_bound(diagnosis,diagnosis_seal)
    require(d['status']=='SOURCE_BOUND_CHECKER_SD_WRITE_DERIVATION_ERROR_NOT_RTL_BUG' and d['retirement']==32191
        and d['input_pins'][str(Path(run).absolute()/'manifest.json')]==seal
        and all(d['input_pins'].get(p)==h for p,h in pins.items()), 'Exact same-run diagnosis/source/successor/test binding')
    pins=life.merge_pins(pins,d['input_pins']);pins=life.merge_pins(pins,{str(diagnosis):diagnosis_seal})
    life.check(pins)
    invoke=FunctionType(original.collect.__code__,dict(original.collect.__globals__,replay=replay))
    invoke(run,seal,out)
    q=out/'qualification.json';core=json.loads(q.read_bytes());life.check(core['input_pins']);life.check(core['output_pins']);life.check(pins)
    receipt=dict(status='EXACT_SD_DERIVATION_SUCCESSOR_ALL_ORIGINAL_GATES_QUALIFIED',
        core_qualification=str(q),core_sha256=life.digest(q),successor_pins=pins,
        input_pins=life.merge_pins(life.merge_pins(core['input_pins'],core['output_pins']),pins),
        diagnosis=str(diagnosis),diagnosis_sha256=diagnosis_seal,
        original_checker_sha256=OLD_SHA,scope='Derived SD after scoped CSR writes; two exact scalar S-ecall trap retirements and immediate handler',
        fields_masked=[],skipped_retirements=0,native_custom_Spike=False,coverage_admitted=False,
        scalar_ECALLs='Both exact scalar ECALL trap retirements compared, not skipped; immediate handler mcause9 required')
    life.save(out/'sd-successor-receipt.json',receipt)
    print(json.dumps(dict(output=str(out),qualification_sha256=receipt['core_sha256'],
        receipt_sha256=life.digest(out/'sd-successor-receipt.json'))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('diagnose','collect'));p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--run-seal')
    p.add_argument('--diagnosis',type=Path);p.add_argument('--diagnosis-seal');a=p.parse_args()
    if a.mode=='diagnose':require(a.run_seal is None,'Diagnosis uses exact original failure');diagnose(a.run,a.output)
    else:
        require(bool(a.run_seal) and a.diagnosis is not None and bool(a.diagnosis_seal),'Explicit frozen run and diagnosis seals')
        collect(a.run,a.run_seal,a.output,a.diagnosis,a.diagnosis_seal)
