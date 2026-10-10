"""Sealed794 complete policy plus exact PMP816 handoff; no DVE entry."""
import argparse
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re

import report_population794_soc61 as global794
import report_population783_fpnew90 as grammar
import pmp_constants816_native as local

life,need,stable=global794.life,global794.need,global794.stable
GLOBAL=life.OUT/'current-population794-soc61-parent-20261008-01'
LOCAL=life.OUT/'pmp-constants816-native-parent-20261008-01'
LOCAL_SHA='1b7bc2ef450a3280094b3f701e80c812a238a2e2d2534ac2dfbdfcc6bd7f7c48'
GLOBAL_SHA='fce23ff83487b83e51c069863710f4fad0c11716070ed3d4327aa57470972007'
GLOBAL_CONFIG_SHA='81526ba2020842417df95403931ca06441716ecf7b98ebf88ba0a67daca9434f'
FLAGS=('complete_approved_EL_bitmask_union','all_other_bits_protected','raw_reset_final_equal',
       'applied_reloaded_equal','raw_hierarchy_vs_rooted_six_metrics_equal','supported_roots_all_six_metrics_present')


def related(a,b):return a==b or a.startswith((b+'.',b+'[')) or b.startswith((a+'.',a+'['))


@lru_cache(maxsize=1)
def fsm_shapes():
    c=life.read_bound(GLOBAL/'config.json',GLOBAL_CONFIG_SHA)
    path=Path(c['input_ledger'][0])/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    need(life.digest(path)==c['pins'][str(path)],'Actual compiled FSM shape pin')
    result={}
    for definition in local.proof.old.base.t.xml(path).findall('fsmdef'):
        for instance in definition.findall('fsminst'):
            for machine in definition.findall('fsmshape/fsmfsm'):
                key=(instance.get('name'),definition.get('chksum'),machine.get('name'),machine.get('chksum'))
                need(key not in result,'Unique compiled FSM machine tuple')
                result[key]=machine
    return result


def compiled_fsm_record(record,records):
    scope,checks,machine,line=record
    checksum=re.fullmatch(r'(\d+) (\d+)',checks)
    header=re.fullmatch(r'Fsm ([^\s"]+) "(\d+)"',line if not machine else machine)
    if not checksum or not header:return False
    node=fsm_shapes().get((scope,checksum[2],header[1],header[2]))
    if node is None:return False
    if not machine:return True
    if (scope,checks,'',machine) not in records:return False
    states={s.get('name'):(s.get('value'),s.get('id')) for s in node.findall('state')}
    state=re.fullmatch(r'State ([^\s"]+) "(\d+)"',line)
    if state:return state[1] in states and state[2]==states[state[1]][0]
    edge=re.fullmatch(r'Transition ([^\s"<>]+)->([^\s"<>]+) "(\d+)->(\d+)"',line)
    if not edge or edge[1] not in states or edge[2] not in states:return False
    a,b=states[edge[1]],states[edge[2]]
    return (edge[3],edge[4])==(a[0],b[0]) and any(t.get('fromid')==a[1] and t.get('toid')==b[1] for t in node.findall('transition'))


def union_gate(base,addition,config):
    members=local.el_gate(addition,config)
    need(len(members)==816,'Exact qualified816 target fields')
    old,extra=stable.semantic(base),stable.semantic(addition)
    occupied,targets=global794.physical(old),global794.physical(extra)
    need(not extra[0] and sum(bin(mask).count('1') for mask in targets.values())==2176,
         'Exact scalar/vector2176 directions, no MDA/scope additions')
    opaque=[r for r in old[0] if not compiled_fsm_record(r,old[0])]
    by_scope=defaultdict(list)
    for key,mask in occupied.items():by_scope[key[0]].append((key,mask))
    for key,mask in targets.items():
        scope,checksum,name,prefix,direction=key
        need(not prefix,'No target MDA')
        need(not any(scope==r[0] or scope.startswith(r[0]+'.') for r in opaque),'Unknown/whole ancestor ownership')
        for before,value in by_scope[scope]:
            need(before[1]==checksum,'Same-scope checksum conflict')
            if before[2:]==key[2:]:need(not value&mask,'Already-owned physical direction including bare scalar')
            elif related(name,before[2]):need(False,'Packed parent/child or MDA ownership ambiguity')
    combined=base.rstrip('\n')+'\n'+addition.rstrip('\n')+'\n'
    actual=stable.semantic(combined);expected=dict(occupied)
    for key,mask in targets.items():expected[key]=expected.get(key,0)|mask
    need(actual[0]==old[0] and global794.physical(actual)==expected,'Entire prior metrics and all masks preserved')
    return combined


def global_gate(q,c):
    need(q['status']=='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['population']==q['actual_selected_tests']==794 and q['admission_seal']==global794.BASE_SHA and
         q['config_seal']==GLOBAL_CONFIG_SHA and
         q['source_design_native_pins']==c['pins'] and q['EL_additions']==c['EL_additions'] and
         q['EL_additions']['new_direction_count']==7686 and q['new_exclusions_added'] is True,
         'Actual794 plus61 qualification required, not prepared/provisional')
    for flag in FLAGS:need(q[flag] is True,'Full prior native gate '+flag)
    need(c['schema']==global794.SCHEMA and len(c['hierarchy_roots'])==72 and
         len(c['input_ledger'])==len(set(c['input_ledger']))==795,'Exact794 population/root ledger')


def zero_gate(q,union,definitions):
    scopes={r['scope'] for r in q['fresh_candidates']}
    need(set(definitions)==scopes and scopes<=set(union),'Complete typed source scopes')
    for scope in scopes:
        row=union[scope]
        nodes,_=local.proof.old.base.typed.typed_nodes(definitions[scope]['shape'],row)
        names={n['name']:n for n in nodes}
        need(len(names)==len(nodes),'Unique serializer fields')
        for r in [r for r in q['fresh_candidates'] if r['scope']==scope]:
            expected=r['compiled'];actual=names.get(expected['name'])
            need(row['checksum']==r['checksum'] and definitions[scope]['module']==r['module'] and actual is not None and
                 all(actual.get(k)==v for k,v in expected.items() if k not in ('missing_coordinates','missing_slots')),
                 'Exact source/serialized attrs/checksum/module')
            coords=list(range(expected['serialized_offset'],expected['serialized_offset']+2*expected['logical_width']))
            need(actual['missing_coordinates']==expected['missing_coordinates']==coords,
                 'Source-zero counterexample in admitted population')


def prepare(out,global_seal):
    need(out.parent==life.OUT and not out.exists(),'Fresh handoff only')
    need(global_seal==GLOBAL_SHA,'Exact parent-published794 qualification SHA; no inference')
    reader=global794.prior.inherited.Reader()
    q=reader.read(GLOBAL/'qualification.json',global_seal,True)
    c=reader.read(GLOBAL/'config.json',q['config_seal'],True);global_gate(q,c)
    pins=stable.merge(c['pins'],q['output_pins'],reader.pins)
    for path,sha in q['output_pins'].items():reader.read(Path(path),sha)
    base=reader.read(GLOBAL/'combined.el',pins[str(GLOBAL/'combined.el')]).decode('ascii')
    need(stable.semantic_seal(stable.semantic(base))==c['expected_EL_semantic_sha256'],'Complete inherited EL seal')
    for name in ('applied.el','reloaded.el'):
        need(stable.semantic(reader.read(GLOBAL/name,pins[str(GLOBAL/name)]).decode('ascii'))==stable.semantic(base),'Actual global applied/reload equality')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        need(reader.read(GLOBAL/name,pins[str(GLOBAL/name)])==b'','Actual global empty reset')
    local_q=reader.read(LOCAL/'capture-result.json',LOCAL_SHA,True)
    local_c=reader.read(LOCAL/'config.json',local_q['config_seal'],True)
    need(local_q['status']=='PMP_CONSTANTS816_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED' and
         local_q['fields']==816 and local_q['directions']==2176 and local_q['target_MDA']==0 and
         local_q['source_MDA_HOLD']==13 and local_q['initial_X_or_delta_instrumentation_qualified'] is False and
         local_q['stages']==list(local.STAGES) and type(local_q['terminal_returncode']) is int and
         local_q['terminal_returncode']==0 and local_q['population_application'] is False,'Exact independent PMP local receipt')
    need(local.verify(LOCAL,local_q['config_seal'])==local_q,'Full local five-stage/source/terminal replay')
    pins=stable.merge(pins,local_c['pins'],local_q['pins'],reader.pins)
    first,second=[reader.read(LOCAL/name,pins[str(LOCAL/name)]).decode('ascii') for name in ('first.el','second.el')]
    need(local.el_gate(first,local_c)==local.el_gate(second,local_c),'Actual scalar/vector local semantic reload')
    need(local_c['design']==c['input_ledger'][0],'Same frozen design')
    proof=reader.read(local.SOURCE,local.SOURCE_SHA,True)
    manifest=reader.read(global794.BASE,global794.BASE_SHA,True)
    authority=stable.merge(manifest['input_pins'],manifest['output_pins'])
    ledger_path=global794.BASE.parent/'combined-inputs.txt'
    need(reader.read(ledger_path,authority[str(ledger_path)]).decode('ascii').splitlines()==c['input_ledger'],'Exact formal794 full prefix')
    up=global794.BASE.parent/'combined-toggle-bits.json';union=reader.read(up,authority[str(up)],True)
    db=Path(c['input_ledger'][0])/'snps/coverage/db';trees=[]
    for name in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        p=db/name;reader.read(p,authority[str(p)]);trees.append(local.proof.old.base.t.xml(p))
    _,definitions=local.proof.old.base.t.definitions(*trees,{r['scope'] for r in proof['fresh_candidates']})
    zero_gate(proof,union,definitions)
    combined=union_gate(base,second,local_c)
    pins=stable.merge(pins,reader.pins)
    for module in (local,global794,grammar,local.proof):pins[str(Path(module.__file__).resolve())]=life.digest(module.__file__)
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_pmp816_global_union.py')):pins[str(p)]=life.digest(p)
    reader.finish(pins)
    result=dict(status='PMP816_EXACT794_UNION_HANDOFF_PREPARED_NOT_POPULATION_APPLIED',population=794,
                global_qualification_sha256=global_seal,local_qualification_sha256=LOCAL_SHA,
                fields=816,directions=2176,source_MDA_HOLD=13,exact_physical_disjoint=True,
                inherited_EL_bytes_preserved=True,global_combined_EL_sha256=pins[str(GLOBAL/'combined.el')],
                union_semantic_sha256=stable.semantic_seal(stable.semantic(combined)),input_pins=pins,
                EDA_started=False,population_application=False,initial_X_qualified=False)
    out.mkdir();(out/'candidate-union.el').write_text(combined)
    result['output_pins']={str(out/'candidate-union.el'):life.digest(out/'candidate-union.el')}
    life.save(out/'handoff.json',result)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'handoff.json'),EDA_started=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--global-qualification-seal',required=True);a=p.parse_args()
    prepare(a.output.resolve(),a.global_qualification_seal)
