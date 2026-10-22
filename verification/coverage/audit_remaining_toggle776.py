"""Readonly typed residual776 minus exact sealed775 EL; not official denominator/waiver."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as t
import report_native_full771 as native
import report_native_full775 as policy

ROOT, OUT = native.life.ROOT, native.life.OUT
BASE = OUT / 'vfirst-offline-admitted776-parent-20261007-01'
BASE_SHA = '85abeb09ddfc3c4ddbfc43eefa7c71d860932dd66af572edac0bd7030ce3c33c'
REPORT = OUT / 'native-full771-padding-pack-prepared-agent-20261007-01'
QUAL = OUT / 'native-full771-pack-owner-offline-closure-parent-review-20261007-01/qualification.json'
QUAL_SHA = '5cb90569a4cde0cfaa8dc064269f90cb2eb9c20a88c732fbaf7b615e1b1b29fd'
POLICY = OUT / 'native-full775-cached-parent-20261007-01'
POLICY_SHA = '9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f'
CACHE = OUT / 'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'


def el_fields(text):
    fields, whole = defaultdict(list), set()
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block.strip(): continue
        scopes = re.findall(r'^INSTANCE:\s*(\S+)\s*$', block, re.M)
        t.require(len(scopes) == 1, 'Exact scope header')
        scope = scopes[0]
        directives = [line for line in block.splitlines() if line.startswith(('Toggle ', 'Fsm ', 'Transition ', 'State ', 'Branch ', 'Condition ', 'Line '))]
        if not directives: whole.add(scope)
        for line in directives:
            if not line.startswith('Toggle '): continue
            match = re.fullmatch(r'Toggle\s+(?:(0to1|1to0)\s+)?(\S+)\s*(.*?)\s+"([^"]+)"', line)
            t.require(match is not None, 'Unknown exact Toggle grammar: ' + line)
            direction, name, selector, typ = match.groups()
            ranges = re.findall(r'\[(-?\d+)(?::(-?\d+))?\]', selector)
            t.require(not re.sub(r'\[(-?\d+)(?::(-?\d+))?\]', '', selector).strip(), 'Unknown bit selector')
            bits = 'MDA_HOLD' if len(ranges) > 1 else None if not ranges else set(range(min(map(int, (ranges[0][0], ranges[0][1] or ranges[0][0]))),
                                                     max(map(int, (ranges[0][0], ranges[0][1] or ranges[0][0]))) + 1))
            fields[scope, name].append((direction, bits, typ))
    return fields, whole


def excluded_bits(entries, legal):
    removed, partial = set(), defaultdict(set)
    for direction, bits, typ in entries:
        selected = legal if bits is None else bits
        t.require(selected <= legal, 'EL bit range outside compiled field')
        if direction is None: removed |= selected
        else:
            for bit in selected: partial[bit].add(direction)
    ambiguous = {bit for bit, directions in partial.items() if directions != {'0to1', '1to0'} and bit not in removed}
    removed |= {bit for bit, directions in partial.items() if directions == {'0to1', '1to0'}}
    return removed, ambiguous


def collect():
    pins = {}
    def bound(path, sha):
        t.require(t.digest(path) == sha, 'Sealed input drift: ' + str(path)); pins[str(path)] = sha
        return path.read_bytes()
    admission = json.loads(bound(BASE / 'admission-manifest.json', BASE_SHA))
    ledger_path = BASE / 'combined-inputs.txt'
    ledger = bound(ledger_path, admission['output_pins'][str(ledger_path)]).decode().splitlines()
    t.require(len(ledger) == len(set(ledger)) == 777 and admission['coverage_admitted'] is True, 'Exact776 population')
    cache = json.loads(bound(CACHE, CACHE_SHA))
    prior = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(ledger[:742] == bound(prior, cache['input_pins'][str(prior)]).decode().splitlines(), 'Exact741 prefix')
    union = {s: {k: row[k] for k in ('width', 'checksum', 'bits')} for s, row in cache['instances'].items()}
    scopes = list(union)
    for db in ledger[742:]:
        files = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(files) == 1, 'One actual native suffix')
        path = files[0]; bound(path, admission['input_pins'][str(path)])
        sample, sha = t.rows(path, scopes); union = t.union(union, sample)
    q = json.loads(bound(QUAL, QUAL_SHA))
    t.require(q['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and q['population'] == 771,
              'Qualified771 actual native inventory required')
    c = json.loads(bound(REPORT / 'config.json', q['config_seal']))
    pc = json.loads(bound(POLICY / 'config.json', POLICY_SHA))
    el_path = POLICY / 'combined.el'; text = bound(el_path, pc['pins'][str(el_path)]).decode()
    t.require(policy.records(text, pc) == pc['expected_union'], 'Frozen775 exact canonical EL')
    el, whole = el_fields(text)
    inventory = defaultdict(set)
    def table(path, scope, reference=None):
        rows = bound(path, q['output_pins'][str(path)]).decode().splitlines()
        rows = [r.split('\t') for r in rows if r and not r.startswith(('handle', 'Handle'))]
        t.require(all(len(r) >= 4 for r in rows), 'Native table schema')
        identity = [r[1:4] for r in rows]
        if reference is not None: t.require(sorted(identity) == sorted(reference), 'Actual771 full native identity')
        inventory[scope].update(r[3] for r in rows)
    for index, group in enumerate(native.model()['merged_observers'](c).values()):
        table(REPORT / ('observer766_before_%d.tsv' % index), group['scope'], group['reference'])
    for index, group in enumerate(c['toggle_groups']):
        table(REPORT / ('combo_before_%d.tsv' % index), group['scope'])
    queue_scopes = c['queue_config']['instances']
    for index, instance in enumerate(queue_scopes):
        table(REPORT / ('native_before_%d.tsv' % index), instance['scope'], c['queue_references'][index])
    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for path in paths: bound(path, admission['input_pins'][str(path)])
    design, info, shape = (t.xml(path) for path in paths)
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def scope_path(key):
        node, module = nodes[key]; parent = node.get('pid')
        return (scope_path(parent) + '.' if parent in nodes else '') + node.get('name')
    modules = {scope_path(key): module for key, (node, module) in nodes.items()}
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    groups, hold = {}, []
    removed_slots, read108_slots, nonnative_missing = 0, 0, 0
    for scope, row in union.items():
        if not scope.startswith('ara_tb.dut.i_ara_soc.i_system.') and scope != 'ara_tb.dut.i_ara_soc.i_system': continue
        if scope in whole: continue
        if scope not in inventory:
            nonnative_missing += row['width'] - bin(int(row['bits'], 16)).count('1'); continue
        module = modules[scope]; t.require(row['checksum'] == checks[scope], 'Compiled/data checksum')
        matches = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope] and d.get('name') == module.get('name')]
        binding = 'EXACT_MODULE_NAME_AND_CHECKSUM'
        if not matches:
            matches = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope] and
                       d.get('name', '').split(' (')[0] == module.get('name', '').split(' (')[0]]
            binding = 'EXACT_NATIVE_INSTANCE_FAMILY_CHECKSUM_PARAMETER_PROOF_HOLD'
        if len(matches) != 1:
            hold.append(dict(scope=scope, reason='Ambiguous typed shape')); continue
        offset = 0
        for node in matches[0].find('tglshape'):
            if node.tag == 'arrays':
                hold.append(dict(scope=scope, field=node.get('name'), reason='MDA physical bit map not inferred')); continue
            t.require(node.tag in ('node', 'vectornode'), 'Unknown typed object')
            left, right = int(node.get('left', '0')), int(node.get('right', '0'))
            width = 1 if node.tag == 'node' else abs(left - right) + 1
            legal = set(range(min(left, right), max(left, right) + 1)); name = node.get('name')
            missing = [offset + i for i in range(2 * width) if not (int(row['bits'], 16) >> (row['width'] - 1 - offset - i) & 1)]
            start = offset; offset += 2 * width
            if not missing: continue
            label = name if node.tag == 'node' else '%s[%d:%d]' % (name, left, right)
            if label not in inventory[scope] and not (width == 1 and name in inventory[scope]):
                hold.append(dict(scope=scope, field=name, missing_slots=len(missing), reason='No exact actual771 native label')); continue
            entries = el.get((scope, name), [])
            if any(bits == 'MDA_HOLD' for direction, bits, typ in entries):
                hold.append(dict(scope=scope, field=name, reason='Multi-dimensional EL selector mapping not inferred')); continue
            if not entries and any(s == scope and name.startswith(n + '.') for s, n in el):
                hold.append(dict(scope=scope, field=name, reason='Parent-struct EL bit ownership requires map')); continue
            waived, ambiguous = excluded_bits(entries, legal)
            if ambiguous:
                hold.append(dict(scope=scope, field=name, reason='Single-direction native mapping not inferred')); continue
            order = list(range(left, right - 1, -1)) if left >= right else list(range(left, right + 1))
            remaining = [position for position in missing if order[(position - start) // 2] not in waived]
            removed_slots += len(missing) - len(remaining)
            if 'i_operand_requester' in scope and 'request_payload.wdata' in name:
                read108_slots += len(missing) - len(remaining)
            if not remaining: continue
            key = module.get('name', '').split(' (')[0], name
            group = groups.setdefault(key, dict(module_family=key[0], field=name, classification='UNKNOWN_SOURCE_PRODUCER_REVIEW_REQUIRED',
                missing_unwaived_serialized_slots=0, members=[]))
            group['missing_unwaived_serialized_slots'] += len(remaining)
            group['members'].append(dict(scope=scope, native_label=label, bounds=[left, right], kind=node.tag,
                module_checksum=module.get('chksum'), toggle_checksum=row['checksum'], binding=binding,
                compiled_attributes=dict(node.attrib), serialized_offset=start, missing_coordinates=remaining,
                waived_logical_bits=sorted(waived), raw_missing_slots=len(missing)))
        t.require(offset == row['width'], 'Complete non-MDA serialization width')
    ranking = sorted(groups.values(), key=lambda g: (-g['missing_unwaived_serialized_slots'], g['module_family'], g['field']))
    for p, sha in pins.items(): t.require(t.digest(p) == sha, 'End-of-read drift')
    return dict(status='FORMAL776_TYPED_RESIDUAL_AFTER_SEALED775_EL_STATIC_ONLY', population=776,
        policy_note='775 prepared exact EL subtraction, NOT a claim of successful775 native population application',
        top10=ranking[:10], all_bound_groups=ranking, hold=hold, actual771_inventory_scopes=len(inventory),
        deducted_raw_missing_slots=removed_slots, read108_requester_wdata_deducted_slots=read108_slots,
        missing_outside_actual771_inventory_not_ranked=nonnative_missing, pins=pins,
        official_denominator=None, percentage_gain_prediction=None, raw_serialized_directions_not_official_counts=True,
        native_direction_order_not_inferred=True, waivers_added=False, EDA_launched=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); t.require(not args.output.exists(), 'Fresh evidence only')
    result = collect()
    with args.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(args.output), sha=t.digest(args.output),
        top10=[(r['module_family'], r['field'], r['missing_unwaived_serialized_slots']) for r in result['top10']])), flush=True)
