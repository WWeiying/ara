"""Offline preedge FIFO/pending witness and exact two-payload Toggle OR; no EDA."""
import argparse
from collections import deque
import json
from pathlib import Path
from types import FunctionType

import audit_gap115_axi_v2 as parser
import collect_qbs_k2_row_pending782 as case
import targeted_toggle_evidence as toggle

life,require=case.life,case.require
CACHE=life.OUT/'qbs-engine-full102-residual766-static-agent-20261007-01.json'
CACHE_SHA='b6fefc0d350ed0ca4d3add37f3b6a43fd6cb4a79742dc2384d9f297abd5a8cca'
ROOT='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine'
ADAPTER=ROOT+'.i_compute_engine.i_block_adapter_bank0'
PAYLOAD=ADAPTER+'.i_payload_buffer'


def cycles(path):
    f=FunctionType(parser.vcd.__code__,dict(vars(parser),ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    iterator=iter(f(path));_,decl=next(iterator)
    names={'clock':'ara_tb.clk','reset':'ara_tb.rst_n'}
    for key,name in dict(pending='activation_pending_q_valid',pending_ctx='activation_pending_q.ctx',
        pending_offset='activation_pending_q.offset',pending_strb='activation_pending_q.strb',
        pending_data='activation_pending_q.data',remaining='activation_remaining',consumed='activation_consumed',
        source_valid='activation_source_valid',count='activation_ingress_count_q',push='activation_ingress_push',
        input_offset='activation_write_offset_i',input_ctx='activation_write_context_i',clear='clear_activation_i').items():
        names[key]=ADAPTER+'.'+name
    for key,name in dict(range_valid='range_valid_i',range_ready='range_ready_o',range_addr='range_vaddr_i',
        range_bytes='range_bytes_i',data_valid='data_valid_o',data_ready='data_ready_i',data_offset='data_offset_o',
        data_strb='data_strb_o',first_lane='response_head.first_lane',take='beat_take_bytes',
        target='data_tag_o.target',k='data_tag_o.k_block').items():names[key]=ROOT+'.i_read_engine.'+name
    for slot in (0,1):
        for name in ('candidate','selected_word','word_match'):
            names['slot%d_%s'%(slot,name)]=PAYLOAD+'.gen_write_merge[%d].gen_bank_plane[2].gen_bank_row[2].%s'%(slot,name)
    names['hit']=PAYLOAD+'.gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].gen_byte_merge[5].hit'
    require(all(name in decl for name in names.values()),'Missing actual wave identity')
    widths=dict(clock=1,reset=1,pending=1,pending_ctx=2,pending_offset=12,pending_strb=16,pending_data=128,
        remaining=32,consumed=32,source_valid=2,count=2,push=1,input_offset=12,input_ctx=2,clear=1,
        range_valid=1,range_ready=1,range_addr=64,range_bytes=16,data_valid=1,data_ready=1,data_offset=16,
        data_strb=16,first_lane=4,take=16,target=2,k=8,hit=16,
        slot0_candidate=16,slot1_candidate=16,slot0_selected_word=3,slot1_selected_word=3,slot0_word_match=16,slot1_word_match=16)
    require(all(decl[names[k]]['width']==v for k,v in widths.items()),'Exact wave field widths')
    codes={k:decl[name]['code'] for k,name in names.items()}
    def get(state,key):
        value=state.get(codes[key],'x');require(not set(value)-set('01'),'Unknown active field '+key)
        return int(value,2)
    symbols,_,_,_=case.elf_view();base=symbols['activation'][0]+64;expected_address=base+1460
    fifo=deque();history=deque(maxlen=6);entry=None;capture=[];witness=None;ordinal=0;current_range=None
    for time,before,after in iterator:
        if before.get(codes['clock'])!='0' or after.get(codes['clock'])!='1':continue
        ordinal+=1
        if before.get(codes['reset'])!='1':fifo.clear();continue
        row=dict(time_100fs=time,rising_edge_ordinal=ordinal)
        for key in ('clear','count','push','source_valid','pending','range_valid','range_ready'):
            row[key]=get(before,key)
        require(row['count']==len(fifo),'Actual ingress count versus reconstructed FIFO')
        if row['range_valid'] and row['range_ready']:
            addr=get(before,'range_addr');length=get(before,'range_bytes')
            if addr==expected_address:
                require(entry is None and length==292,'Exact unique A+1460 range')
                entry=dict(time_100fs=time,address=addr,length=length,activation_base=base)
        if row['source_valid']&2:
            require(fifo,'Source1 without accepted ingress owner');owner=fifo.popleft()
            row['slot1_owner']=owner
        if row['push']:
            require(get(before,'data_valid')==get(before,'data_ready')==1,'Ingress must originate accepted compact beat')
            row['input_ctx']=get(before,'input_ctx');row['input_offset']=get(before,'input_offset')
            require(row['input_ctx']==get(before,'target') and row['input_offset']==get(before,'data_offset'),'Input/compact identity')
            owner=dict(ctx=row['input_ctx'],offset=row['input_offset'],k=get(before,'k'),
                strb=get(before,'data_strb'),take=get(before,'take'),first_lane=get(before,'first_lane'),accepted_at=time)
            require(owner['strb']==(1<<owner['take'])-1,'Exact compact prefix strb')
            fifo.append(owner)
        if row['clear']:fifo.clear()
        relevant=(row.get('slot1_owner',{}).get('ctx'),row.get('slot1_owner',{}).get('k'),row.get('slot1_owner',{}).get('offset'))==(2,1,28)
        if relevant or capture:
            for key in ('remaining','consumed','slot0_candidate','slot1_candidate','slot0_word_match','slot1_word_match','hit'):
                row[key]=get(before,key)
            for slot in (0,1):
                if row['source_valid']>>slot&1:
                    row['slot%d_selected_word'%slot]=get(before,'slot%d_selected_word'%slot)
            if row['pending']:
                for key in ('pending_ctx','pending_offset','pending_strb','pending_data'):row[key]=get(before,key)
        if relevant:
            require(witness is None,'Unique exact offset28 producer')
            require(row['pending']==0 and row['source_valid']==2 and row['slot1_candidate']==0xffff and
                row['slot1_selected_word']==0 and row['slot1_word_match']==0xff and row['remaining']>>16==0xff00,
                'Actual word0 arbitration condition differs')
            witness=dict(producer=row,prior=list(history));capture=[row]
        elif capture and len(capture)<4:capture.append(row)
        if len(capture)==4:break
        history.append({k:v for k,v in row.items() if k!='pending_data'})
    require(entry is not None and witness is not None and len(capture)==4,'Missing complete range/pending witness')
    producer,pending=capture[:2]
    require(pending['time_100fs']-producer['time_100fs']==10000 and pending['pending']==1 and
        pending['pending_ctx']==2 and pending['pending_offset']==28 and pending['pending_strb']==0xff00 and
        pending['source_valid']&1 and pending['slot0_selected_word']==1 and pending['slot0_word_match']&8192 and
        pending['hit']&8192 and pending['consumed']&0xff00==0xff00 and pending['remaining']&0xffff==0,
        'Adjacent same-b pending drain/hit13 differs')
    source=case.recipe.fixture()[1];expected=source[64+1460+28:64+1460+44]
    require(pending['pending_data'].to_bytes(16,'little')==expected,'Pending copied all16 original bytes')
    require(expected[13]==(pending['pending_data']>>(8*13))&255,'Exact writer13 data/source')
    return dict(status='EXACT_RANGE_FIFO_SAME_B_PENDING_WORD1_HIT13_PASS',range_entry=entry,
        producer_to_pending=capture,pending_byte13=expected[13],logical_dest=37,byte_lane=5,
        pending_remains_same_b=True,first_range_first_lane=4,
        missing_direct_wave_objects=['write_req[0][2][2]','write_req[1][2][2]','activation_source unpacked array'],
        source_inference='slot0 write_req = source_valid0 && |candidate0; source1 identity reconstructed from every preedge FIFO push/pop/count, not timestamp shifting or assumed ingress head',
        preceding_fifo_context=witness['prior'],coordinate_proof=[21532,21533],official_percentage=False)


def gain(run):
    base=case.runner.BASE;manifest=life.read_bound(base/'admission-manifest.json',case.runner.BASE_SHA)
    require(manifest['coverage_admitted'] is True,'Formal782 admitted')
    ledger_path=base/'combined-inputs.txt';ledger=life.read_bound(base/'admission-manifest.json',case.runner.BASE_SHA)
    pins={str(base/'admission-manifest.json'):case.runner.BASE_SHA,str(ledger_path):manifest['output_pins'][str(ledger_path)],str(CACHE):CACHE_SHA}
    life.check(pins);ledger=ledger_path.read_text().splitlines()
    require(len(ledger)==len(set(ledger))==783,'Exact compile+782 members')
    cache=life.read_bound(CACHE,CACHE_SHA)
    prefix=next(Path(p) for p in cache['pins'] if p.endswith('/combined-inputs.txt'))
    pins[str(prefix)]=cache['pins'][str(prefix)];life.check(pins)
    require(ledger[:767]==prefix.read_text().splitlines(),'Exact scoped766 prefix')
    scopes=[ROOT+'.i_compute_engine.i_block_adapter_bank%d.i_payload_buffer'%b for b in (0,1)]
    before={r['scope']:dict(width=r['raw_width'],checksum=r['checksum'],bits=r['bits'])
        for r in cache['scope_summaries'] if r['scope'] in scopes}
    require(set(before)==set(scopes),'Both cached payload scopes')
    for db in ledger[767:]:
        files=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Singleton baseline suffix');p=files[0]
        pins[str(p)]=manifest['input_pins'][str(p)]
        require(life.digest(p)==pins[str(p)],'Baseline data pin drift')
        sample,_=toggle.rows(p,scopes);before=toggle.union(before,sample)
    files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1 and files[0].parent.name==case.runner.NAME,'Exact new testcase')
    p=files[0];sample,sha=toggle.rows(p,scopes);pins[str(p)]=sha
    combined=toggle.union(before,sample);gains=toggle.gains(before,combined)
    require(all(before[s]['width']==66340 and before[s]['checksum']=='3657545390' for s in scopes),'Same frozen payload shape')
    life.check(pins)
    return dict(baseline=782,baseline_seal=case.runner.BASE_SHA,before_rows=before,single_rows=sample,
        combined_rows=combined,new_coordinates=gains,new_directions=sum(map(len,gains.values())),
        primary_new=[c for c in (21532,21533) if c in gains[scopes[0]]],input_pins=pins,
        arrays_present=False,official_percentage=False,coverage_admitted=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--vcd',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    require(out.is_dir() and not (out/'cycle-proof.json').exists() and not (out/'payload-gain.json').exists(),'Fresh analysis products')
    prepared=a.run.with_name(a.run.name+'.prepared.json');record=life.read_bound(prepared,'9ec4782319fbac9cb42e82464cef2a7c410ea3017cf8f73f471470005b047932')
    case.native.terminal(a.run);life.check(record['pins'])
    proof=cycles(a.vcd);delta=gain(a.run)
    pins=life.merge_pins(delta['input_pins'],{str(prepared):life.digest(prepared),str(a.vcd):life.digest(a.vcd),
        str(a.run/'qbs-k2-row-pending.vpd'):life.digest(a.run/'qbs-k2-row-pending.vpd'),
        str(case.runner.CONVERTER):record['pins'][str(case.runner.CONVERTER)],str(Path(__file__).resolve()):life.digest(Path(__file__)),
        str(Path(parser.__file__).resolve()):life.digest(Path(parser.__file__))})
    pins=life.merge_pins(pins,{p:h for p,h in record['pins'].items() if '/hardware/src/vlsu/qbs/' in p or p.endswith('/qbs_pkg.sv')})
    life.check(pins);proof['input_pins']=pins
    life.save(out/'cycle-proof.json',proof);life.save(out/'payload-gain.json',delta)
    print(json.dumps(dict(cycle_seal=life.digest(out/'cycle-proof.json'),gain_seal=life.digest(out/'payload-gain.json'),
        new_payload_directions=delta['new_directions'],per_bank={s:len(v) for s,v in delta['new_coordinates'].items()},primary_new=delta['primary_new'])),flush=True)


if __name__=='__main__':main()
