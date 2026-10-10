"""Prepare exact five-scope native qualification. No automatic launch/admission."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import sys

import capture_cva6_parent_rvfi457 as host
import qualify_csr_pmp0_native765 as labels
import targeted_toggle_evidence_v2 as xmltools

life, tools, need = host.life, host.tools, host.require
HERE = Path(__file__).resolve().parent
ENTRY = HERE / 'rvh0_exception60_native772.tcl'
REVIEW = life.OUT / 'rvh0-exception-members-source-review771-agent-20261007-01.json'
REVIEW_SHA = '1afeb33d33fd5ddcbd403e97ba42f30fe6269a3a7690d0cbc833ce5b1461df48'
BASE = life.OUT / 'scalar-fpu-backpressure-offline-admitted-772-agent-20261007-01'
BASE_SHA = '28cc362f64c2c48e8a3b8a1dbf568903434464cc4dcea7e2dfad2aae282ca332'
ANNOTATION = 'Frozen RVH0 source-proven exception members only; cause tval valid and full complement retained'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
FILES = dict(before='initial-empty.el', selected='first.el', reset='reset-empty.el',
             reloaded='second.el', final='final-empty.el')


def proof():
    r = life.read_bound(REVIEW, REVIEW_SHA)
    need(r['fields'] == 60 and r['scopes'] == 5 and sum(r['actual_missing_positions'].values()) == 3058
         and r['coverage_admitted'] is False, 'Exact source-reviewed60 only')
    shape_path = next(Path(p) for p in r['pins'] if p.endswith('/shape/tgl.verilog.shape.xml'))
    design_path = next(Path(p) for p in r['pins'] if p.endswith('/design/verilog.design.xml'))
    life.check({str(p): r['pins'][str(p)] for p in (shape_path, design_path)})
    design = xmltools.xml(design_path)
    instances = {n.get('id'): (n, module) for module in design.findall('srcdef') for n in module.findall('srcinst')}
    def fullname(key):
        n, _ = instances[key]; parent = n.get('pid')
        return (fullname(parent) + '.' if parent in instances else '') + n.get('name')
    modules = {fullname(k): module for k, (_, module) in instances.items()}
    definitions = xmltools.xml(shape_path).findall('tgldef')
    result = []
    for inventory in r['compiled_scope_inventories']:
        scope = inventory['scope']; module = modules[scope]
        matches = [d for d in definitions if d.get('chksum') == inventory['checksum']]
        need(len(matches) == 1 and matches[0].get('name') == module.get('name'), 'Compiled scope/config identity')
        chosen = {n['name']: n for n in r['targets'] if n['scope'] == scope}
        bindings = []
        for n in matches[0].find('tglshape'):
            a = dict(n.attrib); name = a['name']; role = 'target' if name in chosen else 'protected'
            obj = dict(kind=n.tag, **a)
            allowed = sorted(labels.aliases(obj))
            width = 1 if n.tag == 'node' else abs(int(a['left']) - int(a['right'])) + 1 if n.tag == 'vectornode' else None
            if role == 'target':
                need(a == chosen[name]['native'] and n.tag in ('node', 'vectornode') and a['type'] == '1'
                     and a['excluded'] == '0' and name.split('.')[-1] in ('gva', 'tinst', 'tval2'),
                     'Source-bound field/type/port exception only')
            bindings.append(dict(name=name, kind=n.tag, attributes=a, role=role, width=width,
                label=name + labels.bounds(obj), allowed_labels=allowed))
        need(len({b['name'] for b in bindings}) == len(bindings), 'Duplicate compiled object')
        need(len({s for b in bindings for s in b['allowed_labels']}) == sum(len(b['allowed_labels']) for b in bindings),
             'Compiled alias collision')
        result.append(dict(scope=scope, design_checksum=module.get('chksum'),
            toggle_checksum=inventory['checksum'], bindings=bindings,
            children_protected=sorted(s for s in modules if s.startswith(scope + '.'))))
    need(len(result) == 5 and sum(len(i['bindings']) for i in result) == 2854
         and sum(b['role'] == 'target' for i in result for b in i['bindings']) == 60
         and sum(b['kind'] == 'arrays' for i in result for b in i['bindings']) == 38,
         'Exact60 / 2794 full complement partition')
    return r, result


def contract(c):
    _, expected = proof()
    need(c['instances'] == expected and c['source_review_sha256'] == REVIEW_SHA
         and c['baseline_manifest_sha256'] == BASE_SHA and c['baseline'] == 772
         and c['timeout_seconds'] == 900 and c['automatic_retry'] is False
         and c['population_application'] is False, 'Frozen qualification contract')


def atom(value):
    need(not any(x in str(value) for x in '{}\\\r\n'), 'Unsafe Tcl atom')
    return '{' + str(value) + '}'


def selection(c):
    text = ''.join('set ::re_' + key + ' ' + atom(c[key]) + '\n'
                   for key in ('design', 'sample', 'test', 'python', 'helper'))
    return text + 'set ::re_scopes [list ' + ' '.join(atom(i['scope']) for i in c['instances']) + ']\n'


def inventory(out, c, stage, index):
    need(stage in STAGES and index in range(5), 'Exact stage/scope index')
    i = c['instances'][index]
    with (out / ('native_%s_%d.tsv' % (stage, index))).open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        need(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'excluded'], 'Native TSV schema')
        rows = list(reader)
    need(len(rows) == len(i['bindings']) and all(set(row) == set(reader.fieldnames) and all(row.values()) for row in rows),
         'Incomplete full inventory/array complement')
    for key in ('handle', 'path', 'name'):
        need(len({row[key] for row in rows}) == len(rows), 'Duplicate native ' + key)
    by_label = {label: b for b in i['bindings'] for label in b['allowed_labels']}
    found = {}; metadata = []
    for row in rows:
        need(row['handle'].isdigit() and row['path'] == row['meta'] == row['name']
             and row['excluded'] in ('0', '1'), 'Actual path/metadata/Boolean identity')
        obj = by_label.get(row['name'])
        need(obj is not None and obj['name'] not in found, 'Foreign/duplicate full typed object')
        flag = str(int(stage in ('selected', 'reloaded') and obj['role'] == 'target'))
        need(row['excluded'] == flag, 'Target/protected membership differs: ' + row['name'])
        found[obj['name']] = dict(obj, observed_label=row['name'])
        metadata.append([row['path'], row['meta'], row['name']])
    need(set(found) == {b['name'] for b in i['bindings']}, 'Missing complete complement')
    result = dict(scope=i['scope'], bindings=sorted(found.values(), key=lambda b: b['name']), metadata=sorted(metadata))
    if stage != 'before':
        saved = json.loads((out / 'actual-binding.json').read_bytes())
        need(saved['config_seal'] == life.digest(out / 'config.json')
             and saved['before_pins'][str(out / ('native_before_%d.tsv' % index))] == life.digest(out / ('native_before_%d.tsv' % index))
             and result == saved['scopes'][index], 'Fresh-before identity drift')
    return result


def bind(out, c):
    scopes = [inventory(out, c, 'before', index) for index in range(5)]
    text = ''
    for index, scope in enumerate(scopes):
        targets = [b['observed_label'] for b in scope['bindings'] if b['role'] == 'target']
        text += 'set ::re_targets(%d) [list %s]\n' % (index, ' '.join(atom(s) for s in targets))
    path = out / 'actual-selection.tcl'
    need(not path.exists() and not (out / 'actual-binding.json').exists(), 'Fresh actual binding only')
    path.write_text(text)
    life.save(out / 'actual-binding.json', dict(config_seal=life.digest(out / 'config.json'), scopes=scopes,
        before_pins={str(out / ('native_before_%d.tsv' % index)): life.digest(out / ('native_before_%d.tsv' % index)) for index in range(5)},
        actual_selection_sha256=life.digest(path), actual_objects=2854, targets=60, protected=2794, arrays=38))


def records(text, c):
    expected = {i['scope']: i for i in c['instances']}
    checksum = None; scope = None; pending = False; seen_scopes = set(); found = defaultdict(list); annotation = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'): continue
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if m:
            need(not pending, 'Orphan/duplicate checksum'); checksum=m.groups(); pending=True; scope=None; annotation=False; continue
        m = re.fullmatch(r'INSTANCE:\s*(\S+)', line)
        if m:
            scope=m[1]; need(pending and scope in expected and scope not in seen_scopes, 'Foreign/duplicate/whole scope')
            i=expected[scope]; need(checksum == (i['design_checksum'], i['toggle_checksum']), 'Exact scope checksum')
            seen_scopes.add(scope); pending=False; continue
        m = re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"', line)
        if m:
            need(scope is not None and not annotation and m[1] == ANNOTATION, 'Exact source annotation')
            annotation=True; continue
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+?)(?: \[([^\]]+)\])? "logic ([^"\r\n]+)"', line)
        need(m is not None and scope is not None and annotation, 'Only exact typed Toggle; no other metrics')
        direction, name, bit, declaration=m.groups()
        target = next((b for b in expected[scope]['bindings'] if b['name'] == name and b['role'] == 'target'), None)
        need(target is not None, 'Protected cause/tval/valid/array/child/foreign object')
        need(declaration in target['allowed_labels'], 'Exact whole type/name/bounds')
        if direction:
            need(target['width'] == 1 and ((target['kind'] == 'node' and bit is None)
                 or (target['kind'] == 'vectornode' and bit == '0' and declaration == target['label'])), 'Partial vector/direction forbidden')
        else:
            need(bit is None, 'Partial target forbidden')
        found[(scope,name)].append((direction,declaration))
    wanted={(i['scope'],b['name']) for i in c['instances'] for b in i['bindings'] if b['role']=='target'}
    need(not pending and seen_scopes == set(expected) and set(found) == wanted and len(found) == 60, 'Exact full target scope/member union')
    for key, values in found.items():
        need(len(values) == 1 and values[0][0] is None or len(values) == 2 and
             {v[0] for v in values} == {'0to1','1to0'} and values[0][1] == values[1][1], 'Incomplete/duplicate/mixed whole split')
    return sorted(wanted)


def candidate(c):
    lines=[]
    for i in c['instances']:
        lines += ['CHECKSUM: "%s %s"' % (i['design_checksum'],i['toggle_checksum']), 'INSTANCE: '+i['scope'], 'ANNOTATION: "'+ANNOTATION+'"']
        lines += ['Toggle %s "logic %s"' % (b['name'], b['label']) for b in i['bindings'] if b['role']=='target']
    return '\n'.join(lines)+'\n'


def check_el(out,c,stage):
    need(stage in STAGES, 'Exact EL stage')
    text=(out/FILES[stage]).read_text()
    if stage in ('before','reset','final'):
        need(text == '', 'All-scope reset EL must be empty'); return []
    return records(text,c)


def static():
    text=ENTRY.read_text()
    need('info script' not in text and '{*}' not in text and not re.search(r'\bdict\s|\s(?:in|ni)\s',text), 'Tcl8.4/eval compatibility')
    need('uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]' in text, 'Plain global source required')
    need('gui_exit -noprompt' in text and 'after 600' not in text, 'Established exit; DONE not terminal qualification')


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh independent output')
    static(); r, instances=proof(); life.check(r['pins'])
    baseline=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    need(baseline['coverage_admitted'] and baseline['baseline_seal'] == r['baseline_seal'], 'Compatible formal772 exact771 predecessor')
    pins=dict(r['pins']); pins[str(REVIEW)]=REVIEW_SHA; pins[str(BASE/'admission-manifest.json')]=BASE_SHA
    for name in ('combined-inputs.txt','status.json'):
        p=BASE/name; pins[str(p)]=baseline['output_pins'][str(p)]; life.check({str(p):pins[str(p)]})
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    need(len(ledger)==len(set(ledger))==773, 'Formal772 design plus unique tests')
    parent_path=Path(baseline['baseline'])/'admission-manifest.json'
    parent=life.read_bound(parent_path,baseline['baseline_seal']); pins[str(parent_path)]=baseline['baseline_seal']
    parent_ledger=parent_path.parent/'combined-inputs.txt'; pins[str(parent_ledger)]=parent['output_pins'][str(parent_ledger)]
    life.check({str(parent_ledger):pins[str(parent_ledger)]})
    need(ledger[:-1]==parent_ledger.read_text().splitlines(), 'Exact771 prefix unchanged')
    sample=life.OUT/'gap84-div32-old-image-20261006-01/code.vdb'
    need(str(sample) in ledger, 'Representative VDB admitted772')
    dirs=list((sample/'snps/coverage/db/testdata').iterdir()); need(len(dirs)==1 and dirs[0].is_dir(), 'One actual test')
    for name in ('line','cond','branch','fsm','tgl'):
        need((dirs[0]/(name+'.verilog.data.xml')).is_file(), 'Complete representative testdata')
    for p in sample.rglob('*'):
        if p.is_file():pins[str(p)]=life.digest(p)
    design=life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
    design_files=sorted(str(p) for p in design.rglob('*') if p.is_file())
    sample_files=sorted(str(p) for p in sample.rglob('*') if p.is_file())
    need(design_files and sample_files,'Complete nonempty design/sample VDB closures')
    for path in design_files:pins[path]=life.digest(path)
    # Freeze only the actual imported Python and absolute-source Tcl closure.
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).resolve().parent==HERE and Path(path).suffix=='.py':pins[str(Path(path).resolve())]=life.digest(path)
    pending=[ENTRY]; visited=set()
    while pending:
        p=pending.pop()
        if p in visited:continue
        visited.add(p); pins[str(p)]=life.digest(p)
        pending += [Path(s) for s in re.findall(r'source\s+\{(/[^{}\n]+\.tcl)\}',p.read_text())]
    test=HERE/'test_rvh0_exception60_native772.py'; pins[str(test)]=life.digest(test)
    identity=tools.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve','/usr/bin/xvfb-run')
    pins.update({f['path']:f['sha256'] for f in identity['files']})
    c=dict(instances=instances, source_review_sha256=REVIEW_SHA, baseline=772, baseline_manifest_sha256=BASE_SHA,
        design=str(design),sample=str(sample),design_files=design_files,sample_files=sample_files,
        test=str(sample.with_suffix('')/dirs[0].name),python=sys.executable,helper=str(Path(__file__).resolve()),
        output=str(out),pins=pins,identity=identity,timeout_seconds=900,automatic_retry=False,population_application=False,
        native_launched=False,actual_binding='REQUIRED_FROM_FRESH_BEFORE_NOT_PREPARED_NAMES',actual_percentage=None,
        source_missing_coordinates=3058,compiled_target_bits=1529,
        launch_policy='PREPARED_ONLY_PARENT_AUTHORIZATION_REQUIRED_NO_LAUNCH_API',
        complement_accounting=dict(total=2854,targets=60,protected_scalar_vector=2756,
            protected_arrays=38,protected_total=2794),
        child_guard='All descendants except the exact60 source-approved leaves remain protected by all-scope empty/reset EL and strict selected/reloaded exact member union; no child whole-scope or other metric directive accepted')
    contract(c); records(candidate(c),c); life.check(pins); out.mkdir()
    for name,text in (('selection.tcl',selection(c)),('candidate.el',candidate(c))):
        (out/name).write_text(text); pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),scopes=5,objects=2854,targets=60,
        protected=2794,arrays=38,baseline=772,pins=len(pins),native_launched=False)),flush=True)


def verify_config(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins']);tools.revalidate(c['identity'])
    for key in ('design','sample'):
        actual=sorted(str(p) for p in Path(c[key]).rglob('*') if p.is_file())
        need(actual==c[key+'_files'] and all(path in c['pins'] for path in actual),'Complete VDB file closure changed: '+key)
    return c


def inspect(out,seal):
    c=verify_config(out,seal); terminal=json.loads((out/'terminal.json').read_bytes())
    need(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Actual terminal0 required; DONE alone insufficient')
    process=terminal['actual_dve'][0]
    need(process['exe']==c['identity']['executable'] and process['cwd']==str(out),'Actual DVE executable/cwd identity')
    log=(out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('RVH0_EXCEPTION60_NATIVE_DONE')==1 and not re.search(r'RVH0_EXCEPTION60_FAILED|Error:|Fatal:|EK-CMD-|UCAPI-DLMA|DVCDT136',log)
         and not (out/'error.txt').exists(),'Five native stages incomplete/rejected')
    actual=json.loads((out/'actual-binding.json').read_bytes())
    need(actual['actual_selection_sha256']==life.digest(out/'actual-selection.tcl'),'Actual target selection changed')
    for stage in STAGES:
        for index in range(5):inventory(out,c,stage,index)
        check_el(out,c,stage)
    need(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c),'Exact semantic reload')
    need((out/'cleanup-empty.el').read_bytes()==b'','Cleanup EL nonempty')
    pins=dict(c['pins'])
    for p in out.rglob('*'):
        if p.is_file() and p.name not in ('capture-result.json','worker.log'):pins[str(p)]=life.digest(p)
    result=dict(status='RVH0_EXCEPTION60_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',config_seal=seal,
        baseline_manifest_sha256=BASE_SHA,targets=60,objects=2854,protected=2794,arrays=38,
        source_missing_coordinates=3058,native_denominator_reduction=None,official_percentage=None,pins=pins)
    need(not (out/'capture-result.json').exists(),'Fresh result only'); life.save(out/'capture-result.json',result)
    print(json.dumps(dict(result=str(out/'capture-result.json'),seal=life.digest(out/'capture-result.json'))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify-config','bind','inventory','el','selection','inspect'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage',choices=STAGES);p.add_argument('--index',type=int)
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    else:
        need(a.seal,'Exact config seal');c=life.read_bound(out/'config.json',a.seal)
        if a.mode=='verify-config':verify_config(out,a.seal);print('RVH0_EXCEPTION60_PREPARED_VERIFY_PASS_NOT_LAUNCHED')
        elif a.mode=='inspect':inspect(out,a.seal)
        else:
            if a.mode=='bind':bind(out,c);print('ACTUAL_FULL2854_BINDING60_TARGETS2794_PROTECTED')
            elif a.mode=='inventory':inventory(out,c,a.stage,a.index);print('EXACT_SCOPE_INVENTORY_PASS')
            elif a.mode=='el':check_el(out,c,a.stage);print('EXACT_ALL_SCOPE_EL_PASS')
            else:
                b=json.loads((out/'actual-binding.json').read_bytes())
                need(b['config_seal']==a.seal and b['actual_selection_sha256']==life.digest(out/'actual-selection.tcl'),'Actual binding selection pin')
                print('ACTUAL_SELECTION_PIN_PASS')
