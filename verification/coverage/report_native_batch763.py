"""Single formal763 native batch, retaining qualified762 and six exact additions."""
import argparse
import copy
import csv
import inspect
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import report_dispatcher_four_union762 as prior
import capture_scalar_fma22 as scalar22
import capture_scalar_radix158 as scalar158
import queue_fp_temporaries_native_alias as queue336
import qbs_scale_hit_native762_v2 as scale120
import half_fma816_native as half816
import capture_lookahead_send_ready762 as lookahead2
import qbs_even_hit_native762 as parity

life, require = prior.life, prior.require
old = prior.previous.predecessor
merge = old.merge
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
BASE = life.OUT/'native-population-dispatcher-four-full762-agent-20261007-01'
BASE_SHA = '24f8c0b83627fe9cbc772481bbd49c2dcdc6b834ef8136028b0aa885df3ef7ae'
MANIFEST = life.OUT/'operand-mask-data-defined-policy-admitted763-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA = '962d7292ff80e5fffe4fd8e8e8de00938c32dca3a92d21e179b8cf59f915200c'
SCHEMA = 'FORMAL763_APPROVED_NATIVE_SIX_ADDITION_BATCH_V1'
CAPTURES = {
    'scalar22': ('scalar-fma22-native-agent-20261007-01', '976fded90d31b5f71552c9027fda44fb4af68cf89bea060eceba42f98dce0d5f',
                 'EXACT_SCALAR_FMA22_NATIVE_ROUNDTRIP_QUALIFIED'),
    'scalar158': ('scalar-radix158-native-agent-20261007-01', 'd13b7b413162601a68099fb4f24041c07fd00db6829d60e7b29e2fcec51e819e',
                  'SCALAR_RADIX158_NATIVE_ROUNDTRIP_QUALIFIED_NOT_POPULATION_APPLICATION'),
    'queue336': ('queue-disabled-fp-temporaries-native-alias-agent-20261007-02', '7ae0597fde3ba244ddd3dcbd3ae4a9768d6fb7246661ff931afeca8c58946609',
                 'FPU0_QUEUE336_TYPED_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED'),
    'scale120': ('qbs-bank0-scale-hit120-native762-agent-20261007-02', 'fe7737c814f0ff6c70f073981abecf679517c402800bea739021673af05a7aa2',
                 'QBS_BANK0_SCALE_HIT120_EXACT_NATIVE_ROUNDTRIP_NOT_APPLICATION'),
    'half816': ('half-fma816-native-agent-20261007-01', '0cecf445115b92e5fc17eb126100a585f5d14d12f2bc2201e04d605f72259d45',
                'EXACT_HALF_FMA816_NATIVE_FIVE_STAGE_QUALIFIED_NOT_APPLIED'),
    'lookahead2': ('lookahead-send-ready2-native-762-agent-20261007-01', '86147b97220922bc91968f0c3f4857b12549b3124b92d32627616eb761994e13',
                   'EXACT_LOOKAHEAD2_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL'),
    'parity': ('qbs-even-hit19328-native762-agent-20261007-01', 'bf06c26430b00c7201916f564531c6860ee431bee1c0cf5dc151384a323760c7',
               'QBS_EVEN_START9664_BITS19328_NATIVE_ROUNDTRIP_NOT_APPLICATION'),
}


def parse_addition(key, text, c):
    if key == 'scalar22': result = scalar22.records(text,c)
    elif key == 'scalar158': result = scalar158.records(text,c)
    elif key == 'queue336': result = queue336.old.parse_el(text,c)
    elif key == 'scale120': result = scale120.parse_el(text,c)
    elif key == 'half816': result = half816.parse_el(text,c)
    elif key == 'parity': result = parity.parse_el(text,c)
    else: raise ValueError('Unknown Toggle family')
    return old.normalized(result)


def qualification_gates(key,q):
    require(q['status'] == CAPTURES[key][2] and q['population_application'] is False, 'Missing exact native approval')
    if key == 'scalar22':
        require(q['objects'] == 22 and q['logical_bits'] == 1566 and q['semantic_reload'] and
                q['whole_objects_or_complete_direction_pairs'] and q['global_empty_resets'] and
                q['full_typed_complements_protected'] and q['all_other_scopes_protected'], 'Scalar22 gates')
    elif key == 'scalar158':
        require(q['objects'] == 158 and q['logical_bits'] == 9684 and q['protected_local_objects'] == 52 and
                q['all_descendants_protected'] and q['both_directions'] and q['semantic_reload'] and
                q['finalreset'] and q['non_target_exclusions'] == 0 and not q['vector_architecture_borrowed'], 'Scalar158 gates')
    elif key == 'queue336':
        require(q['objects'] == 336 and q['scopes'] == 16 and q['logical_bits'] == 1536 and
                q['protected_local_objects'] == 752 and q['ALU_merged_scopes_held'] == 8 and
                q['source_constant_rationale'] and not q['trusted_IEEE_rationale'] and not q['initial_X_excluded'] and
                q['global_final_reset_empty'] and q['all_other_metrics_and_scopes_protected'] and
                q['exact_saved_EL_source_typed_binding'], 'Queue336 gates')
    elif key == 'scale120':
        require(q['baseline'] == 762 and q['physical_bits'] == 120 and q['bit_directions'] == 240 and
                q['both_directions_explicit'] and q['bank1_protected'] and q['all_non_targets_protected'] and
                q['global_final_empty'] and q['semantic_reload'] and q['protected_target_vector_bits'] == 360 and
                not q['initial_X_excluded'] and not q['usage_d_excluded'], 'Scale120 gates')
    elif key == 'half816':
        require(q['objects'] == 816 and q['scopes'] == 16 and q['logical_bits'] == 12464 and
                q['protected_local_objects'] == 3520 and q['both_directions'] and q['all_children_retained'] and
                q['no_exhaustive_IEEE_claim'] and q['global_final_reset_empty'] and len(q['stages']) == 5, 'Half816 gates')
    elif key == 'lookahead2':
        require(q['targets'] == 2 and q['protected'] == 46 and q['baseline'] == 762 and
                q['five_stages'] and q['semantic_reload'] and q['finalreset'] and q['other46_protected'], 'Lookahead2 gates')
    elif key == 'parity':
        require(q['baseline'] == 762 and q['physical_bits'] == 9664 and q['bit_directions'] == 19328 and
                q['partial_bits_only'] and q['old1792_and_scale120_not_added'] and q['both_directions_explicit'] and
                q['all_non_targets_protected'] and q['global_final_empty'] and q['semantic_reload'] and
                q['protected_target_vector_bits'] == 16928 and not q['initial_X_excluded'] and
                q['source_proof_sha256'] == parity.PROOF_SHA,'Parity gates')
    else: raise ValueError('Unknown capture family')


def captures():
    result, pins = {}, {}
    for key,(directory,sha,_) in CAPTURES.items():
        out = life.OUT/directory
        q = life.read_bound(out/'capture-result.json',sha)
        qualification_gates(key,q)
        qp = q.get('pins') or merge(q['input_pins'],q['output_pins'])
        life.check(qp)
        csha = q.get('config_seal') or qp[str(out/'config.json')]
        c = life.read_bound(out/'config.json',csha)
        bound = merge(qp,{str(out/'capture-result.json'):sha,str(out/'config.json'):csha})
        pins = merge(pins,bound) if pins else bound
        if key == 'lookahead2':
            require(lookahead2.native.native_records((out/'first.el').read_text()) ==
                    lookahead2.native.native_records((out/'second.el').read_text()) ==
                    [tuple(r) for r in q['native_records']], 'Lookahead exact saved/reload identity')
        else:
            require(parse_addition(key,(out/'first.el').read_text(),c) ==
                    parse_addition(key,(out/'second.el').read_text(),c), 'Exact whole/bit native reload differs')
        result[key] = dict(config=c,qualification=q,seal=sha,output=str(out))
    return result,pins


def population(c,manifest,seal):
    require(manifest == MANIFEST and seal == MANIFEST_SHA, 'Only parent-approved formal763 manifest')
    b = life.read_bound(manifest,seal)
    require(b['status'] == 'INDEPENDENT763_ADMITTED_DEFINED_ARCHITECTURE_PASS' and b['population'] == 763 and
            b['baseline'] == 762 and b['baseline_sha256'] == prior.BASE_SHA and b['coverage_admitted'] is True and
            b['qualification_sha256'] == 'c4b7c7663272556595b484753b72270a4aff1fc7edd19299b1e2952841c50a86', 'Formal763 authority differs')
    pins = merge(b['input_pins'],b['output_pins'],{str(manifest):seal});life.check(pins)
    def read(name):
        path = manifest.parent/name
        require(str(path) in b['output_pins'], 'Unsealed formal output')
        return life.read_bound(path,b['output_pins'][str(path)])
    bits,single = read('combined-bits.json'),read('single-bits.json')
    basebook = life.read_bound(prior.BASE/'admission-manifest.json',prior.BASE_SHA)
    basepath = prior.BASE/'combined-bits.json'
    before = life.read_bound(basepath,basebook['output_pins'][str(basepath)])
    require(bits['design'] == before['design'] == single['design'] and bits['tests'][:-1] == before['tests'] and
            len(before['tests']) == 762 and len(bits['tests']) == len(set(bits['tests'])) == 763 and
            single['tests'] == bits['tests'][-1:] and c['input_ledger'][1:] == before['tests'], 'Exact762 prefix/unique763 differs')
    count = 0
    require(set(bits['metrics']) == set(before['metrics']) == set(single['metrics']), 'Metric family differs')
    for metric,rows in before['metrics'].items():
        require(set(rows) == set(bits['metrics'][metric]) == set(single['metrics'][metric]), 'Full hierarchy differs')
        count += len(rows)
        for scope,prev in rows.items():
            now,one = bits['metrics'][metric][scope],single['metrics'][metric][scope]
            require((prev['width'],prev['checksum']) == (now['width'],now['checksum']) == (one['width'],one['checksum']), 'Shape differs')
            require(int(now['bits'],16) == int(prev['bits'],16)|int(one['bits'],16) and
                    int(now['bits'],16).bit_length() <= now['width'], 'Exact6162 OR differs')
    require(count == 6162, 'Not full6162')
    ledger = (manifest.parent/'combined-inputs.txt').read_text().splitlines()
    require(ledger == [c['input_ledger'][0],*bits['tests']], 'Formal ledger differs')
    selected = [str(Path(db).with_suffix('')/test.name) for db in ledger
                for test in sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if test.is_dir()]
    require(len(selected) == len(set(selected)) == 763, 'Actual test selection differs')
    pins = merge(pins,{str(prior.BASE/'admission-manifest.json'):prior.BASE_SHA,
                       str(basepath):basebook['output_pins'][str(basepath)]})
    return ledger,selected,pins,dict(manifest=str(manifest),seal=seal,population=763,exact762prefix=True,full6162_OR=True)


def target_fields(c):
    owners = {}
    for key,item in c['batch_captures'].items():
        if key == 'lookahead2': continue
        cfg = item['config']
        instances = cfg.get('instances',[cfg['instance']] if 'instance' in cfg else [])
        for i in instances:
            for s in i.get('signals',i.get('targets',[])):
                ident = i['scope'],s['name']
                if ident in owners:
                    require(key in ('scale120','parity') and all(k in ('scale120','parity') for k in owners[ident]),
                            'Duplicate added field')
                    for prior_key in owners[ident]:
                        previous = next(t for j in c['batch_captures'][prior_key]['config']['instances']
                                        if j['scope'] == i['scope'] for t in j['signals'] if t['name'] == s['name'])
                        require(not set(previous['bits'])&set(s['bits']), 'Partial-bit policy overlap')
                owners.setdefault(ident,[]).append(key)
    return owners


def records(text,c):
    if 'batch_captures' not in c: return old.records(text,c)
    owners = target_fields(c)
    bit_owners = {(i['scope'],s['name'],bit):key for key in ('scale120','parity')
                  for i in c['batch_captures'][key]['config']['instances'] for s in i['signals'] for bit in s['bits']}
    parts = {k:[] for k in ('prior',*CAPTURES.keys()) if k != 'lookahead2'}
    for scope,block in old.blocks(text):
        header,pending,body,last = [],[],{k:[] for k in parts},None
        for line in block.splitlines():
            if not line or line.startswith('//'): continue
            if line.startswith(('CHECKSUM:','INSTANCE:')): header.append(line)
            elif line.startswith('ANNOTATION:'): (body[last] if last else pending).append(line)
            else:
                m = re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?([\w.\[\]]+)(?:\s|$)',line)
                families = owners.get((scope,m[1]),[]) if m else []
                if families and families[0] in ('scale120','parity'):
                    bit_match = re.fullmatch(r'Toggle(?:\s+(0to1|1to0))?\s+([\w.\[\]]+)\s+\[(\d+)(?::(\d+))?\](?:\s+"([^"\n]+)")?',line)
                    require(bit_match is not None,'Partial fields require explicit bounded bits')
                    direction,name,left,right,signature = bit_match.groups()
                    for bit in range(min(int(left),int(right or left)),max(int(left),int(right or left))+1):
                        key=bit_owners.get((scope,name,bit))
                        require(key in families,'Unknown/protected/duplicate partial bit')
                        body[key].extend(pending);pending=[]
                        body[key].append('Toggle '+((direction+' ') if direction else '')+name+' [%d]'%bit+
                                         (' "'+signature+'"' if signature else ''))
                        last=key
                    continue
                family = families[0] if families else 'prior'
                body[family].extend(pending);pending=[];body[family].append(line);last=family
        if not any(body.values()):
            # Only this approved empty bank has a module-only native checksum.
            empty = c['batch_captures']['scale120']['config']['instances'][1]
            family = 'scale120' if scope == empty['scope'] and any(
                h == 'CHECKSUM: "'+empty['design_module_checksum']+'"' for h in header) else 'prior'
            parts[family].append(block)
        else:
            require(not pending,'Orphan annotation')
            for key,lines in body.items():
                if lines: parts[key].append('\n'.join(header+lines)+'\n')
    legacy_config = dict(c,toggle_groups=[g for g in c['toggle_groups'] if g['policy'] not in CAPTURES])
    result = old.records(''.join(parts['prior']),legacy_config)
    result['batch'] = {key:parse_addition(key,''.join(parts[key]),item['config'])
                       for key,item in c['batch_captures'].items() if key != 'lookahead2'}
    return old.normalized(result)


def append_groups(c):
    for key,item in c['batch_captures'].items():
        if key in ('lookahead2','scale120','parity'): continue
        cfg,out = item['config'],Path(item['output'])
        instances = cfg.get('instances',[cfg['instance']] if 'instance' in cfg else [])
        for index,i in enumerate(instances):
            stage = 'initial' if key == 'half816' else 'before'
            reference = old.table(out/('native_%s_%d.tsv'%(stage,index)),['handle','path','meta','name'])
            targets = [s['native_name'] for s in i.get('signals',i.get('targets',[]))]
            names = [r[2] for r in reference]
            require(len(names) == len(set(names)) and set(targets) <= set(names), 'Complete added native inventory')
            c['toggle_groups'].append(dict(policy=key,index=index,scope=i['scope'],targets=targets,
                protected=[n for n in names if n not in targets],reference=sorted(reference)))
    cfg = c['batch_captures']['scale120']['config'];out=Path(c['batch_captures']['scale120']['output'])
    c['batch_scale_references'] = [old.table(out/('native_before_%d.tsv'%index),
        ['handle','path','meta','name','column1','column2']) for index in range(2)]
    p=Path(c['batch_captures']['parity']['output'])
    for index in range(2):
        require(old.table(p/('native_before_%d.tsv'%index),['handle','path','meta','name','column1','column2']) ==
                c['batch_scale_references'][index], 'Scale/parity full native complement differs')


def selection_tail(c):
    atom = old.frozen.prior.old.base.capture.tcl_atom
    lines = ['set combo_groups {}\n']
    for index,g in enumerate(c['toggle_groups']):
        lines.append('lappend combo_groups [list %s %d [list %s]]\n' %
                     (atom(g['scope']),index,' '.join(atom(r[2]) for r in g['reference'])))
    lines.append('set ::batch_scale_instances {}\n')
    for i in c['batch_captures']['scale120']['config']['instances']:
        other=next(j for j in c['batch_captures']['parity']['config']['instances'] if j['scope']==i['scope'])
        labels=sorted({s['native_label'] for s in i['signals']+other['signals']})
        lines.append('lappend ::batch_scale_instances [list %s [list %s]]\n' %
                     (atom(i['scope']),' '.join(map(atom,labels))))
    cfg = c['batch_captures']['lookahead2']['config']
    plan = cfg['plan']
    existing = {(g['scope'],g['machine']['name'],g['mode']) for g in c['plan']['groups']}
    for g in plan['groups']:
        matches=[(index,j) for index,j in enumerate(c['plan']['groups'])
                 if (j['scope'],j['machine']['name'],j['mode']) == (g['scope'],g['machine']['name'],g['mode'])]
        require(len(matches)==1,'Missing/ambiguous existing full lookahead inventory')
        index,current=matches[0]
        require(current['checksum']==g['checksum'] and current['machine']==g['machine'] and
                [dict(r,target=False) for r in current['rows']]==[dict(r,target=False) for r in g['rows']],
                'Full48 lookahead source/native inventory differs')
        for row,addition in zip(current['rows'],g['rows']):
            if addition['target']:
                require(not row['target'] and row['raw_index'] in (23,47),'Duplicate/foreign FSM target')
                row['target']=True
        names=[r['name'] for r in current['rows'] if r['target']]
        lines.append('set batch_group [lindex $fx_groups %d]\n'%index)
        lines.append('set batch_group [lreplace $batch_group 5 5 [list %s]]\n'%' '.join(map(atom,names)))
        lines.append('set fx_groups [lreplace $fx_groups %d %d $batch_group]\n'%(index,index))
    c['plan']['targets'] += 2;c['plan']['protected'] -= 2
    return ''.join(lines)


def host_hook(selection,c):
    import test_report_native_population_union as tests
    def audit(out,prefix,refs):
        old.audit_six(out,prefix,refs)
        if prefix == 'child': old.audit_six(out,'batch_scale',c['batch_scale_references'])
    proxy = SimpleNamespace(**dict(vars(old),TCL=TCL,audit_six=audit))
    ns = dict(tests.actual_hook_regression.__globals__,report=proxy)
    # The existing host regression checks all production combo walks; the new
    # scale walk uses the same rows already modeled by diagnostic scope audits.
    body=inspect.getsource(tests.actual_hook_regression)
    anchor="    model = ''"
    require(body.count(anchor)==1,'Actual host model anchor differs')
    body=body.replace(anchor,"    for instance,rows in zip(config['batch_captures']['scale120']['config']['instances'], config['batch_scale_references']):\n"
        "        identities[instance['scope']] = rows\n"+anchor)
    exec(compile(body,__file__,'exec'),ns)
    return ns['actual_hook_regression'](selection,c)


def prepare(out,runtime_ready=False):
    require(out.parent == life.OUT and not out.exists(),'Fresh independent report output')
    q = life.read_bound(BASE/'qualification.json',BASE_SHA)
    require(q['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and q['population'] == 762 and
            q['qualified_fsm_union'] == 159,'Qualified762 required')
    c = life.read_bound(BASE/'config.json',q['config_seal'])
    life.check(c['pins']);life.check(q['output_pins'])
    ledger,selected,pop_pins,admission = population(c,MANIFEST,MANIFEST_SHA)
    additions,addpins = captures()
    c = copy.deepcopy(c)
    c.update(schema=SCHEMA,output=str(out),population=763,successor_entry=str(Path(__file__).resolve()),
        admission=admission,input_ledger=ledger,expected_selected=selected,batch_captures=additions,
        runtime_apply_authorized=runtime_ready,runtime_timeout_seconds=5400)
    existing = old.ownership(c)
    require(not set(existing)&set(target_fields(c)), 'New/retained field overlap')
    require(not any(s == o or s.startswith(o+'.') for s,_ in target_fields(c) for o in c['observers']), 'Observer overlap')
    append_groups(c)
    selection = (BASE/'selection.tcl').read_text()+selection_tail(c)
    combined = (BASE/'applied.el').read_text()+''.join((Path(item['output'])/'first.el').read_text() for item in additions.values())
    c['expected_union'] = records(combined,c)
    retained = copy.deepcopy(c['expected_union']);del retained['batch']
    expected = copy.deepcopy(life.read_bound(BASE/'config.json',q['config_seal'])['expected_union'])
    oldfsm = expected['retained']['prior']['original']['prior'][0]
    wanted = [tuple(r) for r in additions['lookahead2']['qualification']['native_records']]
    newfsm = retained['retained']['prior']['original']['prior'][0]
    require({tuple(r) for r in newfsm} == {tuple(r) for r in oldfsm}|set(wanted) and
            len(newfsm) == len(oldfsm)+2,'Exact two disjoint FSM additions')
    retained['retained']['prior']['original']['prior'][0] = oldfsm
    require(retained == expected,'Retained762 canonical records changed')
    c['qualified_fsm_union'] = 161
    dependencies = [Path(__file__).resolve(),TCL,HERE/'test_report_native_batch763.py',Path(prior.__file__).resolve(),
        Path(old.__file__).resolve(),HERE/'test_report_native_population_union.py',
        *[Path(m.__file__).resolve() for m in (scalar22,scalar158,queue336,scale120,half816,lookahead2,parity)]]
    pins = merge(c['pins'],q['output_pins'],pop_pins,addpins,
        {str(BASE/'qualification.json'):BASE_SHA,str(BASE/'config.json'):q['config_seal']},
        {str(p):life.digest(p) for p in dependencies})
    life.check(pins);out.mkdir()
    for name,text in [('selection.tcl',selection),('combined.el',combined),('inputs.txt','\n'.join(ledger)+'\n')]:
        with (out/name).open('x') as f:f.write(text)
        require((out/name).read_bytes() == text.encode('ascii'),'Text serialization differs')
        pins[str(out/name)] = life.digest(out/name)
    syntax = old.parser(HERE/'check_generated_tcl.py')
    checks = [syntax.check(out/'selection.tcl'),syntax.check(TCL)]
    evaluated = old.generated.evaluate(out/'selection.tcl',{str(out/'selection.tcl'):pins[str(out/'selection.tcl')]},
        ('combo_groups','diagnostic_instances','child_instances','report745_roots','fx_groups','batch_scale_instances'))
    hook = host_hook(out/'selection.tcl',c)
    life.save(out/'host-generated-tcl-evidence.json',dict(syntax=checks,selection=evaluated,hook=hook,no_EDA=True))
    pins[str(out/'host-generated-tcl-evidence.json')] = life.digest(out/'host-generated-tcl-evidence.json')
    c['pins'] = pins;life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(status='PREPARED_NO_DVE',output=str(out),seal=life.digest(out/'config.json'),population=763,
        qualified_fsm_union=161,batch_counts={k:len(v) for k,v in c['expected_union']['batch'].items()},pins=len(pins))),flush=True)


def check(out,seal):
    c = life.read_bound(out/'config.json',seal)
    require(c['schema'] == SCHEMA and c['output'] == str(out) and c['population'] == 763 and
            c['successor_entry'] == str(Path(__file__).resolve()) and c['runtime_timeout_seconds'] == 5400 and
            c['qualified_fsm_union'] == 161 and set(c['batch_captures']) == set(CAPTURES),'Batch identity differs')
    life.check(c['pins'])
    require((out/'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            len(c['expected_selected']) == len(set(c['expected_selected'])) == 763,'Population differs')
    for key,item in c['batch_captures'].items():
        qualification_gates(key,item['qualification'])
        require(item['seal'] == CAPTURES[key][1], 'Unapproved capture seal')
    require(records((out/'combined.el').read_text(),c) == c['expected_union'],'Combined canonical union differs')
    return c


def snapshot_stdout(data,out):
    prior.snapshot_stdout(data,out)
    data.update(fsm_prior=130,qualified_fsm_union=161,population=763,batch_capture_seals={k:v[1] for k,v in CAPTURES.items()},
                added_whole_objects=1332,added_scale_bits=120,added_fsm_transitions=2,
                added_parity_bits=9664,no_new_simulation=True,no_exhaustive_IEEE_claim=True)


def namespace():
    ns = prior.namespace()
    ns.update(__file__=__file__,TCL=TCL,check=check,records=records,snapshot_stdout=snapshot_stdout)
    body = inspect.getsource(old.verify)
    anchor = '        if path.exists():'
    require(body.count(anchor) == 1,'Substantive save anchor differs')
    body = body.replace(anchor,'        snapshot_stdout(data,out)\n'+anchor)
    anchor = "    audit_six(out, 'child', c['child_references'])"
    require(body.count(anchor) == 1,'Full protection anchor differs')
    body = body.replace(anchor,anchor+"\n    audit_six(out, 'batch_scale', c['batch_scale_references'])")
    exec(compile(body,__file__,'exec'),ns)
    ns['run'] = FunctionType(old.run.__code__,ns)
    return ns


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--runtime-ready',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.mode == 'prepare':prepare(out,a.runtime_ready)
    else:
        require(a.seal,'Exact sealed config required')
        if a.mode == 'check':check(out,a.seal);print('BATCH763_CHECK_PASS_NO_EDA')
        else:namespace()[a.mode](out,a.seal)
