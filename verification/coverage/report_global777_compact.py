"""Fresh777 global report. Reuse qualified locals, never their GUI inventory loops.

Preparation/checks are offline. Only explicit run-reviewed launches one DVE.
Complete physical EL membership, not vector aggregate flags, protects low bits.
Native percentages are reported; official exclusion denominator is not inferred.
"""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

import prepare_global777_masku1 as inherited
import cvxif_padding_native776_v2 as cvx
import close_cvxif_padding776_offline as closure
import branch720_next_report_contract as inventory
import dve_tool_identity as tools
from report_scope_ancestors import report_ancestors

life, need = inherited.life, inherited.need
HERE, OUT = Path(__file__).resolve().parent, life.OUT
TCL = Path(__file__).with_suffix('.tcl')
EXPORT = HERE / 'export_dve_coverage.tcl'
ROOT_HELPER = HERE / 'apply_points740_v4.tcl'
SCHEMA = 'FORMAL777_COMPACT_GLOBAL_FIVE_PHASE_V1'
REFERENCE = OUT / 'global777-masku-parent1-prepared-agent-20261007-01'
REFERENCE_SHA = 'c5f9be05b6d047bc78eed146e38239e135d88cba89dd5c554f682007057c7baf'
REFERENCE_RECEIPT_SHA = '24164eef074331e9d5117b2b7daf1780f585c1e8b56db4b93dd69246b96bf66f'
CLOSURE = OUT / 'cvxif-padding776-offline-closure-parent-20261007-01.json'
CLOSURE_SHA = '232dbc6deabf69fc849cfd4d33a032daca271f7c8a35688db146475158877190'
PROOF = OUT / 'cvxif-padding776-static-prepared-agent-20261007-01.json'
PROOF_SHA = 'e37df8f2750fdc90be822307856aefbadfe92b394909e49651b211551ac7edb2'
STAGES = ('raw', 'applied', 'reset', 'reloaded', 'final')
EL_FILES = dict(raw='initial-empty.el', applied='applied.el', reset='reset-empty.el',
                reloaded='reloaded.el', final='final-empty.el')
METRICS = ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')
SUMMARY_HEADER = ['Stage', 'Scope', 'Token', 'Handle', 'GUIPath', 'Name', *METRICS]
SUPPORTED_ROOTS = frozenset(('ara_tb', 'ara_tb.dut.i_ara_soc.i_system'))


def merge(*maps):
    result = {}
    for mapping in maps:
        for path, sha in mapping.items():
            need(path not in result or result[path] == sha, 'Conflicting exact pin: ' + path)
            result[path] = sha
    return result


class Reader:
    """One evaluation's content capture. No cache crosses pre/post boundaries."""
    def __init__(self):
        self.pins, self.jsons = {}, {}

    def read(self, path, sha, parse=False):
        path = str(Path(path))
        need(Path(path).is_absolute() and re.fullmatch('[0-9a-f]{64}', sha), 'Absolute exact pin')
        need(path not in self.pins or self.pins[path] == sha, 'Conflicting read pin')
        if parse and path in self.jsons:
            return self.jsons[path]
        raw = Path(path).read_bytes()
        need(hashlib.sha256(raw).hexdigest() == sha, 'Input drift: ' + path)
        self.pins[path] = sha
        if parse:
            def pairs(items):
                value = {}
                for k, v in items:
                    need(k not in value, 'Duplicate JSON key'); value[k] = v
                return value
            self.jsons[path] = json.loads(raw, object_pairs_hook=pairs)
            return self.jsons[path]
        return raw

    def finish(self, pins):
        # Large inputs are streamed; no multi-GB all-file byte cache.
        for path, sha in pins.items():
            need(path not in self.pins or self.pins[path] == sha, 'Conflicting captured pin')
            if path not in self.pins:
                need(life.digest(Path(path)) == sha, 'Input drift: ' + path)
                self.pins[path] = sha


def membership(ledger, selected, count=777):
    need(len(ledger) == len(set(ledger)) == count + 1, 'Unique design plus exact population')
    need(len(selected) == len(set(selected)) == count, 'Unique actual selected tests')
    actual = [str(Path(db).with_suffix('') / p.name) for db in ledger
              for p in sorted((Path(db) / 'snps/coverage/db/testdata').glob('*')) if p.is_dir()]
    need(selected == actual, 'Exact ordered selected tests; no missing/extra/relabel')


def chain(reader, delta, old):
    pins = merge(old['pins'], delta['pins'],
                 {str(inherited.predecessor.OLD / 'config.json'): inherited.predecessor.OLD_SHA})
    previous_dir, previous_sha = inherited.prior.BASE, inherited.prior.BASE_SHA
    previous = reader.read(previous_dir / 'combined-bits.json', pins[str(previous_dir / 'combined-bits.json')], True)
    ledger = old['input_ledger']
    for directory, sha, count in [(inherited.predecessor.BASE, inherited.predecessor.BASE_SHA, 776),
                                  (inherited.BASE, inherited.BASE_SHA, 777)]:
        manifest = reader.read(directory / 'admission-manifest.json', sha, True)
        need(manifest['coverage_admitted'] is True and manifest['baseline'] == str(previous_dir)
             and manifest['baseline_seal'] == previous_sha, 'Explicit775->776->777 sealed genealogy')
        pins = merge(pins, manifest['input_pins'], manifest['output_pins'],
                     {str(directory / 'admission-manifest.json'): sha})
        current = reader.read(directory / 'combined-bits.json', pins[str(directory / 'combined-bits.json')], True)
        single = reader.read(directory / 'single-bits.json', pins[str(directory / 'single-bits.json')], True)
        new_ledger = reader.read(directory / 'combined-inputs.txt', pins[str(directory / 'combined-inputs.txt')]).decode().splitlines()
        inherited.chain_gate(previous, current, single, count, ledger, new_ledger)
        status = reader.read(directory / 'status.json', pins[str(directory / 'status.json')], True)
        need(status['aggregate_passed'] == count and status['coverage_admitted'] is True and
             status['full_OR_metric_instances'] == 6162, 'Historical PASS-only complete6162 OR')
        previous_dir, previous_sha, previous, ledger = directory, sha, current, new_ledger
    need(ledger == delta['input_ledger'], 'Reference777 population changed')
    return pins, ledger, previous


def semantic(text):
    """Native dimensions stay dimensions. Never flatten MDA or strip array indices.

    Duplicate identical legacy directives are idempotent, just as native import.
    Whole observers and FSM/Branch context retain exact sealed identity. Toggle
    selectors normalize to per-prefix physical bit masks, including directions.
    """
    old, branches = inventory.native_inventory(text.encode('ascii'))
    other, masks = set(), {}
    pattern = re.compile(r'^Toggle(?: (0to1|1to0))? (\S+)(?: ((?:\[\d+(?::\d+)?\])+))?(?: "(logic|reg|wire|net) ([^"\n]+)")?$')
    for (scope, checks, machine, line) in old:
        if not line.startswith('Toggle '):
            other.add((scope, checks, machine, line)); continue
        m = pattern.fullmatch(line)
        need(m is not None, 'Unknown Toggle grammar')
        direction, name, selectors, kind, declaration = m.groups()
        extents = re.findall(r'\[(\d+)(?::(\d+))?\]', selectors or '')
        if not selectors:
            suffix = declaration[len(name):] if declaration and declaration.startswith(name) else None
            prefix = declaration[:-len(name)] if declaration and declaration.endswith(name) else None
            bounds = suffix if suffix is not None else prefix
            if bounds and re.fullmatch(r'(?:\[\d+(?::\d+)?\])+', bounds):
                extents = re.findall(r'\[(\d+)(?::(\d+))?\]', bounds)
            elif declaration == name:
                # A source-bound native scalar (including a named array leaf)
                # has one bit; keep the complete name, never strip [0].
                extents = [('0', None)]
            else:
                # Unknown whole-array grammar is kept opaque, never guessed.
                other.add((scope, checks, machine, line)); continue
        ranges = []
        for hi, lo in extents:
            hi, lo = int(hi), int(lo if lo else hi)
            hi, lo = max(hi, lo), min(hi, lo)
            need(0 <= lo <= hi < 1000000, 'Native range bounds')
            ranges.append((lo, hi))
        need(ranges and len(ranges) <= 4, 'Explicit native dimensions')
        prefixes = itertools.product(*(range(a, b+1) for a, b in ranges[:-1]))
        lo, hi = ranges[-1]; mask = ((1 << (hi-lo+1))-1) << lo
        for prefix in prefixes:
            for d in (direction,) if direction else ('0to1', '1to0'):
                key = (scope, checks, name, kind or '', declaration or '', tuple(prefix), d)
                masks[key] = masks.get(key, 0) | mask
    other.update((scope, checks, '', line) for scope, checks, line in branches)
    return other, masks


def semantic_seal(value):
    other, masks = value
    encoded = [sorted(other), [(list(k), hex(v)) for k, v in sorted(masks.items())]]
    return hashlib.sha256(json.dumps(encoded, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def el_gate(blob, stage, expected):
    need(stage in STAGES, 'Unknown five-phase stage')
    if stage in ('raw', 'reset', 'final'):
        need(blob == b'', 'Global exclusions not empty'); return
    need(semantic_seal(semantic(blob.decode('ascii'))) == expected, 'Complete approved physical EL union differs')


def roots_gate(roots):
    need(len(roots) == 72 and len({r['scope'] for r in roots}) == 72 and
         roots[0] == dict(scope='ara_tb.dut.i_ara_soc.i_system', name='i_system'), 'Exact real72 module roots')
    need(all(set(r) == {'scope', 'name'} and r['scope'].startswith(roots[0]['scope']) and r['name'] for r in roots),
         'Unknown hierarchy identity')


def percent(value, allow_na=True):
    need(type(value) is str, 'Missing/nontext native percentage')
    if value == 'NA':
        need(allow_na, 'Supported top-level metric cannot be NA')
        return
    need(re.fullmatch(r'(?:\d+(?:\.\d+)?)(?:%)?', value) and 0 <= float(value.rstrip('%')) <= 100,
         'Invalid native percentage')


def summary(blob, stage, roots):
    reader = csv.DictReader(io.StringIO(blob.decode('utf-8')))
    need(reader.fieldnames == SUMMARY_HEADER, 'Complete rooted CSV schema')
    rows = list(reader); expected = [dict(scope='ara_tb', name='ara_tb'), *roots]
    need(len(rows) == len(expected), 'Missing/extra summary roots')
    result = {}
    for row, wanted in zip(rows, expected):
        need(set(row) == set(SUMMARY_HEADER) and all(v is not None for v in row.values()), 'Incomplete CSV fields')
        need(row['Stage'] == stage and row['Scope'] == row['Token'] == wanted['scope'] and
             row['GUIPath'] == row['Name'] == wanted['name'] and row['Handle'].isdigit(), 'Root token/path/name binding')
        for metric in METRICS: percent(row[metric], wanted['scope'] not in SUPPORTED_ROOTS)
        result[row['Scope']] = {m: row[m] for m in METRICS}
    return result


def summaries_gate(reports):
    need(set(reports) == set(STAGES) and reports['raw'] == reports['reset'] == reports['final'] and
         reports['applied'] == reports['reloaded'], 'Raw/reset/final or apply/reload metrics differ')


def raw_summary_gate(blob, roots, modules_raw):
    reader = csv.DictReader(io.StringIO(blob.decode('utf-8')))
    fields = reader.fieldnames
    rows = list(reader)
    need(fields is not None and len(fields) == len(set(fields)) and len(rows) == 2989 and
         {'Name', 'Depth', *METRICS} <= set(fields), 'Complete real raw hierarchy2989')
    expected = [dict(scope='ara_tb', name='ara_tb'), *roots]
    targets = {r['scope'] for r in expected}
    # Validate depths, collapsed generate names, uniqueness and target presence
    # using the shared report-tree contract before consuming its Depth stack.
    report_ancestors(rows, targets)
    stack, bound = [], {}
    for row in rows:
        need(set(row) == set(fields) and all(v is not None for v in row.values()), 'Incomplete raw CSV fields')
        depth = int(row['Depth'])
        stack = stack[:depth] + [row['Name']]
        scope = '.'.join(stack)
        for metric in METRICS: percent(row[metric], scope not in SUPPORTED_ROOTS)
        if scope in targets:
            bound[scope] = row
    need(set(bound) == set(modules_raw) == targets, 'Raw/rooted scope membership differs')
    for root in expected:
        row = bound[root['scope']]
        need(row['Name'] == root['name'] and {m: row[m] for m in METRICS} == modules_raw[root['scope']],
             'Full raw hierarchy vs rooted six-metric mismatch: ' + root['scope'])


def approved(reader):
    delta = reader.read(REFERENCE / 'config.json', REFERENCE_SHA, True)
    receipt = reader.read(REFERENCE / 'prepare-receipt.json', REFERENCE_RECEIPT_SHA, True)
    need(receipt['config_seal'] == REFERENCE_SHA and receipt['status'] == 'GLOBAL777_MASKU1_PREPARED_CHECK_PASS_NO_EDA'
         and receipt['EDA_launched'] is False, 'Sealed host preparation is not a completed global report')
    need(delta['schema'] == inherited.SCHEMA and delta['population'] == 777 and
         delta['reused775_config'] == str(inherited.predecessor.OLD / 'config.json') and
         delta['reused775_config_sha256'] == inherited.predecessor.OLD_SHA, 'Exact reference family')
    old = reader.read(delta['reused775_config'], delta['reused775_config_sha256'], True)
    pins, ledger, bitmap = chain(reader, delta, old)
    source = dict(old, **delta)
    source['pins'] = pins
    membership(ledger, delta['expected_selected']); roots_gate(old['hierarchy_roots'])
    q = old['predecessor_full_qualification']
    oldqual = reader.read(q['path'], q['seal'], True)
    need(oldqual['population'] == 771, 'Qualified native ancestor771 required')
    # The sealed predecessor's authoritative per-family EL checks were completed
    # at preparation. Reuse those unchanged bindings, not failed full775 evidence.
    inherited.predecessor.masku(source)
    closed = reader.read(CLOSURE, CLOSURE_SHA, True)
    need(closed['all_original_gates_replayed'] is True and closed['semantic_reload'] is True and
         closed['final_reset'] is True and closed['directions'] == 18516 and closed['protected_objects'] == 76 and
         closed['population_application'] is False, 'Complete CVXIF local qualification only')
    pins = merge(pins, closed['pins'], {str(CLOSURE): CLOSURE_SHA, str(PROOF): PROOF_SHA}, reader.pins)
    cc = reader.read(closure.CAPTURE / 'config.json', closure.CONFIG_SHA, True)
    cf = reader.read(closure.CAPTURE / 'first.el', pins[str(closure.CAPTURE / 'first.el')]).decode('ascii')
    second = reader.read(closure.CAPTURE / 'second.el', pins[str(closure.CAPTURE / 'second.el')]).decode('ascii')
    need(cvx.parse_el(cf, cc) == cvx.parse_el(second, cc) and len(cvx.parse_el(cf, cc)) == 18516,
         'CVXIF exact high-only bit/direction native binding')
    proof = reader.read(PROOF, PROOF_SHA, True)
    pins = merge(pins, proof['pins'])
    db = Path(ledger[0]) / 'snps/coverage/db'
    trees = []
    for relative in ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml'):
        path = db / relative
        raw = reader.read(path, pins[str(path)])
        trees.append(ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw))
    checks, definitions = cvx.base.proof.typed.definitions(*trees, cvx.base.proof.SCOPES)
    raw_shapes = {}
    for scope in cvx.base.proof.SCOPES:
        definition = ET.fromstring(definitions[scope]['shape'])
        _, _, width = cvx.base.proof.bind_scope(scope, definition, checks[scope], definitions[scope]['module']['chksum'])
        raw_shapes[scope] = (width, checks[scope])
    base_el = reader.read(REFERENCE / 'combined.el', pins[str(REFERENCE / 'combined.el')]).decode('ascii')
    need(not cvx.base.proof.existing_overlap(base_el, proof['targets']), 'New CVXIF overlaps retained native union')
    # Only the newly admitted777 suffix is additional to the proven776 padding.
    files = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1 and str(files[0]) in pins, 'Exact pinned777 Toggle suffix')
    rows, sha = cvx.base.proof.typed.rows(files[0], cvx.base.proof.SCOPES)
    need(sha == pins[str(files[0])], '777 Toggle read identity')
    for target in proof['targets']:
        row = rows[target['scope']]
        need((row['width'], row['checksum']) == raw_shapes[target['scope']] and
             row['checksum'] == target['checksum'], 'Fresh777 typed padding shape')
        need(all(not(int(row['bits'], 16) >> (row['width']-1-i) & 1) for i in target['raw_positions']), '777 padding observed activity')
    mfpu = reader.read(inherited.prior.MFPU / 'capture-result.json', inherited.prior.MFPU_SHA, True)
    rvh = reader.read(inherited.prior.RVH_CLOSURE, inherited.prior.RVH_SHA, True)
    need(mfpu['EL_semantic_roundtrip'] is True and mfpu['targets'] == 272 and
         mfpu['initial_X_waiver'] is False and rvh['original_inspect_all_checks_replayed'] is True and
         rvh['empty_before_reset_final_cleanup'] is True and rvh['targets'] == 60,
         'Exact local native reference books')
    native = inherited.predecessor.strict.qualification
    masku_config = reader.read(inherited.predecessor.Q / 'config.json', inherited.predecessor.strict.NATIVE_SHA, True)
    masku_text = reader.read(inherited.predecessor.Q / 'first.el', inherited.predecessor.NATIVE_EL_SHA).decode('ascii')
    need(len(native.records(masku_text, masku_config)) > 0 and delta['masku_raw776']['missing_slots'] == 512,
         'Only qualified MASKU parent512; child candidates protected')
    prior_delta = reader.read(inherited.PREP776/'config.json', inherited.PREP776_SHA, True)
    ms = native.source.SCOPE
    sample_rows, sample_sha = native.typed.rows(files[0], [ms])
    need(sample_sha == pins[str(files[0])], 'MASKU actual777 sample pin')
    merged = native.typed.union({ms: prior_delta['masku_raw776']['union']}, sample_rows)[ms]
    need(merged == delta['masku_raw776']['union'] and
         format(int(merged['bits'],16), '0%db' % merged['width'])[3422:3934] == '0'*512,
         'MASKU512 exact777 source/shape/bitmap union remains zero')
    need(delta['unexpanded_MASKU_child_objects'] == inherited.predecessor.unexpanded_objects(masku_config),
         'All other MASKU child fields protected')
    pins = merge(pins, reader.pins)
    return source, pins, base_el + cf, bitmap


def tcl_atom(value):
    # Tcl list quoting including bracketed array variable names, not string substitution.
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('[', '\\[').replace(']', '\\]').replace('\n', '\\n') + '"'


def selection(roots):
    roots_gate(roots)
    lines = ['set p740_scopes {}', 'array set p740_root_names {}']
    for r in [dict(scope='ara_tb', name='ara_tb'), *roots]:
        lines += ['lappend p740_scopes ' + tcl_atom(r['scope']),
                  'set ' + tcl_atom('p740_root_names(' + r['scope'] + ')') + ' ' + tcl_atom(r['name'])]
    lines += ['set compact_root_helper ' + tcl_atom(ROOT_HELPER)]
    return '\n'.join(lines) + '\n'


def prepare(out, service_unit):
    need(out.parent == OUT and not out.exists(), 'Fresh agent-owned report directory')
    need(re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', service_unit), 'Exact managed unit required')
    reader = Reader(); source, pins, text, bitmap = approved(reader)
    tools.revalidate(source['tool_identity'])
    deps = (Path(__file__).resolve(), TCL, HERE / 'test_report_global777_compact.py', EXPORT, ROOT_HELPER,
            Path(inventory.__file__).resolve(), Path(tools.__file__).resolve(), HERE/'report_scope_ancestors.py')
    pins = merge(pins, {str(p): life.digest(p) for p in deps})
    reader.finish(pins)
    config = dict(schema=SCHEMA, population=777, output=str(out), successor_entry=str(Path(__file__).resolve()),
        admission=dict(path=str(inherited.BASE / 'admission-manifest.json'), sha256=inherited.BASE_SHA),
        reference=dict(path=str(REFERENCE / 'config.json'), sha256=REFERENCE_SHA),
        cvxif_closure=dict(path=str(CLOSURE), sha256=CLOSURE_SHA),
        input_ledger=source['input_ledger'], expected_selected=source['expected_selected'],
        hierarchy_roots=source['hierarchy_roots'], tool_identity=source['tool_identity'],
        pins=pins, expected_EL_semantic_sha256=semantic_seal(semantic(text)),
        timeout_seconds=3600, owning_service_unit=service_unit, owner_uid=os.getuid(),
        expected_cgroup='/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (os.getuid(), os.getuid(), service_unit),
        local_protection_inherited=True, global_protection='Complete approved physical bitmask/FSM/Branch union; empty reset',
        CVXIF_passive_scope_not_DUT_gain=True, CVXIF_directions=18516, MASKU_directions=512,
        MASKU_child_candidates_included=False, GUI_singleton_inventory_hooks=False,
        official_denominator_verified=False, historical_PASS_only_no_new_RTL_signoff=True,
        full_OR_metric_instances=6162, raw_hierarchy_rows=2989, parent_launch_approval_required=True)
    out.mkdir()
    for name, data in [('combined.el', text), ('inputs.txt', '\n'.join(source['input_ledger'])+'\n'),
                       ('root-selection.tcl', selection(source['hierarchy_roots']))]:
        (out/name).write_text(data); pins[str(out/name)] = life.digest(out/name)
    life.save(out/'config.json', config)
    seal = life.digest(out/'config.json')
    # Same evaluation's hashes already checked. Public check creates a fresh epoch.
    receipt = dict(status='COMPACT777_PREPARED_NOT_LAUNCHED', config_seal=seal,
        formal777_manifest_seal=inherited.BASE_SHA, approved_EL_semantic_sha256=config['expected_EL_semantic_sha256'],
        local_qualified_only_not_global_application=True, EDA_launched=False,
        source_design_shape_native_pins=len(pins), module_roots=72, actual_selected_expected=777,
        official_percentage=None, official_denominator_verified=False)
    life.save(out/'prepare-receipt.json', receipt)
    print(json.dumps(dict(output=str(out), seal=seal, receipt_seal=life.digest(out/'prepare-receipt.json'))), flush=True)


def check(out, seal):
    # The externally sealed consumer config is not one of its own source pins.
    # Keep this capture separate from approved()'s complete input obligations.
    c = Reader().read(out/'config.json', seal, True)
    reader = Reader()
    need(c['schema'] == SCHEMA and c['population'] == 777 and c['output'] == str(out) and
         c['successor_entry'] == str(Path(__file__).resolve()) and c['admission'] ==
         dict(path=str(inherited.BASE/'admission-manifest.json'), sha256=inherited.BASE_SHA), 'Exact frozen777 consumer')
    source, pins, approved_text, _ = approved(reader)
    need(c['input_ledger'] == source['input_ledger'] and c['expected_selected'] == source['expected_selected'] and
         c['hierarchy_roots'] == source['hierarchy_roots'] and c['tool_identity'] == source['tool_identity'], 'Retained exact identities')
    need(all(c['pins'].get(p) == h for p,h in pins.items()), 'Omitted source/native/input obligations')
    need(c['GUI_singleton_inventory_hooks'] is False and c['MASKU_child_candidates_included'] is False and
         c['CVXIF_directions'] == 18516 and c['MASKU_directions'] == 512 and
         c['timeout_seconds'] == 3600 and c['official_denominator_verified'] is False, 'No family/scope/gate expansion')
    need(type(c['owner_uid']) is int and c['owner_uid'] == os.getuid() and
         re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', c['owning_service_unit']) and
         c['expected_cgroup'] == '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' %
         (c['owner_uid'], c['owner_uid'], c['owning_service_unit']), 'Exact service cgroup contract')
    need((out/'inputs.txt').read_text().splitlines() == c['input_ledger'] and
         (out/'root-selection.tcl').read_text() == selection(c['hierarchy_roots']), 'Exact inputs and properly quoted roots')
    need((out/'combined.el').read_text() == approved_text and
         semantic_seal(semantic(approved_text)) == c['expected_EL_semantic_sha256'], 'Approved bitmask union')
    for p in (Path(__file__).resolve(), TCL, HERE/'test_report_global777_compact.py', EXPORT, ROOT_HELPER,
              HERE/'report_scope_ancestors.py'):
        need(c['pins'].get(str(p)) == life.digest(p), 'Consumer source/test binding')
    reader.finish(c['pins']); tools.revalidate(c['tool_identity'])
    need(life.digest(out/'config.json') == seal, 'Consumer config changed during check')
    return c


def terminal_gate(t, c):
    need(type(t['returncode']) is int and t['returncode'] == 0 and type(t['timeout']) is bool and
         t['timeout'] is False, 'Strict terminal0/no timeout')
    need(t['config_seal'] and len(t['actual_dve']) == 1, 'Exactly one proven live DVE')
    row = t['actual_dve'][0]
    need(type(row['pid']) is int and row['executable_verified'] is True and row['cwd'] == c['output'] and
         row['executable'] == c['tool_identity']['executable'] and row['cgroup'] == c['expected_cgroup'], 'Actual owning executable/cwd/cgroup')


def diagnostics(text):
    need(not re.search(r'(?:Warning-|Error-|Fatal-|\b(?:Error|Fatal):|^DVE_COVERAGE_EXPORT_FAILED:|^COMPACT777_FAILED:)', text, re.M),
         'DVE warning/error/failure diagnostic')


def verify(out, seal):
    c = check(out, seal)
    terminal = json.loads((out/'terminal.json').read_bytes()); terminal_gate(terminal, c)
    need(terminal['config_seal'] == seal, 'Executed configuration seal')
    paths = [out/'terminal.json', out/'execution.json', out/'selected_tests.txt', out/'raw.csv']
    membership(c['input_ledger'], (out/'selected_tests.txt').read_text().splitlines())
    reports = {}
    for stage in STAGES:
        ep, sp = out/EL_FILES[stage], out/('modules_'+stage+'.csv')
        el_gate(ep.read_bytes(), stage, c['expected_EL_semantic_sha256'])
        reports[stage] = summary(sp.read_bytes(), stage, c['hierarchy_roots']); paths.extend((ep, sp))
    summaries_gate(reports)
    raw_summary_gate((out/'raw.csv').read_bytes(), c['hierarchy_roots'], reports['raw'])
    gui = out/'DVEfiles/dve_gui.log'
    for file in (out/'launcher.log', gui): diagnostics(file.read_text())
    lines = gui.read_text().splitlines()
    need(lines.count('COMPACT777_FIVE_PHASE_DONE') == 1 and lines.count('DVE_COVERAGE_EXPORT_DONE') == 1,
         'Completed hook and exporter exactly once')
    paths.append(out/'cleanup-empty.el'); need(paths[-1].read_bytes() == b'', 'Cleanup leaves no exclusions')
    # Pin immutable terminal snapshots, never growing live launcher/DVE logs.
    snapshots = out/'terminal-evidence'; snapshots.mkdir(exist_ok=True)
    for name, original in [('launcher.log',out/'launcher.log'), ('dve_gui.log',gui)]:
        dest = snapshots/name
        if dest.exists(): need(dest.read_bytes() == original.read_bytes(), 'Terminal evidence changed')
        else: dest.write_bytes(original.read_bytes())
        paths.append(dest)
    result = dict(status='FORMAL777_COMPACT_GLOBAL_FIVE_PHASE_VERIFIED', population=777,
        config_seal=seal, admission_seal=inherited.BASE_SHA, actual_selected_tests=777,
        source_design_native_pins=c['pins'], output_pins={str(p):life.digest(p) for p in paths},
        complete_approved_EL_bitmask_union=True, all_other_bits_protected=True,
        local_protection_basis='Sealed exact native local complements; global completeEL/empty reset prevents any extra exclusions',
        raw_reset_final_equal=True, applied_reloaded_equal=True, module_reports=reports,
        raw_hierarchy_vs_rooted_six_metrics_equal=True, supported_roots_all_six_metrics_present=True,
        official_denominator_verified=False, CVXIF_passive_scope_not_DUT_gain=True,
        historical_PASS_only_no_new_RTL_signoff=True)
    qp = out/'qualification.json'
    if qp.exists(): need(json.loads(qp.read_bytes()) == result, 'Existing qualification differs')
    else: life.save(qp, result)
    print(json.dumps(dict(output=str(out), status=result['status'], seal=life.digest(qp))), flush=True)
    return result


def run(out, seal, reviewed):
    need(reviewed == seal, 'Explicit parent-reviewed config seal')
    c = check(out, seal)
    need(Path('/proc/self/cgroup').read_text().splitlines() == ['0::'+c['expected_cgroup']] and
         os.getuid() == c['owner_uid'], 'Foreground reviewed service ownership')
    env = tools.controlled_environment(c['tool_identity'], os.environ); env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), DVE_REVIEWED_WAIVERS=str(TCL))
    cmd = [c['tool_identity']['roles']['xvfb_run'], '-a', '-e', str(out/'xvfb.log'),
           c['tool_identity']['roles']['launcher'], '-full64', '-cov', '-script', str(EXPORT)]
    with (out/'execution.json').open('x') as stream:
        json.dump(dict(command=cmd, cwd=str(out), config_seal=seal, timeout_seconds=c['timeout_seconds']),stream)
    observed=[]; timeout=False
    with (out/'launcher.log').open('x') as log:
        p = subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        start=tools.process_info(p.pid)['starttime']; deadline=time.monotonic()+90
        while time.monotonic()<deadline and not observed and p.poll() is None:
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit(): continue
                try:
                    if (proc/'exe').resolve()==Path(c['tool_identity']['executable']) and (proc/'cwd').resolve()==out:
                        proof=tools.verify_live_executable(int(proc.name),c['tool_identity'],p.pid,start)
                        cg=(proc/'cgroup').read_text().splitlines()
                        need(cg==['0::'+c['expected_cgroup']], 'DVE in wrong owning cgroup')
                        observed.append(dict(proof,cwd=str(out),cgroup=c['expected_cgroup']))
                except (OSError,ProcessLookupError): continue
            if not observed: time.sleep(1)
        life.save(out/'live-identity.json', observed)
        print(json.dumps(dict(status='DVE_IDENTITY_OBSERVED',actual_dve=observed)),flush=True)
        try: p.wait(timeout=c['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timeout=True; os.killpg(p.pid,signal.SIGTERM)
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL);p.wait()
    life.save(out/'terminal.json',dict(config_seal=seal,returncode=p.returncode,timeout=timeout,actual_dve=observed))
    verify(out,seal)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('prepare','check','verify','run-reviewed'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seal')
    ap.add_argument('--service-unit');ap.add_argument('--parent-reviewed-seal')
    args=ap.parse_args();directory=args.output.resolve()
    if args.mode=='prepare':prepare(directory,args.service_unit)
    elif args.mode=='check':check(directory,args.seal);print('COMPACT777_CHECK_PASS_NO_EDA')
    elif args.mode=='verify':verify(directory,args.seal)
    else:run(directory,args.seal,args.parent_reviewed_seal)
