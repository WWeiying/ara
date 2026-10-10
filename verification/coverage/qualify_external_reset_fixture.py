"""Offline first shared-reset fixture qualification; no simulation/admission."""
from collections import deque
from pathlib import Path
from types import FunctionType
import json
import re
import subprocess
import sys
import run_external_reset_fixture as run
import audit_gap115_axi_v2 as parser
import postprocess_gap115_events_v2 as events
import prepare_fpu_half_reset744 as gold
import review_reset_full_design742 as coverage

life, require = run.life, run.require
OUT = life.OUT/'external-reset-fpu-half-ex2-qualified-745-agent-20261007-01'
SEAL = '39086e6bc8744cd02816eaddd09bd499c3208766d31e24a2b4c29832ed0d0b2d'
BASE = life.OUT/'gap115-offline-admitted-745-agent-20261007-01'
BASE_SHA = '965ec298fcd169b9a184367893ddfad7b080c75ac71e85fad72fe4977cf7b5b6'
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
VCD = run.OUT/'external-reset.vcd'


def wave(path, selection, source, snapshot):
    names = {'clk': 'ara_tb.clk', 'reset': 'ara_tb.rst_n', 'stage': selection['ext_target'],
             'guard': selection['ext_guard']}
    widths = {'clk': 1, 'reset': 1, 'stage': 4, 'guard': 1}
    for channel, fields in {'ar': {'id':4,'addr':64,'len':8,'size':3,'burst':2},
                            'aw': {'id':4,'addr':64,'len':8,'size':3,'burst':2},
                            'w': {'data':128,'strb':16,'last':1}}.items():
        for field, width in fields.items():
            key = channel+'_'+field; names[key] = ARA+'.axi_req_o.'+channel+'.'+field; widths[key] = width
    for key, member, width in [('ar_valid','axi_req_o.ar_valid',1),('ar_ready','axi_resp_i.ar_ready',1),
        ('aw_valid','axi_req_o.aw_valid',1),('aw_ready','axi_resp_i.aw_ready',1),
        ('w_valid','axi_req_o.w_valid',1),('w_ready','axi_resp_i.w_ready',1),
        ('r_valid','axi_resp_i.r_valid',1),('r_ready','axi_req_o.r_ready',1),
        ('r_id','axi_resp_i.r.id',4),('r_data','axi_resp_i.r.data',128),('r_last','axi_resp_i.r.last',1),
        ('r_resp','axi_resp_i.r.resp',2),('b_valid','axi_resp_i.b_valid',1),('b_ready','axi_req_o.b_ready',1),
        ('b_id','axi_resp_i.b.id',4),('b_resp','axi_resp_i.b.resp',2)]:
        names[key] = ARA+'.'+member; widths[key] = width
    namespace = dict(parser.vcd.__globals__, ROOT='ara_tb', WIDTHS={names[k][7:]: w for k,w in widths.items()})
    # Same frozen parser code, private concrete field inventory; no original-module mutation.
    reader = FunctionType(parser.vcd.__code__, namespace)
    iterator = iter(reader(path)); _, declarations = next(iterator)
    codes = {k: declarations[p]['code'] for k,p in names.items()}
    def val(state, k):
        bits = state.get(codes[k], 'x'); require(set(bits) <= set('01'), 'Unknown active waveform field: '+k)
        return int(bits, 2)
    def payload(state, channel):
        return tuple(val(state, k) for k in widths if k.startswith(channel+'_') and k not in (channel+'_valid',channel+'_ready'))
    resets=[]; periods=set(); last_edge=None; phase=0; counts=[dict(ar=0,r=0,aw=0,w=0,b=0),dict(ar=0,r=0,aw=0,w=0,b=0)]
    reads={}; write_queue=deque(); beats=deque(); b_pending={}; read_addresses=set(); write_addresses=set(); held={}
    asserted_stage=None; reset_edges=0
    for time, before, after in iterator:
        rb, ra = before.get(codes['reset']), after.get(codes['reset'])
        if rb == '1' and ra == '0':
            require(phase == 0 and not resets and val(before,'stage') == selection['ext_value'] and
                    val(before,'guard') == 1 and not reads and not write_queue and not beats and not b_pending,
                    'Target/guard/reset or outstanding AXI at reset differs')
            require(all(v == 0 for v in counts[0].values()), 'Unexpected epoch0 AXI traffic')
            asserted_stage=val(before,'stage'); resets.append(time); phase=1; held={}
        if rb == '0' and ra == '1' and resets:
            require(len(resets) == 1, 'Multiple reset releases'); resets.append(time)
        falling = before.get(codes['clk']) == '1' and after.get(codes['clk']) == '0'
        if falling and resets and time > resets[0] and (len(resets)==1 or time==resets[1]): reset_edges += 1
        rising = before.get(codes['clk']) == '0' and after.get(codes['clk']) == '1'
        if not rising: continue
        if last_edge is not None: periods.add(time-last_edge)
        if rb == '1' or last_edge is not None: last_edge=time
        if rb != '1': continue
        for channel in ('ar','aw','w','r','b'):
            valid, ready = val(before,channel+'_valid'), val(before,channel+'_ready')
            if channel in held:
                require(valid and payload(before,channel) == held[channel], 'AXI stalled payload changed: '+channel)
            if valid and not ready: held[channel] = payload(before,channel)
            else: held.pop(channel,None)
        for channel in ('ar','aw'):
            if val(before,channel+'_valid') and val(before,channel+'_ready'):
                key, address, length, size, burst = [val(before,channel+'_'+f) for f in ('id','addr','len','size','burst')]
                require(size==4 and burst==1 and address%16==0 and address//4096==(address+16*length)//4096,
                        'AXI burst layout differs')
                counts[phase][channel]+=1
                if channel=='ar':
                    require(key not in reads and source<=address and address+16*(length+1)<=source+1024, 'AR range/ID differs')
                    reads[key]=[address,length+1,0]
                else:
                    require(snapshot<=address and address+16*(length+1)<=snapshot+4096, 'AW outside full VRF snapshot')
                    write_queue.append([key,address,length+1,0])
        if val(before,'w_valid') and val(before,'w_ready'):
            beats.append(tuple(val(before,'w_'+f) for f in ('data','strb','last'))); counts[phase]['w']+=1
        while beats and write_queue:
            key,address,total,index=write_queue[0]; data,strb,last=beats.popleft(); address+=16*index
            require(strb==65535 and last==int(index+1==total) and address not in write_addresses,
                    'W byte enable/last/duplicate differs')
            word0=gold.expected_word((address-snapshot)//8); word1=gold.expected_word((address-snapshot)//8+1)
            require(data==word0+(word1<<64), 'Full VRF snapshot AXI W data differs')
            write_addresses.add(address); write_queue[0][3]+=1
            if index+1==total:
                write_queue.popleft(); b_pending[key]=b_pending.get(key,0)+1
        if val(before,'r_valid') and val(before,'r_ready'):
            key=val(before,'r_id'); require(key in reads, 'R without AR')
            address,total,index=reads[key]; address+=16*index
            require(val(before,'r_resp')==0 and val(before,'r_last')==int(index+1==total) and
                    val(before,'r_data')==0x123456789abcdef0*(1+(1<<64)) and address not in read_addresses,
                    'R payload/RLAST/source differs')
            read_addresses.add(address); reads[key][2]+=1; counts[phase]['r']+=1
            if index+1==total: del reads[key]
        if val(before,'b_valid') and val(before,'b_ready'):
            key=val(before,'b_id'); require(b_pending.get(key,0)>0 and val(before,'b_resp')==0, 'B without completed AW/W')
            b_pending[key]-=1; counts[phase]['b']+=1
            if not b_pending[key]: del b_pending[key]
    require(len(resets)==2 and len(periods)==1 and resets[1]-resets[0]==4*next(iter(periods)) and reset_edges==4,
            'Exact four complete external reset cycles differ')
    require(not reads and not write_queue and not beats and not b_pending and not held and
            read_addresses==set(range(source,source+1024,16)) and write_addresses==set(range(snapshot,snapshot+4096,16)) and
            counts[1]['r']==64 and counts[1]['w']==256 and counts[1]['aw']==counts[1]['b'], 'AXI final drain/coverage incomplete')
    return dict(status='TARGET6_HALF_VALID_FOUR_CYCLE_RESET_ALL_AR_R_AW_W_B_PASS', resets_100fs=resets,
        reset_negedges=reset_edges, period_100fs=next(iter(periods)), actual_stage=asserted_stage,
        phases=counts, source_bytes=1024, full_vrf_snapshot_bytes=4096, pending=0, pre_timebucket_sampling=True,
        field_mapping={k:dict(path=names[k],**declarations[names[k]]) for k in names})


def epoch0_bytes(rows):
    allocations={int(r['arch_seq']):r for r in rows if r['event']=='alloc'}
    count=0
    for r in rows:
        if r['event']!='write': continue
        owner=allocations[int(r['arch_seq'])]; word=int(owner['insn'],16); vd=int(owner['vd'])
        if int(owner['eew'])==3 and word & 0xfc00707f == 0x5c004057:
            expected=0x0101010101010101*(0x40+vd)
        elif word==0x5e02c057 and int(owner['eew'])==1: expected=0x3c003c003c003c00
        elif word==0x5e02c857 and int(owner['eew'])==1: expected=0x4200420042004200
        elif word==0x92001457: expected=0x3c003c003c003c00
        else: raise ValueError('Unexpected epoch0 writer; division must have no pre-reset result')
        be=int(r['be'],16); actual=int(r['wdata'],16)
        for i in range(8):
            if be>>i&1:
                require((actual>>(8*i))&255 == (expected>>(8*i))&255, 'Epoch0 seed/multiply byte differs'); count+=1
    return count


def collect():
    require(not OUT.exists(), 'Fresh qualification only')
    prepared=run.OUT.with_name(run.OUT.name+'.prepared.json'); plan=life.read_bound(prepared,SEAL)
    pins=life.merge_pins(plan['pins'],{str(prepared):SEAL})
    pre=life.read_bound(run.PRE/'preflight.json',run.PRE_SHA)
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    pins=life.merge_pins(pins,base['input_pins']); pins=life.merge_pins(pins,base['output_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA})
    paths=[p for p in run.OUT.rglob('*') if p.is_file()]
    paths += [Path(__file__).resolve(),Path(__file__).with_name('test_qualify_external_reset_fixture.py')]
    for module in (parser,events,gold,coverage): paths.append(Path(module.__file__).resolve())
    for p in paths: pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins); OUT.mkdir()
    try:
        require(json.loads((run.OUT/'simulation-status.json').read_bytes())['returncode']==0, 'Not successful terminal')
        require(json.loads((run.OUT/'manifest.json').read_bytes())==dict(plan,pins=life.merge_pins(plan['pins'],{str(prepared):SEAL})),
                'Executed plan differs')
        require(life.digest(run.OUT/'external-reset-selection.tcl')==plan['selection_sha256'], 'Executed selection differs')
        log=(run.OUT/'run.vcs.log').read_text(); console=(run.OUT/'console.log').read_text()
        expected=['EXT_RESET_READY %s 6'%plan['selection']['ext_target'], 'EXT_RESET_TARGET %s 6'%plan['selection']['ext_target'],
                  'EXT_RESET_ASSERT', *['EXT_RESET_LOW_EDGE %d'%i for i in range(1,5)], 'EXT_RESET_RELEASE','EXT_RESET_DONE']
        require([line for line in console.splitlines() if line.startswith('EXT_RESET_')]==expected, 'Exact executed markers differ')
        require(console.count('Core Test *** SUCCESS ***')==1 and not re.search(r'(?m)^UVM_(ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]|trace.*truncat',log), 'Terminal/error/truncation')
        cf,cr=events.run.reset.read_csv(run.OUT/'commit_trace.csv'); vf,vr=events.run.reset.read_csv(run.OUT/'vector_trace.csv')
        epochs,cut=events.run.reset.split_epochs(cr,vr)
        for i,(commits,vectors) in enumerate(epochs):
            ep=OUT/('epoch%d'%i); ep.mkdir(); events.run.reset.write_csv(ep/'commit_trace.csv',cf,commits)
            events.run.reset.write_csv(ep/'vector_trace.csv',vf,vectors)
        pending={}; cancelled=[]
        for r in epochs[0][1]:
            if r['event']=='alloc': pending[int(r['vid'])]=r
            elif r['event']=='done': pending.pop(int(r['vid']))
        require({int(r['insn'],16) for r in pending.values()}=={0x5e02c857,0x82881c57}, 'Expected seed/DIV cancellation differs')
        for r in pending.values():
            seq=int(r['arch_seq']); cancelled.append(seq)
            matching=[c for c in epochs[0][0] if c['event']=='arch_start' and int(c['order'])==seq]
            require(len(matching)==1 and int(matching[0]['insn'],16)==int(r['insn'],16), 'Cancelled owner differs')
        backend=[events.backend(*epochs[0],cancelled),events.backend(*epochs[1],set())]
        prefix=events.run.shared.shared.spike_trace.compare_commit_prefix(run.PRE/'spike.trace',OUT/'epoch0/commit_trace.csv',
            0x80000000,rvfi_store_data_layout='unshifted')
        require(prefix['status']=='PREFIX' and prefix['mismatch'] is None and prefix['skipped_unobservable_register_values']==0
                and prefix['ara_retired_instructions']==prefix['matched_instructions'] and prefix['ara_trap_events']==0, 'Cancelled scalar prefix differs')
        initial_bytes=epoch0_bytes(epochs[0][1])
        original=events.run.reset.check_real_uvm_log(run.OUT/'run.vcs.log',require_events=True,require_backend=True,
            require_axi=True,vector_trace=run.OUT/'vector_trace.csv',reset_kind='state')
        life.save(OUT/'original-uvm-audit.json',original)
        require(original['uvm_backend_event_sha256']==original['vector_backend_event_sha256'] and
                original['uvm_backend_event_count']==original['vector_backend_event_count']<100000,
                'Independent UVM/vector backend event sequence differs')
        observed=list(events.uvm._RESET_OBSERVED.finditer(log)); require([int(m['epoch']) for m in observed]==[1,2], 'Reset epochs differ')
        boundary=int(observed[1]['cycle']); ue,ui=events.uvm._events(log,'[CVXIF/EVENT]',events.uvm._UVM_EVENT,10)
        ce,ci=events.uvm._events(log,'[ARA_CONTRACT_TRACE]',events.uvm._CONTRACT_EVENT,16)
        require(not ui and not ci and events.uvm._event_digest(ue)==events.uvm._event_digest(ce) and len(ue)<100000,
                'Independent CVXIF event trace differs')
        cvx=[]
        for i,(rows,_) in enumerate(epochs):
            selected=[e for e in ce if (e[0]<boundary if i==0 else e[0]>boundary)]
            counts=events.traffic(selected); require(counts['aborted']==0, 'Pending CVXIF owner at reset/end')
            commits=[(int(r['cycle']),r['event'],int(r['trans_id']),int(r['insn'],16) if r['event']=='cvx_req' else 0,int(r['trap']))
                     for r in rows if r['event'] in ('cvx_req','cvx_resp')]
            flattened=[(e[0],name,key,insn,exc) for e in selected for name,key,insn,exc in
                       ([('cvx_req',e[2],e[3],0)] if e[1] else [])+([('cvx_resp',e[5],0,e[6])] if e[4] else [])]
            require(events.relative_events(commits)==events.relative_events(flattened), 'Commit/CVXIF epoch identity differs')
            cvx.append(counts)
        require(original['contract_counts']['requests']==cvx[1]['requests']==original['contract_counts']['responses']
                and cvx[1]['responses']==cvx[1]['requests'] and all(original['contract_counts'][k]==0
                    for k in ('exceptions','protocol_errors','outstanding')), 'Final independent contract differs')
        memory={}
        for row in epochs[1][0]:
            if row['event']=='retire':
                store=events.run.shared.shared.scalar_store(row)
                if store: memory.update({store[0]+i:b for i,b in enumerate(store[1])})
        def value(name,offset=0,size=8):
            address=pre['symbols'][name]+offset
            require(all(address+i in memory for i in range(size)), 'Missing recovery oracle byte')
            return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
        gold.oracle(value)
        scalar=events.run.shared.shared.spike_trace.compare_commit_prefix(run.PRE/'spike.trace',OUT/'epoch1/commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        events.run.shared.shared.scalar_exact(scalar,pre['counts'])
        vector=events.run.shared.shared.compare_vector_commits(run.PRE/'spike.trace',OUT/'epoch1/commit_trace.csv',
            OUT/'epoch1/vector_trace.csv',0x80000000)
        require(vector['status']=='PASS' and all(vector[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions'))
                and not vector['incomplete_requests'] and not vector['unretired_requests'] and all(
                    r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0 for r in vector['instructions']), 'Recovery vector bytes differ')
        reader=events.run.shared.template.s.LLVM/'llvm-readelf'
        snapshot=events.run.shared.template.s._elf_symbol(run.PRE/'input.elf',reader,'snapshot')
        axi=wave(VCD,plan['selection'],pre['symbols']['source']+128,snapshot)
        timestamps=re.findall(r'@ (\d+):[^\n]*\[CVXIF/RESET\][^\n]*epoch=2',log)
        require(len(timestamps)==1 and axi['resets_100fs'][0]<int(timestamps[0])<=axi['resets_100fs'][1], 'Reset trace/wave epoch boundary differs')
        for n,v in [('axi-and-stage-audit.json',axi),('event-audit.json',dict(cvx_epochs=cvx,backend_epochs=backend,epoch0_known_write_bytes=initial_bytes)),
            ('prefix-scalar.json',prefix),('recovery-scalar.json',scalar),('recovery-vector.json',vector)]: life.save(OUT/n,v)
        before=life.read_bound(BASE/'combined-bits.json',base['output_pins'][str(BASE/'combined-bits.json')])
        require(len(before['tests'])==len(set(before['tests']))==745 and str(run.OUT/'code.vdb') not in before['tests'], 'Exact745 prefix/novel candidate differs')
        with (OUT/'single-inputs.txt').open('x') as f: f.write(str(coverage.DESIGN)+'\n'+str(run.OUT/'code.vdb')+'\n')
        single=coverage.bitmap.collect(OUT/'single-inputs.txt'); combined=coverage.bitmap.combine(before,single)
        delta=coverage.all_delta(before,combined); target_hits=[]
        for t in pre['targets']:
            old,new=before['metrics']['fsm'][t['scope']],single['metrics']['fsm'][t['scope']]
            require((old['width'],old['checksum'])==(new['width'],new['checksum']) and new['width']==17, 'Controller shape differs')
            target_hits.append(dict(scope=t['scope'],raw_index=8,before=bool(int(old['bits'],16)&(1<<8)),single=bool(int(new['bits'],16)&(1<<8))))
        life.check(pins)
        for n,v in [('single-bits.json',single),('raw-delta.json',delta),('fsm-targets.json',target_hits),('evidence-pins.json',pins)]: life.save(OUT/n,v)
        life.save(OUT/'qualification.json',dict(status='EXTERNAL_TBPIN_HALF_EX2_WAVE_ARCHITECTURE_PASS_NOT_ADMITTED', baseline=745,
            software_checks=679,full_vrf_bytes=4096,csr_words=5,source_guards_checked=True,epoch_count=2,
            scalar_counts=pre['counts'],vector_instructions=vector['compared_instructions'],vector_bytes=vector['compared_bytes'],
            actual_target_hits=sum(t['single'] and not t['before'] for t in target_hits),raw_delta=delta['metrics'],
            axi_all_channels_verified=True,uvm_check_report_pass=False,coverage_admitted=False,
            output_pins={str(p):life.digest(p) for p in OUT.rglob('*') if p.is_file()}))
        print('QUALIFIED '+life.digest(OUT/'qualification.json')+' '+json.dumps(delta['metrics']))
    except Exception as exc:
        life.save(OUT/'failure.json',dict(reason=str(exc),coverage_admitted=False)); raise


if __name__=='__main__': collect()
