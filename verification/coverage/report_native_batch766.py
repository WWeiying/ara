"""Formal766 population, retained765 policies plus qualified observer leaves."""
import argparse
import copy
import csv
import inspect
import json
import re
from pathlib import Path
from types import FunctionType

import report_native_batch765 as predecessor
import prepare_rvfi788_union_successor as observers
import qualify_csr_pmp0_native765 as pmp

life, require, merge = predecessor.life, predecessor.require, predecessor.merge
old = observers.retained.old
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
BASE = observers.BASE
BASE_SHA = '6f375f9e5fd6ee04a1a0dcf5a70a12ce88e774e7d7ffe9500cc8cbb65aaa751a'
MANIFEST = life.OUT/'qbs-payload-matrix4-offline-admitted-766-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA = 'bbad20298653af04606493c1e6c6433cf22bb9f532b4cc16f52922fe9b7bfb3b'
SCHEMA = 'FORMAL766_RETAINED765_RVFI788_CVA6_OUTPUT457_PMP770_V1'
PMP = life.OUT/'csr-pmp0-internal770-native765-agent-20261007-01'
PMP_SHA = 'b3e8898b50035449d861c4f41e283485df5f5e2bd6bf95cc481d3f1559191954'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')


def full_or(before, bits, single):
    require(len(before['tests']) == 765 and bits['tests'][:-1] == before['tests'] and
            len(bits['tests']) == len(set(bits['tests'])) == 766 and single['tests'] == bits['tests'][-1:] and
            bits['design'] == before['design'] == single['design'], 'Exact765 prefix/design differs')
    require(set(bits['metrics']) == set(before['metrics']) == set(single['metrics']), 'Metric families differ')
    count = 0
    for metric, rows in before['metrics'].items():
        require(set(rows) == set(bits['metrics'][metric]) == set(single['metrics'][metric]), 'Hierarchy differs')
        count += len(rows)
        for scope, p in rows.items():
            now, one = bits['metrics'][metric][scope], single['metrics'][metric][scope]
            require((p['width'], p['checksum']) == (now['width'], now['checksum']) ==
                    (one['width'], one['checksum']), 'Compiled shape differs')
            require(int(now['bits'], 16) == int(p['bits'], 16) | int(one['bits'], 16) and
                    int(now['bits'], 16).bit_length() <= now['width'], 'Full OR/overflow differs')
    require(count == 6162, 'Not full6162')


def population(original):
    book = life.read_bound(MANIFEST, MANIFEST_SHA)
    require(book['schema'] == 'QBS_MATRIX4_HISTORICAL766_NATIVE_ADMISSION_V1' and
            book['baseline'] == str(predecessor.MANIFEST.parent) and
            book['baseline_seal'] == predecessor.MANIFEST_SHA and book['output'] == str(MANIFEST.parent) and
            book['coverage_admitted'] is True, 'Formal766 authority differs')
    pins = merge(book['input_pins'], book['output_pins'], {str(MANIFEST): MANIFEST_SHA})
    def read(name):
        p = MANIFEST.parent/name
        require(str(p) in book['output_pins'], 'Unsealed766 output')
        return life.read_bound(p, book['output_pins'][str(p)])
    before = predecessor.MANIFEST.parent/'combined-bits.json'
    require(str(before) in pins, 'Unsealed765 bitmap')
    bits = read('combined-bits.json')
    full_or(life.read_bound(before, pins[str(before)]), bits, read('single-bits.json'))
    status = read('status.json')
    require(status['aggregate_passed'] == 766 and status['exact765_prefix'] is True and
            status['full_OR_instances'] == 6162 and status['coverage_admitted'] is True,
            'Formal766 status differs')
    ledger = (MANIFEST.parent/'combined-inputs.txt').read_text().splitlines()
    require(ledger[:-1] == original['input_ledger'] and ledger ==
            [original['input_ledger'][0], *bits['tests']], 'Exact765 ledger prefix differs')
    selected = [str(Path(db).with_suffix('')/test.name) for db in ledger
                for test in sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if test.is_dir()]
    require(len(selected) == len(set(selected)) == 766, 'Actual766 membership differs')
    return ledger, selected, pins


def captures():
    result, pins = {}, None
    for key, out, sha, module, gate in (
        ('rvfi788', observers.CAPTURE, observers.CAPTURE_SHA, observers.native, observers.qualification_gate),
        ('cva6rvfi457', observers.CVA6, observers.CVA6_SHA, observers.cva6, observers.cva6_gate)):
        q = life.read_bound(out/'capture-result.json', sha)
        c = life.read_bound(out/'config.json', q['config_seal'])
        gate(q, c)
        first = module.records((out/'first.el').read_text(), c)
        require(first == module.records((out/'second.el').read_text(), c), 'Observer semantic reload differs')
        refs = [module.inventory(out, c, s) for s in STAGES]
        if key == 'cva6rvfi457':
            refs = [r[0] for r in refs]
            targets = [p['observed_label'] for p in module.inventory(out, c, 'before')[1] if p['role'] == 'target']
            scope = c['scope']
        else:
            targets = [p['observed_label'] for p in c['native_bindings'] if p['role'] == 'target']
            scope = module.core.review.SCOPE
        require(all(r == refs[0] for r in refs), 'Observer full five-stage identity differs')
        result[key] = dict(output=str(out), seal=sha, config=c, qualification=q,
            reference=old.normalized(refs[0]), targets=sorted(targets), scope=scope)
        bound = merge(c['pins'], q['pins'],
            {str(out/'capture-result.json'):sha, str(out/'config.json'):q['config_seal']})
        pins = merge(pins, bound) if pins else bound
    q = life.read_bound(PMP/'capture-result.json',PMP_SHA)
    c = life.read_bound(PMP/'config.json',q['config_seal']);pmp.contract(c)
    require(q['status'] == 'PMP0_INTERNAL770_NATIVE_QUALIFIED_NOT_APPLIED' and
            q['objects'] == 770 and q['logical_bits'] == 7936 and q['protected_objects'] == 1307 and
            q['output_aliases_protected'] == 7 and q['d_protected'] is True and
            q['valid_reset_settled_only'] is True and q['initial_X_excluded'] is False and
            q['population_application'] is False,'PMP internal-only qualification boundary differs')
    terminal=json.loads((PMP/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and terminal['timeout'] is False and
            len(terminal['actual_dve']) == 1,'PMP actual terminal differs')
    gui=(PMP/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('PMP0_NATIVE_DONE') == 1 and 'PMP0_NATIVE_FAILED' not in gui and
            not (PMP/'error.txt').exists(),'PMP native session incomplete')
    require(pmp.parse_el((PMP/'first.el').read_text(),c) == pmp.parse_el((PMP/'second.el').read_text(),c),
            'PMP semantic reload differs')
    refs=[pmp.inventory(PMP,c,s,0) for s in STAGES]
    require(all(r == refs[0] for r in refs),'PMP complete complement differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):pmp.check_file(PMP,c,name)
    wanted={n['name'] for n in c['instances'][0]['targets']}
    result['pmp770']=dict(output=str(PMP),seal=PMP_SHA,config=c,qualification=q,
        reference=old.normalized(sorted(r[1:] for r in refs[0])),
        targets=sorted(r[3] for r in refs[0] if r[0] in wanted),scope=c['instances'][0]['scope'])
    pins=merge(pins,c['pins'],q['pins'],{str(PMP/'capture-result.json'):PMP_SHA,
        str(PMP/'config.json'):q['config_seal']})
    return result, pins


def records(text, c):
    additions = c['observer_captures']
    pc=additions['pmp770']['config'];wanted={p['name'] for p in pc['instances'][0]['targets']}
    previous, extra=[],[]
    for scope,block in old.blocks(text):
        if scope != pc['instances'][0]['scope']:
            previous.append(block);continue
        header=[];bodies=[[],[]];annotation=None
        for line in block.splitlines():
            if not line or line.startswith('//'):continue
            if line.startswith(('CHECKSUM:','INSTANCE:')):header.append(line);continue
            if line.startswith('ANNOTATION:'):annotation=line;continue
            m=re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?(\S+)',line)
            which=int(m is not None and m[1] in wanted)
            if annotation:bodies[which].append(annotation)
            bodies[which].append(line)
        for body,parts in zip(bodies,(previous,extra)):
            if body:parts.append('\n'.join(header+body)+'\n')
        if not any(bodies):previous.append(block)
    union = observers.records(''.join(previous), c, additions['rvfi788']['config'], additions['cva6rvfi457']['config'])
    result = union.pop('retained')
    result.update(union)
    result['pmp770']=old.normalized(pmp.parse_el(''.join(extra),pc))
    return result


def selection_tail(c):
    atom = old.frozen.prior.old.base.capture.tcl_atom
    lines = ['set ::observer766_groups {}\n']
    for index, item in enumerate(c['observer_captures'].values()):
        lines.append('lappend ::observer766_groups [list %s %d [list %s]]\n' %
            (atom(item['scope']), index, ' '.join(map(atom, item['targets']))))
    return ''.join(lines)


def audit_observers(out, c):
    for index, item in enumerate(c['observer_captures'].values()):
        wanted = set(item['targets'])
        for stage in STAGES:
            with (out/('observer766_%s_%d.tsv' % (stage, index))).open() as f:
                reader = csv.DictReader(f, delimiter='\t')
                require(reader.fieldnames == ['handle','path','meta','name','excluded'], 'Observer audit schema differs')
                rows = list(reader)
            require(len(rows) == len(item['reference']) and all(all(p.values()) for p in rows) and
                    len({p['handle'] for p in rows}) == len(rows), 'Observer audit incomplete/duplicate')
            refs = sorted([p['path'], p['meta'], p['name']] for p in rows)
            require(refs == item['reference'], 'Observer full native complement differs')
            for p in rows:
                expected = str(int(stage in ('selected','reloaded') and p['name'] in wanted))
                require(p['excluded'] == expected, 'Observer target/protected membership differs: '+p['name'])


def host_hook(selection, c):
    # Retain the actual generated full-session model; add selection and exclusion readback.
    import test_report_native_population_union as tests
    body = inspect.getsource(tests.actual_hook_regression)
    anchor = '    model = \'\''
    require(body.count(anchor) == 1, 'Host model anchor differs')
    body = body.replace(anchor, "    for item in config['observer_captures'].values():\n"
        "        identities[item['scope']] = item['reference']\n"+anchor)
    anchor = 'rename source host_original_source'
    body = body.replace(anchor, '''rename source host_original_source
proc dw_select {path meta} {set ::observer766_selected $meta}
rename gui_exclusion observer766_old_exclusion
proc gui_exclusion {args} {
    if {[lsearch -exact $args -excluded] >= 0} {
        foreach group $::observer766_groups {
            if {[lindex $group 0] eq $::scope} {
                return [expr {$::active && [lsearch -exact [lindex $group 2] $::observer766_selected] >= 0}]
            }
        }
    }
    return [eval [linsert $args 0 observer766_old_exclusion]]
}''')
    anchor = "        evidence.update(status="
    require(body.count(anchor) == 1, 'Host observer audit anchor differs')
    body = body.replace(anchor, "        observer_audit(out, config)\n"+anchor)
    from types import SimpleNamespace
    def audit(out, prefix, refs):
        old.audit_six(out, prefix, refs)
        if prefix == 'child': old.audit_six(out, 'batch_scale', c['batch_scale_references'])
    proxy = SimpleNamespace(**dict(vars(old), TCL=TCL, audit_six=audit))
    scope = dict(tests.actual_hook_regression.__globals__, report=proxy, observer_audit=audit_observers)
    # Match the inherited scale full-complement model as well.
    body = body.replace("    model = ''", "    for instance,rows in zip(config['batch_captures']['scale120']['config']['instances'], config['batch_scale_references']):\n"
        "        identities[instance['scope']] = rows\n    model = ''")
    exec(compile(body, __file__, 'exec'), scope)
    return scope['actual_hook_regression'](selection, c)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent766 output only')
    q = life.read_bound(BASE/'qualification.json', BASE_SHA)
    require(q['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and
            q['population'] == 765 and q['qualified_fsm_union'] == 173, 'Qualified765 required')
    original = life.read_bound(BASE/'config.json', observers.BASE_CONFIG_SHA)
    ledger, selected, ppins = population(original)
    additions, apins = captures()
    c = copy.deepcopy(original)
    c.update(schema=SCHEMA, output=str(out), population=766, successor_entry=str(Path(__file__).resolve()),
        admission=dict(manifest=str(MANIFEST),seal=MANIFEST_SHA,population=766,exact765prefix=True,full6162_OR=True),
        input_ledger=ledger,expected_selected=selected,observer_captures=additions)
    combined = (BASE/'combined.el').read_text()+''.join((Path(i['output'])/'first.el').read_text() for i in additions.values())
    c['expected_union'] = records(combined, c)
    legacy = copy.deepcopy(c['expected_union'])
    require(len(legacy.pop('rvfi788')) == 788 and len(legacy.pop('cva6rvfi457')) == 457 and
            len(legacy.pop('pmp770')) == 770 and
            legacy == original['expected_union'], 'Retained765 or observer canonical union differs')
    selection = (BASE/'selection.tcl').read_text()+selection_tail(c)
    deps = [Path(__file__).resolve(), TCL, HERE/'test_report_native_batch766.py',
            Path(predecessor.__file__).resolve(),Path(observers.__file__).resolve(),
            Path(observers.native.__file__).resolve(),Path(observers.native.parser.__file__).resolve(),
            Path(observers.cva6.__file__).resolve(),Path(pmp.__file__).resolve()]
    pins = merge(original['pins'],q['output_pins'],ppins,apins,
        {str(BASE/'qualification.json'):BASE_SHA,str(BASE/'config.json'):observers.BASE_CONFIG_SHA},
        {str(p):life.digest(p) for p in deps})
    life.check(pins);out.mkdir()
    for name, text in [('selection.tcl',selection),('combined.el',combined),('inputs.txt','\n'.join(ledger)+'\n')]:
        with (out/name).open('x') as f:f.write(text)
        require((out/name).read_bytes() == text.encode('ascii'), 'Text serialization differs')
        pins[str(out/name)] = life.digest(out/name)
    syntax = old.parser(HERE/'check_generated_tcl.py')
    evidence = dict(syntax=[syntax.check(out/'selection.tcl'),syntax.check(TCL)],
        hook=host_hook(out/'selection.tcl',c),no_EDA=True)
    life.save(out/'host-generated-tcl-evidence.json',evidence)
    pins[str(out/'host-generated-tcl-evidence.json')] = life.digest(out/'host-generated-tcl-evidence.json')
    c['pins'] = pins;life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(status='PREPARED_NO_DVE',output=str(out),seal=life.digest(out/'config.json'),
        population=766,pins=len(pins))),flush=True)


def check(out,seal):
    c = life.read_bound(out/'config.json',seal)
    require(c['schema'] == SCHEMA and c['population'] == 766 and c['output'] == str(out) and
            c['successor_entry'] == str(Path(__file__).resolve()) and c['qualified_fsm_union'] == 173 and
            c['admission']['seal'] == MANIFEST_SHA and c['runtime_apply_authorized'] is True and
            c['runtime_timeout_seconds'] == 5400, 'Exact766 report identity differs')
    require(set(c['observer_captures']) == {'rvfi788','cva6rvfi457','pmp770'}, 'Unapproved new family')
    life.check(c['pins'])
    require(len(c['expected_selected']) == len(set(c['expected_selected'])) == 766 and
            (out/'inputs.txt').read_text().splitlines() == c['input_ledger'], '766 membership differs')
    require(records((out/'combined.el').read_text(),c) == c['expected_union'], 'Canonical union differs')
    observers.qualification_gate(c['observer_captures']['rvfi788']['qualification'],c['observer_captures']['rvfi788']['config'])
    observers.cva6_gate(c['observer_captures']['cva6rvfi457']['qualification'],c['observer_captures']['cva6rvfi457']['config'])
    return c


def snapshot_stdout(data,out):
    predecessor.snapshot_stdout(data,out)
    data.update(population=766,formal766_manifest_seal=MANIFEST_SHA,exact765prefix=True,
        observer788_capture_seal=observers.CAPTURE_SHA,cva6observer457_capture_seal=observers.CVA6_SHA,
        new_observer_objects=1245, new_observer_complement_objects=1733,
        pmp_internal_objects=770,pmp_internal_capture_seal=PMP_SHA,pmp_initial_X_excluded=False,
        raw_population_fsm_gain=0,raw_population_condition_gain=12)


def namespace():
    ns = predecessor.namespace()
    ns.update(__file__=__file__,TCL=TCL,check=check,records=records,snapshot_stdout=snapshot_stdout,
              audit_observers=audit_observers)
    body = predecessor.metadata.verifier_body()
    anchor = "    audit_six(out, 'batch_scale', c['batch_scale_references'])"
    require(body.count(anchor) == 1, 'Full complement verifier anchor differs')
    body = body.replace(anchor,anchor+'\n    audit_observers(out,c)')
    exec(compile(body,__file__,'exec'),ns)
    ns['run'] = FunctionType(ns['run'].__code__,ns)
    return ns


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');a=p.parse_args();out=a.output.resolve()
    if a.mode == 'prepare':prepare(out)
    else:
        require(a.seal,'Sealed config required');namespace()[a.mode](out,a.seal)
        if a.mode == 'check':print('FULL766_CHECK_PASS_NO_EDA')
