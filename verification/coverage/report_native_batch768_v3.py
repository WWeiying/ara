"""Source-first full-session successor; never promotes failed local captures."""
import argparse
import inspect
import json
from pathlib import Path
from types import FunctionType

import report_native_batch768 as base
import report_native_batch768_v2 as v2
import verify_cva6_fixed_fields_native768_offline as typed

life, require = base.life, base.require
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'FORMAL768_SOURCE_FIRST_FULL_SESSION_V3'
FIRST = frozenset(('csr1193', 'tlb726', 'accum66'))
ROLE = 'SOURCE_PROVEN_FIRST_FULL_SESSION'
MODULES = v2.MODULES
SOURCES = {
    'csr1193': (base.CSR, base.CSR_SHA),
    'tlb726': (life.OUT/'tlb-rvh0-726-native-agent-20261007-02',
               '22b16fecce042cf781301b59323821ad0e4532fc46206694a13d7f1a8ef5424d'),
    'accum66': (life.OUT/'qbs-accum66-native-agent-20261007-01',
                'c08cab66d3ecd385d397b09433ea0daacc49fb9350a720eef396185a527f04c5')}
FIXED = life.OUT/'cva6-fixed120-native768-offline-qualified-agent-20261007-01/qualification.json'
FIXED_SHA = '3944a6e765d78ee007833e526c5f203be236dfc7818cb0cfcfa5d6bb7beb206d'


def origin_gate(key, item):
    if key in FIRST:
        require(item['qualification_origin'] == ROLE and item['local_qualified'] is False
                and item['qualification_seal'] is None,
                'Source candidate cannot inherit local PASS')
        require(item['reference_pins'] and item['population_application'] is False,
                'Missing captured reference or premature application')
        life.check(item['reference_pins'])
    else:
        require(item['local_qualified'] is True and item['qualification_seal'],
                'Qualified receipt required outside exact source-first registry')


def source_family(key):
    require(key in FIRST, 'Closed source-first registry')
    out, seal = SOURCES[key]
    c = life.read_bound(out/'config.json', seal)
    life.check(c['pins']); MODULES[key].contract(c)
    terminal = json.loads((out/'terminal.json').read_bytes())
    marker = out/('qualification-reject.json' if key == 'accum66' else 'qualification-hold.json')
    reject = json.loads(marker.read_bytes())
    require(reject['status'] == ('REJECTED_NOT_QUALIFIED' if key == 'accum66' else 'HOLD_NOT_APPLIED'),
            'Preserve actual unqualified local origin')
    require(not (out/'capture-result.json').exists() and not (out/'qualification.json').exists(),
            'Source-first origin unexpectedly contains qualification')
    if key != 'accum66':
        require(terminal['timeout'] is True and terminal['returncode'] != 0, 'Expected local exit HOLD')
    pins = {str(out/'config.json'): seal, str(out/'terminal.json'): life.digest(out/'terminal.json'),
            str(marker): life.digest(marker)}
    if key == 'csr1193':
        item = base.family(key, out, c, (out/'first.el').read_text())
        tables = [out/'objects-before.tsv']
    else:
        module = v2.REGISTRY[key]['module']
        refs, signals, labels, whole, tables = {}, {}, {}, {}, []
        for index, instance in enumerate(c['instances']):
            table = out/('objects-before-%d.tsv' % index if key == 'tlb726'
                         else 'native_before_%d.tsv' % index)
            require(table.is_file(), 'Missing complete captured before inventory')
            mapping = dict(module.inventory(out, c, 'before', index))
            scope = instance['scope']; names = sorted(t.get('signal', t.get('name')) for t in instance['targets'])
            refs[scope] = sorted(list(row) for row in mapping.values())
            signals[scope] = names; labels[scope] = sorted(mapping[n][2] for n in names)
            whole[scope] = sorted(mapping[t.get('signal', t.get('name'))][2]
                                  for t in instance['targets'] if not t.get('retained_source_bits'))
            tables.append(table)
        el = out/'candidate.el'
        text = el.read_text(); canonical = v2.parse(key, text, c)
        item = dict(config=c, output=str(out), canonical=canonical, reference=refs,
                    signals=signals, native_targets=labels, targets=whole, el=text,
                    source_pins=base.merge(c['pins'], {str(el): life.digest(el)}))
    reference_pins = {str(p): life.digest(p) for p in tables}
    item.update(local_qualified=False, qualification_seal=None, qualification_origin=ROLE,
                population_application=False, reference_pins=reference_pins,
                membership_authority='Source-bound exact paired EL; first full-session complete complement required')
    item['source_pins'] = base.merge(item['source_pins'], pins, reference_pins)
    origin_gate(key, item)
    return item


def fixed_family():
    q = life.read_bound(FIXED, FIXED_SHA); life.check(q['pins'])
    require(q['status'] == 'CVA6_FIXED120_4396_NATIVE_OFFLINE_REVERIFIED_NOT_APPLIED'
            and q['population_application'] is False and q['capture'] == str(typed.CAPTURE),
            'Exact parent offline typed receipt, not capture directory receipt')
    out = Path(q['capture']); c = life.read_bound(out/'config.json', q['config_seal'])
    v2.fixed_contract(c); life.check(c['pins'])
    refs, signals, labels, whole, rpins = {}, {}, {}, {}, {}
    for index, instance in enumerate(c['instances']):
        stages = {s: (out/('native_%s_%d.tsv' % (s, index))).read_text() for s in base.prior.STAGES}
        typed.audit_native(instance, stages)
        rows = v2.fixed.native_rows(stages['before']); typed.bind_inventory(instance, rows)
        scope = instance['scope']; refs[scope] = sorted([v['path'], v['meta'], n] for n,v in rows.items())
        signals[scope] = sorted(s['name'] for s in instance['signals'])
        labels[scope] = sorted(s['native_label'] for s in instance['signals'])
        whole[scope] = sorted(s['native_label'] for s in instance['signals']
                             if set(s['bits']) == set(range(s['right'], s['left']+1)))
        for stage in stages:
            p = out/('native_%s_%d.tsv' % (stage,index)); rpins[str(p)] = life.digest(p)
    text = (out/'first.el').read_text(); canonical = v2.parse('fixed120', text, c)
    require(canonical == v2.parse('fixed120', (out/'second.el').read_text(), c), 'Fixed semantic reload')
    return dict(config=c, output=str(out), canonical=canonical, reference=refs, signals=signals,
                native_targets=labels, targets=whole, local_qualified=True, qualification_seal=FIXED_SHA,
                qualification_origin='PARENT_OFFLINE_TYPED_QUALIFIED', source_pins=base.merge(c['pins'],q['pins'],rpins,
                {str(FIXED):FIXED_SHA, str(out/'config.json'):q['config_seal'],
                 str(out/'first.el'):life.digest(out/'first.el')}), el=text)


def private_namespace():
    ns = dict(vars(base), __file__=__file__, TCL=TCL, SCHEMA=SCHEMA, MODULES=MODULES)
    for name in ('partition','records','merged_observers','audit_observers','host_hook','snapshot_stdout'):
        ns[name] = FunctionType(getattr(base,name).__code__,ns)
    body = inspect.getsource(base.check)
    anchor = "require(item['local_qualified'] == (key != 'csr1193'), 'Separate qualification origins')"
    require(body.count(anchor) == 1, 'Frozen origin adapter anchor')
    ns['origin_gate'] = origin_gate
    exec(compile(body.replace(anchor, 'origin_gate(key,item)'), __file__, 'exec'), ns)
    ns['snapshot_stdout'] = snapshot_stdout
    ns['host_hook'] = host_hook
    return ns


def host_hook(selection,c):
    # The mock must not reorder a shared scope's existing native traversal.
    prior=base.prior
    body=inspect.getsource(prior.host_hook)
    anchor='"        identities[item[\'scope\']] = item[\'reference\']\\n"'
    replacement=("        if item['scope'] in identities:\n"
                 "            report.require(sorted(identities[item['scope']]) == sorted(item['reference']), 'Shared observer native identity differs')\n"
                 "        else:\n"
                 "            identities[item['scope']] = item['reference']\n")
    require(body.count(anchor)==1,'Frozen host identity adapter anchor differs')
    body=body.replace(anchor,repr(replacement))
    ns=dict(vars(prior),TCL=TCL)
    exec(compile(body,__file__,'exec'),ns)
    cc=dict(c,observer_captures=private_namespace()['merged_observers'](c))
    return ns['host_hook'](selection,cc)


def snapshot_stdout(data,out):
    base.snapshot_stdout(data,out)
    data.update(source_first_full_session_qualified=sorted(FIRST),
                source_first_local_qualification_inherited=False,
                fixed120_parent_offline_qualification_seal=FIXED_SHA)


def prepare(out):
    require(not out.exists(), 'Fresh V3 only')
    extra = {key:source_family(key) for key in sorted(FIRST)}
    extra['fixed120'] = fixed_family()
    read = life.OUT/'requester-read108-native767-agent-20261007-01/capture-result.json'
    read_sha = 'a31abca542924c82f51f53e4e2c5ed17b22c3476eae035ecdccd5f355dbe749b'
    ns = private_namespace()
    ns['additions'] = lambda *args: dict(base.additions(False, read, read_sha), **extra)
    body = inspect.getsource(base.prepare)
    body = body.replace("HERE/'test_report_native_batch768.py'", "HERE/'test_report_native_batch768_v3.py', Path(base.__file__), base.TCL, Path(v2.__file__), v2.TCL, Path(typed.__file__)")
    ns.update(base=base, v2=v2, typed=typed)
    anchor = "    c['expected_union']=records(combined,c)"
    require(body.count(anchor) == 1, 'Frozen prepare adapter anchor')
    body = body.replace(anchor, "    c['pending_next_family']=None\n    c['source_first_groups']=sorted(FIRST)\n"+anchor)
    ns['FIRST'] = FIRST
    exec(compile(body,__file__,'exec'),ns)
    ns['prepare'](out,True,read,read_sha)


def namespace():
    ns = base.namespace(); private = private_namespace()
    ns.update({k:private[k] for k in ('__file__','TCL','SCHEMA','MODULES','check','records','audit_observers','snapshot_stdout')})
    check = ns['check']
    def exact_check(out,seal):
        c = check(out,seal)
        require(c['source_first_groups'] == sorted(FIRST) and c['pending_next_family'] is None,
                'All exact source-first groups must be present')
        return c
    ns['check'] = exact_check
    for name in ('verify','run'): ns[name] = FunctionType(ns[name].__code__,ns)
    return ns


def authorize(reviewed, first_session):
    require(reviewed and first_session, 'Explicit parent full-session authorization required')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    p.add_argument('--authorize-reviewed-run',action='store_true')
    p.add_argument('--authorize-source-first-full-session',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        require(a.seal,'Exact config seal required')
        if a.mode=='run':authorize(a.authorize_reviewed_run,a.authorize_source_first_full_session)
        namespace()[a.mode](out,a.seal)
