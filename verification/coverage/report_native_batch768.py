"""Formal768 preparation: qualified cause/read fields and optional first CSR qualification."""
import argparse
import copy
import inspect
import json
import re
from pathlib import Path
from types import FunctionType

import report_native_batch766 as prior
import prepare_native_batch767_host as prefix
import qbs_cause_constants_native as cause
import qualify_requester_read108_native as read
import capture_csr_reserved1193_v2 as csr

life, require, merge = prior.life, prior.require, prior.merge
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
BASE = life.OUT/'native-batch-full766-agent-20261007-01'
BASE_SHA = 'ce709dbf1da6a16f16c8c10e7c2006c59429a3ff08c09237a3355a7267f53650'
FORMAL = life.OUT/'stride-metadata-full64-offline-admitted-768-agent-20261007-01'
MANIFEST = FORMAL/'admission-manifest.json'
MANIFEST_SHA = '1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198'
CAUSE = life.OUT/'qbs-cause9-constant13-native-offline-qualified-parent-20261007-01/capture-result.json'
CAUSE_SHA = '46df5c8c2ec8b08df3c3ca2f7101cbb5acacfdd78e4917be312bf3d72d112006'
CSR = life.OUT/'csr-reserved1193-native-agent-20261007-02'
CSR_SHA = '564012de8606df39dc91981ab857092cd6e49ff5f2463b8cebd40c5629c3786d'
MODULES = dict(cause=cause, read108=read, csr1193=csr)
SCHEMA = 'FORMAL768_RETAINED766_CAUSE_READ_OPTIONAL_FIRST_CSR_QUALIFICATION_V1'


def full_or(before, after, single, count):
    require(len(before['tests']) == count-1 and len(after['tests']) == len(set(after['tests'])) == count
            and after['tests'][:-1] == before['tests'] and single['tests'] == after['tests'][-1:]
            and before['design'] == after['design'] == single['design'], 'Exact prefix/unique/design differs')
    require(set(before['metrics']) == set(after['metrics']) == set(single['metrics']), 'Metric families differ')
    total = 0
    for metric, rows in before['metrics'].items():
        require(set(rows) == set(after['metrics'][metric]) == set(single['metrics'][metric]), 'Hierarchy differs')
        total += len(rows)
        for scope, old in rows.items():
            now, one = after['metrics'][metric][scope], single['metrics'][metric][scope]
            require((old['width'], old['checksum']) == (now['width'], now['checksum']) ==
                    (one['width'], one['checksum']), 'Compiled shape differs')
            require(int(now['bits'], 16) == int(old['bits'], 16) | int(one['bits'], 16)
                    and max(int(now['bits'],16).bit_length(), int(one['bits'],16).bit_length()) <= now['width'],
                    'Complete OR/overflow differs')
    require(total == 6162, 'Not complete6162')


def population(original):
    prefix.population()
    book = life.read_bound(MANIFEST, MANIFEST_SHA)
    require(book['coverage_admitted'] is True and book['output'] == str(FORMAL)
            and book['baseline'] == str(prefix.MANIFEST.parent) and book['baseline_seal'] == prefix.MANIFEST_SHA,
            'Exact formal768 authority')
    pins = merge(book['input_pins'], book['output_pins'], {str(MANIFEST):MANIFEST_SHA})
    def bound(path):
        require(str(path) in pins, 'Unsealed population input/output')
        return life.read_bound(path, pins[str(path)])
    after = bound(FORMAL/'combined-bits.json')
    full_or(bound(prefix.MANIFEST.parent/'combined-bits.json'), after, bound(FORMAL/'single-bits.json'), 768)
    status = bound(FORMAL/'status.json')
    require(status['aggregate_passed'] == 768 and status['exact767_prefix'] is True
            and status['coverage_admitted'] is True, 'Formal768 status')
    ledger_path = FORMAL/'combined-inputs.txt'
    require(life.digest(ledger_path) == pins[str(ledger_path)], 'Actual ledger bytes')
    ledger = ledger_path.read_text().splitlines()
    require(ledger[:-2] == original['input_ledger'] and ledger == [original['input_ledger'][0], *after['tests']],
            'Exact766 prefix through768 ledger')
    selected = [str(Path(db).with_suffix('')/p.name) for db in ledger for p in
                sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if p.is_dir()]
    require(len(selected) == len(set(selected)) == 768, 'Actual768 membership')
    return ledger, selected, pins


def family(key, out, c, text, q=None, qpath=None, qsha=None):
    module = MODULES[key]
    module.contract(c)
    if key == 'csr1193':
        terminal = json.loads((out/'terminal.json').read_bytes())
        require(terminal['timeout'] is True and terminal['returncode'] != 0
                and not (out/'capture-result.json').exists(), 'CSR local remains unqualified timeout')
        hold = json.loads((out/'qualification-hold.json').read_bytes())
        require(hold['status'] == 'HOLD_NOT_APPLIED', 'CSR preserved HOLD')
        instances = [dict(scope=c['scope'], nodes=c['nodes'], targets=c['targets'])]
        parse = module.records
        before=module.inventory(out,c,'before')
        refs = {c['scope']: [list(r[1]) for r in before]}
        labels={c['scope']:{r[0]:r[1][2] for r in before}}
    else:
        require(q is not None and q['population_application'] is False, 'Qualified native record required')
        wanted = ('QBS_CAUSE9_CONSTANT13_PARTIAL743_NATIVE_OFFLINE_QUALIFIED_NOT_POPULATION_APPLIED'
                  if key == 'cause' else 'REQUESTER_READ_FIELDS108_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED')
        require(q['status'] == wanted, 'Unqualified native status')
        terminal = json.loads((out/'terminal.json').read_bytes())
        require(terminal['returncode'] == 0 and terminal['timeout'] is False
                and len(terminal['actual_dve']) == 1, 'Native actual terminal')
        instances = c['instances'];parse = module.records if key == 'cause' else module.parse_el
        refs = {};labels={}
        for index, i in enumerate(instances):
            before = module.inventory(out,c,'before',index)
            require(all(module.inventory(out,c,s,index) == before for s in prior.STAGES), 'Native five-stage identity')
            refs[i['scope']] = [[r[1][0],r[1][1],r[1][2]] for r in before] if key == 'cause' else [list(r[1:]) for r in before]
            labels[i['scope']]={r[0]:r[1][2] for r in before} if key == 'cause' else {r[0]:r[3] for r in before}
        require(parse((out/'first.el').read_text(),c) == parse((out/'second.el').read_text(),c), 'Native semantic reload')
        for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
            require((out/name).read_bytes() == b'', 'Native global empty reset')
    canonical = prior.old.normalized(parse(text,c))
    pins = merge(c['pins'], {str(out/'config.json'):life.digest(out/'config.json'),
                            str(out/'first.el'):life.digest(out/'first.el')})
    if q is not None:
        pins = merge(pins,q['pins'],{str(qpath):qsha})
    else:
        pins = merge(pins,{str(out/n):life.digest(out/n) for n in ('terminal.json','qualification-hold.json')})
    signals = {i['scope']: sorted(t['signal'] if 'signal' in t else t['name'] for t in i['targets']) for i in instances}
    native_targets={scope:sorted(labels[scope][name] for name in names) for scope,names in signals.items()}
    # Object-level DVE flags report complete exclusion, not partial-bit membership.
    targets={i['scope']:sorted(labels[i['scope']][t.get('signal',t.get('name'))] for t in i['targets']
               if not t.get('retained_source_bits')) for i in instances}
    return dict(config=c,output=str(out),canonical=canonical,reference=refs,targets=targets,
                signals=signals,native_targets=native_targets,local_qualified=key != 'csr1193',
                membership_authority='Exact paired typed EL; aggregate flags only, no per-bit GUI claim',
                qualification_seal=qsha,source_pins=pins,el=text)


def additions(include_csr=False, read_qualification=None, read_seal=None):
    q = life.read_bound(CAUSE, CAUSE_SHA)
    out = Path(q['original_native_output']);c = life.read_bound(out/'config.json',q['config_seal'])
    result = dict(cause=family('cause',out,c,(out/'first.el').read_text(),q,CAUSE,CAUSE_SHA))
    if read_qualification is not None:
        require(read_seal, 'Explicit read108 qualification seal required')
        q = life.read_bound(read_qualification,read_seal);out = read_qualification.parent
        c = life.read_bound(out/'config.json',q['config_seal'])
        result['read108'] = family('read108',out,c,(out/'first.el').read_text(),q,read_qualification,read_seal)
    if include_csr:
        c = life.read_bound(CSR/'config.json',CSR_SHA)
        result['csr1193'] = family('csr1193',CSR,c,(CSR/'first.el').read_text())
    return result


def partition(text,c):
    routes = {(scope,name):key for key,item in c['new_families'].items()
              for scope,names in item['signals'].items() for name in names}
    require(len(routes) == sum(len(n) for i in c['new_families'].values() for n in i['signals'].values()),
            'New field ownership overlap')
    parts = dict(retained=[] , **{k:[] for k in c['new_families']})
    for scope, block in prior.old.blocks(text):
        header=[];body={k:[] for k in parts};pending=[];last=None
        for line in block.splitlines():
            if not line or line.startswith('//'):continue
            if line.startswith(('CHECKSUM:','INSTANCE:')):header.append(line);continue
            if line.startswith('ANNOTATION:'):
                (body[last] if last else pending).append(line);continue
            m=re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?(\S+)',line)
            key=routes.get((scope,m[1]),'retained') if m else 'retained'
            body[key].extend(pending);pending=[]
            body[key].append(line);last=key
        if not any(body.values()):
            # Pure observer scope blocks carry annotation but no Toggle directive.
            parts['retained'].append(block);continue
        require(not pending,'Orphan union annotation')
        for key, lines in body.items():
            if lines:
                parts[key].append('\n'.join(header+lines)+'\n')
    return {k:''.join(v) for k,v in parts.items()}


def records(text,c):
    parts = partition(text,c)
    value = prior.records(parts.pop('retained'),c)
    for key,item in c['new_families'].items():
        parse = MODULES[key].parse_el if key == 'read108' else MODULES[key].records
        value[key] = prior.old.normalized(parse(parts[key],item['config']))
    return value


def merged_observers(c):
    observers = copy.deepcopy(c['observer_captures'])
    byscope={i['scope']:i for i in observers.values()}
    for key,item in c['new_families'].items():
        for index,(scope,reference) in enumerate(item['reference'].items()):
            if scope in byscope:
                i=byscope[scope]
                require(sorted(i['reference']) == sorted(reference), 'Shared full native inventory differs')
                i['targets']=sorted(set(i['targets'])|set(item['targets'][scope]))
            else:
                i=dict(scope=scope,reference=sorted(reference),targets=item['targets'][scope])
                observers[key+str(index)]=i;byscope[scope]=i
    return observers


def audit_observers(out,c):
    cc=dict(c,observer_captures=merged_observers(c))
    prior.audit_observers(out,cc)


def host_hook(selection,c):
    cc=dict(c,observer_captures=merged_observers(c))
    return FunctionType(prior.host_hook.__code__,dict(vars(prior),TCL=TCL))(selection,cc)


def prepare(out, include_csr=False, read_qualification=None, read_seal=None):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent768 output')
    q = life.read_bound(prefix.PREDECESSOR,prefix.PREDECESSOR_SHA)
    require(q['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and q['population'] == 766,
            'Qualified full766 closure required')
    original=life.read_bound(BASE/'config.json',BASE_SHA)
    ledger,selected,ppins=population(original)
    extra=additions(include_csr,read_qualification,read_seal)
    c=copy.deepcopy(original)
    c.update(schema=SCHEMA,population=768,output=str(out),successor_entry=str(Path(__file__).resolve()),
             input_ledger=ledger,expected_selected=selected,new_families=extra,
             admission=dict(manifest=str(MANIFEST),seal=MANIFEST_SHA,population=768,exact766prefix=True,full6162_OR=True),
             csr_first_population_qualification=include_csr,parent_launch_approval_required=True,
             pending_read108=read_qualification is None,pending_next_family='TLB_RVH0_NOT_INCLUDED_NOT_QUALIFIED')
    combined=(BASE/'combined.el').read_text()+''.join(i['el'] for i in extra.values())
    c['expected_union']=records(combined,c)
    retained=copy.deepcopy(c['expected_union'])
    for key,item in extra.items():require(retained.pop(key) == item['canonical'],'New canonical membership differs')
    require(retained == original['expected_union'],'Retained complete766 union changed')
    selection=(BASE/'selection.tcl').read_text()+prior.selection_tail(dict(c,observer_captures=merged_observers(c)))
    deps=[Path(__file__).resolve(),TCL,HERE/'test_report_native_batch768.py',Path(prefix.__file__),
          Path(prior.__file__),*(Path(m.__file__) for m in MODULES.values())]
    pins=merge(original['pins'],q['output_pins'],ppins,{str(prefix.PREDECESSOR):prefix.PREDECESSOR_SHA},
               {str(p):life.digest(p) for p in deps},*(i['source_pins'] for i in extra.values()))
    life.check(pins);out.mkdir()
    for name,text in [('selection.tcl',selection),('combined.el',combined),('inputs.txt','\n'.join(ledger)+'\n')]:
        with (out/name).open('x') as stream:stream.write(text)
        require((out/name).read_bytes() == text.encode('ascii'),'No JSON serialized Tcl')
        pins[str(out/name)]=life.digest(out/name)
    syntax=prior.old.parser(HERE/'check_generated_tcl.py')
    evidence=dict(syntax=[syntax.check(out/'selection.tcl'),syntax.check(TCL)],hook=host_hook(out/'selection.tcl',c),no_EDA=True)
    life.save(out/'host-generated-tcl-evidence.json',evidence)
    pins[str(out/'host-generated-tcl-evidence.json')]=life.digest(out/'host-generated-tcl-evidence.json')
    c['pins']=pins;life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(status='PREPARED_NO_DVE',output=str(out),seal=life.digest(out/'config.json'),
                         groups=list(extra),pending_read108=c['pending_read108'],CSR_local_qualified=False,pins=len(pins))),flush=True)


def check(out,seal):
    c=life.read_bound(out/'config.json',seal)
    require(c['schema'] == SCHEMA and c['population'] == 768 and c['output'] == str(out)
            and c['successor_entry'] == str(Path(__file__).resolve()) and c['admission']['seal'] == MANIFEST_SHA,
            'Exact768 identity')
    require(c['qualified_fsm_union'] == 173 and c['runtime_timeout_seconds'] == 5400
            and c['parent_launch_approval_required'] is True,'Inherited budget/gates')
    require(set(c['new_families']) <= set(MODULES) and 'cause' in c['new_families'], 'Only explicit groups')
    require(c['csr_first_population_qualification'] == ('csr1193' in c['new_families'])
            and ('csr1193' not in c['new_families'] or c['new_families']['csr1193']['local_qualified'] is False),
            'CSR cannot inherit local qualification')
    require(len(c['expected_selected']) == len(set(c['expected_selected'])) == 768
            and (out/'inputs.txt').read_text().splitlines() == c['input_ledger'], 'Full768 ledger')
    life.check(c['pins'])
    for key,item in c['new_families'].items():
        MODULES[key].contract(item['config'])
        require(item['local_qualified'] == (key != 'csr1193'), 'Separate qualification origins')
        require(all(len(set(item['native_targets'][s])) == len(item['signals'][s]) for s in item['signals']),
                'Every target has a unique actual native label')
    require(records((out/'combined.el').read_text(),c) == c['expected_union'], 'Canonical complete union')
    return c


def snapshot_stdout(data,out):
    # Retain the successful immutable prefix/self-pin contract, not a live log pin.
    prior.snapshot_stdout(data,out)
    c=json.loads((out/'config.json').read_bytes())
    data.update(population=768,formal768_manifest_seal=MANIFEST_SHA,exact766prefix=True,
                first_CSR_population_qualification=c['csr_first_population_qualification'],
                CSR_local_qualified=False,new_family_seals={k:i['qualification_seal'] for k,i in c['new_families'].items()},
                main_root_toggle_hit_total=None,raw_population_condition_gain=None,raw_population_fsm_gain=None)


def namespace():
    ns=prior.namespace()
    ns.update(__file__=__file__,TCL=TCL,check=check,records=records,snapshot_stdout=snapshot_stdout,audit_observers=audit_observers)
    ns['verify']=FunctionType(ns['verify'].__code__,ns)
    ns['run']=FunctionType(ns['run'].__code__,ns)
    return ns


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    p.add_argument('--include-csr-candidate',action='store_true')
    p.add_argument('--read-qualification',type=Path);p.add_argument('--read-seal')
    p.add_argument('--authorize-reviewed-run',action='store_true')
    p.add_argument('--authorize-csr-first-qualification',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.mode == 'prepare':prepare(out,a.include_csr_candidate,a.read_qualification,a.read_seal)
    else:
        require(a.seal,'Exact config seal required')
        if a.mode == 'run':
            c=check(out,a.seal)
            require(a.authorize_reviewed_run and (not c['csr_first_population_qualification'] or
                    a.authorize_csr_first_qualification),'Explicit parent authorization required')
        namespace()[a.mode](out,a.seal)
        if a.mode == 'check':print('FULL768_CHECK_PASS_NO_EDA')
