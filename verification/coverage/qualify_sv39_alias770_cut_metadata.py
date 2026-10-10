"""Offline exact preedge FIFO/AXI-cut correlation; preserves both prior HOLDs."""
import argparse
from collections import defaultdict, deque
from pathlib import Path
from types import FunctionType
import qualify_sv39_alias770_known_tail as checked

p=checked.prior
life,require=p.life,p.require
PLAN=life.OUT/'sv39-alias770-known-tail-plan-agent-20261007-01/plan.json'
SEAL='c158a759640b43c8763e6e30e8f048b381bb3f3c919c78954af6f0c749d9b015'
REQ='i_vlsu.i_addrgen.axi_addrgen_req_o.'
WIDTHS=dict(p.WIDTHS,**{REQ+k:v for k,v in dict(addr=128,len=8,size=3,is_load=1,is_exception=1,is_skip=1).items()})


def frames(iterator,codes,physical):
    def v(state,name):
        bits=state.get(codes[name],'x');require(set(bits)<=set('01'),'Unknown active waveform field: '+name)
        return int(bits,2)
    aw=deque();metadata=deque();ar=defaultdict(deque);bq=defaultdict(deque)
    records=[];target_aw=loads=total_push=total_completed=0;previous_pointer=None;active=False
    for time,before,after in iterator:
        if before.get(codes['clk_i'])!='0' or after.get(codes['clk_i'])!='1':continue
        if before.get(codes['rst_ni'])!='1':require(not active,'Unexpected reset');continue
        active=True
        require(v(before,p.FIFO+'flush_i')==0,'Unexpected flush')
        pointer=v(before,p.FIFO+'write_pointer_q');push=v(before,p.FIFO+'push_i')
        require(previous_pointer is None or pointer==previous_pointer,'Actual preedge pointer drift')
        require(not(push and v(before,p.FIFO+'full_o')),'Full FIFO push');previous_pointer=(pointer+push)%16
        if push:
            row=dict(accepted_at_100fs=time,pointer=pointer,address=v(before,REQ+'addr'),
                vaddr=v(before,p.FIFO+'data_i.vaddr'),owner_slot=v(before,p.FIFO+'data_i.slot'),
                length=v(before,REQ+'len')+1,size=v(before,REQ+'size'),elem_start=v(before,p.FIFO+'data_i.elem_start'))
            require(v(before,REQ+'is_load')==v(before,REQ+'is_exception')==v(before,REQ+'is_skip')==0 and
                row['vaddr']==v(before,REQ+'vaddr') and row['elem_start']==v(before,REQ+'elem_start'),
                'Exact normal-store producer/FIFO fields')
            row['target']=row['address']==physical
            if row['target']:
                phase=len(records)//16
                require(phase<3 and row['length']==4 and row['size']==4 and row['elem_start']==0 and
                    v(before,'acc_mmu_en_q')==1 and row['vaddr']==p.run.reference.prior.address(phase),
                    'Exact48 translated producer pushes')
                row['phase']=phase;records.append(row)
            else:require(row['vaddr'] not in [p.run.reference.prior.address(i) for i in range(3)],'Extra alias producer')
            metadata.append(row);total_push+=1
            # Frozen non-bypassed W spill has two entries; every push owns one final W.
            require(len(metadata)<=2,'AXI-cut pending final-W capacity exceeded')
        if v(before,'axi_req_o.aw_valid') and v(before,'axi_resp_i.aw_ready'):
            row=dict(id=v(before,'axi_req_o.aw.id'),address=v(before,'axi_req_o.aw.addr'),
                length=v(before,'axi_req_o.aw.len')+1,size=v(before,'axi_req_o.aw.size'),
                burst=v(before,'axi_req_o.aw.burst'),received=0)
            row['target']=row['address']==physical
            if row['target']:
                require(target_aw<48 and row['length']==4 and row['size']==4 and row['burst']==1,'Target AW')
                row['phase']=target_aw//16;target_aw+=1
            aw.append(row)
        if v(before,'axi_req_o.w_valid') and v(before,'axi_resp_i.w_ready'):
            require(bool(aw),'Orphan W');row=aw[0]
            require(v(before,'axi_req_o.w.last')==int(row['received']==row['length']-1),'WLAST')
            if row['target']:
                pattern=p.run.reference.prior.PATTERNS[row['phase']]
                require(v(before,'axi_req_o.w.strb')==65535 and v(before,'axi_req_o.w.data')==pattern|(pattern<<64),
                        'Exact64 target W bytes')
            row['received']+=1
            if row['received']==row['length']:
                aw.popleft();require(bool(metadata),'External final W has no prior internal owner')
                owner=metadata.popleft();total_completed+=1
                require(owner['accepted_at_100fs']<time and
                    (owner['address'],owner['length'],owner['size'],owner['target'])==
                    (row['address'],row['length'],row['size'],row['target']),'AXI-cut ordered payload/owner identity')
                if row['target']:
                    require(owner['phase']==row['phase'],'AXI phase mismatch')
                    owner['external_last_W_100fs']=time;owner['external_aw_id']=row['id']
                bq[row['id']].append(row)
        if v(before,'axi_resp_i.b_valid') and v(before,'axi_req_o.b_ready'):
            ident=v(before,'axi_resp_i.b.id')
            require(bool(bq[ident]) and v(before,'axi_resp_i.b.resp')==0,'Orphan/error B');bq[ident].popleft()
        if v(before,'axi_req_o.ar_valid') and v(before,'axi_resp_i.ar_ready'):
            row=dict(length=v(before,'axi_req_o.ar.len')+1,received=0,
                     target=v(before,'axi_req_o.ar.addr')==physical)
            if row['target']:
                require(loads<48 and row['length']==4 and v(before,'axi_req_o.ar.size')==4 and
                        v(before,'axi_req_o.ar.burst')==1,'Target AR');row['phase']=loads//16;loads+=1
            ar[v(before,'axi_req_o.ar.id')].append(row)
        if v(before,'axi_resp_i.r_valid') and v(before,'axi_req_o.r_ready'):
            ident=v(before,'axi_resp_i.r.id');require(bool(ar[ident]),'Orphan R');row=ar[ident][0]
            require(v(before,'axi_resp_i.r.resp')==0 and v(before,'axi_resp_i.r.last')==
                int(row['received']==row['length']-1),'RRESP/RLAST')
            if row['target']:
                pattern=p.run.reference.prior.PATTERNS[row['phase']]
                require(v(before,'axi_resp_i.r.data')==pattern|(pattern<<64),'Exact64 target R bytes')
            row['received']+=1
            if row['received']==row['length']:ar[ident].popleft()
    require(active and not aw and not metadata and not any(ar.values()) and not any(bq.values()) and
        total_push==total_completed and len(records)==target_aw==loads==48,'Complete FIFO/AXI last-drain')
    for phase in range(3):
        require({r['pointer'] for r in records if r['phase']==phase}==set(range(16)),'All16 actual slots each phase')
    for slot in range(16):
        require([r['vaddr'] for r in records if r['pointer']==slot]==
            [p.run.reference.prior.address(i) for i in range(3)],'Actual slot low/high/low')
    return dict(status='ACTUAL_PREEDGE48_PUSHES_ORDERED_AXI_CUT_DATA_DRAIN_PASS',preedge_sampling=True,
        stores=48,loads=48,total_internal_final_W_pushes=total_push,total_external_final_W=total_completed,
        pushes=records,all16slots_both_virtual_directions=True,no_retiming_or_waveform_rewrite=True)


def metadata(path,physical):
    parse=FunctionType(p.wave.vcd.__code__,dict(p.wave.vcd.__globals__,ROOT=p.ROOT,WIDTHS=WIDTHS))
    iterator=iter(parse(path));_,decl=next(iterator);codes={n:decl[p.ROOT+'.'+n]['code'] for n in WIDTHS}
    result=frames(iterator,codes,physical);result['field_mapping']={n:decl[p.ROOT+'.'+n] for n in WIDTHS}
    return result


def prepare(out):
    plan=life.read_bound(PLAN,SEAL);life.check(plan['pins'])
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh direct successor plan')
    pins=life.merge_pins(plan['pins'],{str(PLAN):SEAL})
    bookpath=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book=life.read_bound(bookpath,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    for rel in ('hardware/src/vlsu/vlsu.sv','hardware/deps/axi/src/axi_cut.sv',
                'hardware/deps/common_cells/src/spill_register.sv','hardware/deps/common_cells/src/spill_register_flushable.sv'):
        path=life.ROOT/rel;pins=life.merge_pins(pins,{str(path):book[str(path)]})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_alias770_cut_metadata.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins);out.mkdir();record=dict(plan,pins=pins,axi_cut_correlation=
        'Preedge local FIFO push/data and producer addr/len/size; ordered external final-W owners through nonbypassed two-entry spill. No same-cycle assertion, no trace rewriting. Exact48 targets/all16 slots and external R/W/B checks retained.')
    life.save(out/'plan.json',record);print('PLAN',life.digest(out/'plan.json'))


def collect(plan,seal,out):
    record=life.read_bound(plan,seal);require(str(Path(__file__).resolve()) in record['pins'],'Pinned implementation')
    fn=FunctionType(p.collect.__code__,dict(p.collect.__globals__,scalar_exact=checked.scalar_exact,
        vector_exact=checked.vector_exact,native_exact=checked.native_exact,raw_gain=checked.raw_gain,metadata=metadata))
    return fn(plan,seal,out)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=('prepare','verify','collect'))
    a.add_argument('--output',type=Path);a.add_argument('--plan',type=Path);a.add_argument('--seal');args=a.parse_args()
    if args.action=='prepare':prepare(args.output.absolute())
    elif args.action=='verify':life.check(life.read_bound(args.plan,args.seal)['pins']);print('VERIFY_PASS')
    else:collect(args.plan,args.seal,args.output.absolute())
