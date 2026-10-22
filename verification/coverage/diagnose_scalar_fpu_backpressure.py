"""Offline diagnosis of the one sealed run; no simulation or population admission."""
import csv
import json
from pathlib import Path
from types import FunctionType
import re
import subprocess
import run_scalar_fpu_backpressure as original

p=original
SEAL='b09ea4216a01a684c50c4eef0475111736dd5d555fb7fbc3a5b3a7489184ba61'
SOURCE_SHA='438409a4f03660f9d02c3a347ce3100fb6231a91a75c2fe99e21ca984ac8d697'
OUT=p.OUT/'scalar-fpu-backpressure-offline-diagnostic-771-agent-20261007-03'


def stdout_audit(text):
    lines=text.splitlines()
    p.require(lines.count('Core Test *** SUCCESS ***')==1 and lines.count('BP_PROBE_READY')==1,
              'Unique actual terminal/probe markers required')
    # Tcl command echo is not an emitted failure. Actual failure marker is anchored.
    for line in lines:
        p.require(not re.match(r'^BP_PROBE_ERROR(?:\s|$)',line) and not re.search(r'\bError-',line),
                  'Actual simulator/probe error')
        if re.search(r'\bUVM_(?:ERROR|FATAL)\b',line):
            p.require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line) is not None,
                      'Actual UVM error/fatal or nonzero summary')
    contracts=[line for line in lines if line.startswith('[ARA_CONTRACT] ')]
    p.require(len(contracts)==1,'Unique actual contract required')
    fields='requests responses exceptions mmu_request_cycles protocol_errors outstanding req_stalled resp_stalled'.split()
    pattern=r'\[ARA_CONTRACT\] '+' '.join(name+r'=(\d+)' for name in fields)
    match=re.fullmatch(pattern,contracts[0])
    p.require(match is not None and all(v=='0' for v in match.groups()),'Exact complete zero contract')
    return dict(zip(fields,map(int,match.groups())))


def guard_loads(rows,address):
    selected=[r for r in rows if int(r['mem_rmask'],16) or int(r['mem_wmask'],16)]
    selected=[r for r in selected if address<=int(r['mem_addr'],16)<address+16]
    expected=[0x539af02c168be47d,0xce71049af28635bd]
    p.require(len(selected)==2,'Exact two initialized guard readbacks required')
    for i,row in enumerate(selected):
        insn=int(row['insn'],16)
        p.require(int(row['mem_addr'],16)==address+8*i and int(row['mem_rmask'],16)==255 and
                  int(row['mem_wmask'],16)==0 and insn&0x707f==0x3003 and
                  int(row['rd'])==(insn>>7)&31 and int(row['rd'])!=0 and
                  int(row['rd_wdata'],16)==expected[i], 'Independent full64 LD guard oracle')
    return expected


def wave_audit(path):
    parse=FunctionType(p.wave.vcd.__code__,dict(p.wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    it=iter(parse(path));_,decl=next(it)
    widths={'state_q':1,'flush_i':1,'fpu_valid_i':1,'fpu_ready_o':1,'fpu_in_ready':1,
            'hold_inputs':1,'use_hold':1,'operand_a_d':64,'operand_b_d':64,'operand_a_q':64,'operand_b_q':64}
    p.require(all(decl.get(p.signal(n),{}).get('width')==w for n,w in widths.items()),'Exact original probe declarations')
    def value(state,name):
        bits=state.get(decl[p.signal(name)]['code'],'x')
        p.require(set(bits)<=set('01'),'Unknown active probe '+name)
        return int(bits,2)
    pending=None;witnesses=[];stalls=0;released=False;idle_flushes=[]
    for time,before,after in it:
        if before.get(decl['ara_tb.clk']['code'])!='0' or after.get(decl['ara_tb.clk']['code'])!='1' or before.get(decl['ara_tb.rst_n']['code'])!='1':continue
        state=value(before,'state_q');valid=value(before,'fpu_valid_i')
        if released:
            p.require(state==0,'Accepted holding request must return READY');released=False
        if value(before,'flush_i'):
            # Ordinary initialization/CSR flush is legal only with no FPU owner.
            p.require(pending is None and state==0 and valid==0 and value(before,'hold_inputs')==0,
                      'Flush cancels an active FPU request')
            idle_flushes.append(time);continue
        if pending is not None:
            p.require(state==1 and value(before,'use_hold')==1 and value(before,'hold_inputs')==0,
                      'Captured request not owned by STALL')
            p.require([value(before,'operand_a_q'),value(before,'operand_b_q')]==pending['operands'],
                      'Held data changed')
            stalls+=1
            if value(before,'fpu_in_ready'):
                p.require(value(before,'fpu_ready_o')==1,'Missing upstream completion')
                witnesses.append(dict(pending,release_time=time));pending=None;released=True
        else:
            p.require(state==0,'Unowned STALL')
            if valid and not value(before,'fpu_in_ready'):
                p.require(value(before,'hold_inputs')==1 and value(before,'fpu_ready_o')==0,'Missing capture controls')
                pending=dict(capture_time=time,operands=[value(before,'operand_a_d'),value(before,'operand_b_d')])
    p.require(pending is None,'Unreleased request')
    return dict(observed=bool(witnesses),captured_released=len(witnesses),stall_cycles=stalls,
                witnesses=witnesses,idle_ownerless_flush_times=idle_flushes)


def main():
    p.require(not OUT.exists(),'Fresh diagnostic only')
    path=p.RUN.with_suffix('.prepared.json')
    record=p.life.read_bound(path,SEAL)
    p.require(p.life.digest(Path(p.__file__))==SOURCE_SHA,'Frozen original consumer identity')
    p.life.check(record['pins'])
    p.require(json.loads((p.RUN/'manifest.json').read_text())==record,'Executed manifest exact')
    status=json.loads((p.RUN/'simulation-status.json').read_text())
    p.require(status.get('returncode')==0 and status.get('status')=='SIMULATION_EXITED_NOT_ADMITTED',
              'Successful bounded terminal required')
    console=(p.RUN/'console.log').read_text()
    contract=stdout_audit(console)
    pre=p.life.read_bound(p.PRE/'preflight.json',record['preflight_seal'])
    pins=p.life.merge_pins(record['pins'],{str(path):SEAL,
        str(Path(__file__).resolve()):p.life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_diagnose_scalar_fpu_backpressure.py')):
            p.life.digest(Path(__file__).with_name('test_diagnose_scalar_fpu_backpressure.py'))})
    for file in p.RUN.rglob('*'):
        if file.is_file():pins=p.life.merge_pins(pins,{str(file):p.life.digest(file)})
    p.life.check(pins);OUT.mkdir()
    try:
        scalar=p.old.architecture.spike_trace.compare_commit_prefix(p.PRE/'spike.trace',p.RUN/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        p.old.architecture.scalar_exact(scalar,pre['counts'])
        p.life.save(OUT/'scalar-comparison.json',scalar)
        with (p.RUN/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        p.require(all(r['event']=='retire' and not int(r['trap']) for r in rows) and
            [int(r['order']) for r in rows]==list(range(len(rows))), 'Complete retire-only prefix')
        memory={}
        for row in rows:
            store=p.old.architecture.scalar_store(row)
            if store:
                address,data=store
                for i,value in enumerate(data):memory[address+i]=value
        def word(address,size=8):return sum(memory[address+i]<<(8*i) for i in range(size))
        symbols=pre['symbols']
        results=[word(symbols['bp_observed']+8*i) for i in range(16)]
        p.require(results==[v for row in p.cases() for v in row['expected']], 'Independent full16 numerical/NaNbox oracle')
        csr=[word(symbols['bp_csr']+8*i) for i in range(5)]
        p.require(csr==[csr[0],64,64,64,csr[0]],'Exact FCSR/flags/restoration')
        guards=guard_loads(rows,symbols['bp_guards'])
        p.require(guards==[0x539af02c168be47d,0xce71049af28635bd] and
            [word(symbols['g75_result'],4),word(symbols['g75_result']+4,4),word(symbols['num_failed'],4),
             word(symbols['tohost'])]==[22,0,0,1], 'Exact guards/22checks/tohost')
        with (p.RUN/'vector_trace.csv').open() as f:
            p.require(all(r['event']=='config' for r in csv.DictReader(f)), 'Unexpected vector data')
        vpd=p.RUN/'scalar-fpu-backpressure.vpd'
        p.require(0<vpd.stat().st_size<=64*1024*1024,'Bounded existing wave')
        with (OUT/'converter.log').open('x') as log:
            subprocess.run([str(p.converter.CONVERTER),str(vpd),str(OUT/'probe.vcd')],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        observed=wave_audit(OUT/'probe.vcd')
        p.life.save(OUT/'backpressure.json',observed)
        p.life.check(pins)
        result=dict(status='OFFLINE_ARCHITECTURE_AND_BACKPRESSURE_DIAGNOSED_NOT_ADMITTED',
            original_worker_failure='Tcl source echo misclassified as emitted BP_PROBE_ERROR; next contract gate omitted mmu_request_cycles',
            scalar_counts=pre['counts'],contract=contract,checks=22,results=results,csr=csr,guards=guards,
            vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',backpressure=observed,
            input_pins=pins,output_pins={str(f):p.life.digest(f) for f in OUT.iterdir()},
            original_artifacts_modified=False,simulation_repeated=False,coverage_admitted=False,
            raw_coverage_gain_not_evaluated=True)
        p.life.save(OUT/'diagnostic.json',result)
        print(json.dumps(dict(seal=p.life.digest(OUT/'diagnostic.json'),backpressure=observed,
                              scalar_counts=pre['counts'])),flush=True)
    except Exception as error:
        p.life.save(OUT/'failure.json',dict(reason=str(error),coverage_admitted=False));raise


if __name__=='__main__':main()
