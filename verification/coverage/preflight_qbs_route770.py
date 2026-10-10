"""Source-bound routing-domain proof and one host witness; no RTL simulator."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
REPORT = OUT/'qbs-route-domain-host-preflight770-agent-20261007-01.json'
AUDIT = OUT/'toggle-outside-prepared-union770-static-agent-20261007-01.json'
AUDIT_SHA = 'c6dd804cbee8e8d872c6058da0defb8e1c0facd1ca816caf8326e6b12105f036'
BASE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank'
PROFILES = {'Q4_K':144, 'Q5_K':176, 'Q6_K':210, 'Q3_K':110, 'Q8_0_WEIGHT':34,
            'Q4_0':18, 'Q2_K':84, 'Q5_0':22, 'IQ4_NL':18}
SOURCES = ['hardware/include/qbs_pkg.sv', 'hardware/src/vlsu/qbs/qbs_engine.sv',
           'hardware/src/vlsu/qbs/qbs_read_engine.sv', 'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
           'hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv', 'hardware/src/vlsu/qbs/qbs_block_adapter.sv',
           'hardware/src/vlsu/qbs/qbs_payload_buffer.sv']


def need(ok, why):
    if not ok: raise ValueError(why)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def xml(p):
    raw = p.read_bytes()
    return ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


def configuration(profile, layout, weight_phase, activation_phase):
    need(profile in PROFILES and layout in ('ROW', 'M4', 'M8'), 'Legal profile/layout')
    need(weight_phase in range(0,16,2) and activation_phase in range(0,16,4), 'ABI base alignment')
    return {'weight_profile':profile, 'activation_profile':'Q8_K' if profile.endswith('_K') else 'Q8_0',
            'weight_layout':'R4_BLOCK_MAJOR', 'activation_layout':layout, 'm':8 if layout=='M8' else 4,
            'n':8, 'k_blocks':1, 'vd':8, 'weight_phase':weight_phase, 'activation_phase':activation_phase,
            'activation_access':'DIRECT', 'context_id':0, 'generation':0}


def location(profile, offset):
    p, o = 2, offset
    if profile=='Q4_K' and offset>=16: p,o=0,offset-16
    elif profile=='Q5_K':
        if offset>=48:p,o=0,offset-48
        elif offset>=16:p,o=1,offset-16
    elif profile=='Q6_K':p,o=(0,offset) if offset<128 else (1,offset-128) if offset<192 else (2,offset-192)
    elif profile=='Q3_K':p,o=(1,offset) if offset<32 else (0,offset-32) if offset<96 else (2,offset-96)
    elif profile=='Q2_K':p,o=(2,offset-64) if offset>=80 else (0,offset-16) if offset>=16 else (2,offset)
    elif profile=='Q5_0' and offset>=6:p,o=0,offset-6
    elif profile in ('Q4_0','Q8_0_WEIGHT','IQ4_NL') and offset>=2:p,o=0,offset-2
    return p,o


def activation_map(config, absolute, context):
    scale,quants,block=(4,256,292) if config['activation_profile']=='Q8_K' else (2,32,34)
    count=1 if config['activation_layout']=='ROW' else 4 if config['activation_layout']=='M4' else 8
    if count==1:return context,absolute,absolute<block
    if absolute<count*scale:ctx,off=divmod(absolute,scale)
    elif absolute<count*(scale+quants):
        quant=absolute-count*scale;ctx=quant%count;off=scale+quant//count
    else:
        aux=absolute-count*(scale+quants);ctx=(aux//2)%count;off=scale+quants+(aux//(2*count))*2+aux%2
    return ctx,off,absolute<count*block


def beats(length, phase):
    offset=0
    while offset<length:
        count=min(16-((phase+offset)%16),length-offset)
        yield offset,count
        offset+=count


def streams(config, role, bank):
    block=PROFILES[config['weight_profile']] if role=='weight' else 292 if config['activation_profile']=='Q8_K' else 34
    ranges=[(0,4*block)] if role=='weight' else ([(c,block) for c in range(4)] if config['activation_layout']=='ROW' else [(0,(8 if config['activation_layout']=='M8' else 4)*block)])
    for context,length in ranges:
        phase=config['weight_phase'] if role=='weight' else (config['activation_phase']+context*block)%16
        for offset,count in beats(length,phase):
            targets=[]
            for b in range(16):
                absolute=offset+b
                if role=='weight':
                    row,native=divmod(absolute,block);valid=b<count and row<4
                    plane,loc=location(config['weight_profile'],native)
                else:
                    ctx,native,valid=activation_map(config,absolute,context)
                    row=ctx-4*bank;valid=valid and b<count and 0<=row<4
                    scale,quants=(4,256) if config['activation_profile']=='Q8_K' else (2,32)
                    plane,loc=(0,native-scale) if scale<=native<scale+quants else (2,native-quants if native>=scale+quants else native)
                targets.append({'valid':bool(valid),'row':row%4,'native':native,'plane':plane,'loc':loc,'b':b})
            yield {'role':role,'context':context,'offset':offset,'count':count,'targets':targets}


def coordinate(kind, slot, row, plane_or_group, byte, bit):
    if kind=='hit':return ('hit',slot,plane_or_group,row,byte,bit)
    return ('group_hit',slot,row,plane_or_group,bit)


def overapprox(beat, role, slot):
    result=set()
    for b,t in enumerate(beat['targets']):
        if not t['valid']:continue
        result.add((role,coordinate('group_hit',slot,t['row'],t['native']//16,0,b)))
        if t['plane']<2:
            plane=2 if role=='activation' else t['plane'];width=32 if plane==2 else 16
            result.add((role,coordinate('hit',slot,t['row'],plane,t['loc']%width,b)))
    return result


def cycle(older,newer,role):
    consumed=[set(),set()];events=set();selected={}
    for slot,beat in enumerate((older,newer)):
        if beat is None:continue
        for plane in ([2] if role=='activation' else [0,1]):
            for row in range(4):
                candidates=[t for t in beat['targets'] if t['valid'] and t['row']==row and t['plane']==(0 if role=='activation' else plane)]
                if not candidates:continue
                shift=5 if plane==2 else 4
                word=selected.get((plane,row),candidates[0]['loc']>>shift)
                if slot==0:selected[plane,row]=word
                for t in candidates:
                    if t['loc']>>shift!=word:continue
                    consumed[slot].add(t['b']);events.add((role,coordinate('hit',slot,row,plane,t['loc']% (1<<shift),t['b'])))
        for t in beat['targets']:
            if t['valid'] and t['plane']==2:consumed[slot].add(t['b'])
        for t in beat['targets']:
            if t['b'] in consumed[slot]:events.add((role,coordinate('group_hit',slot,t['row'],t['native']//16,0,t['b'])))
    remaining=[]
    for slot,beat in enumerate((older,newer)):
        if beat is None:remaining.append(None);continue
        rem=dict(beat,targets=[dict(t,valid=t['valid'] and t['b'] not in consumed[slot]) for t in beat['targets']])
        remaining.append(rem if any(t['valid'] for t in rem['targets']) else None)
    return events,remaining


def trace(config,role,bank):
    observed={};pending=None
    for tick,beat in enumerate(streams(config,role,bank)):
        events,rem=cycle(pending,beat,role)
        for e in events:observed.setdefault(e,{'tick':tick,'new_range_offset':beat['offset'],
                                               'pending_range_offset':None if pending is None else pending['offset']})
        # Integrated pending slot stores the accepted newer beat's original byte indices.
        need(rem[0] is None, 'Model requires old pending drained before accepting newer leftovers')
        pending=rem[1]
    if pending:
        events,rem=cycle(pending,None,role);need(rem==[None,None],'Pending drain')
        for e in events:observed.setdefault(e,{'tick':'last_drain','new_range_offset':None,'pending_range_offset':pending['offset']})
    return observed


def parse_node(scope,n):
    bank=int(scope[len(BASE)])
    m=re.fullmatch(r'gen_write_merge\[(\d+)\].gen_bank_plane\[(\d+)\].gen_bank_row\[(\d+)\].gen_byte_merge\[(\d+)\].hit',n['name'])
    if m:
        slot,p,row,j=map(int,m.groups());return bank,'activation' if p==2 else 'weight',lambda b:coordinate('hit',slot,row,p,j,b)
    m=re.fullmatch(r'gen_bitmap_storage.gen_byte_valid\[(\d+)\].gen_(weight|activation)\[(\d+)\].group_hit',n['name'])
    need(m,'Exact generated routing field');row,role,g=int(m[1]),m[2],int(m[3])
    return bank,role,lambda b:coordinate('group_hit',b//16,row,g,0,b%16)


def collect():
    need(digest(AUDIT)==AUDIT_SHA,'Exact770 actual audit seal')
    bookpath=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    need(digest(bookpath)=='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b','Frozen build sourcebook')
    book=json.loads(bookpath.read_bytes());pins={str(AUDIT):AUDIT_SHA,str(bookpath):digest(bookpath)}
    for rel in SOURCES:
        p=ROOT/rel;need(digest(p)==book[str(p)],'Frozen source mismatch '+rel);pins[str(p)]=digest(p)
    db=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    for rel in ('shape/tgl.verilog.shape.xml','auxiliary/verilog.sourceinfo.xml'):
        p=db/rel;pins[str(p)]=digest(p)
    defs={d.get('chksum'):d for d in xml(db/'shape/tgl.verilog.shape.xml').findall('tgldef')}
    files={n.get('id'):n.get('name') for n in xml(db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    audit=json.loads(AUDIT.read_bytes());nodes=[]
    for s in audit['scopes']:
        if not s['scope'].startswith(BASE):continue
        if s['module'] not in ('qbs_block_adapter','qbs_payload_buffer'):continue
        d=defs[s['checksum']]
        need((s['module'],s['checksum']) in [('qbs_block_adapter','3028946256'),
                                           ('qbs_payload_buffer','3657545390')], 'Exact compiled routing definition')
        # VCS merged definitions omit param attributes; do not invent per-instance metadata.
        compute=(ROOT/'hardware/src/vlsu/qbs/qbs_compute_engine.sv').read_text()
        need('.ActivationContextBase (4)' in compute and ') i_block_adapter_bank1 (' in compute,
             'Pinned bank1 producer source binding')
        for n in s['objects']:
            if not(n['name'].endswith('.hit') or n['name'].endswith('.group_hit')):continue
            need(n['kind']=='vectornode' and n['portnode']=='0' and n['right']=='0' and n['left'] in ('15','31'),'Exact internal routingvector')
            expected=ROOT/'hardware/src/vlsu/qbs'/('qbs_payload_buffer.sv' if n['name'].endswith('.hit') else 'qbs_block_adapter.sv')
            need(files[n['file']]==str(expected),'Actual field declaration source')
            nodes.append((s,n,parse_node(s['scope'],n)))
    need(len(nodes)==520 and sum(n['missing_slots'] for _,n,_ in nodes)==13428,'Exact actual routing gaps')
    needed=defaultdict(set)
    for s,n,(bank,role,coord) in nodes:
        for i in n['missing_coordinates']:needed[bank].add((role,coord((i-n['serialized_offset'])//2)))
    possible=defaultdict(set);best=None;witnesses={};domains=0
    # Finite legal ABI residue classes, host proof enumeration only, never DUT trial runs.
    for profile in PROFILES:
      for layout in ('ROW','M4','M8'):
       for wp in range(0,16,2):
        for ap in range(0,16,4):
         c=configuration(profile,layout,wp,ap);domains+=1;seen={}
         for bank in range(2):
          seen[bank]={}
          for role in ('weight','activation'):
           for beat in streams(c,role,bank):
            for slot in range(2):possible[bank].update(overapprox(beat,role,slot))
           seen[bank].update(trace(c,role,bank))
         score=sum(2*len(set(seen[b])&needed[b]) for b in range(2))
         if best is None or score>best['potential_missing_directions_upper_bound']:
          best={'descriptor':c,'potential_missing_directions_upper_bound':score};witnesses=seen
    classified=[];counts=defaultdict(int)
    for s,n,(bank,role,coord) in nodes:
        categories=defaultdict(list)
        for i in n['missing_coordinates']:
            b=(i-n['serialized_offset'])//2;key=(role,coord(b))
            cat='structural_no_legal_byte_mapping' if key not in possible[bank] else 'selected_host_trace_witness' if key in witnesses[bank] else 'legal_mapping_pending_or_schedule_unresolved'
            categories[cat].append(i);counts[cat]+=1
        classified.append({'scope':s['scope'],'name':n['name'],'checksum':s['checksum'],
                           'source_file':files[n['file']],'source_line':n['line_num'],'bounds':[n['left'],n['right']],
                           'attributes':{k:v for k,v in n.items() if k not in ('missing_coordinates','missing_slots')},
                           'classification_missing_coordinates':dict(categories)})
    examples=[]
    for s,n,(bank,role,coord) in nodes:
        for i in n['missing_coordinates']:
            bit=(i-n['serialized_offset'])//2;key=(role,coord(bit))
            if key in witnesses[bank]:examples.append({'scope':s['scope'],'name':n['name'],'bit':bit,'missing_coordinate':i,**witnesses[bank][key]});break
        if len(examples)>=12:break
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_preflight_qbs_route770.py')):pins[str(path)]=digest(path)
    for p,h in pins.items():need(digest(p)==h,'Phase-end pin drift')
    return {'status':'STATIC_ROUTING_DOMAIN_AND_HOST_TRACE_ONLY','population':770,'fields':520,'actual_missing_directions':13428,
            'classification_counts':dict(counts),'legal_residue_classes_enumerated':domains,'selected_one_case':best,
            'selected_witness_examples':examples,'fields_with_exact_missing_coordinates':classified,
            'source_lemmas':['Reader compact byte b retains original b through registered/pending targets; physical aligned beat boundaries cannot add odd weight range offset.',
             'Every valid weight profile block size and payload region displacement is even. Therefore weight hit byte_lane parity must equal writer b parity, including stale registered/pending values.',
             'Bank1 activation targets require global contexts4..7. Engine supplies these only from M8 interleaving; bank0 also permits ROW/M4. Profile/layout changes cannot invent targets beyond previously accepted source byte mappings.',
             'Mapping overapprox admits ALL valid bytes in both slots, any selected SRAM word, any consume schedule. A coordinate absent even from that superset is impossible on a legal accepted-byte mapping; no idle/valid-cycle-only constant claim.',
             'Source group_hit is native target offset/16 with commit gating; hit is payload location byte plus exact word_match. Side metadata never enters payload hit.'],
            'limits':['Compiled VCS routing definitions carry module/checksum/source coordinates but no param attribute. Bank context0/4 and StreamWriteData/PredecodedWriteLocations are pinned source instantiation bindings, not invented native parameter metadata.',
             'Structural classification is source/host proof, not native qualification or an EL candidate. Abort/reset/stale metadata and invalid descriptors must remain protected until independent temporal driver review.',
             'Selected trace assumes continuous legal response availability and exact older-first per-bank word selection; pending drain assertions are checked. Host witness does not guarantee DUT timing or both native directions.',
             'This preflight has no ELF/Spike/full-VRF/CSR or independent numerical oracle; any proposed run requires those before authorization.',
             'No RTL simulation, random parameter trials, EDA or coverage admission. MFPU272 seals untouched.'],
            'simulation_recommended':bool(examples),'vcs_launched':False,'EDA_launched':False,'coverage_admitted':False,'official_percentage':None,'pins':pins}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','verify']);p.add_argument('--seal');a=p.parse_args()
    if a.mode=='prepare':
        need(not REPORT.exists(),'Fresh output only');r=collect();REPORT.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'report':str(REPORT),'seal':digest(REPORT),'classification':r['classification_counts'],'case':r['selected_one_case']}))
    else:
        need(a.seal and digest(REPORT)==a.seal,'Exact report seal');need(json.loads(REPORT.read_bytes())==collect(),'Independent host replay differs');print('QBS_ROUTE_HOST_VERIFY_PASS_NOT_DUT_QUALIFIED')
