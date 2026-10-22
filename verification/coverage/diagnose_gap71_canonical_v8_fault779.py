"""Read existing rejected capture; seal byte-level diagnosis, never qualify or simulate."""
import argparse
import csv
from dataclasses import replace
from pathlib import Path
import struct
from ara_verify.vector_commit import _parse_vector_trace, _architectural_bytes
import preflight_gap71_canonical779 as p

ROOT=p.ROOT
RUN=ROOT/'verification/out/gap71-canonical-qbs-positive779-run-agent-20261008-03'
PRE=ROOT/'verification/out/gap71-canonical779-qbs-positive-preflight-agent-20261008-03/preflight.json'
SNAP=ROOT/'verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv'
SOURCE_SHA='9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'


def diagnose(output):
    p.need(output.parent==ROOT/'verification/out' and not output.exists(),'Fresh diagnostic artifact')
    pre=p.h.read(PRE); p.need(p.h.sha(PRE)=='2a73b8a7ee19b477288f6a6f1b021ca732b23e4917030a986ef31e329a50de39','Preflight pin')
    book=ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    p.need(p.h.sha(SNAP)==SOURCE_SHA==p.h.read(book)[str(ROOT/'hardware/src/ara_dispatcher.sv')],'Frozen dispatcher snapshot')
    source=SNAP.read_text()
    p.need('eew_d[layout_req.vd + i]       = layout_req.vtype.vsew;' in source
        and 'ara_req.eew_vd_op = EW32;' in source, 'Exact frozen metadata paths')
    with (RUN/'commit_trace.csv').open(newline='') as stream: rows=list(csv.DictReader(stream))
    with (RUN/'vector_trace.csv').open(newline='') as stream: vector_rows=list(csv.DictReader(stream))
    lanes,vlen,acts=_parse_vector_trace(RUN/'vector_trace.csv')
    p.need((lanes,vlen)==(4,1024),'Frozen lane geometry')
    starts=[r for r in rows if r['event']=='arch_start' and int(r['insn'],16)==0x00b5045b]
    p.need(len(starts)==2,'Exactly fault and retry custom attempts')
    fault_seq,retry_seq=[int(r['order']) for r in starts]
    fault,retry=acts[fault_seq],acts[retry_seq]
    p.need(fault.allocations==fault.completions==1 and not fault.writes,'Fault raw VRF writes must be absent')
    retry_bytes=bytes(v for (r,i),(v,w) in sorted(_architectural_bytes(retry.writes,4,1024).items()))
    p.need(retry_bytes==struct.pack('<32I',0xc0c00000,*([0]*31)),'Retry numerical bytes exact')
    seed_entries=[(seq,a) for seq,a in acts.items() if any(32<=w.addr<36 for w in a.writes)
        and seq<fault_seq]
    p.need(len(seed_entries)==1,'Unique initial physical v8 writer')
    seed_seq,seed_activity=seed_entries[0]
    base=pre['artifacts']['dut']['metadata']['symbols']['gap71_output']+64+8*128
    reads={}
    for row in rows:
        address=int(row['mem_addr'],16)
        if row['event']=='retire' and int(row['mem_rmask'],16)==255 and base<=address<base+128:
            value=int(row['rd_wdata'],16)
            p.need(address not in reads or reads[address]==value,'Snapshot readback changed')
            reads[address]=value
    p.need(set(reads)=={base+i*8 for i in range(16)},'Full fault v8 readback')
    actual=struct.pack('<16Q',*[reads[base+i*8] for i in range(16)])
    gold=struct.pack('<16Q',*[p.audit.seed(128+i) for i in range(16)])
    decoded={}
    for eew in range(4):
        values=_architectural_bytes([replace(w,eew=eew) for w in seed_activity.writes],4,1024)
        decoded[eew]=bytes(v for (r,i),(v,w) in sorted(values.items()) if r==8)
    p.need(decoded[0]==gold and decoded[2]==actual and decoded[1]!=actual and decoded[3]!=actual,
        'Exact byte-layout differential, not a pattern guess')
    stores=[r for r in rows if r['event']=='retire' and int(r['insn'],16)==0x02828427]
    p.need(len(stores)==2 and int(stores[0]['cycle'])<int(starts[1]['cycle']),'Fault snapshot before retry')
    projection={}
    for row in rows:
        a=int(row['mem_addr'],16); b=pre['artifacts']['dut']['metadata']['symbols']['gap71_records']
        if row['event']=='retire' and int(row['mem_rmask'],16)==255 and b<=a<b+192:
            phase,slot=divmod((a-b)//8,12); projection[f'{phase}:{slot}']=row['rd_wdata']
    p.need(int(projection['0:0'],16)==13 and int(projection['0:2'],16)==0x1555402080,
        'Actual fault CSR record identity')
    paths=[PRE,SNAP,book,Path(__file__),RUN/'commit_trace.csv',RUN/'vector_trace.csv',RUN/'run.vcs.log',
        RUN/'simulation-status.json',RUN/'qbs-canonical-focused.vpd',
        ROOT/'verification/out/closure92-current-20261005-01/outcomes/gap71_qbs_fault.json',
        ROOT/'verification/out/qbs-fault-layout-repair-20261005-01/results/gap71_qbs_fault/audit.json',
        ROOT/'verification/out/qbs-fault-layout-repair-20261005-01/image/build-status.json']
    pins=p.h.pins(paths); p.h.verify(pins)
    p.h.save(output,dict(status='FUNCTIONAL_FAIL_INDEX60_BYTE_LAYOUT_DIAGNOSED_NOT_ADMITTED',
        checks=dict(preceding=51,index=60,snapshot=0,register=8,all16_words_differ=True),
        native_fault=dict(arch_seq=fault_seq,alloc=fault.allocations,done=fault.completions,writes=0,
            allocation_EEW=fault.eew,allocation_VL=fault.vl,CSR_records=projection),
        native_seed=dict(arch_seq=seed_seq,recorded_EEW=seed_activity.eew,
            instruction=hex(seed_activity.instruction),physical_writes=len(seed_activity.writes)),
        native_retry=dict(arch_seq=retry_seq,write_bytes=len(retry_bytes),first_word='0xc0c00000'),
        snapshot=dict(address=hex(base),store_cycle=int(stores[0]['cycle']),store_pc=stores[0]['pc'],
            retry_start_cycle=int(starts[1]['cycle']),actual_hex=actual.hex(),gold_hex=gold.hex(),
            words=[dict(i=i,actual=hex(reads[base+i*8]),expected=hex(p.audit.seed(128+i))) for i in range(16)]),
        exact_permutation=dict(EW8_matches_gold=True,EW32_matches_actual_all128bytes=True,
            other_EEW_match_actual=False,method='Same observed physical writes, independently change only byte-des huffle EEW'),
        source=dict(snapshot=str(SNAP),sha256=SOURCE_SHA,qbexec_force_EW32_line=4944,
            metadata_update_line=5903,blocked_cleanup_line=5871,
            gate='ara_req_valid_d && ara_req_d.use_vd && ara_req_ready_i && state_q != OVERLAP_PREFIX_FIXUP',
            selector='backend_req -> segment layout_req; decode_blocked selects idle committed path and init_decoder_outputs',
            no_terminal_success_condition_on_metadata_gate=True),
        history=dict(original_gap71_index60_FAIL=True,repair_image_gap71_PASS=True,
            repair_dispatcher_sha256='78d022070953e360345c5986682a997a15a432deb42ff670cef9e3ca68e6043d',
            different_image_PASS_does_not_qualify_frozen_image=True),
        conclusions=['Fault direct VRF write hypothesis is contradicted by native events.',
            'Snapshot ordering is correct; initial seed logical bytes match independent gold.',
            'Observed failure is exactly consistent with EW32 interpretation of unchanged EW8 physical seed layout.',
            'Dispatcher EEW registers/layout_req were not captured. Exact update cycle versus blocked cleanup/rollback remains unobserved.',
            'No RTL modification, no rerun, no waiver or coverage admission.'],
        input_pins=pins,coverage_admitted=False,RTL_modified=False,EDA_launched=False))
    print('DIAGNOSIS_SEALED',p.h.sha(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    diagnose(parser.parse_args().output.resolve())
