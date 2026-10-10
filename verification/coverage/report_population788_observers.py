"""Consolidated788 five-stage report with exact passive observer boundaries."""
import argparse
import gzip
import json
import os
import re
from pathlib import Path
from types import FunctionType
import xml.etree.ElementTree as ET

import report_population784_rr190 as prior
import capture_cvxif_passive_two_scope770 as observer

life, stable, need = prior.life, prior.stable, prior.need
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BASE = life.OUT / 'scalar-entropy64-offline-admitted788-agent-20261008-01'
BASE_SHA = 'cf59a7fd898c33493f662b247448d52642b694a6cce68785e938f20112d12641'
REPORT = life.OUT / 'current-population785-rr190-prepared-agent-20261008-01'
CONFIG_SHA = '796fbe9f3c009b8b6aed24b840d3699a965a9e257341757e5615d6b08b997a49'
QUAL_SHA = '8e0a97845146bd0296be674c65f889fae674d2726516c593be748c47d6f960c2'
PROOF = life.OUT / 'cvxif-observer-boundary785-source-review-agent-20261008-01.json'
PROOF_SHA = '4e2a14d50cedb57891cec0d58d948cae10825adcc50512701e79b19f0e5531a0'
SUPPLEMENT = life.OUT / 'cvxif-observer-boundary785-no-drive-supplement-agent-20261008-01.json'
SUPPLEMENT_SHA = '8cfba664bbc15c7433b3cdd43ad242e54e756d5c2fdea914378596fd059f59b7'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind'
SCOPES = (SCOPE, SCOPE + '.cvxif')
IDENTITIES = ((SCOPE, '2332976182', '498965595'),
              (SCOPE + '.cvxif', '1958759582', '2981092130'))
METRICS = ('Line', 'Condition', 'Branch', 'FSM', 'Toggle')
SCHEMA = 'FORMAL788_PASSIVE_TWO_LEAF_CONSOLIDATED_HOST_CONTRACT_V1'


def boundary(proof, supplement):
    actual = tuple((v['scope'], v['module_checksum'], v['toggle_checksum'])
                   for v in supplement['exact_compiled_boundary'])
    need(actual == IDENTITIES, 'Foreign observer compiled boundary')
    need(tuple(v['scope'] for v in proof['exact_scopes']) == SCOPES,
         'Exact two observer leaves required')
    p = proof['source_proof']
    need((p['adapter_inputs'], p['adapter_output_inout_ref'],
          p['continuous_assignments']) == (41, 0, 43), 'Passive source boundary differs')
    need(set(proof['proposed_boundary']['metrics']) == set(METRICS) and
         proof['proposed_boundary']['assertion_coverage_excluded'] is False and
         supplement['checks_preservation']['assertion_coverage_excluded'] is False,
         'Assertions or non-code metric requested')
    need(supplement['parent_review_sha256'] == PROOF_SHA and
         proof['native_evidence']['prior_whole_qualified'] is False,
         'Source proof is not whole-observer native authority')


def corpus(ledger, old, bits):
    need(len(ledger) == 789 and len(set(ledger)) == 789 and ledger[:786] == old,
         'Exact788 ledger / qualified785 prefix differs')
    need(len(bits['tests']) == len(set(bits['tests'])) == 788,
         'Exact788 unique raw membership')
    need(bits['tests'] == ledger[1:], 'Raw test identities/order differ from exact input ledger')
    counts = {k: len(v) for k, v in bits['metrics'].items()}
    need(counts == dict(line=1892, cond=2023, branch=2155, fsm=92),
         'Full6162 raw metric shape required')


def completed(q, c, texts):
    need(q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         q['population'] == q['actual_selected_tests'] == c['population'] == 785 and
         q['config_seal'] == CONFIG_SHA, 'Completed785 report authority differs')
    for name in ('complete_approved_EL_bitmask_union', 'all_other_bits_protected',
                 'raw_reset_final_equal', 'applied_reloaded_equal'):
        need(q[name] is True, 'Prior native five-stage gate missing: ' + name)
    need(all(stable.semantic_seal(stable.semantic(t)) == c['expected_EL_semantic_sha256']
             for t in texts), 'Inherited EL changed')


def contract():
    a = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    pins = stable.merge(a['input_pins'], a['output_pins'],
                        {str(BASE / 'admission-manifest.json'): BASE_SHA})
    status = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    need(status['coverage_admitted'] is True and status['aggregate_passed'] == 788,
         'Formal788 admission required')
    c = life.read_bound(REPORT / 'config.json', CONFIG_SHA)
    q = life.read_bound(REPORT / 'qualification.json', QUAL_SHA)
    pins = stable.merge(pins, c['pins'], q['output_pins'],
                        {str(REPORT / 'config.json'): CONFIG_SHA,
                         str(REPORT / 'qualification.json'): QUAL_SHA})
    texts = []
    for n in ('combined.el', 'applied.el', 'reloaded.el'):
        p = REPORT / n
        need(life.digest(p) == pins[str(p)], 'Inherited EL source seal differs')
        texts.append(p.read_text(encoding='ascii'))
    completed(q, c, texts)
    ledger_path = BASE / 'combined-inputs.txt'
    need(life.digest(ledger_path) == pins[str(ledger_path)], '788 ledger seal differs')
    ledger = ledger_path.read_text().splitlines()
    bits = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    corpus(ledger, c['input_ledger'], bits)
    proof = life.read_bound(PROOF, PROOF_SHA)
    supplement = life.read_bound(SUPPLEMENT, SUPPLEMENT_SHA)
    boundary(proof, supplement)
    source_pins = {str(ROOT / p): h for p, h in proof['pins'].items()}
    pins = stable.merge(pins, source_pins, {str(PROOF): PROOF_SHA, str(SUPPLEMENT): SUPPLEMENT_SHA},
                        {str(p): life.digest(p) for p in
                         (Path(__file__).resolve(), HERE / 'test_report_population788_observers.py')})
    life.check(pins)
    return dict(schema=SCHEMA, status='HOST_CONTRACT_VERIFIED_NATIVE_INTEGRATION_PENDING',
                population=788, admission=dict(path=str(BASE / 'admission-manifest.json'), sha256=BASE_SHA),
                inherited_report=dict(path=str(REPORT), config_seal=CONFIG_SHA, qualification_seal=QUAL_SHA),
                input_ledger=ledger, input_pins=pins, inherited_EL_sha256=pins[str(REPORT / 'combined.el')],
                exact_observer_identities=[list(v) for v in IDENTITIES],
                code_metrics=list(METRICS), recursive=False, protected_metrics=['Assert', 'Group'],
                stages=['raw', 'applied', 'reset', 'reloaded', 'final'],
                native_requirements=[
                    'Capture actual nonrecursive code inventories before any new exclusion',
                    'Bind native headers to exact compiled module and per-metric checksums',
                    'Canonical native union subtracts existing18516 padding directions exactly once',
                    'All other scopes and loaded Assert/Group inventories unchanged',
                    'Reset/final empty EL; inherited EL exact; reload full identity/attribute multiset equal',
                    'Recalculate rooted summaries; selected tests exact788',
                    'Recheck inherited constant-mask suffixes786/787/788 before runtime approval'],
                native_qualified=False, launch_ready=False, EDA_started=False,
                official_percentage=None)


def prepare_plan(out):
    need(not out.exists(), 'Fresh host contract output required')
    c = contract()
    out.mkdir(parents=True)
    life.save(out / 'plan.json', c)
    print(json.dumps(dict(status=c['status'], plan=str(out / 'plan.json'),
                          seal=life.digest(out / 'plan.json'), launch_ready=False)))


TCL = HERE / 'report_population788_observers.tcl'
NATIVE_TCL = HERE / 'capture_cvxif_passive_two_scope770_v2.tcl'
NATIVE_PINS = {
    str(HERE / 'capture_cvxif_passive_two_scope770.tcl'): '70aeac1fd5a3f5dd3300f613c2bf0253f80a27fa40251aaef68fee1d3e2f0546',
    str(NATIVE_TCL): '7562ff42582a6adab356f8eecbacd41aa1abecf7ea957137c35539b838ab21f3'}
CSR787 = life.OUT / 'csr-satp-sepc-offline-admitted787-parent-20261008-01'
CSR787_SHA = 'aaef43fef3b8da3a1e854e4907b0823a3488270ddb8b7ae5af0c21be5cb8d5fc'


def status787(value):
    need(value['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and value['coverage_admitted'] is True and
         value['aggregate_passed'] == 787 and value['baseline'] == 786 and
         value['full_OR_instances'] == 6162 and 'full_OR_metric_instances' not in value,
         'Exact historical787 status schema')
    return dict(value, full_OR_metric_instances=value['full_OR_instances'])


class PopulationReader(stable.Reader):
    def read(self, path, sha, parse=False):
        value = super().read(path, sha, parse)
        if Path(path) == CSR787/'status.json' and parse:
            manifest = super().read(CSR787/'admission-manifest.json', CSR787_SHA, True)
            need(sha == manifest['output_pins'][str(path)], '787 status authority differs')
            return status787(value)
        return value


def suffix_chain(chain):
    rows = [r for r in chain if r['population'] > 783]
    need([r['population'] for r in rows] == list(range(784, 789)), 'Exact784..788 lineage')
    need(rows[0]['manifest'] == str(prior.FORMAL784) and rows[0]['seal'] == prior.FORMAL784_SHA,
         'Exact parent784 ancestor')
    need(rows[-1]['manifest'] == str(BASE / 'admission-manifest.json') and
         rows[-1]['seal'] == BASE_SHA, 'Exact formal788 endpoint')
    return rows


def approved():
    host = contract()
    reader = PopulationReader()
    source, pins, _, bits, chain, activity = prior.population.approved(
        reader, BASE / 'admission-manifest.json', BASE_SHA)
    old = reader.read(REPORT / 'config.json', CONFIG_SHA, True)
    pins = stable.merge(pins, host['input_pins'])
    corpus(source['input_ledger'], old['input_ledger'], bits)
    rr = reader.read(prior.LOCAL / 'config.json', prior.LOCAL_SHA, True)
    check_suffix = FunctionType(prior.suffix_zero.__code__,
                               dict(prior.suffix_zero.__globals__, suffix_chain=suffix_chain))
    activity = dict(activity, inherited_constants=check_suffix(reader, pins, chain, rr))
    review = reader.read(observer.REVIEW, observer.REVIEW_SHA, True)
    compiled = review['compiled_scopes']
    need(len(compiled) == 2 and len({i['scope'] for i in compiled}) == 2 and
         {i['scope']: str(i['design_module_checksum']) for i in compiled} ==
         {s: m for s, m, _ in IDENTITIES}, 'Bound native typed inventories differ')
    compiled = sorted(compiled, key=lambda i: SCOPES.index(i['scope']))
    checksums = {s: [] for s in SCOPES}
    per_metric = {s: {} for s in SCOPES}
    capacities = {s: {} for s in SCOPES}
    shapes = Path(source['input_ledger'][0]) / 'snps/coverage/db/shape'
    design_path = shapes.parent/'design/verilog.design.xml'
    raw = reader.read(design_path, pins[str(design_path)])
    design = ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
    modules = {}
    for item in compiled:
        candidates = [n for n in design.iter('srcdef') if n.get('name') == item['module'] and
                      n.get('chksum') == str(item['design_module_checksum'])]
        need(len(candidates) == 1, 'Compiled observer module identity ambiguous')
        modules[item['scope']] = candidates[0]
    for metric in ('line', 'cond', 'branch', 'fsm', 'tgl'):
        p = shapes / (metric + '.verilog.shape.xml')
        need(str(p) in pins, 'Unbound compiled metric shape')
        raw = reader.read(p, pins[str(p)])
        tree = ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        for item in compiled:
            found = []
            candidates = [n for n in tree if
                          (n.get('name') == item['module'] if metric in ('tgl','fsm') else
                           n.get('id') == modules[item['scope']].get('id'))]
            if metric == 'fsm':
                file_id = next(i['source_file_id'] for i in life.read_bound(PROOF, PROOF_SHA)['exact_scopes']
                               if i['scope'] == item['scope'])
                candidates = [n for n in tree if n.get('name') == item['module'] or n.get('file') == file_id]
            if metric != 'tgl':
                row = bits['metrics'][metric].get(item['scope'])
                width = row['width'] if row is not None else 0
                info_path = shapes/(metric+'.verilog.info.xml')
                info_matches = []
                if info_path.exists():
                    need(str(info_path) in pins, 'Unbound metric instance info')
                    info_raw = reader.read(info_path,pins[str(info_path)])
                    info = ET.fromstring(gzip.decompress(info_raw) if info_raw[:2] == b'\x1f\x8b' else info_raw)
                    info_matches = [n for n in info.iter('instance_data') if n.get('name') == item['scope']]
                if width:
                    candidates = [n for n in candidates if n.get('chksum') == str(row['checksum'])]
                    need(len(candidates) == 1, 'Exact nonToggle checksum/definition binding')
                    need(len(info_matches) == 1 and info_matches[0].get('chksum') == str(row['checksum']),
                         'Exact per-instance code metric ownership')
                else:
                    need(not candidates and not info_matches, 'Compiled zero scope has a metric definition/instance')
                capacities[item['scope']][metric] = width
            else:
                need(len(candidates) == 1, 'Exactly one typed Toggle definition')
                capacities[item['scope']][metric] = len(item['typed_inventory'])
            for n in candidates:
                if n.get('chksum'):
                    checksums[item['scope']].append(n.get('chksum'))
                    found.append(n.get('chksum'))
            per_metric[item['scope']][metric] = sorted(set(found))
    need(all(checksums.values()), 'No compiled metric identities')
    ob = dict(compiled_scopes=compiled, metric_checksums={s: sorted(set(v)) for s, v in checksums.items()},
              per_metric_checksums=per_metric, capacities=capacities)
    deps = {str(p): life.digest(p) for p in (TCL, Path(__file__).resolve(),
        HERE / 'test_report_population788_observers.py', Path(observer.__file__).resolve(),
        HERE / 'capture_cvxif_passive_two_scope770.tcl', stable.TCL)}
    pins = stable.merge(pins, deps, NATIVE_PINS, {str(observer.REVIEW): observer.REVIEW_SHA})
    reader.finish(pins)
    stable.tools.revalidate(source['tool_identity'])
    return source, pins, (REPORT / 'combined.el').read_text(), chain, activity, ob


def selection(roots, ob):
    quote = stable.tcl_atom
    return stable.selection(roots) + '\n'.join([
        'set ::observers788_compact_library ' + quote(stable.TCL),
        'set ::observers788_native_library ' + quote(NATIVE_TCL),
        'set ::cv_scopes [list ' + ' '.join(map(quote, SCOPES)) + ']',
        'set ::cv_root ' + quote('ara_tb.dut.i_ara_soc.i_system'),
        'set ::cv_annotation ' + quote(observer.ANNOTATION),
        'array set ::observers788_capacity {' + ' '.join(
            quote(s+','+label)+' '+str(ob['capacities'][s][metric]) for s in SCOPES
            for label, metric in zip(METRICS, ('line','cond','branch','fsm','tgl'))) + '}', ''])


def prepare(out, unit):
    need(out.parent == life.OUT and not out.exists(), 'Fresh native report output required')
    need(re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', unit), 'Exact owning service required')
    source, pins, text, chain, activity, ob = approved()
    c = dict(schema=SCHEMA, population=788, output=str(out), successor_entry=str(Path(__file__).resolve()),
             admission=dict(path=str(BASE / 'admission-manifest.json'), sha256=BASE_SHA),
             input_ledger=source['input_ledger'], expected_selected=source['expected_selected'],
             hierarchy_roots=source['hierarchy_roots'], tool_identity=source['tool_identity'],
             pins=pins, genealogy=chain, suffix_activity=activity, observer=ob,
             expected_EL_semantic_sha256=stable.semantic_seal(stable.semantic(text)),
             timeout_seconds=3600, owner_uid=os.getuid(), owning_service_unit=unit,
             expected_cgroup='/user.slice/user-%d.slice/user@%d.service/app.slice/%s' %
                 (os.getuid(), os.getuid(), unit), full_OR_metric_instances=6162,
             official_denominator_verified=False, observer_native_pending=True)
    out.mkdir()
    for name, value in [('combined.el', text), ('inputs.txt', '\n'.join(c['input_ledger'])+'\n'),
                        ('root-selection.tcl', selection(c['hierarchy_roots'], ob))]:
        (out / name).write_text(value)
        pins[str(out / name)] = life.digest(out / name)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), EDA_started=False)))


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    source, pins, text, chain, activity, ob = approved()
    need(c['schema'] == SCHEMA and c['population'] == 788 and c['output'] == str(out) and
         c['successor_entry'] == str(Path(__file__).resolve()) and
         c['admission'] == dict(path=str(BASE / 'admission-manifest.json'), sha256=BASE_SHA),
         'Exact consolidated consumer identity')
    for key, expected in [('input_ledger', source['input_ledger']), ('expected_selected', source['expected_selected']),
                          ('hierarchy_roots', source['hierarchy_roots']), ('tool_identity', source['tool_identity']),
                          ('genealogy', chain), ('suffix_activity', activity), ('observer', ob)]:
        need(c[key] == expected, 'Runtime contract drift: ' + key)
    need(c['timeout_seconds'] == 3600 and type(c['owner_uid']) is int and c['owner_uid'] == os.getuid() and
         re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', c['owning_service_unit']) and
         c['expected_cgroup'] == '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' %
         (os.getuid(), os.getuid(), c['owning_service_unit']), 'Managed lifecycle drift')
    need(c['full_OR_metric_instances'] == 6162 and c['official_denominator_verified'] is False and
         c['observer_native_pending'] is True, 'Native scope / claim expansion')
    need(all(c['pins'].get(p) == h for p, h in pins.items()), 'Omitted sealed input')
    for name, expected in [('combined.el', text), ('inputs.txt', '\n'.join(c['input_ledger'])+'\n'),
                           ('root-selection.tcl', selection(c['hierarchy_roots'], ob))]:
        need((out / name).read_text() == expected, 'Generated native input drift')
    need(c['expected_EL_semantic_sha256'] == stable.semantic_seal(stable.semantic(text)), 'Inherited EL seal')
    for name in ('combined.el','inputs.txt','root-selection.tcl'):
        need(c['pins'].get(str(out/name)) == life.digest(out/name), 'Missing generated file pin')
    life.check(c['pins'])
    need(life.digest(out / 'config.json') == seal, 'Consumer changed during check')
    return c


def native_gate(text, inherited, ob):
    actual, old = stable.semantic(text), stable.semantic(inherited)
    for values, before in zip(actual, old):
        outside = (lambda v: {k: x for k, x in v.items() if k[0] not in SCOPES}) if isinstance(values, dict) else (
            lambda v: {r for r in v if r[0] not in SCOPES})
        need(outside(values) == outside(before), 'Nonobserver native mask/identity changed')
    # Retain complete headers and annotation during scoped extraction. Unknown
    # native scope-only serialization fails the existing code-only parser.
    blocks, current, scope = [], [], None
    for line in text.splitlines():
        if line.startswith('CHECKSUM:'):
            if scope in SCOPES: blocks.extend(current)
            current, scope = [line], None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip(); current.append(line)
        elif not line.startswith('ANNOTATION:'):
            current.append(line)
    if scope in SCOPES: blocks.extend(current)
    records = observer.parse_el('\n'.join(blocks), ob)
    directive_metric = dict(Block='line', Line='line', Condition='cond', Branch='branch',
                            Fsm='fsm', FSM='fsm', Toggle='tgl')
    for scope, checks, line in records:
        metric = directive_metric.get(line.split()[0])
        need(metric is not None and checks[1] in ob['per_metric_checksums'][scope][metric],
             'Native directive checksum belongs to another metric')
    need(not any(r[0] in SCOPES and r[3].startswith('Toggle ') for r in actual[0]),
         'Unresolved native Toggle object/declaration')
    padding_covered(inherited, ob)
    actual_toggle = {k: v for k, v in actual[1].items() if k[0] in SCOPES}
    old_toggle = {k: v for k, v in old[1].items() if k[0] in SCOPES}
    expected = {}
    for scope, item in ((i['scope'], i) for i in ob['compiled_scopes']):
        fields = {i[1]: i for i in item['typed_inventory']}
        whole = [r for r in records if r[0] == scope and r[2] == 'Toggle']
        need(len(whole) <= 1, 'Duplicate whole Toggle directive')
        if whole:
            for name, row in fields.items():
                node, _, _, typecode, _, left, right = row
                need(node in ('node','vectornode') and typecode == '1', 'Unbound whole Toggle typed field')
                lo, hi = (0,0) if node == 'node' else sorted((int(left),int(right)))
                for direction in ('0to1','1to0'):
                    expected[(scope,name,direction)] = ((1 << (hi-lo+1))-1) << lo
        for key, mask in actual_toggle.items():
            if key[0] != scope: continue
            _, checks, name, kind, decl, prefix, direction = key
            need(name in fields and kind == 'logic' and prefix == () and
                 direction in ('0to1','1to0'), 'Unknown native typed observer object/kind')
            node, _, _, typecode, _, left, right = fields[name]
            need(typecode == '1' and node in ('node','vectornode'), 'Unbound native logic kind')
            lo, hi = (0,0) if node == 'node' else sorted((int(left),int(right)))
            declaration = name if node == 'node' else name+'['+str(left)+':'+str(right)+']'
            full_mask = ((1 << (hi-lo+1))-1) << lo
            need(decl == declaration and mask > 0 and mask & ~full_mask == 0,
                 'Native declaration/range outside the compiled object')
            if whole:
                need(old_toggle.get(key) == mask,
                     'Only exact inherited partial records may coexist with whole Toggle')
            else:
                need(mask == full_mask, 'Missing full compiled object directions')
            need(str(checks).split()[-1] in ob['per_metric_checksums'][scope]['tgl'], 'Toggle checksum')
            expected[(scope,name,direction)] = expected.get((scope,name,direction),0) | mask
        need({(s,n,d) for s,n,d in expected if s == scope} ==
             {(scope,n,d) for n in fields for d in ('0to1','1to0')}, 'Missing full typed observer directions')
    for key, mask in old_toggle.items():
        need(expected.get((key[0],key[2],key[-1]),0) & mask == mask,
             'Applied observer directions deleted inherited padding')
    return records


def padding_covered(inherited, ob):
    """All target typed objects are excluded in both directions by the audited
    code-metric operation. Establish the old partial masks are a subset of that
    physical ownership, not lost records or additional excluded capacity.
    """
    _, masks = stable.semantic(inherited)
    covered = 0
    for key, mask in masks.items():
        scope, checks, name, kind, declaration, prefix, direction = key
        if scope not in SCOPES: continue
        item = next(v for v in ob['compiled_scopes'] if v['scope'] == scope)
        candidates = [v for v in item['typed_inventory'] if v[1] == name]
        need(len(candidates) == 1 and prefix == () and direction in ('0to1', '1to0'),
             'Unbound inherited observer physical object')
        node, _, _, _, _, left, right = candidates[0]
        need(node in ('node', 'vectornode'), 'No array ownership inference')
        lo, hi = (0, 0) if node == 'node' else sorted((int(left), int(right)))
        full = ((1 << (hi-lo+1))-1) << lo
        need(mask > 0 and mask & ~full == 0 and str(checks).split()[-1] in
             ob['per_metric_checksums'][scope]['tgl'], 'Inherited mask outside compiled typed object')
        covered += bin(mask).count('1')
    need(covered == 18516, 'Exact inherited18516 observer padding physical directions')
    return covered


def observer_audit(out, c):
    stages = observer.STAGES
    availability = [json.loads((out / (s + '_availability.json')).read_text()) for s in stages]
    need(all(a == availability[0] for a in availability) and
         set(availability[0]) == set(observer.METRICS + observer.PROTECTED) and
         all(type(v) is bool for v in availability[0].values()) and
         all(availability[0][m] for m in observer.METRICS), 'Actual metric availability differs')
    for metric in observer.METRICS + observer.PROTECTED:
        if not availability[0][metric]: continue
        scopes = SCOPES if metric in observer.METRICS else (observer.ROOT,)
        for i, scope in enumerate(scopes):
            capacity = c['observer']['capacities'][scope][dict(zip(METRICS,('line','cond','branch','fsm','tgl')))[metric]] if metric in METRICS else 1
            if capacity == 0:
                for stage in stages:
                    path = out/('%s_%s_%d.skipped.json' % (stage,metric,i))
                    need(json.loads(path.read_text()) == dict(status='SKIPPED_COMPILED_ZERO',
                         scope=scope, metric=metric, capacity=0), 'Exact compiled absence receipt')
                    need(not (out/('%s_%s_%d.tsv' % (stage,metric,i))).exists() and
                         not (out/('%s_%s_%d.columns' % (stage,metric,i))).exists(), 'Zero scope has invented snapshot')
                continue
            rows = {s: observer.rows((out / ('%s_%s_%d.tsv' % (s, metric, i))).read_text()) for s in stages}
            headers = [(out / ('%s_%s_%d.columns' % (s, metric, i))).read_text() for s in stages]
            need(headers[0].strip() and all(h == headers[0] for h in headers), 'Native columns changed')
            before = rows['before']
            need(before, 'Actual nonzero compiled inventory missing')
            if metric in observer.PROTECTED: need(before, 'Loaded protected inventory empty')
            if metric == 'Toggle':
                item = next(v for v in c['observer']['compiled_scopes'] if v['scope'] == scope)
                labels = {observer.local.normalized_label(n if k == 'node' else n+'['+l+':'+r+']')
                          for k, n, _, _, _, l, r in item['typed_inventory']}
                actual = [observer.local.normalized_label(v[2]) for v in before]
                need(len(actual) == len(set(actual)) and labels == set(actual), 'Exact typed observer inventory')
            for s, actual in rows.items():
                need(set(actual) == set(before), 'Complete native identities changed')
                if metric in observer.PROTECTED or s in ('before', 'reset', 'final'):
                    need(actual == before, 'Protected attributes/reset changed')
                else: need(all(v[0] == '1' for v in actual.values()), 'Observer code not excluded')
            need(rows['selected'] == rows['reloaded'], 'Full native attributes reload differs')


def verify(out, seal):
    c = check(out, seal)
    terminal = json.loads((out/'terminal.json').read_bytes())
    stable.terminal_gate(terminal, c)
    need(terminal['config_seal'] == seal, 'Actual executed configuration seal')
    gui = out / 'DVEfiles/dve_gui.log'
    for path in (out/'launcher.log', gui): stable.diagnostics(path.read_text())
    log = gui.read_text().splitlines()
    need(log.count('OBSERVERS788_NATIVE_FIVE_PHASE_DONE') == 1 and
         log.count('COMPACT777_FIVE_PHASE_DONE') == 1 and
         log.count('DVE_COVERAGE_EXPORT_DONE') == 1, 'Native five-stage protocol incomplete')
    observer_audit(out, c)
    inherited = (out / 'combined.el').read_text()
    applied = (out / 'applied.el').read_text()
    reloaded = (out / 'reloaded.el').read_text()
    need(native_gate(applied, inherited, c['observer']) == native_gate(reloaded, inherited, c['observer']) and
         stable.semantic(applied) == stable.semantic(reloaded), 'Exact complete native semantic reload')
    stable.membership(c['input_ledger'], (out/'selected_tests.txt').read_text().splitlines(), 788)
    paths = [out/n for n in ('terminal.json', 'execution.json', 'selected_tests.txt', 'raw.csv')]
    reports = {}
    for stage in stable.STAGES:
        ep, sp = out/stable.EL_FILES[stage], out/('modules_'+stage+'.csv')
        if stage in ('raw', 'reset', 'final'): need(ep.read_bytes() == b'', 'Global empty reset')
        else: native_gate(ep.read_text(encoding='ascii'), inherited, c['observer'])
        reports[stage] = stable.summary(sp.read_bytes(), stage, c['hierarchy_roots'])
        paths.extend((ep, sp))
    stable.summaries_gate(reports)
    stable.raw_summary_gate((out/'raw.csv').read_bytes(), c['hierarchy_roots'], reports['raw'])
    need((out/'cleanup-empty.el').read_bytes() == b'', 'Final cleanup not empty')
    paths.append(out/'cleanup-empty.el')
    availability = json.loads((out/'before_availability.json').read_text())
    for stage in observer.STAGES:
        paths.append(out/(stage+'_availability.json'))
        for metric in observer.METRICS + observer.PROTECTED:
            if not availability[metric]: continue
            for i in range(2 if metric in observer.METRICS else 1):
                cap = c['observer']['capacities'][SCOPES[i]][dict(zip(METRICS,('line','cond','branch','fsm','tgl')))[metric]] if metric in METRICS else 1
                extensions = ('skipped.json',) if cap == 0 else ('tsv','columns')
                paths.extend(out/('%s_%s_%d.%s' % (stage, metric, i, ext)) for ext in extensions)
    snapshots = out/'terminal-evidence'; snapshots.mkdir(exist_ok=True)
    for original in (out/'launcher.log', gui):
        dest = snapshots/original.name
        if dest.exists(): need(dest.read_bytes() == original.read_bytes(), 'Terminal evidence changed')
        else: dest.write_bytes(original.read_bytes())
        paths.append(dest)
    result = dict(status='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED', population=788,
        config_seal=seal, admission_seal=BASE_SHA, actual_selected_tests=788,
        source_design_native_pins=c['pins'], output_pins={str(p):life.digest(p) for p in paths},
        complete_approved_EL_bitmask_union=True, all_other_bits_protected=True,
        raw_reset_final_equal=True, applied_reloaded_equal=True, module_reports=reports,
        suffix_activity=c['suffix_activity'], raw_hierarchy_vs_rooted_six_metrics_equal=True,
        supported_roots_all_six_metrics_present=True, official_denominator_verified=False,
        historical_PASS_only_no_new_RTL_signoff=True, observer_exact_scopes=list(SCOPES),
        observer_metrics=list(METRICS), observer_recursive=False, observer_code_native_reload_exact=True,
        observer_Assert_Group_full_attributes_preserved=True, inherited_observer_padding_directions_covered=18516,
        observer_source_review=dict(path=str(PROOF), sha256=PROOF_SHA),
        observer_no_drive_supplement=dict(path=str(SUPPLEMENT), sha256=SUPPLEMENT_SHA))
    life.check(result['output_pins'])
    target = out/'qualification.json'
    if target.exists(): need(json.loads(target.read_text()) == result, 'Existing full qualification differs')
    else: life.save(target, result)
    receipt = dict(status='FORMAL788_PASSIVE_TWO_LEAF_NATIVE_REPORT_VERIFIED',
                   population=788, config_seal=seal,
                   global_qualification_sha256=life.digest(out / 'qualification.json'),
                   input_pins=c['pins'], output_pins=result['output_pins'],
                   exact_scopes=list(SCOPES), code_metrics=list(METRICS), recursive=False,
                   loaded_Assert_Group_complete_attributes_preserved=True,
                   all_nonobserver_native_masks_and_records_preserved=True,
                   semantic_reload=True, reset_final_empty=True,
                   runtime_UVM_assertions_not_disabled=True)
    life.check(receipt['output_pins'])
    path = out / 'observer-qualification.json'
    if path.exists(): need(json.loads(path.read_text()) == receipt, 'Existing observer qualification differs')
    else: life.save(path, receipt)
    return result


def run(out, seal, reviewed):
    return FunctionType(stable.run.__code__, dict(stable.run.__globals__,
                        check=check, verify=verify, TCL=TCL))(out, seal, reviewed)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'verify', 'run-reviewed', 'prepare-plan'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--service-unit')
    p.add_argument('--parent-reviewed-seal')
    args = p.parse_args()
    if args.mode == 'prepare':
        need(args.seal is None, 'Prepare does not accept prior seal')
        prepare(args.output.resolve(), args.service_unit)
    elif args.mode == 'prepare-plan':
        prepare_plan(args.output.resolve())
    elif args.mode == 'check':
        need(args.seal, 'Reviewed plan seal required')
        check(args.output.resolve(), args.seal)
        print('CONSOLIDATED788_CHECK_PASS_NO_EDA')
    elif args.mode == 'verify': verify(args.output.resolve(), args.seal)
    else: run(args.output.resolve(), args.seal, args.parent_reviewed_seal)
