"""Fresh775 consumer: closed771 + exact Branch720/MFPU272/RVH60. No automatic launch."""
import argparse
import copy
import csv
import io
import json
from pathlib import Path
import re
from types import FunctionType

import report_native_full773_branch720 as prior
import mfpu272_five_phase as mfpu
import verify_rvh0_exception60_v5_completion_offline as rvh

life, need, HERE = prior.life, prior.require, prior.HERE
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'FORMAL775_CLOSED771_BRANCH720_MFPU272_RVH60_V1'
BASE = life.OUT / 'vmacc-offline-admitted775-parent-20261007-01'
BASE_SHA = '59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13'
BASE774 = life.OUT / 'itlb-bulk-offline-admitted774-parent-20261007-01'
SHA774 = '5a5f9cdb4fcd5a26ba48628344a1c1028426709453bd8cb1adbc2c94d3344a28'
PREP773 = life.OUT / 'native-full773-branch720-prepared-agent-20261007-01'
PREP773_SHA = '7f7b90a659e724d5ba0cd2a7b88abf340886fa9c32387338c02d0f06cfdf6588'
MFPU = life.OUT / 'mfpu272-five-phase-prepared-agent-20261007-01'
MFPU_SHA = '5b6ec22297d34ce9e7a944c0c9c677bca25d0856c1e39f4c82854e6cfa3e8dc8'
RVH_CLOSURE = life.OUT / 'rvh0-exception60-v5-offline-completion-receipt-agent-20261007-01.json'
RVH_SHA = '347dc22e6a8740b966bb324282b940ba94c299006903e83e57f15b51d5506372'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')


def population(old, new, single, count):
    need(len(new['tests']) == len(set(new['tests'])) == count and new['tests'][:-1] == old['tests']
         and single['tests'] == new['tests'][-1:] and old['design'] == new['design'] == single['design'],
         'Exact unique prefix / sample / frozen design')
    need(set(old['metrics']) == set(new['metrics']) == set(single['metrics']) and
         sum(map(len, new['metrics'].values())) == 6162, 'Complete6162 metric shape')
    for metric, rows in old['metrics'].items():
        need(set(rows) == set(new['metrics'][metric]) == set(single['metrics'][metric]), 'Metric scope union')
        for scope, a in rows.items():
            b, s = new['metrics'][metric][scope], single['metrics'][metric][scope]
            need((a['width'], a['checksum']) == (b['width'], b['checksum']) == (s['width'], s['checksum'])
                 and int(b['bits'],16) == int(a['bits'],16) | int(s['bits'],16), 'Exact full OR / shape')


def wanted(c):
    return {'mfpu': {(i['scope'], s['name']) for i in c['mfpu775']['config']['bound'] for s in i['signals']},
            'rvh': {(i['scope'], b['name']) for i in c['rvh775']['config']['instances']
                    for b in i['bindings'] if b['role'] == 'target'}}


def partition(text, targets):
    parts = {k: [] for k in ('retained', *targets)}
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block.strip(): continue
        scope = re.findall(r'^INSTANCE:\s*(\S+)$', block, re.M)
        need(len(scope) == 1, 'Exact scope header')
        header, bodies, annotation, last = [], {k: [] for k in parts}, [], 'retained'
        for line in block.splitlines():
            if not line or line.startswith('//'): continue
            if line.startswith(('CHECKSUM:', 'INSTANCE:')): header.append(line); continue
            if line.startswith('ANNOTATION:'): annotation.append(line); continue
            match = re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?(\S+)', line)
            owners = [key for key, names in targets.items() if match and (scope[0], match[1]) in names]
            need(len(owners) <= 1, 'Duplicate new-family target ownership')
            last = owners[0] if owners else 'retained'
            bodies[last].extend(annotation + [line]); annotation = []
        if annotation: bodies[last].extend(annotation)
        if not any(bodies.values()): bodies['retained'] = []
        for key, body in bodies.items():
            if body or (key == 'retained' and not any(bodies.values())):
                parts[key].append('\n'.join(header+body)+'\n')
    return {k: ''.join(v) for k,v in parts.items()}


def records(text, c):
    split = partition(text, wanted(c))
    need([list(r) for r in sorted(mfpu.el_members(split['mfpu'], c['mfpu775']['config']))] == c['mfpu775']['expected'],
         'ExactMFPU source/native EL union')
    need([list(r) for r in rvh.native.records(split['rvh'], c['rvh775']['config'])] == c['rvh775']['expected'],
         'ExactRVH scalar/vector native EL union')
    return prior.records(split['retained'], c)


def owners(text):
    result = set()
    inventory, _ = prior.branch.native_inventory(text.encode('ascii'))
    for scope, _, _, line in inventory:
        need(line != 'WHOLE_SCOPE' or not scope.endswith('i_vlsu'), 'Whole functional scope excluded')
        m = re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?(\S+)', line)
        if m: result.add((scope, m[1]))
    return result


def owns(scope, name, kind, approved):
    return (scope,name) in approved or (kind == 'arrays' and any(
        s == scope and n.startswith(name+'[') for s,n in approved))


def row_gate(rows, expected, active, approved, scope, stage, before=None):
    need(len(rows) == len(expected) and len({r['handle'] for r in rows}) == len(rows), 'Complete native complement')
    by_label = {label: obj for obj in expected for label in obj['labels']}
    need(len(by_label) == sum(len(o['labels']) for o in expected), 'Ambiguous native alias')
    seen = set()
    for row in rows:
        obj = by_label.get(row['name'])
        need(obj is not None and row['path'] == row['meta'] == row['name'] and row['handle'].isdigit(), 'Typed native identity')
        need(obj['name'] not in seen, 'Duplicate native object'); seen.add(obj['name'])
        is_owner = obj['target'] or owns(scope,obj['name'],obj['kind'],approved)
        need(row['excluded'] == str(int(active and is_owner)), 'Exact target/retained membership: '+row['name'])
    need(seen == {o['name'] for o in expected}, 'Missing typed protection')
    if before is not None:
        need(sorted((r['path'],r['meta'],r['name']) for r in rows) ==
             sorted((r['path'],r['meta'],r['name']) for r in before), 'Five-phase identity differs')


def expanded_groups(c):
    oc = c['rvh775']['config']
    oldowner = life.read_bound(Path(c['future_captures']['c910240']['output'])/'config.json', prior.owner.OWNER_CONFIG)
    original = prior.frozen.model()['merged_observers'](c)
    groups, _, _ = prior.owner.corrected_groups(original, oldowner['instances'],
        prior.owner.native.source_bindings(oldowner), {tuple(r) for r in c['expected_union']['c910240']})
    labels = {(i['scope'],b['label']) for i in oc['instances'] for b in i['bindings'] if b['role']=='target'}
    labels |= {(i['scope'],s['native_label']) for i in c['mfpu775']['config']['bound'] for s in i['signals']}
    changes = []
    for key, item in groups.items():
        refs = {r[2] for r in item['reference']}
        added = sorted(label for scope,label in labels if scope == item['scope'] and label in refs and label not in item['targets'])
        if added:
            item['targets'] = sorted(set(item['targets']) | set(added)); changes.append(dict(group=key,scope=item['scope'],added=added))
    return groups, changes


def inventories(out, c):
    approved = owners(Path(c['canonical_EL']['path']).read_text())
    # Each original semantic parser still owns its exact EL. Boolean aggregate
    # flags cannot certify bit complements; the global exact EL union does.
    for family, instances in [('mfpu',c['mfpu775']['config']['compiled']), ('rvh',c['rvh775']['config']['instances'])]:
        for index, inst in enumerate(instances):
            before = None
            for stage in STAGES:
                path = out / ('%s775_%s_%d.tsv' % (family,stage,index))
                with path.open(newline='') as stream:
                    reader=csv.DictReader(stream,delimiter='\t'); rows=list(reader)
                    need(reader.fieldnames == ['handle','path','meta','name','type','coverage','display','excluded'], 'Complete inventory schema')
                if family == 'mfpu':
                    text = io.StringIO(); writer=csv.DictWriter(text,fieldnames=reader.fieldnames[:-1],delimiter='\t',lineterminator='\n')
                    writer.writeheader(); writer.writerows({k:r[k] for k in reader.fieldnames[:-1]} for r in rows)
                    bound, _ = mfpu.indexed.bind_with_aliases(inst,text.getvalue())
                    ref = c['mfpu775']['config']['bound'][index]
                    need(bound['reference'] == ref['reference'] and bound['signals'] == ref['signals'] and
                         bound['array_bindings'] == ref['array_bindings'], 'All788 typed bindings / targets / MDA protections')
                    resolver=mfpu.indexed.Resolver(inst); expected=[]
                    for r in rows:
                        matches=resolver.matches(r['name'],r['type']); need(len(matches)==1,'Exact compiled owner')
                        n=matches[0][0]
                        expected.append(dict(name=r['name'],labels=[r['name']],kind=n['kind'],target=any(s['native_label']==r['name'] for s in ref['signals']),source_name=n['name']))
                    # Query flags at the actual native row; source mapping retains
                    # all dimensions. No array-to-bit flattening is performed.
                    native_approved={(inst['scope'],r['name']) for r in rows if any(
                        s==inst['scope'] and (name==r['name'] or r['name'].startswith(name+'[')) for s,name in approved)}
                    row_gate(rows,expected,stage in ('selected','reloaded'),native_approved,inst['scope'],stage,before)
                else:
                    expected=[dict(name=b['name'],labels=b['allowed_labels'],kind=b['kind'],target=b['role']=='target') for b in inst['bindings']]
                    row_gate(rows,expected,stage in ('selected','reloaded'),approved,inst['scope'],stage,before)
                if before is None: before=rows
                if stage in ('reset','final'):
                    need([{k:v for k,v in r.items() if k!='handle'} for r in rows] ==
                         [{k:v for k,v in r.items() if k!='handle'} for r in before], 'Reset restores every native field')


def observers(out, c):
    for name in ('applied.el','reloaded.el'):
        need(records((out/name).read_text(),c) == c['expected_union'], 'Complete canonical union')
    groups, changes = expanded_groups(c)
    need(changes == c['observer775_changes'], 'Exact cross-policy owner conversion')
    prior.frozen.base.prior.audit_observers(out,dict(c,observer_captures=groups))
    for stage in prior.branch.STAGES:
        name='initial' if stage=='raw' else stage
        prior.branch.check_stage_rows((out/('states_'+name+'.tsv')).read_bytes(),stage,c['branch720'])
    inventories(out,c)
    return dict(new_families=['mfpu272','rvh0_exception60'],observer_owner_changes=changes)


def check(out, seal):
    c=life.read_bound(out/'config.json',seal)
    need(c['schema']==SCHEMA and c['output']==str(out) and c['population']==775 and
         c['admission']['seal']==BASE_SHA and c['successor_entry']==str(Path(__file__).resolve()),'Fresh775 immutable identity')
    life.check(c['pins'])
    old=life.read_bound(PREP773/'config.json',PREP773_SHA)
    changed={'schema','output','population','successor_entry','admission','input_ledger','expected_selected','pins'}
    need(all(c.get(k)==v for k,v in old.items() if k not in changed),'Retained frozen policies / runtime / shape differ')
    mq=life.read_bound(MFPU/'capture-result.json',MFPU_SHA)
    rq=life.read_bound(RVH_CLOSURE,RVH_SHA)
    need(c['mfpu775']['config']==life.read_bound(MFPU/'config.json',mq['config_seal']) and
         c['rvh775']['config']==life.read_bound(rvh.OUT/'config.json',rq['original_config_sha256']),
         'Complete qualified source/native binding retained')
    need((out/'inputs.txt').read_text().splitlines()==c['input_ledger'] and len(c['expected_selected'])==len(set(c['expected_selected']))==775,'Actual775 full population')
    need(records((out/'combined.el').read_text(),c)==c['expected_union'],'Exact family union')
    prior.fresh_targets(life.read_bound(prior.branch.AUDIT,prior.branch.AUDIT_SHA),
        life.read_bound(BASE/'combined-bits.json',c['pins'][str(BASE/'combined-bits.json')]))
    need(expanded_groups(c)[1]==c['observer775_changes'],'Exact observer owner reconciliation')
    return c


def namespace():
    ns=prior.namespace()
    def snapshot(data,out):
        c=life.read_bound(out/'config.json',data['config_seal']); prior.stdout_contract.snapshot_stdout(data,out)
        data.update(population=775,admission=c['admission'],formal775_manifest_seal=BASE_SHA,
            additional_qualified_families=['branch720','mfpu272','rvh0_exception60'],
            official_denominator_verified=False,expected_Branch_denominator_delta=720,
            MFPU_targets=272,RVH_targets=60,complete_new_native_inventories_verified=True,
            retained_closed771_owner_closure=True,new_RTL_signoff=False,
            historical_MFPU_HOLD_resolved_by_exact_local_receipt=MFPU_SHA)
        extra={str(p):life.digest(p) for family in ('mfpu','rvh') for p in out.glob(family+'775_*.tsv')}
        need(len(extra)==5*(788+5),'Every fresh native inventory must be sealed')
        data['output_pins']=prior.merge(data['output_pins'],extra)
    ns.update(check=check,records=records,audit_observers=observers,snapshot_stdout=snapshot,TCL=TCL,__file__=__file__)
    for name in ('run','verify'): ns[name]=FunctionType(ns[name].__code__,ns)
    return ns


def prepare(out):
    need(out.parent==life.OUT and not out.exists(),'Fresh independent775 prepare')
    old=life.read_bound(PREP773/'config.json',PREP773_SHA)
    pins=prior.merge(old['pins'],{str(PREP773/'config.json'):PREP773_SHA})
    previous=life.read_bound(prior.MANIFEST.parent/'combined-bits.json',pins[str(prior.MANIFEST.parent/'combined-bits.json')])
    for base, seal, count in [(BASE774,SHA774,774),(BASE,BASE_SHA,775)]:
        m=life.read_bound(base/'admission-manifest.json',seal)
        need(m['coverage_admitted'] is True and m['baseline']==str(prior.MANIFEST.parent if count==774 else BASE774)
             and m['baseline_seal']==(prior.MANIFEST_SHA if count==774 else SHA774),'Exact formal chain')
        pins=prior.merge(pins,m['input_pins'],m['output_pins'],{str(base/'admission-manifest.json'):seal})
        bits=life.read_bound(base/'combined-bits.json',pins[str(base/'combined-bits.json')])
        population(previous,bits,life.read_bound(base/'single-bits.json',pins[str(base/'single-bits.json')]),count)
        status=life.read_bound(base/'status.json',pins[str(base/'status.json')])
        need(status['aggregate_passed']==count and status['coverage_admitted'] is True and status['full_OR_instances']==6162,'Formal terminal PASS')
        previous=bits
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    need(ledger==[old['input_ledger'][0],*bits['tests']] and ledger[:len(old['input_ledger'])]==old['input_ledger'],'775 complete773prefix')
    mq=life.read_bound(MFPU/'capture-result.json',MFPU_SHA)
    need(mq['status']=='MFPU272_EXACT_FIVE_PHASE_LOCAL_QUALIFIED_NOT_APPLIED' and mq['targets']==272 and
         mq['directions']==34816 and mq['terminal_returncode']==0 and mq['EL_semantic_roundtrip'] is True,'MFPU qualified native source')
    mc=life.read_bound(MFPU/'config.json',mq['config_seal'])
    rq=life.read_bound(RVH_CLOSURE,RVH_SHA)
    need(rq['status']=='RVH0_EXCEPTION60_POST_WRAPPER_OFFLINE_CLOSURE_PASS_NOT_POPULATION_APPLIED' and
         rq['original_inspect_all_checks_replayed'] is True and rq['targets']==60 and rq['protected']==2794,'RVH closed qualification')
    rc=life.read_bound(rvh.OUT/'config.json',rq['original_config_sha256'])
    pins=prior.merge(pins,mq['pins'],rq['completion_pins'],{str(MFPU/'capture-result.json'):MFPU_SHA,str(RVH_CLOSURE):RVH_SHA})
    c=dict(old,schema=SCHEMA,output=str(out),population=775,successor_entry=str(Path(__file__).resolve()),
        admission=dict(manifest=str(BASE/'admission-manifest.json'),seal=BASE_SHA,population=775,exact773prefix=True,full6162_OR=True),input_ledger=ledger,
        expected_selected=[str(Path(db).with_suffix('')/p.name) for db in ledger for p in sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if p.is_dir()],
        mfpu775=dict(config=mc,expected=[list(r) for r in sorted(mfpu.el_members((MFPU/'first.el').read_text(),mc))]),
        rvh775=dict(config=rc,expected=[list(r) for r in rvh.native.records((rvh.OUT/'first.el').read_text(),rc)]))
    # Parser tuples become JSON lists at the immutable boundary.
    text=(PREP773/'combined.el').read_text()+(MFPU/'first.el').read_text()+(rvh.OUT/'first.el').read_text()
    need(not (wanted(c)['mfpu'] & wanted(c)['rvh']) and not any(k in owners((PREP773/'combined.el').read_text())
         for names in wanted(c).values() for k in names),'No target/target duplicate')
    c['observer775_changes']=expanded_groups(c)[1]
    # Serialize only once: downstream check/verify receives identical list forms.
    c['mfpu775']['expected']=[list(r) for r in c['mfpu775']['expected']]
    need(records(text,c)==c['expected_union'],'Actual sealed family parsers accept exact combined union')
    files=[Path(__file__),TCL,Path(__file__).with_name('test_report_native_full775.py'),Path(mfpu.__file__),
           Path(rvh.__file__),HERE/'mfpu272_five_phase.tcl',HERE/'rvh0_exception60_native772_v5.tcl',Path(prior.__file__)]
    pins=prior.merge(pins,{str(p.resolve()):life.digest(p) for p in files})
    life.check(pins)
    selection=(PREP773/'selection.tcl').read_text()
    for family, instances in [('mfpu',mc['bound']),('rvh',rc['instances'])]:
        selection+='\nset ::full775_%s_scopes [list %s]\n' % (family,' '.join(prior.tcl_atom(i['scope']) for i in instances))
    out.mkdir()
    for name,value in [('combined.el',text),('selection.tcl',selection),('inputs.txt','\n'.join(ledger)+'\n')]:
        with (out/name).open('x') as stream: stream.write(value)
        pins[str(out/name)]=life.digest(out/name)
    c['pins']=pins; life.save(out/'config.json',c)
    print(json.dumps(dict(status='PREPARED_NO_EDA',output=str(out),seal=life.digest(out/'config.json'),population=775,
        Branch_targets=720,MFPU_targets=272,RVH_targets=60,official_denominator_verified=False)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--authorize-reviewed-run',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        need(a.seal,'Exact config seal required')
        if a.mode=='run':need(a.authorize_reviewed_run,'Parent launch authorization required')
        namespace()[a.mode](out,a.seal)
