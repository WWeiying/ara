"""Fixed32nop active DIV reset, two epochs, strict normal recovery, no admission."""
import csv
import json
from pathlib import Path
import re
import subprocess

import run_gap114_fsm as shared
import qualify_gap113_cached_reset as reset

life,require=shared.life,shared.require
APP=life.ROOT/'apps/riscv-tests/isa/rv64uv/vgap115_active_div_reset.c'
PRE=life.OUT/'gap115-active-div-reset-preflight-742-20261007-01'
RUN=life.OUT/'gap115-active-div-reset-old-image-742-20261007-01'
ARGS=['+ARA_UVM_RESET_ON_AXI=read','+ARA_UVM_RESET_READ_INDEX=1',
      '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000']
SYMBOLS=('g115_div','g115_first_ar_load','g115_vrf','g115_csr','g75_result','num_failed','tohost','trap_fail')


def expected_word(i):
    reg=i//16
    return (0x7ffffffffffffffd if reg<8 else 0x2aaaaaaaaaaaaaa9 if reg<16 else
            0x123456789abcdef0 if reg<24 else 0x0101010101010101*(0x40+reg))


def oracle(value):
    require(value('g75_result',0,4)==679 and value('g75_result',4,4)==value('num_failed',0,4)==0 and
            value('tohost')==1,'679 checks/terminal failed')
    for i in range(512):require(value('g115_vrf',8*i)==expected_word(i),'Canonical full VRF differs')
    require([value('g115_csr',8*i) for i in range(5)]==[128,27,0,0,0],'Exact CSR differs')


def build():
    require(not PRE.exists() and not RUN.exists(),'One fresh attempt only')
    book=life.read_bound(shared.reviewed.base.BASE/'admission-manifest.json',shared.reviewed.base.BASE_SHA)
    bitpath=shared.reviewed.base.BASE/'combined-bits.json'
    before=life.read_bound(bitpath,book['output_pins'][str(bitpath)])
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66,'Frozen66 image required')
    pins=dict(plan['image']);pins[str(life.PLAN)]=life.PLAN_SEAL
    pins[str(shared.reviewed.base.BASE/'admission-manifest.json')]=shared.reviewed.base.BASE_SHA
    pins[str(bitpath)]=book['output_pins'][str(bitpath)]
    srcbook=shared.reviewed.base.capture.BUILD/'build-source-pins.json'
    src=life.read_bound(srcbook,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins[str(srcbook)]='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
    for r in ('hardware/tb/ara_tb.sv','hardware/tb/ara_commit_monitor.sv','verification/uvm/ara_cvxif_uvm_pkg.sv',
              'verification/uvm/ara_acc_contract_monitor.sv','hardware/src/lane/simd_div.sv',
              'hardware/src/lane/vmfpu.sv','hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv'):
        p=life.ROOT/r;pins[str(p)]=src[str(p)]
    tb=(life.ROOT/'hardware/tb/ara_tb.sv').read_text()
    require('ARA_UVM_RESET_READ_INDEX=%d' in tb and 'dut.i_ara_soc.i_system.i_ara.axi_req_o.ar_valid' in tb and
            'repeat (4) @(negedge clk);' in tb,'Frozen reset contract differs')
    command=json.loads((shared.template.OUT/'gap104-whole-nf-reserved-preflight-720-20261006-01/compile-command.json').read_bytes())
    command=[str(APP) if x.endswith('/vgap104_whole_nf_reserved.c') else str(PRE/'input.elf') if x.endswith('/input.elf') else x for x in command]
    for p in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_run_gap115_active_reset.py'),
              Path(shared.__file__).resolve(),Path(reset.__file__).resolve(),Path(command[0]),
              life.ROOT/'verification/tests/gap75_start.S',life.ROOT/'verification/tests/gap75.ld'):
        pins[str(p)]=life.digest(p)
    start=(life.ROOT/'verification/tests/gap75_start.S').read_text()
    require('la t0, __bss_start' in start and 'sd zero, 0(t0)' in start and 'la t1, __bss_end' in start,
            'Reset restart BSS initialization unproven')
    life.check(pins);PRE.mkdir();life.save(PRE/'compile-command.json',command)
    with (PRE/'build.log').open('x') as stream:subprocess.run(command,check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    symbols={k:shared.template.s._elf_symbol(PRE/'input.elf',shared.template.s.LLVM/'llvm-readelf',k) for k in SYMBOLS}
    dis=subprocess.check_output([str(shared.template.s.LLVM/'llvm-objdump'),'-d','--no-show-raw-insn',str(PRE/'input.elf')],text=True)
    chunk=dis.split('<g115_div>:')[1].split('<g115_first_ar_load>:')[0]
    require(len(re.findall(r'\bnop\b',chunk))==32,'Actual ELF not fixed32 scalar NOPs')
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    pins[str(spike)]=life.digest(spike)
    sc=[str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(PRE/'input.elf')]
    life.save(PRE/'spike-command.json',sc)
    with (PRE/'spike.trace').open('x') as stream:subprocess.run(sc,check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    commits=shared.shared.spike_trace.parse_spike_commits(PRE/'spike.trace')
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    oracle(lambda n,o=0,size=8:writes.get(symbols[n]+o))
    require(not any(c.pc==symbols['trap_fail'] for c in commits) and 'exception ' not in (PRE/'spike.trace').read_text(),'Unexpected Spike exception')
    counts=shared.shared.reference_counts(commits,symbols)
    for name in ('input.elf','spike.trace','compile-command.json','spike-command.json'):
        pins[str(PRE/name)]=life.digest(PRE/name)
    for p in (life.ROOT/'verification/ara_verify').glob('*.py'):pins[str(p)]=life.digest(p)
    life.check(pins)
    pre=dict(status='SPIKE679_PASS_ACTIVE_RESET_NOT_YET_MEASURED',symbols=symbols,counts=counts,pins=pins,
             source_restart='ELF initialized data restored; startup explicitly clears BSS on both epochs',
             full_scalar_ISA=False,coverage_admitted=False,fixed_nops=32,reset_read_index=1)
    life.save(PRE/'preflight.json',pre)
    return pre,before


def collect(pre,before):
    life.check(pre['pins'])
    log=(RUN/'run.vcs.log').read_text()
    require(log.count('[ARA_UVM_RESET_TEST] kind=read accepted=1 read_index=1')==1 and
            log.count('[ARA_UVM_RESET_TEST] kind=read released=1')==1,'Exact single reset not observed')
    audit=reset.check_real_uvm_log(RUN/'run.vcs.log',require_events=True,require_backend=True,
        require_axi=True,vector_trace=RUN/'vector_trace.csv',reset_kind='read')
    require(audit['status']=='PASS','Reset conservation failed');life.save(RUN/'reset-global-audit.json',audit)
    cf,cr=reset.read_csv(RUN/'commit_trace.csv');vf,vr=reset.read_csv(RUN/'vector_trace.csv')
    epochs,cycle=reset.split_epochs(cr,vr)
    for i,(commits,vectors) in enumerate(epochs):
        ep=RUN/('epoch%d'%i);ep.mkdir();reset.write_csv(ep/'commit_trace.csv',cf,commits);reset.write_csv(ep/'vector_trace.csv',vf,vectors)
    first=epochs[0][1]
    divs=[r for r in first if r['event']=='alloc' and int(r['vd'])==8 and int(r['vl'])==128 and int(r['eew'])==3]
    require(len(divs)==1,'One active DIV required')
    seq=int(divs[0]['arch_seq']);vid=int(divs[0]['vid'])
    require(not any(r['event']=='done' and int(r['arch_seq'])==seq for r in first),'DIV completed before reset')
    require(not any(r['event']=='retire' and int(r['pc'],16)==pre['symbols']['g115_div'] for r in epochs[0][0]),'Cancelled DIV retired')
    ep=RUN/'epoch1';rows=epochs[1][0];memory={}
    for r in rows:
        if r['event']=='retire':
            store=shared.shared.scalar_store(r)
            if store:memory.update({store[0]+i:v for i,v in enumerate(store[1])})
    def value(n,o=0,size=8):
        a=pre['symbols'][n]+o;require(all(a+i in memory for i in range(size)),'Missing recovery byte')
        return int.from_bytes(bytes(memory[a+i] for i in range(size)),'little')
    oracle(value)
    scalar=shared.shared.spike_trace.compare_commit_prefix(PRE/'spike.trace',ep/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    life.save(RUN/'recovery-scalar.json',scalar);shared.shared.scalar_exact(scalar,pre['counts'])
    vector=shared.shared.compare_vector_commits(PRE/'spike.trace',ep/'commit_trace.csv',ep/'vector_trace.csv',0x80000000)
    life.save(RUN/'recovery-vector.json',vector)
    require(vector['status']=='PASS' and vector['compared_instructions']==35 and vector['compared_bytes']==7168 and
            vector['skipped_unknown_bytes']==vector['non_bit_exact_instructions']==vector['unobservable_instructions']==0 and
            not vector['incomplete_requests'] and not vector['unretired_requests'],'Recovery vector oracle failed')
    require(all(i['unknown_write_bytes']==i['skipped_unknown_bytes']==i['mismatch_count']==0 for i in vector['instructions']),
            'Unknown recovery writes')
    inputs=RUN/'measurement-inputs.txt'
    with inputs.open('x') as stream:stream.write(str(shared.reviewed.base.capture.BUILD/'sim/simv.vdb')+'\n'+str(RUN/'code.vdb')+'\n')
    single=shared.shared.bitmap.collect(inputs);delta=shared.shared.bitmap.delta(before,shared.shared.bitmap.combine(before,single))
    hits=[]
    for lane in range(4):
        scope='ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.i_simd_div'%lane
        v=single['metrics']['fsm'][scope];a=before['metrics']['fsm'][scope]
        require(v['width']==29 and v['checksum']==a['checksum']=='1353388720','SIMD shape differs')
        for index in (9,24):hits.append(dict(scope=scope,raw_index=index,before=bool(int(a['bits'],16)&(1<<(28-index))),
                                           single=bool(int(v['bits'],16)&(1<<(28-index)))))
    life.check(pre['pins'])
    life.save(RUN/'single-bits.json',single);life.save(RUN/'raw-delta-742.json',delta)
    life.save(RUN/'strict-result.json',dict(status='TWO_EPOCH_RECOVERY_PASS_RESET_FSM_DIAGNOSTIC_NOT_ADMITTED',
        reset_cycle=cycle,cancelled_div_arch_seq=seq,cancelled_vid=vid,targets=hits,delta=delta,coverage_admitted=False))


def main():
    pre,before=build();pins=life.merge_pins(pre['pins'],{str(PRE/'preflight.json'):life.digest(PRE/'preflight.json')})
    cmd=[str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(PRE/'input.elf'),
         '+TESTCASE=vgap115_active_div_reset','+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(RUN/'commit_trace.csv'),
         '+VECTOR_TRACE='+str(RUN/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch','-cm_dir',str(RUN/'code.vdb'),
         '-cm_name','vgap115_active_div_reset',*ARGS]
    life.run(RUN,dict(case='vgap115_active_div_reset',pins=pins,command=cmd,timeout_s=600,coverage_admitted=False))
    collect(pre,before)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        dest=RUN if RUN.exists() else PRE
        if dest.exists() and not (dest/'failure.json').exists():life.save(dest/'failure.json',dict(reason=str(exc),no_retry=True,coverage_admitted=False))
        raise
