"""Static prepare only: exact312 fields, historical native binding, all68 rows/scope."""
import argparse
from collections import defaultdict
import csv
from functools import lru_cache
import json
from pathlib import Path
import re
import qualify_requester_read108_native as base
import review_queue_fp_residual768 as source

life,require,HERE=base.life,base.require,base.HERE
REVIEW=life.OUT/'operand-queue-fp-residual768-static-agent-20261007-02.json'
REVIEW_SHA='7f0b43d380871fb7986abf2c547117a6d7bf7cdefe121a32c8e6737293c98d5d'
PRIOR=life.OUT/'queue-constant-native-744-agent-20261007-03'
PRIOR_SHA='b2d53834d046de0a722342dfdce8dbdacc7c3898c2abb21e9618d8adae0dd7a6'
CAPTURE_SHA='15dcd0fc0a923f0ea8d49ef0a6edd3c89d711cee7ff546edf1ede125347daa87'
ANNOTATION='Frozen global queue FP temporaries: FPU0 globals or unconditional global fp8 zero; settled known controls only, no initial-X waiver'
STAGES=base.STAGES
bounds,aliases=base.bounds,base.aliases


@lru_cache(maxsize=1)
def instances():
    r=life.read_bound(REVIEW,REVIEW_SHA)
    old=life.read_bound(PRIOR/'config.json',PRIOR_SHA)
    result=[]
    for scope in sorted({n['scope'] for n in r['candidates']}):
        previous=[i for i in old['instances'] if i['scope']==scope]
        require(len(previous)==1,'Exact historical scope, not checksum-only specialization')
        targets=[dict(n['definition'],kind=n['kind']) for n in r['candidates'] if n['scope']==scope]
        protected=next(i['objects'] for i in r['protected_by_scope'] if i['scope']==scope)
        alu=scope.split('.')[-1] in ('i_operand_queue_alu_a','i_operand_queue_alu_b')
        expected=source.old.fields() if alu else source.FP8
        require({n['name'] for n in targets}==expected and len(targets)+len(protected)==68,
                'Per-scope target/complement, no dynamic MFPU FP16/32')
        require(len({n['name'] for n in targets+protected})==68,'Complete unique compiled fields')
        result.append(dict(scope=scope,targets=targets,protected=protected,
            design_module_checksum=previous[0]['design_module_checksum'],toggle_checksum='2109767059',
            source_FPUSupport=0 if alu else 56,parameter_proof='Explicit frozen instance FPUSupportNone' if alu else
                'No FPUSupport dependence in global fp8 zero proof',shape_parameters_are_not_instance_proof=True))
    require(len(result)==20 and sum(len(i['targets']) for i in result)==312 and
            sum(len(i['protected']) for i in result)==1048,'Exact20/312/1048 scope')
    return result


def bind_rows(rows,i,stage,flags=True):
    count=5 if flags else 6
    require(stage in STAGES and len(rows)==68 and all(len(r)==count and all(r[:4]) for r in rows),
            'All68 native objects with exact schema')
    require(len({r[0] for r in rows})==len({r[1] for r in rows})==68,'Unique native handles/paths')
    byname=defaultdict(list)
    for r in rows:byname[r[3]].append(r)
    used=set();result=[];targets={n['name'] for n in i['targets']}
    for n in i['targets']+i['protected']:
        matches=[r for name in aliases(n) for r in byname[name]]
        require(len(matches)==1 and matches[0][0] not in used,'Missing/ambiguous complete field: '+n['name'])
        r=matches[0];used.add(r[0])
        require(r[1]==r[3] and r[2] in (r[3],'logic '+n['name']+bounds(n),'logic '+bounds(n)+n['name']),
                'Exact field path/meta; no automatic local shadow alias')
        if flags:
            expected='1' if stage in ('selected','reloaded') and n['name'] in targets else '0'
            require(r[4]==expected,'Target/protected excluded flag: '+n['name'])
        result.append((n['name'],r[1],r[2],r[3]))
    require(len(used)==len(rows),'No extra/untyped native container silently ignored')
    return sorted(result)


def historical_binding():
    old=life.read_bound(PRIOR/'config.json',PRIOR_SHA)
    capture=life.read_bound(PRIOR/'capture-result.json',CAPTURE_SHA)
    require(capture['status']=='QUEUE_CONSTANT_EXACT_NATIVE_BIT_DIRECTION_ROUNDTRIP_PASS','Actual successful prior capture')
    review=life.read_bound(REVIEW,REVIEW_SHA)
    for rel in ('hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_queues_stage.sv'):
        key=str(life.ROOT/rel)
        require(old['pins'][key]==review['pins'][key],'Historical/current frozen source linkage')
    pins={str(PRIOR/'config.json'):PRIOR_SHA,str(PRIOR/'capture-result.json'):CAPTURE_SHA}
    bindings=[]
    for i in instances():
        k=next(k for k,n in enumerate(old['instances']) if n['scope']==i['scope'])
        p=PRIOR/('native_before_%d.tsv'%k);h=capture['pins'][str(p)]
        require(life.digest(p)==h,'Historical actual rows drift');pins[str(p)]=h
        with p.open(newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
        require(rows[0]==['handle','path','meta','name','column1','column2'],'Actual historical schema')
        bindings.append(dict(scope=i['scope'],actual_file=str(p),actual_sha=h,
            exact_full68_identity=bind_rows(rows[1:],i,'before',False),
            proof='Actual path/name/meta full bijection plus frozen source instance; shared shape/checksum alone is insufficient',
            historical_excluded_flags_not_claimed=True,fresh_five_stage_flags_required=True))
    return bindings,pins


def contract(c):
    require(c['instances']==instances() and c['source_review_seal']==REVIEW_SHA and c['timeout_seconds']==900 and
            c['population_application'] is False and c['automatic_retry'] is False and c['launch_authorized'] is False,
            'Only approved static prepare, exact source/field scope')


def inventory(out,c,stage,index):
    require(stage in STAGES and 0<=index<20,'Exact stage/scope')
    with (out/('native_%s_%d.tsv'%(stage,index))).open(newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
    require(rows and rows[0]==['handle','path','meta','name','excluded'],'Live full excluded-status schema')
    bound=bind_rows(rows[1:],c['instances'][index],stage)
    require(bound==c['historical_bindings'][index]['exact_full68_identity'] or
            [tuple(r) for r in c['historical_bindings'][index]['exact_full68_identity']]==bound,
            'Actual scope identity differs from historical full68 binding')
    return bound


def parse_el(text,c):
    expected={(i['scope'],n['name']):(i,n) for i in c['instances'] for n in i['targets']}
    found=defaultdict(list);blocks=set();scope=check=annotation=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            require(line=='ANNOTATION: "'+ANNOTATION+'"','Exact annotation');annotation=ANNOTATION
        elif line.startswith('CHECKSUM:'):
            m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line);require(m is not None,'Checksum syntax');check=m.groups();scope=None
        elif line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip();require(scope not in blocks,'Duplicate scope block');blocks.add(scope)
            i=next((i for i in c['instances'] if i['scope']==scope),None)
            require(i and check==(i['design_module_checksum'],i['toggle_checksum']),'Exact source scope/checksum, not merged-family substitution')
        else:
            m=re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) "logic ([^"]+)"',line)
            require(m is not None and annotation==ANNOTATION,'Only exact typed whole Toggle')
            direction,name,decl=m.groups();key=scope,name
            require(key in expected,'Protected field/port/local shadow or wrong specialization')
            _,n=expected[key];require(decl in (name+bounds(n),bounds(n)+name),'Exact full ordered dimensions')
            found[key].append(direction)
    require(set(found)==set(expected) and len(blocks)==20,'Exact312 fields across20 scopes')
    for dirs in found.values():require(dirs==[None] or len(dirs)==2 and set(dirs)=={'0to1','1to0'},'Duplicate or missing direction')
    return sorted((scope,name,bounds(expected[scope,name][1]),ANNOTATION) for scope,name in found)


def check_file(out,c,name):
    require(name in ('first.el','second.el','initial-empty.el','reset-empty.el','final-empty.el'),'Exact filename')
    if name.endswith('empty.el'):require((out/name).read_bytes()==b'','Global empty EL');return 0
    return len(parse_el((out/name).read_text(),c))


def inspect(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and terminal['timeout'] is False and len(terminal['actual_dve'])==1,'Actual executable/terminal')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('QUEUE_FP312_NATIVE_DONE')==1 and 'QUEUE_FP312_NATIVE_FAILED' not in gui and
            not (out/'error.txt').exists(),'Five stages incomplete')
    for index in range(20):
        before=inventory(out,c,'before',index)
        for stage in STAGES[1:]:require(inventory(out,c,stage,index)==before,'Complete target/complement drift')
    for name in ('first.el','second.el','initial-empty.el','reset-empty.el','final-empty.el'):check_file(out,c,name)
    require(parse_el((out/'first.el').read_text(),c)==parse_el((out/'second.el').read_text(),c),'Exact annotation/type semantic reload')
    pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and
        p.name not in ('capture-result.json','worker.log')})
    result=dict(status='EXACT_QUEUE_FP312_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=seal,
        source_review_seal=REVIEW_SHA,objects=312,logical_bits=1152,protected_objects=1048,full_native_rows=1360,
        historical_identity_full_bijection=True,fresh_all_five_stage_flags_checked=True,
        exact_EL_scope_checksum_full_types_annotation_directions=True,semantic_reload=True,
        global_initial_reset_final_empty=True,merged_shape_not_used_as_parameter_proof=True,
        initial_X_excluded=False,population_application=False,official_percentage=None,pins=pins)
    path=out/'capture-result.json'
    if path.exists():require(json.loads(path.read_bytes())==result,'Existing result differs; sealed output not overwritten')
    else:life.save(path,result)
    print('FULL312_FIVE_STAGE_GATES_PASS_NOT_APPLIED')


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh static prepare directory')
    r=life.read_bound(REVIEW,REVIEW_SHA);life.check(r['pins'])
    source.source_contract((life.ROOT/'hardware/src/lane/operand_queue.sv').read_text(),
                           (life.ROOT/'hardware/src/lane/operand_queues_stage.sv').read_text())
    bindings,pins=historical_binding()
    origin=base.runner.inherited.PRODUCT/'config.json';identity=json.loads(origin.read_bytes())['identity'];base.tools.revalidate(identity)
    deps=[REVIEW,origin,Path(__file__),HERE/'qualify_queue_fp312_native.tcl',HERE/'test_qualify_queue_fp312_native.py',
          Path(base.__file__),Path(source.__file__),Path(source.old.__file__),Path(source.lexical.__file__),Path(base.primitive.__file__),
          Path(base.runner.__file__),Path(base.runner.inherited.__file__),Path(life.__file__),Path(base.tools.__file__),
          HERE/'qualify_requester_read108_native.tcl',HERE/'queue_fp_temporaries_native.tcl',HERE/'fma_datapath_native.tcl']
    deps.append(HERE/'test_qualify_requester_read108_native.py')
    vdb=life.OUT/'stride-metadata-full64-old-image767-agent-20261007-01/code.vdb'
    tests=list((vdb/'snps/coverage/db/testdata').iterdir());require(len(tests)==1,'One admitted native context')
    pins=life.merge_pins(life.merge_pins(r['pins'],pins),
        {str(p):life.digest(p) for p in deps+list(vdb.rglob('*')) if p.is_file()})
    c=dict(instances=instances(),historical_bindings=bindings,identity=identity,pins=pins,source_review_seal=REVIEW_SHA,
        timeout_seconds=900,automatic_retry=False,population_application=False,launch_authorized=False,output=str(out),
        status='STATIC_PREPARED_HISTORICAL_FULL68_IDENTITY_BOUND_FRESH_NATIVE_QUALIFICATION_HOLD',
        objects=312,logical_bits=1152,protected_objects=1048,full_rows=1360,
        source_scope='Known legal config/controls after valid reset and settled evaluation; no X/delta exclusion',
        parameter_join='ALU literal None comes from exact frozen stage instance, never inferred from shared0/56 shape; MFPU fp8 proof is parameter independent',
        live_before_barrier='All20 scopes full68 identity/zero-excluded audit precedes any exclusion; later typed EL must retain exact per-scope allowlist',
        bounded_calls=dict(scope_bindings=120,excluded_status_queries=8160,target_excludes=312,EL_saves=5,reloads=1,global_resets=2),
        approved_launch_command=None)
    contract(c);life.check(pins);out.mkdir()
    values=dict(fma_design=str(life.IMAGE)+'.vdb',fma_vdb=str(vdb),fma_test=str(vdb.with_suffix('')/tests[0].name),
        fma_python=str(life.ROOT/'verification/tools/soc-venv/bin/python'),fma_helper=str(Path(__file__).resolve()),
        qfp_primitives=str(HERE/'fma_datapath_native.tcl'))
    require(all(not any(ch in value for ch in '{}\\\r\n') for value in values.values()),'Safe Tcl literal paths')
    lines=['set %s {%s}\n'%pair for pair in values.items()]+['set fma_instances {}\n']
    for k,i in enumerate(c['instances']):
        lines.append('lappend fma_instances [list {%s} {%s} {%s} %d %d 68]\n'%(i['scope'],
            ' '.join(n['name']+bounds(n) for n in i['targets']),' '.join(n['name']+bounds(n) for n in i['protected']),k,len(i['targets'])))
    with (out/'selection.tcl').open('x') as f:f.write(''.join(lines))
    pins[str(out/'selection.tcl')]=life.digest(out/'selection.tcl');life.save(out/'config.json',c)
    print('PREPARED_NO_LAUNCH',str(out),life.digest(out/'config.json'),len(pins))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','verify','inventory','el','inspect'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seal');ap.add_argument('--stage');ap.add_argument('--index',type=int);ap.add_argument('--file')
    a=ap.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('inventory','el'):
        c=json.loads((out/'config.json').read_bytes())
        print(len(inventory(out,c,a.stage,a.index)) if a.mode=='inventory' else check_file(out,c,a.file))
    else:
        require(a.seal,'Exact config seal')
        if a.mode=='inspect':inspect(out,a.seal)
        else:c=life.read_bound(out/'config.json',a.seal);contract(c);life.check(c['pins']);historical_binding();print('STATIC_VERIFY_PASS_NATIVE_HOLD_NO_LAUNCH')
