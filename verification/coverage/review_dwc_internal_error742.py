"""Frozen INCR-only DWC error-port source proof candidate; no EDA or exclusion generation."""
import argparse
import itertools
import json
import re
from pathlib import Path
import targeted_toggle_evidence_v2 as t
from review_qbs_scale742 import scalar_shape

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'verification/out'
BASE=OUT/'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA='f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
BUILD=OUT/'repaired-aligned-build-20260930-01'; DB=BUILD/'sim/simv.vdb/snps/coverage/db'
DWC='ara_tb.dut.i_ara_soc.i_system.i_ariane_axi_dwc.gen_dw_upsize.i_axi_dw_upsizer'
ERR=DWC+'.i_axi_err_slv'; FILTER=ERR+'.genblk1.i_atop_filter'
SOURCES=['hardware/src/ara_system.sv','hardware/deps/cva6/core/cva6.sv',
    'hardware/deps/cva6/core/cache_subsystem/wt_cache_subsystem.sv',
    'hardware/deps/cva6/core/cache_subsystem/wt_axi_adapter.sv','hardware/deps/cva6/core/axi_shim.sv',
    'hardware/deps/axi/src/axi_dw_converter.sv','hardware/deps/axi/src/axi_dw_upsizer.sv',
    'hardware/deps/axi/src/axi_demux.sv','hardware/deps/axi/src/axi_demux_simple.sv',
    'hardware/deps/axi/src/axi_atop_filter.sv','hardware/deps/axi/src/axi_err_slv.sv',
    'hardware/deps/common_cells/src/fifo_v3.sv','hardware/deps/common_cells/src/stream_register.sv',
    'hardware/deps/common_cells/src/counter.sv','hardware/deps/common_cells/src/delta_counter.sv',
    'hardware/deps/common_cells/src/spill_register.sv','hardware/deps/axi/src/axi_pkg.sv']


def clean(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)


def source_contract(shim,upsizer,demux):
    shim,upsizer,demux=map(clean,(shim,upsizer,demux))
    for channel in ('aw','ar'):
        rhs=re.findall(r'axi_req_o\.'+channel+r'\.burst\s*=\s*([^;]+);',shim)
        t.require(rhs==['axi_pkg::BURST_INCR'],'Non-INCR/multiple producer assignment')
    blocks=re.findall(r'axi_pkg::BURST_WRAP:\s*begin(.*?)\bend\s*default:',upsizer,re.S)
    ones=re.findall(r'(r_req_d\.ar_throw_error|w_req_d\.aw_throw_error)\s*=\s*1\x27b1',upsizer)
    wrap_ones=[n for b in blocks for n in re.findall(
        r'(r_req_d\.ar_throw_error|w_req_d\.aw_throw_error)\s*=\s*1\x27b1',b)]
    t.require(len(blocks)==3 and ones==wrap_ones==[
        'r_req_d.ar_throw_error','r_req_d.ar_throw_error','w_req_d.aw_throw_error'],
        'Unexpected error-producing assignment')
    for b in blocks:
        t.require(re.search(r'if\s*\([^)]*\.len\s*==\s*\x270\)\s*\w+_req_d\.\w+_throw_error\s*=\s*1\x27b0',b),
                  'Single-beat WRAP override missing')
    t.require('r_req_d.ar.burst     = w_req_q.aw.burst' in upsizer,'Injected AR burst provenance differs')
    t.require(re.search(r'mst_reqs_o\[i\]\.aw_valid\s*=\s*1\x27b0',demux) and
              re.search(r'aw_valid\s*&&\s*\(slv_aw_select_i\s*==\s*i\)',demux) and
              re.search(r'ar_valid\s*&&\s*\(slv_ar_select_i\s*==\s*i\)',demux), 'Demux gating differs')
    return dict(producer_burst='INCR', error_assignment_paths=3, injected_AR='original AW burst',
                error_route='WRAP && len!=0 only', direct_ATOP_route_override=False)


def induction():
    # Abstract source-bound event model, NOT DUT cases or a four-state simulation.
    checks=0
    for path,length,atop,capture in itertools.product(('native_AR','injected_AR','AW'),range(256),range(64),(False,True)):
        burst=1  # axi_pkg::BURST_INCR, also inherited by injected AR.
        previous_error=0
        next_error=int(burst==2 and length!=0) if capture else previous_error
        t.require(next_error==0,'Reachable error select in INCR contract');checks+=1
    return dict(status='SOURCE_BOUND_KNOWN_LEGAL_EVENT_INDUCTION', combinations=checks,
        paths=3,lengths=256,ATOP_encodings=64,hold_capture_modes=2, initial_error=0, select_after_hold_or_capture=0,
        reset_reestablishes_zero=True, model_is_not_DUT_execution=True,
        limitation='Settled known RTL after valid reset; no force, X injection, alternate producer or illegal state seeding')


def fsm_points(definition,row):
    bits=format(int(row['bits'],16),'0%db'%row['width']); result=[]; offset=0
    allowed={'w_state_q':{'W_RESET','W_FEEDTHROUGH'},'r_state_q':{'R_RESET','R_FEEDTHROUGH'}}
    for machine in definition.find('fsmshape'):
        name=machine.get('name');t.require(name in allowed,'Unreviewed extra FSM machine')
        states=machine.findall('state'); arcs=machine.findall('transition')
        ids={s.get('id'):s.get('name') for s in states}
        for i,s in enumerate(states):
            result.append(dict(machine=name,machine_checksum=machine.get('chksum'),kind='state',
                state=s.get('name'),line=s.get('line'),raw_index=offset+i,
                candidate=s.get('name') not in allowed[name],hit=bits[offset+i]=='1'))
        for i,a in enumerate(arcs):
            frm,to=ids[a.get('fromid')],ids[a.get('toid')];pos=offset+len(states)+i
            result.append(dict(machine=name,machine_checksum=machine.get('chksum'),kind='transition',
                from_state=frm,to_state=to,line=a.get('line'),raw_index=pos,
                candidate=frm not in allowed[name] or to not in allowed[name],hit=bits[pos]=='1'))
        offset+=len(states)+len(arcs)
    t.require(offset==row['width']==39,'FSM complete width differs')
    t.require(all(not p['hit'] for p in result if p['candidate']), 'Source invariant conflicts with measured FSM')
    t.require(sum(p['candidate'] for p in result)==31,'Expected exact31 candidate points')
    return result


def collect():
    t.require(t.digest(BASE/'admission-manifest.json')==BASE_SHA,'Formal742 drift')
    manifest=json.loads((BASE/'admission-manifest.json').read_bytes())
    bpath=BASE/'combined-bits.json';t.require(t.digest(bpath)==manifest['output_pins'][str(bpath)],'Bitmap drift')
    bitmap=json.loads(bpath.read_bytes());t.require(len(bitmap['tests'])==742,'Wrong population')
    buildpath=BUILD/'build-source-pins.json'
    t.require(t.digest(buildpath)=='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b','Build drift')
    build=json.loads(buildpath.read_bytes());pins={str(BASE/'admission-manifest.json'):BASE_SHA,
        str(bpath):t.digest(bpath),str(buildpath):t.digest(buildpath)}
    texts={}
    for name in SOURCES:
        p=ROOT/name;t.require(t.digest(p)==build[str(p)],'Frozen source drift: '+name)
        pins[str(p)]=build[str(p)];texts[name]=p.read_text()
    contract=source_contract(texts[SOURCES[4]],texts[SOURCES[6]],texts[SOURCES[8]])
    source=t.xml(DB/'auxiliary/verilog.sourceinfo.xml')
    files={n.get('id'):n.get('name') for n in source.iter('fileinfo')}
    design=t.xml(DB/'design/verilog.design.xml');nodes={}
    for m in design.findall('srcdef'):
        for n in m.findall('srcinst'):nodes[n.get('id')]=(n,m)
    def path(key):
        n,_=nodes[key];p=n.get('pid');return (path(p)+'.' if p in nodes else '')+n.get('name')
    hierarchy={path(k):m for k,(_,m) in nodes.items()}
    t.require(hierarchy[FILTER].get('name')=='axi_atop_filter' and
        files[hierarchy[FILTER].find('srclocmult').get('file_id')]==str(ROOT/SOURCES[9]),'Compiled FSM source differs')
    shape=t.xml(DB/'shape/fsm.verilog.shape.xml');row=bitmap['metrics']['fsm'][FILTER]
    defs=[d for d in shape.iter('fsmdef') if d.get('chksum')==row['checksum'] and
          any(n.get('name')==FILTER for n in d.findall('fsminst'))]
    t.require(len(defs)==1 and row['checksum']=='2300800093','Exact scope FSM binding differs')
    points=fsm_points(defs[0],row)
    tshape=t.xml(DB/'shape/tgl.verilog.shape.xml');info=t.xml(DB/'shape/tgl.verilog.info.xml')
    up=[d for d in tshape.iter('tgldef') if d.get('name')=='axi_dw_upsizer']
    t.require(len(up)==1 and all(x in up[0].get('param','') for x in
        ('AxiMaxReads=2,','AxiSlvPortDataWidth=64,','AxiMstPortDataWidth=128,')), 'Compiled64->128 DWC differs')
    rankpath=OUT/'toggle741-capacity-ranking-agent-20261007-01.json';rank=json.loads(rankpath.read_bytes())
    pins[str(rankpath)]=t.digest(rankpath);pins.update(rank['input_pins'])
    vdb=bitmap['tests'][-1];candidate=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    t.require(len(candidate)==1 and t.digest(candidate[0])==manifest['input_pins'][str(candidate[0])],
              'Admitted742 singleton Toggle drift')
    scopes=[FILTER,ERR,ERR+'.i_r_counter.i_counter'];sample,sha=t.rows(candidate[0],scopes)
    pins[str(candidate[0])]=sha
    zero_signals={FILTER:{'w_cnt_d.cnt','w_cnt_q.cnt','w_cnt_d.underflow','w_cnt_q.underflow',
        'id_d','id_q','r_beats_d','r_beats_q','r_resp_cmd_pop.len','r_resp_cmd_push_valid',
        'r_resp_cmd_pop_valid','r_resp_cmd_pop_ready','aw_without_complete_w_downstream',
        'complete_w_without_aw_downstream'},ERR:{'r_cnt_clear','r_cnt_en','r_cnt_load','r_current_beat',
        'r_busy_d','r_busy_q','r_busy_load','w_fifo_full','b_fifo_full','r_fifo_full',
        'w_fifo_push','w_fifo_pop','b_fifo_push','b_fifo_pop','r_fifo_push','r_fifo_pop'},
        ERR+'.i_r_counter.i_counter':{'counter_d','counter_q'}}
    targets=[];protected=[]
    for scope in scopes:
        old=rank['instances'][scope];new=sample[scope]
        t.require((old['width'],old['checksum'])==(new['width'],new['checksum']),'Toggle identity drift')
        bits=format(int(old['bits'],16)|int(new['bits'],16),'0%db'%old['width'])
        ds=[d for d in tshape.iter('tgldef') if d.get('chksum')==old['checksum'] and
            d.get('id')==hierarchy[scope].get('id')]
        t.require(len(ds)==1,'Missing scoped Toggle definition')
        for p in scalar_shape(ds[0],len(bits)):
            if p['signal'] not in zero_signals[scope]:continue
            t.require(p['attributes'].get('portnode')=='0','Interface point must stay protected')
            value=bits[p['raw_offset']:p['raw_offset']+2*p['width']]
            t.require(set(value)=={'0'},'Constant candidate conflicts with actual union: '+p['signal'])
            targets.append(dict(scope=scope,checksum=old['checksum'],**p,expected_value=0,
                zero_serialized_positions=list(range(p['raw_offset'],p['raw_offset']+2*p['width']))))
        protected.append(dict(scope=scope,width=old['width'],checksum=old['checksum'],
            positions=[i for i in range(old['width']) if not any(i in p['zero_serialized_positions']
                for p in targets if p['scope']==scope)]))
    for rel in ('auxiliary/verilog.sourceinfo.xml','design/verilog.design.xml',
                'shape/fsm.verilog.shape.xml','shape/tgl.verilog.shape.xml','shape/tgl.verilog.info.xml'):
        p=DB/rel;pins[str(p)]=t.digest(p)
    pins[str(Path(__file__).resolve())]=t.digest(Path(__file__).resolve())
    test=Path(__file__).with_name('test_review_dwc_internal_error742.py');pins[str(test)]=t.digest(test)
    for p,sha in pins.items():t.require(t.digest(Path(p))==sha,'Final input drift')
    return dict(status='SOURCE_PROVEN_POINT_CANDIDATE_NATIVE_HOLD_NOT_APPLIED',baseline=742,
        scope=FILTER,compiled_fsm_checksum=row['checksum'],compiled_fsm_width=39,
        source_contract=contract,induction=induction(),fsm_points=points,
        fsm_candidate_states=sum(p['candidate'] and p['kind']=='state' for p in points),
        fsm_candidate_arcs=sum(p['candidate'] and p['kind']=='transition' for p in points),
        fsm_protected_points=[p for p in points if not p['candidate']],
        toggle_candidates=targets,toggle_candidate_positions=sum(len(p['zero_serialized_positions']) for p in targets),
        toggle_protection=protected,input_pins=pins,
        proof_chain=['CVA6 WT cache -> wt_axi_adapter -> axi_shim INCR AW/AR -> narrow DWC64->128',
            'DWC ar_throw_error/aw_throw_error reset0, hold/capture INCR0, injected AR inherits INCR AW',
            'Demux select0 normal master; select1 error port AW/AR/W valid never asserted',
            'Empty err-slave FIFOs -> no B/R valid; ATOP filter counter0, no atomic admission/injection',
            'w/r FSM only RESET and FEEDTHROUGH; stream cmd invalid, readcounter disabled stays0'],
        protects=['All interfaces including mirrored AW/AR/W payload and R/B readiness',
            'All line/branch/condition points including default/reset',
            'All other instances, especially SoC decode error and i_l2mem_atop_filter',
            'All state_q/state_d Toggle bits; native FSM initial/reset/feedthrough points',
            'FIFO storage, r_fifo_inp and r_resp_cmd_push.len can observe invalid mirrored payload; not blanket constants'],
        native_identity_qualified=False,exclude_import_apply=False,EDA_launched=False,RTL_modified=False,
        prior_AMO_error_path_argument='Rejected: ATOP does not change INCR producer or DWC err selection')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t.require(not a.output.exists(),'Fresh artifact required');result=collect()
    with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(output=str(a.output),seal=t.digest(a.output),states=result['fsm_candidate_states'],
        arcs=result['fsm_candidate_arcs'],tgl=result['toggle_candidate_positions'],native='HOLD')))
