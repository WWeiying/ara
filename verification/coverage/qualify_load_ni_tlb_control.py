"""Offline frozen NI/TLB architecture, preedge AXI and exact raw FSM audit."""
import argparse
from collections import Counter, defaultdict, deque
import csv
import json
from pathlib import Path
import re
import sys
from types import FunctionType
import run_load_ni_tlb_control as run
import audit_gap115_axi_v2 as wave
import coverage_bitmap_delta as bitmap

life, require = run.life, run.require
OUT = life.OUT / 'load-ni-tlb-qualified-760-agent-20261007-01'
BASE = life.OUT / 'qbs-affine-min-slot15-offline-admitted-761-agent-20261007-01'
BASE_SHA = 'fb32312b28f37c0a674fbefa521f75dd041e78bf6cfe6f83f0d7dc8f8b61f9f7'
ADMIT = life.OUT / 'load-ni-tlb-offline-admitted-762-agent-20261007-01'
SEAL = '91300ca4259958308c0fe7fabf74498d58beed2ff10049f6df0de4da962e09b6'
CORE = run.LOAD.split('.ex_stage_i')[0]
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'


def waveform(path):
    # Private copy of the proven streaming VCD parser; original module is unchanged.
    ns = dict(wave.vcd.__globals__, ROOT='ara_tb', WIDTHS={'clk': 1, 'rst_n': 1})
    parse = FunctionType(wave.vcd.__code__, ns)
    iterator = iter(parse(path)); _, decl = next(iterator)
    widths = {'id':4,'addr':64,'len':8,'size':3,'burst':2,'lock':1,'cache':4,'prot':3,
              'qos':4,'region':4,'user':1,'atop':6,'data':64,'strb':8,'last':1,'resp':2}
    for channel,fields in {'ar':('id','addr','len','size','burst','lock','cache','prot','qos','region','user'),
        'aw':('id','addr','len','size','burst','lock','cache','prot','qos','region','atop','user'),
        'w':('data','strb','last','user'),'r':('id','data','resp','last','user'),'b':('id','resp','user')}.items():
        req = channel in ('ar','aw','w')
        prefix = CORE + ('.noc_req_o' if req else '.noc_resp_i')
        for name in fields:
            require(decl.get(prefix+'.'+channel+'.'+name,{}).get('width') == widths[name], 'Frozen packed width differs')
        require(decl.get(prefix+'.'+channel+'_valid',{}).get('width') == 1 and
            decl.get(CORE+('.noc_resp_i' if req else '.noc_req_o')+'.'+channel+'_ready',{}).get('width') == 1,
            'Handshake width differs')
    for name,width in {'state_q':4,'valid_i':1,'req_port_i.data_gnt':1,'dtlb_hit_i':1,'stall_ni':1,
        'paddr_ni':1,'not_commit_time':1,'inflight_stores':1,'commit_tran_id_i':3,
        'lsu_ctrl_i.trans_id':3,'lsu_ctrl_i.vaddr':64}.items():
        require(decl.get(run.LOAD+'.'+name,{}).get('width') == width,'Frozen load probe width differs')
    def val(state, full):
        require(full in decl, 'Missing waveform field: ' + full)
        bits = state.get(decl[full]['code'], 'x')
        require(set(bits) <= set('01'), 'Unknown active field: ' + full)
        return int(bits, 2)
    def c(state, suffix): return val(state, CORE + '.' + suffix)
    def l(state, suffix): return val(state, run.LOAD + '.' + suffix)
    reads, writes = defaultdict(deque), defaultdict(deque)
    aws, frames, wframe = deque(), deque(), []
    counts = Counter(); held = {}; edges = Counter(); witnesses = []
    previous = None; ctrl_reads = 0; sampled = 0; activated = False
    names = {'ar': ['id','addr','len','size','burst','lock','cache','prot','qos','region','user'],
             'aw': ['id','addr','len','size','burst','lock','cache','prot','qos','region','atop','user'],
             'w': ['data','strb','last','user'], 'r': ['id','data','resp','last','user'],
             'b': ['id','resp','user']}
    for time, before, after in iterator:
        clk = decl['ara_tb.clk']['code']; rst = decl['ara_tb.rst_n']['code']
        require(not (activated and before.get(rst) == '1' and after.get(rst) == '0'), 'Unexpected reset')
        if before.get(clk) != '0' or after.get(clk) != '1' or before.get(rst) != '1': continue
        activated = True; sampled += 1
        state = l(before, 'state_q')
        if previous is not None and previous != state:
            edges[(previous, state)] += 1
        previous = state
        if l(before,'valid_i') and l(before,'req_port_i.data_gnt') and state in (1,2):
            hit = l(before,'dtlb_hit_i'); stall = l(before,'stall_ni')
            if not hit or stall:
                witnesses.append(dict(time_100fs=time,state=state,dtlb_hit=hit,stall_ni=stall,
                    paddr_ni=l(before,'paddr_ni'),not_commit_time=l(before,'not_commit_time'),
                    inflight_stores=l(before,'inflight_stores'),commit_id=l(before,'commit_tran_id_i'),
                    load_id=l(before,'lsu_ctrl_i.trans_id'),vaddr=hex(l(before,'lsu_ctrl_i.vaddr'))))
        fired = {}
        for channel in names:
            req = channel in ('ar','aw','w')
            prefix = 'noc_req_o' if req else 'noc_resp_i'
            ready_prefix = 'noc_resp_i' if req else 'noc_req_o'
            valid = c(before, prefix+'.'+channel+'_valid')
            ready = c(before, ready_prefix+'.'+channel+'_ready')
            payload = tuple(c(before,prefix+'.'+channel+'.'+n) for n in names[channel]) if valid else None
            require(channel not in held or payload == held[channel], 'AXI unstable held '+channel)
            if valid and not ready: held[channel] = payload
            else: held.pop(channel, None)
            if valid and ready: fired[channel] = payload; counts[channel] += 1
        for channel in ('ar','aw'):
            if channel not in fired: continue
            p = fired[channel]; ident, address, length, size, burst = p[:5]
            require(size <= 3 and burst in (0,1) and (address & 4095)+(length+1)*(1<<size) <= 4096,
                    'Invalid AXI burst')
            require(not(channel == 'aw' and 0xd0000000 <= address < 0xd0001000), 'CTRL write request')
            record = dict(id=ident,address=address,beats=length+1,received=0,size=size)
            if channel == 'ar':
                reads[ident].append(record)
                if 0xd0000000 <= address < 0xd0001000:
                    require(address == 0xd0000000 and length == 0 and size == 3, 'CTRL read contract differs')
                    ctrl_reads += 1
            else:
                require(p[10] == 0, 'Unexpected atomic AW'); aws.append(record)
        if 'r' in fired:
            ident,data,resp,last,_ = fired['r']
            require(reads[ident], 'Orphan AXI R')
            record = reads[ident][0]; record['received'] += 1
            require(resp == 0 and last == int(record['received'] == record['beats']), 'AXI R error/RLAST')
            if record['address'] == 0xd0000000: require(data == 0, 'CTRL reset data differs')
            if last: reads[ident].popleft()
        if 'w' in fired:
            wframe.append(fired['w'])
            if fired['w'][2]: frames.append(wframe); wframe = []
        while aws and frames:
            record, frame = aws.popleft(), frames.popleft()
            require(len(frame) == record['beats'] and all(p[2] == int(i == len(frame)-1)
                for i,p in enumerate(frame)), 'AXI W length/last differs')
            writes[record['id']].append(record)
        if 'b' in fired:
            ident,resp,_ = fired['b']
            require(writes[ident] and resp == 0, 'Orphan/error AXI B'); writes[ident].popleft()
    require(sampled > 0 and ctrl_reads == 1 and not held and not aws and not frames and not wframe and
            not any(reads.values()) and not any(writes.values()), 'AXI final drain/one CTRL read incomplete')
    return dict(status='COMPLETE_PREEDGE_AXI_PASS', channels=dict(counts), ctrl_reads=ctrl_reads,
        sampled_edges=sampled, transitions=[dict(source=a,destination=b,count=n) for (a,b),n in sorted(edges.items())],
        predicate_witnesses=witnesses, pre_timebucket_handshake=True, no_reset_after_startup=True,
        declarations=decl)


def union(before, single, count):
    require(len(before['tests']) == len(set(before['tests'])) == count and len(single['tests']) == 1,
            'Baseline/single membership differs')
    combined = bitmap.combine(before,single); instances = 0
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            add = single['metrics'][metric][scope]
            require(int(combined['metrics'][metric][scope]['bits'],16) ==
                    int(row['bits'],16) | int(add['bits'],16), 'Independent OR differs')
            instances += 1
    require(instances == 6162 and combined['tests'] == before['tests'] + single['tests'] and
            len(set(combined['tests'])) == count+1, 'Exact full population prefix differs')
    return combined


def collect():
    require(not OUT.exists(), 'Fresh qualification only')
    prepared = run.RUN.with_name(run.RUN.name+'.prepared.json')
    record = life.read_bound(prepared,SEAL)
    pre = life.read_bound(run.PRE/'preflight.json',record['preflight_seal'])
    pins = life.merge_pins(record['pins'], {str(prepared):SEAL})
    require(json.loads((run.RUN/'manifest.json').read_text()) == dict(record,pins=pins), 'Actual run binding differs')
    require(json.loads((run.RUN/'simulation-status.json').read_text())['returncode'] == 0, 'Nonterminal simulator')
    for p in run.RUN.rglob('*'):
        if p.is_file(): pins = life.merge_pins(pins,{str(p):life.digest(p)})
    for module in tuple(sys.modules.values()):
        f = getattr(module,'__file__',None)
        if f and str(life.ROOT/'verification') in f and Path(f).is_file():
            pins = life.merge_pins(pins,{str(Path(f).resolve()):life.digest(Path(f).resolve())})
    pins = life.merge_pins(pins,{str(Path(__file__).with_name('test_qualify_load_ni_tlb_control.py')):
        life.digest(Path(__file__).with_name('test_qualify_load_ni_tlb_control.py')), str(CONVERTER):CONVERTER_SHA})
    life.check(pins); OUT.mkdir()
    try:
        lines = (run.RUN/'console.log').read_text().splitlines()
        require(lines.count('LOAD_NI_PROBE_READY') == 1 and
            len([x for x in lines if x.startswith('LOAD_NI_PROBE_OBJECT ')]) == 18 and
            not any(re.match(r'^(LOAD_NI_PROBE_ERROR|UVM_ERROR|UVM_FATAL|Error-)',x) for x in lines), 'Probe/error markers differ')
        require(sum('Core Test *** SUCCESS ***' == x for x in lines) == 1 and
            re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',
                '\n'.join(lines)) == [('0','0','0','0','0')], 'Terminal software/contract differs')
        scalar = run.architecture.spike_trace.compare_commit_prefix(run.PRE/'spike.trace',run.RUN/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(OUT/'scalar-comparison.json',scalar); run.architecture.scalar_exact(scalar,pre['counts'])
        with (run.RUN/'commit_trace.csv').open() as f: rows = list(csv.DictReader(f))
        require(all(r['event'] == 'retire' and not int(r['trap']) for r in rows) and
            [int(r['order']) for r in rows] == list(range(len(rows))), 'Retire prefix/backend/trap differs')
        memory = {}
        for r in rows:
            store = run.architecture.scalar_store(r)
            if store:
                address,data = store
                for i,value in enumerate(data): memory[address+i] = value
        # scalar_store reconstructs bytes from unshifted RVFI data and native lane masks.
        def word(address,size=8): return sum(memory[address+i] << (8*i) for i in range(size))
        observed = [word(pre['symbols']['lnt_observed']+8*i) for i in range(9)]
        require(observed == run.expected(pre['symbols'],word(pre['symbols']['lnt_original_status'])) and
            [word(pre['symbols']['g75_result'],4),word(pre['symbols']['g75_result']+4,4),
             word(pre['symbols']['num_failed'],4)] == [14,0,0], 'Full native CSR/data oracle differs')
        with (run.RUN/'vector_trace.csv').open() as f:
            vectors = list(csv.DictReader(f))
        require(all(r['event'] == 'config' for r in vectors), 'Unexpected vector activity')
        life.save(OUT/'native-observed.json',dict(observed=observed,checks=14,failed=0,vector_writes=0))
        axi = waveform(run.RUN/'load-ni-tlb.vcd'); life.save(OUT/'wave-audit.json',axi)
        design = life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
        with (OUT/'single-inputs.txt').open('x') as f: f.write(str(design)+'\n'+str(run.RUN/'code.vdb')+'\n')
        single = bitmap.collect(OUT/'single-inputs.txt')
        before = life.read_bound(run.BASE/'combined-bits.json',pins[str(run.BASE/'combined-bits.json')])
        combined = union(before,single,760); delta = bitmap.delta(before,combined)
        row = single['metrics']['fsm'][run.LOAD]
        require((row['width'],row['checksum']) == (42,'1874282190'), 'Native FSM shape differs')
        mapping = {21:(2,4),22:(2,5),28:(1,4),29:(1,5)}
        observed_edges = {(x['source'],x['destination']) for x in axi['transitions']}
        hits = [dict(raw_index=i,hit_single=bool(int(row['bits'],16)&(1<<(41-i))),
            waveform_transition=list(edge),waveform_seen=edge in observed_edges) for i,edge in mapping.items()]
        require(all(x['hit_single'] == x['waveform_seen'] for x in hits), 'Native bitmap/wave FSM disagree')
        for n,v in [('single-bits.json',single),('delta760.json',delta),('target-hits.json',hits)]: life.save(OUT/n,v)
        for p,sha in single['input_hashes'].items(): pins = life.merge_pins(pins,{p:sha})
        for rel,sha in single['design'].items():
            pins = life.merge_pins(pins,{str(design/'snps/coverage/db'/rel):sha})
        life.check(pins); life.save(OUT/'evidence-pins.json',pins)
        life.save(OUT/'qualification.json',dict(status='NI_TLB_ARCHITECTURE_AXI_FSM_QUALIFIED_NOT_ADMITTED',
            baseline=760,raw_delta=delta['metrics'],target_hits=hits,software_checks=14,
            full_scalar_ISA=True,ctrl_device_emulated_by_Spike=False,ctrl_scope=pre['ctrl_scope'],
            uvm_check_report_pass=False,missing_uvm_summary_preserved=True,rtl_changed=False,
            input_pins=pins,output_pins={str(p):life.digest(p) for p in OUT.iterdir() if p.is_file()}))
        print('QUALIFIED '+life.digest(OUT/'qualification.json')+' '+str(delta['metrics']),flush=True)
    except Exception as e:
        life.save(OUT/'failure.json',dict(reason=str(e),coverage_admitted=False)); raise


def admit(qualification_seal):
    q = life.read_bound(OUT/'qualification.json',qualification_seal)
    require(q['status'] == 'NI_TLB_ARCHITECTURE_AXI_FSM_QUALIFIED_NOT_ADMITTED', 'Qualified PASS required')
    base = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    pins = life.merge_pins(q['input_pins'],q['output_pins'])
    pins = life.merge_pins(pins,life.merge_pins(base['input_pins'],base['output_pins']))
    pins = life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,
        str(OUT/'qualification.json'):qualification_seal})
    life.check(pins)
    before = life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    single = life.read_bound(OUT/'single-bits.json',pins[str(OUT/'single-bits.json')])
    require((BASE/'combined-inputs.txt').read_text().splitlines()[1:] == before['tests'], '761 exact ledger differs')
    combined = union(before,single,761); delta = bitmap.delta(before,combined)
    require(sum(delta['metrics'].values()) > 0, 'Zero fresh gain: PASS not called an improvement/admission')
    require(not ADMIT.exists(), 'Fresh762 admission only'); ADMIT.mkdir()
    for n,v in [('combined-bits.json',combined),('single-bits.json',single),('raw-delta.json',delta),
        ('status.json',dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=762,baseline=761,
            coverage_admitted=True,exact761_prefix=True,full_OR_instances=6162,raw_delta=delta['metrics'],
            qualification=str(OUT/'qualification.json'),qualification_seal=qualification_seal,
            official_denominator_verified=False,rtl_changed=False,simulation_rerun=False,
            uvm_check_report_pass=False,missing_uvm_summary_preserved=True))]: life.save(ADMIT/n,v)
    with (ADMIT/'combined-inputs.txt').open('x') as f:
        f.write('\n'.join([str(life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb')]+combined['tests'])+'\n')
    life.check(pins)
    life.save(ADMIT/'admission-manifest.json',dict(schema='LOAD_NI_TLB_FORMAL762_V1',output=str(ADMIT),
        baseline=str(BASE),baseline_seal=BASE_SHA,input_pins=pins,
        output_pins={str(p):life.digest(p) for p in ADMIT.iterdir()},explicit_parent_authorized=True))
    print('ADMITTED762 '+life.digest(ADMIT/'admission-manifest.json')+' '+str(delta['metrics']),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--collect',action='store_true'); p.add_argument('--admit-qualified')
    a=p.parse_args(); require(bool(a.collect) != bool(a.admit_qualified),'One mode required')
    if a.collect: collect()
    else: admit(a.admit_qualified)
