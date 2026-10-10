"""One bounded speculative-load flush experiment; no automatic admission."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import build_gap104_preflight as template
import collect_gap103_strict as shared
import capture_fsm124 as reviewed

life, require = reviewed.life, reviewed.require
APP=life.ROOT/'apps/riscv-tests/isa/rv64uv/vgap114_spec_load_flush.c'
PRE=life.OUT/'gap114-spec-load-flush-preflight-742-20261007-01'
RUN=life.OUT/'gap114-spec-load-flush-old-image-742-20261007-01'
SYMBOLS=('g114_trap_a','g114_trap_b','g114_trap_recovery','g114_cancelled_load_a',
         'g114_cancelled_load_b','g114_cancelled_store','g114_fatal','g114_ledger',
         'g114_traps','g114_data','g114_guards','g114_recovered','g114_vrf','g114_csr',
         'g114_restore','g75_result','num_failed','tohost')


def oracle(value,symbols):
    require(value('g75_result',0,4)==2619 and value('g75_result',4,4)==value('num_failed',0,4)==0,
            '2619 software checks failed')
    require(value('tohost')==1 and value('g114_traps')==8,'Terminal/trap count differs')
    for phase in range(4):
        dividend=(1<<(24 if phase&1 else 12))-1
        ledger=[value('g114_ledger',(2*phase)*40+8*i) for i in range(5)]
        pc=symbols['g114_trap_a' if phase<2 else 'g114_trap_b']
        require(ledger==[9,pc,0,dividend//3,0x6a39c572e1048dbf],'Precise cancellation ledger differs')
        recovery=[value('g114_ledger',(2*phase+1)*40+8*i) for i in range(5)]
        require(recovery==[9,symbols['g114_trap_recovery'],0,0,0x13579bdf2468ace0],'Recovery ledger differs')
        require(value('g114_recovered',8*phase)==0x13579bdf2468ace0,'Recovery data differs')
        for i in range(512):
            require(value('g114_guards',phase*4096+8*i)==0x13579bdf2468ace0+i,'Younger store altered memory')
    for i in range(512):
        require(value('g114_vrf',8*i)==0x0101010101010101*(0x40+i//16),'Preserved VRF differs')
    require([value('g114_csr',8*i) for i in range(6)]==[128,0,0,0,0,0],'CSR differs')
    for i in range(0,8,2): require(value('g114_restore',8*i)==value('g114_restore',8*(i+1)),'Handler restoration differs')


def reference(trace,symbols):
    commits=shared.spike_trace.parse_spike_commits(trace)
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    oracle(lambda n,o=0,size=8:writes.get(symbols[n]+o),symbols)
    bad={symbols[n] for n in ('g114_cancelled_load_a','g114_cancelled_load_b','g114_cancelled_store','g114_fatal')}
    require(not any(c.pc in bad for c in commits),'Cancelled instruction retired')
    events=re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)',trace.read_text())
    pcs=[symbols['g114_trap_a' if p<2 else 'g114_trap_b'] for p in range(4)]
    expected=[pc for p in pcs for pc in (p,symbols['g114_trap_recovery'])]
    require(len(events)==8 and [int(pc,16) for _,pc in events]==expected,'Spike exceptions differ')
    return shared.reference_counts(commits,symbols)


def build():
    require(not PRE.exists() and not RUN.exists(),'No repeat experiment')
    book=life.read_bound(reviewed.base.BASE/'admission-manifest.json',reviewed.base.BASE_SHA)
    bits=life.read_bound(reviewed.base.BASE/'combined-bits.json',book['output_pins'][str(reviewed.base.BASE/'combined-bits.json')])
    pins={str(reviewed.base.BASE/'admission-manifest.json'):reviewed.base.BASE_SHA,
          str(reviewed.base.BASE/'combined-bits.json'):book['output_pins'][str(reviewed.base.BASE/'combined-bits.json')]}
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['simv']==str(life.IMAGE),'Wrong frozen image')
    pins=life.merge_pins(pins,plan['image']);pins[str(life.PLAN)]=life.PLAN_SEAL
    sourcebook=reviewed.base.capture.BUILD/'build-source-pins.json'
    oldpins=book['input_pins']
    expected=oldpins.get(str(sourcebook)) or json.load(open(reviewed.base.BASE/'evidence-pins.json'))[str(sourcebook)]
    src=life.read_bound(sourcebook,expected);pins[str(sourcebook)]=expected
    for r in ('core/load_unit.sv','core/load_store_unit.sv','core/cva6_mmu/cva6_mmu.sv',
              'core/cva6_mmu/cva6_ptw.sv','core/ex_stage.sv','core/controller.sv','core/commit_stage.sv',
              'core/issue_read_operands.sv','core/scoreboard.sv'):
        p=life.ROOT/'hardware/deps/cva6'/r;pins[str(p)]=src[str(p)]
    command=json.loads((template.OUT/'gap104-whole-nf-reserved-preflight-720-20261006-01/compile-command.json').read_bytes())
    command=[str(APP) if x.endswith('/vgap104_whole_nf_reserved.c') else str(PRE/'input.elf') if x.endswith('/input.elf') else x for x in command]
    for p in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_run_gap114_fsm.py'),
              Path(command[0]),life.ROOT/'verification/tests/gap75_start.S',life.ROOT/'verification/tests/gap75.ld'):
        pins[str(p)]=life.digest(p)
    life.check(pins);PRE.mkdir();life.save(PRE/'input-pins.json',pins)
    life.save(PRE/'compile-command.json',command)
    with (PRE/'build.log').open('x') as stream:subprocess.run(command,check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    symbols={k:template.s._elf_symbol(PRE/'input.elf',template.s.LLVM/'llvm-readelf',k) for k in SYMBOLS}
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    pins[str(spike)]=life.digest(spike)
    spike_command=[str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(PRE/'input.elf')]
    life.save(PRE/'spike-command.json',spike_command)
    with (PRE/'spike.trace').open('x') as stream:subprocess.run(spike_command,check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    counts=reference(PRE/'spike.trace',symbols)
    for name in ('input.elf','spike.trace','compile-command.json','spike-command.json'):
        pins[str(PRE/name)]=life.digest(PRE/name)
    targets={ 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.i_load_unit':[34,37],
             reviewed.base.capture.PTW:[21,25] }
    for s,indices in targets.items():
        v=bits['metrics']['fsm'][s]
        require(all(not(int(v['bits'],16)&(1<<(v['width']-1-i))) for i in indices),'Target already hit')
    life.check(pins)
    pre=dict(status='SPIKE_PREFLIGHT_PASS_NOT_RTL',symbols=symbols,counts=counts,pins=pins,
             targets=targets,baseline_tests=742,checks=2619,coverage_admitted=False)
    life.save(PRE/'preflight.json',pre)
    return pre,bits


def collect(pre,before):
    life.check(pre['pins'])
    rows=list(csv.DictReader((RUN/'commit_trace.csv').open()))
    memory={}
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(len(retired))),'Retirement prefix differs')
    for r in retired:
        store=shared.scalar_store(r)
        if store: memory.update({store[0]+i:v for i,v in enumerate(store[1])})
    def value(n,o=0,size=8):
        a=pre['symbols'][n]+o
        require(all(a+i in memory for i in range(size)),'Unobserved oracle byte')
        return int.from_bytes(bytes(memory[a+i] for i in range(size)),'little')
    oracle(value,pre['symbols'])
    scalar=shared.spike_trace.compare_commit_prefix(PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    life.save(RUN/'scalar-comparison.json',scalar);shared.scalar_exact(scalar,pre['counts'])
    vector=shared.compare_vector_commits(PRE/'spike.trace',RUN/'commit_trace.csv',RUN/'vector_trace.csv',0x80000000)
    life.save(RUN/'vector-comparison.json',vector)
    require(vector['status']=='PASS' and vector['compared_instructions']==32 and vector['compared_bytes']==4096 and
            vector['skipped_unknown_bytes']==vector['non_bit_exact_instructions']==vector['unobservable_instructions']==0 and
            not vector['incomplete_requests'] and not vector['unretired_requests'],'Vector oracle differs')
    require(all(i['unknown_write_bytes']==i['skipped_unknown_bytes']==i['mismatch_count']==0 for i in vector['instructions']),
            'Unknown vector bytes')
    console=(RUN/'console.log').read_text()
    require(console.count('Core Test *** SUCCESS ***')==1 and not shared.check_contract_log(RUN/'run.vcs.log'),'TB failure')
    ledger=RUN/'measurement-inputs.txt'
    with ledger.open('x') as stream:stream.write(str(reviewed.base.capture.BUILD/'sim/simv.vdb')+'\n'+str(RUN/'code.vdb')+'\n')
    single=shared.bitmap.collect(ledger);union=shared.bitmap.combine(before,single)
    delta=shared.bitmap.delta(before,union)
    hits=[]
    for scope,indices in pre['targets'].items():
        a,b=before['metrics']['fsm'][scope],single['metrics']['fsm'][scope]
        require((a['checksum'],a['width'])==(b['checksum'],b['width']),'FSM shape differs')
        for index in indices: hits.append(dict(scope=scope,raw_index=index,hit=bool(int(b['bits'],16)&(1<<(b['width']-1-index)))))
    life.check(pre['pins'])
    life.save(RUN/'single-bits.json',single);life.save(RUN/'raw-delta-742.json',delta)
    life.save(RUN/'target-hits.json',hits)
    life.save(RUN/'strict-result.json',dict(status='ARCHITECTURE_PASS_RAW_DIAGNOSTIC_NOT_ADMITTED',checks=2619,
        targets=hits,delta=delta,coverage_admitted=False,baseline_tests=742))


def main():
    pre,bits=build()
    pins=life.merge_pins(pre['pins'],{str(PRE/'preflight.json'):life.digest(PRE/'preflight.json')})
    cmd=[str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(PRE/'input.elf'),
         '+TESTCASE=vgap114_spec_load_flush','+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(RUN/'commit_trace.csv'),
         '+VECTOR_TRACE='+str(RUN/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch','-cm_dir',str(RUN/'code.vdb'),'-cm_name','vgap114_spec_load_flush']
    life.run(RUN,dict(case='vgap114_spec_load_flush',pins=pins,command=cmd,timeout_s=600,coverage_admitted=False))
    collect(pre,bits)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        dest=RUN if RUN.exists() else PRE
        if dest.exists() and not (dest/'failure.json').exists():life.save(dest/'failure.json',dict(reason=str(exc),no_retry=True,coverage_admitted=False))
        raise
