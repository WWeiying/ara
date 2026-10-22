"""Read-only cycle chain on the one converted known-old VPD; no EDA."""
import argparse
from pathlib import Path
from types import FunctionType
import audit_gap115_axi_v2 as parser
import collect_mask_compare_restart_known786 as frozen

life,require=frozen.life,frozen.require
ROOT='ara_tb.dut.i_ara_soc.i_system.i_ara'
ANALYSIS=life.OUT/'mask-compare-known786-failure-analysis-agent-20261008-01'


def audit(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh wave audit output')
    path=ANALYSIS/'focused.vcd'
    native=life.read_bound(ANALYSIS/'native-compares.json',life.digest(ANALYSIS/'native-compares.json'))
    reader=FunctionType(parser.vcd.__code__,dict(parser.vcd.__globals__,WIDTHS={}),argdefs=parser.vcd.__defaults__)
    iterator=iter(reader(path)); tag,declarations=next(iterator)
    require(tag=='declarations','Actual converted declarations')
    def val(state,name,width=None):
        d=declarations[name]
        require(width is None or d['width']==width,'Actual width differs '+name)
        bits=state.get(d['code'],'x')
        require(set(bits)<=set('01'),'Unknown active value '+name)
        return int(bits,2)
    def known(state,name):
        d=declarations[name]; bits=state.get(d['code'],'x')
        return int(bits,2) if set(bits)<=set('01') else None
    def piece(value,index,width): return value>>(index*width)&((1<<width)-1)
    requests=[[] for _ in range(4)]; reads=[[] for _ in range(4)]; responses=[[] for _ in range(4)]; merges=[]
    clock_code=declarations['ara_tb.clk']['code']
    for time,before,after in iterator:
        if before.get(clock_code)!='0' or after.get(clock_code)!='1': continue
        if known(before,'ara_tb.rst_n')!=1: continue
        for lane in range(4):
            scope=ROOT+'.gen_lanes[%d].i_lane'%lane; req=scope+'.i_operand_requester'
            valid=known(before,req+'.operand_request_valid_i')
            ready=known(before,req+'.operand_request_ready_o')
            if valid is not None and ready is not None and valid&ready&(1<<5):
                raw=piece(val(before,req+'.operand_request_i',702),5,78)
                vs=raw>>70&31; eew=raw>>60&7; vstart=raw>>24&2047
                if vs==1:
                    requests[lane].append(dict(time_100fs=time,vs=vs,eew=eew,vstart=vstart,
                        vl=raw>>35&2047,vid=raw>>75&7,raw_packed78=hex(raw)))
            vrf=known(before,req+'.vrf_req_o'); wen=known(before,req+'.vrf_wen_o')
            if vrf is not None and wen is not None:
                tgt=known(before,req+'.vrf_tgt_opqueue_o'); addresses=known(before,req+'.vrf_addr_o')
                if tgt is not None and addresses is not None:
                    for bank in range(8):
                        if vrf>>bank&1 and not(wen>>bank&1) and piece(tgt,bank,4)==5:
                            row=piece(addresses,bank,10)
                            reads[lane].append(dict(time_100fs=time,bank=bank,bank_row_addr=row,addr=row*8+bank))
            vrf_scope=scope+'.i_vrf'
            rv=known(before,vrf_scope+'.rdata_valid_q'); targets=known(before,vrf_scope+'.tgt_opqueue_q')
            if rv is not None and targets is not None:
                data=known(before,vrf_scope+'.rdata')
                for bank in range(8):
                    if rv>>bank&1 and piece(targets,bank,4)==5:
                        # Only the selected bank must be known; inactive banks may be X.
                        raw_bits=before[declarations[vrf_scope+'.rdata']['code']]
                        selected=raw_bits[512-(bank+1)*64:512-bank*64]
                        require(set(selected)<=set('01'),'Unknown selected MaskB VRF response')
                        responses[lane].append(dict(time_100fs=time,bank=bank,data='%016x'%int(selected,2)))
        mask=ROOT+'.i_masku'
        if known(before,mask+'.out_vrf_word_valid')==1:
            entry=dict(time_100fs=time)
            for name,width in (('masku_operand_vd_seq',256),('alu_result_compressed_seq',256),
                               ('result_queue_active_mask_seq',256),('background_data_init_seq',256),
                               ('alu_result_vm_m',256)):
                entry[name]='%064x'%val(before,mask+'.'+name,width)
            entry['iteration']=val(before,mask+'.iteration_cnt_q',5)
            merges.append(entry)
    require(all(len(r)==3 for r in requests),'Exact three old-vd requests per lane')
    for lane in range(4):
        for case,r in enumerate(requests[lane]):
            require((r['vs'],r['eew'],r['vstart'])==(1,3,frozen.p.STARTS[case]//4),
                'Source-bound vs1/EW64/lane vstart mismatch: '+repr((lane,case,r)))
    require(len(merges)==3,'Exact three MASKU result merge events')
    chains=[]
    for case,m in enumerate(merges):
        lanes=[]
        for lane in range(4):
            request=requests[lane][case]
            end=requests[lane][case+1]['time_100fs'] if case<2 else m['time_100fs']+1
            selected=[r for r in reads[lane] if request['time_100fs']<=r['time_100fs']<end]
            require(len(selected)==1,'Exactly one old-vd VRF read before this merge')
            read=selected[0]
            response=[r for r in responses[lane] if r['bank']==read['bank'] and
                read['time_100fs']<r['time_100fs']<=m['time_100fs']]
            require(len(response)==1,'Exactly one delayed selected VRF return')
            expected_addr=4+frozen.p.STARTS[case]//4
            require(read['addr']==expected_addr,'Actual VRF address not hypothesis predicted')
            lanes.append(dict(lane=lane,request=request,read=read,response=response[0],
                expected_packed_mask_base_addr=4,actual_wrong_addr=read['addr']))
        predicted=(frozen.p.old_bytes(0)[32:40] if case==0 else frozen.p.old_bytes(0)[64:72]
                   if case==1 else frozen.p.old_bytes(1)[:8])
        start=frozen.p.STARTS[case]; mask=(1<<start)-1
        old=int(m['masku_operand_vd_seq'],16)
        require(old&mask==int.from_bytes(predicted,'little')&mask,'Wrong-word data prediction differs from merge old')
        actual=int(native['cases'][case]['actual_low64'],16)
        require(actual&mask==old&mask,'Native wrong prestart differs from MASKU old word')
        chains.append(dict(case=case,vstart=start,lanes=lanes,merge=m,
            native_write_cycles=[native['cases'][case]['write_cycle_first'],native['cases'][case]['write_cycle_last']],
            predicted_wrong_word_low64=predicted.hex(),prestart_wrong_bits=native['cases'][case]['prestart_wrong_bits']))
    out.mkdir()
    pins={str(path):life.digest(path),str(ANALYSIS/'native-compares.json'):life.digest(ANALYSIS/'native-compares.json'),
        str(Path(__file__).resolve()):life.digest(Path(__file__)),str(Path(parser.__file__)):life.digest(Path(parser.__file__))}
    life.check(pins)
    result=dict(status='MEASURED_MASK_PRESTART_WRONG_WORD_BUG_NO_QUALIFICATION',chains=chains,
        VCD_time_unit='100fs',layout_binding=dict(request_count=9,request_bits=78,MaskB_index=5,
        vs_offset=70,eew_offset=60,eew_bits=3,vstart_offset=24,VRF_bank_addr_bits=10),
        input_pins=pins,coverage_admitted=False,RTL_modified=False,VCS_launched=False)
    life.save(out/'wave-causality.json',result)
    print('WAVE_CAUSALITY_SEALED',life.digest(out/'wave-causality.json'))


if __name__=='__main__':
    parser_cli=argparse.ArgumentParser(); parser_cli.add_argument('--output',type=Path,required=True)
    audit(parser_cli.parse_args().output.resolve())
