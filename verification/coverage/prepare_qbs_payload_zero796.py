"""Source-derived exact QBS zero candidates; offline preparation, never EL/EDA."""
import argparse
import ast
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import re
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as native
import rank_cva6_scalar_data767 as typed
import prove_qbs_hit_congruence780 as congruence
import prepare_qbs_payload_side1792_732 as side
import preflight_qbs_route770 as route

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
HERE = Path(__file__).resolve().parent
BASE = OUT / 'akv-canonical-alias-offline-admitted796-parent-20261008-01'
REPORT = OUT / 'current-population796-alua137-ptw156-agent-20261008-01'
BOOK = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BASE_SHA = '1aa18b04d4b1f3a4a2d8182c0457e240f43e0538bbeabe1b0385724e5a56400d'
CONFIG_SHA = '062daf585d00ef170942b36f5a631dee7f4676af32fcbb4e5d8af86a8159badf'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
EL_SHA = '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9'
CHECKSUM = '3657545390'
SCOPES = [route.BASE + str(b) + '.i_payload_buffer' for b in (0, 1)]
SCHEMA = 'QBS_PAYLOAD_ZERO796_SOURCE_CANDIDATES_ONLY_V1'
need = native.require


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')


def value_sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def extracted(path, names, namespace, pins):
    """Reuse reviewed parsers without importing their report/EDA dependency tree."""
    pins[str(path)] = native.digest(path)
    tree = ast.parse(path.read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    need({n.name for n in functions} == set(names), 'Exact parser function set')
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def parse_el(text, pins):
    ns = extracted(HERE / 'branch720_next_report_contract.py', {'native_inventory'},
                   dict(re=re, Counter=Counter, require=need), pins)
    ns = extracted(HERE / 'report_global777_compact.py', {'semantic'},
                   dict(re=re, itertools=itertools, need=need,
                        inventory=SimpleNamespace(native_inventory=ns['native_inventory'])), pins)
    return ns['semantic'](text)


def all_writes(text, names):
    # Assertions contain <= comparisons, not storage writers.
    cleaned = re.sub(r'\bassert\b[^;]*;', '', side.lexical.clean(text))
    return side.writes(cleaned, names)


def ingress_contract(adapter):
    result = {}
    compact = re.sub(r'\s+', '', side.lexical.clean(adapter))
    for kind in ('weight', 'activation'):
        stems = ('ingress_q', 'ingress_target_q', 'ingress_location_q', 'input_target',
                 'input_location', 'ingress_count_q', 'ingress_rd_q', 'ingress_wr_q')
        names = [kind + '_' + n for n in stems]
        ledger = all_writes(adapter, names)
        counts = Counter(lhs.split('[')[0].split('.')[0] for lhs, _, _ in ledger)
        expected = dict(zip(names, (1, 1, 1, 3, 1, 4, 3, 3)))
        need(dict(counts) == expected, 'All ingress/target writers: ' + kind)
        for stem, rhs in (('ingress_q', kind + '_input'),
                          ('ingress_target_q', kind + '_input_target[b]'),
                          ('ingress_location_q', kind + '_input_location[b]')):
            wanted = kind + '_' + stem + ('[entry]' if stem == 'ingress_q' else '[entry][b]')
            need([r for r in ledger if r[0] == wanted] == [(wanted, '<=', rhs)],
                 'Whole captured tuple has an alternate writer')
        for token in (f'assign{kind}_ingress_push={kind}_write_valid_i&&{kind}_write_ready_o;',
                      f'if({kind}_ingress_push&&{kind}_ingress_wr_q==1\'(entry))begin',
                      f'assign{kind}_source[1]={kind}_ingress_q[{kind}_ingress_rd_q];',
                      f'{kind}_ingress_count_q<2&&',
                      f'{kind}_ingress_count_q!=0&&'):
            need(token in compact, 'Ingress occupancy/tuple ownership anchor')
        result[kind] = ledger
    return result


def queue_induction():
    # Mark whether an entry was initialized by a legal full-tuple capture.
    states = {(0, 0, 0, (False, False))}
    frontier = list(states)
    transitions = 0
    while frontier:
        count, rd, wr, initialized = frontier.pop()
        need(count == 0 or initialized[rd], 'Occupied queue exposes uninitialized tuple')
        for push, pop, clear in itertools.product((False, True), repeat=3):
            if push and count == 2 or pop and count == 0:
                continue
            known = list(initialized)
            if clear:
                nxt = (0, 0, 0, tuple(known))
            else:
                if push:
                    known[wr] = True
                nxt = (count + int(push) - int(pop), rd ^ int(pop), wr ^ int(push), tuple(known))
            transitions += 1
            if nxt not in states:
                states.add(nxt)
                frontier.append(nxt)
    return dict(states=len(states), transitions=transitions,
                stale_initialized_entries_retain_legal_tuples=True,
                uninitialized_entry_X_not_excluded=True)


def bank1_domain(step=4):
    need(step == 4, 'Producer alignment cannot be relaxed')
    keys, witnesses = set(), {}
    counts = Counter()
    for profile, scale, quants in (('Q8_K', 4, 256), ('Q8_0', 2, 32)):
        for layout in ('ROW', 'M4', 'M8'):
            for context in range(4):
                for offset in range(0, 4096, step):
                    for writer in range(16):
                        counts['enumerated'] += 1
                        ctx, off, valid = route.activation_map(
                            dict(activation_profile=profile, activation_layout=layout),
                            offset + writer, context)
                        block = scale + quants + (32 if quants == 256 else 0)
                        if not valid or not 4 <= ctx < 8 or not 0 <= off < block:
                            continue
                        need(layout == 'M8', 'ROW/M4 produced a bank1 tuple')
                        independent = congruence.m.activation_target(offset + writer, 8, scale, quants)
                        need((ctx, off) == independent, 'Independent format mapping disagreement')
                        plane, dest = congruence.m.activation_location(off, scale, quants)
                        key = ('activation', ctx - 4, plane, dest % 32 if plane == 0 else dest, writer)
                        keys.add(key)
                        witnesses.setdefault(key, dict(profile=profile, layout=layout, context_input=context,
                            response_offset=offset, original_writer=writer, global_context=ctx,
                            native_offset=off, plane=plane, destination=dest))
                        counts['accepted'] += 1
    return keys, witnesses, dict(counts)


def source_receipt(ctx):
    pins = ctx['pins']
    producer = congruence.source_proof(pins)
    sources = {}
    book = ctx['book']
    for rel in route.SOURCES + ['hardware/src/vlsu/qbs/qbs_activation_context.sv']:
        path = ROOT / rel
        need(native.digest(path) == book[str(path)], 'Frozen source drift: ' + rel)
        pins[str(path)] = book[str(path)]
        sources[path.name] = path.read_text()
    adapter, payload, compute = (sources[n] for n in
        ('qbs_block_adapter.sv', 'qbs_payload_buffer.sv', 'qbs_compute_engine.sv'))
    pending_ledger = side.source_contract(adapter, payload, compute)
    ingress_ledger = ingress_contract(adapter)
    compact = re.sub(r'\s+', '', side.lexical.clean(payload))
    for token in ('assignword_match[b]=candidate[b]&&selected_word==offset[b][WordShift+:3];',
                  'wire[15:0]hit=word_match&',
                  'activation_mask_i[B]&&activation_location[B].plane==0&&activation_context_i[B]==2\'(r)',
                  'assignactivation_side_offset[b][n]=activation_location[n].offset==8\'(b);'):
        need(token in compact, 'All hit fan-in dominance anchor')
    ledger = all_writes(payload, ('hit', 'word_match', 'candidate', 'activation_byte_select',
                                'weight_byte_select', 'activation_side_row', 'activation_side_offset',
                                'weight_side_row', 'weight_side_offset'))
    need(len(ledger) == 12, 'Alternate hit fan-in writer')
    producer_writers = {}
    for filename, names in {
        'qbs_read_engine.sv': ('planner_cursor_q', 'planner_offset_q', 'ar_chunk_bytes_q',
                               'burst_fifo_q', 'response_head', 'data_o', 'data_strb_o', 'data_offset_o'),
        'qbs_engine.sv': ('compute_activation_write_offset', 'read_range_vaddr',
                          'activation_k_offset_q', 'activation_row_offset_q', 'activation_row_bytes_q',
                          'weight_k_offset_q', 'weight_row_bytes_q', 'activation_layout_q'),
        'qbs_activation_context.sv': ('replay_offset_q', 'replay_issue_beat_q'),
    }.items():
        writers = all_writes(sources[filename], names)
        found = {lhs.split('[')[0].split('.')[0] for lhs, _, _ in writers}
        need(found == set(names), 'Incomplete producer writer inventory: ' + filename)
        producer_writers[filename] = dict(all_writers=writers, inventory_sha256=value_sha(writers))
    return dict(producer=producer, ingress_all_writers=ingress_ledger,
                producer_all_writers=producer_writers,
                pending_all_writers=pending_ledger, hit_fanin_all_writers=ledger,
                queue_induction=queue_induction(), side_induction=side.induction_check(),
                proof_chain=[
                    'Validated producer base/strides, MMU low12, page/burst/take recurrence preserve offset4.',
                    'All original byte writers0..15, both profiles, all layouts, ctx0..3 and full12-bit offset domain enumerated.',
                    'Ingress captures full target/location/data at the same writer b; all writers and occupied-entry ownership checked.',
                    'Retired initialized entries retain legal tuples even when source_valid=0: unqualified hit is not silently treated as a commit.',
                    'Pending copies same b/location with remaining strb; drain only removes bits, never compacts writers.',
                    'Side bytes are consumed on acceptance, so pending strb AND captured plane2 is always zero after reset.',
                    'Candidate/word_match/side-hit include target.valid. Mask plus immutable captured tuple implies forbidden hit has no known-one.',
                    'Clear gates valid/count but retains metadata; abort/backpressure cannot introduce a new tuple writer.',
                ], startup_X_qualified=False, arbitrary_initial_state_proven=False,
                uninitialized_ingress='May be X until captured. This packet makes no X-transition exclusion.')


def owner_for(scope, name, width, semantic):
    other, masks = semantic
    for s, _, _, directive in other:
        need(not (directive == 'WHOLE_SCOPE' and (scope == s or scope.startswith(s + '.'))),
             'Whole-scope EL ownership HOLD')
        if s == scope and directive.startswith('Toggle '):
            raise ValueError('Opaque same-scope Toggle EL HOLD')
    covered = {'0to1': 0, '1to0': 0}
    for (s, checks, field, _, _, prefix, direction), mask in masks.items():
        if s != scope:
            continue
        need(checks.split()[-1] == CHECKSUM, 'EL checksum identity')
        if field != name:
            need(not any(name.startswith(field + sep) or field.startswith(name + sep)
                         for sep in ('.', '[')),
                 'Packed parent/child EL ownership HOLD')
            continue
        need(not prefix, 'MDA EL ownership cannot be flattened')
        need(mask.bit_length() <= width, 'EL range outside compiled field')
        covered[direction] |= mask
    return covered


def scoped_semantic(scope, semantic):
    other, masks = semantic
    return ({r for r in other if r[0] == scope or
             (r[3] == 'WHOLE_SCOPE' and scope.startswith(r[0] + '.'))},
            {k: v for k, v in masks.items() if k[0] == scope})


def partition(scope, nodes, row, semantic, classify, source_sha):
    need(row['checksum'] == CHECKSUM and row['width'] == 66340, 'Compiled payload checksum/width')
    raw = int(row['bits'], 16)
    need(0 <= raw < 1 << row['width'], 'Raw bitmap overflow')
    semantic = scoped_semantic(scope, semantic)
    targets, protected, seen = [], [], set()
    for n in nodes:
        name = n['name']
        if not name.endswith('.hit'):
            continue
        need(n['right'] == '0' and n['logical_width'] in (16, 32) and
             n['file'] == '571' and n['line_num'] in ('269', '355', '381') and
             n['portnode'] == '0' and n['excluded'] == '0', 'Exact compiled hit declaration')
        ownership = owner_for(scope, name, n['logical_width'], semantic)
        selected, kept, removed = [], [], []
        for bit in range(n['logical_width']):
            key, slot, is_side = congruence.m.identity(name, bit)
            if not classify(key, slot, is_side):
                kept.append(bit)
                continue
            need((name, bit) not in seen, 'Duplicate source target')
            seen.add((name, bit))
            coords = [n['serialized_offset'] + 2 * bit + d for d in (0, 1)]
            need(all(not (raw >> (row['width'] - 1 - c)) & 1 for c in coords),
                 'Observed raw796 counterexample: ' + name + ':' + str(bit))
            both = all(ownership[d] >> bit & 1 for d in ownership)
            single = bool((ownership['0to1'] ^ ownership['1to0']) >> bit & 1)
            need(not single, 'Single-direction EL ownership HOLD; no pair-direction guess')
            rec = dict(bit=bit, original_writer=key[-1], slot=slot, side=is_side,
                       mapping_key=list(key), raw_zero_coordinates=coords)
            (removed if both else selected).append(rec)
        if selected or removed:
            attrs = {k: v for k, v in n.items() if k not in
                     ('serialized_offset', 'logical_width', 'missing_coordinates', 'missing_slots')}
            targets.append(dict(scope=scope, checksum=CHECKSUM, signal=name,
                compiled_attributes=attrs, serialized_offset=n['serialized_offset'],
                logical_width=n['logical_width'], source_sha256=source_sha,
                source_candidate_bits=selected + removed, unowned_bits=selected,
                both_direction_EL_removed_bits=removed, protected_bit_indices=kept))
        else:
            protected.append(dict(signal=name, bit_indices=kept))
    return dict(targets=targets, protected_other_hit_fields=protected,
                source_proven_bits=len(seen),
                EL_removed_positions=2 * sum(len(t['both_direction_EL_removed_bits']) for t in targets),
                candidate_positions=2 * sum(len(t['unowned_bits']) for t in targets),
                all_other_non_hit_fields_protected=True, native_direction_labels_not_inferred=True)


def checked_group(name, producer, expected=None):
    try:
        result = producer()
        if expected is not None:
            need(result['candidate_positions'] == expected, 'Exact residual group size: ' + name)
        return dict(group=name, status='PREPARED_SOURCE_CANDIDATE_NOT_NATIVE_QUALIFIED', **result)
    except (ValueError, KeyError, AssertionError, TypeError, OSError) as error:
        return dict(group=name, status='HOLD', reason=str(error), targets=[], candidate_positions=0)


def constant_contract(payload, compute):
    p = re.sub(r'\s+', '', side.lexical.clean(payload))
    c = re.sub(r'\s+', '', side.lexical.clean(compute))
    need(c.count('.NativeView(1\'b0),.UniqueInputBytes(1\'b1)') == 2,
         'NativeView0 frozen instance binding')
    need('if(p!=2)begin:gen_unused_upperassignwrite_be[slot][p][r][31:16]=\'0;'
         'assignwrite_data[slot][p][r][255:128]=\'0;end' in p, 'Weight upper-half zero writer')
    for token in ('localparamintWordShift=p==2?5:4;',
                  'localparamintWordBytes=1<<WordShift;',
                  'for(genvarbyte_lane=0;byte_lane<WordBytes;byte_lane++)',
                  'localparamintDataWidth=p==2?256:128;',
                  '.rdata_o(read_data[p][r][DataWidth-1:0])',
                  'if(p!=2)assignread_data[p][r][255:128]=\'0;',
                  'endelsebegin:gen_no_native_view',
                  'assignweight_view_o[row][b]=\'0;', 'assignactivation_view_o[row][b]=\'0;'):
        need(token in p, 'Constant branch/range contract')
    writes = all_writes(payload, ('write_data', 'write_be', 'read_data', 'weight_view_o', 'activation_view_o'))
    counts = Counter(lhs.split('[')[0] for lhs, _, _ in writes)
    need(dict(counts) == dict(write_data=3, write_be=3, read_data=1,
                             weight_view_o=11, activation_view_o=4), 'All constant-field writers')
    return writes


def constant_projection(ctx):
    payload_path = ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'
    compute_path = payload_path.with_name('qbs_compute_engine.sv')
    package_path = ROOT / 'hardware/include/qbs_pkg.sv'
    for path in (payload_path, compute_path, package_path):
        need(native.digest(path) == ctx['book'][str(path)], 'Constant frozen source hash binding')
    package = re.sub(r'\s+', '', side.lexical.clean(package_path.read_text()))
    need('QbsMaxWeightBlockBytes=210;' in package and 'QbsMaxActivationBlockBytes=292;' in package,
         'Frozen constant dimension binding')
    ledger = constant_contract(payload_path.read_text(), compute_path.read_text())
    fields = []
    for scope in SCOPES:
        semantic = scoped_semantic(scope, ctx['semantic'])
        specs = [
            ('write_data', [range(2), range(2), range(4)], (128, 255), 'weight_word_upper_padding'),
            ('write_be', [range(2), range(2), range(4)], (16, 31), 'weight_byte_enable_upper_padding'),
            ('read_data', [range(2), range(4)], (128, 255), 'weight_read_upper_padding'),
            ('weight_view_o', [range(4), range(210)], (0, 7), 'NativeView0'),
            ('activation_view_o', [range(4), range(292)], (0, 7), 'NativeView0'),
        ]
        binary = {n['name']: n for n in ctx['nodes'][scope]}
        arrays = ctx['arrays'][scope]
        for stem, dimensions, bounds, proof in specs:
            for indices in itertools.product(*dimensions):
                field = stem + ''.join('[%d]' % i for i in indices)
                # No MDA flattening: absent exact binary leaves stay source-only HOLD.
                need(field not in binary, 'New binary constant leaf requires a successor exact binder')
                ownership = owner_for(scope, field, bounds[1] + 1, semantic)
                need(not any(ownership.values()), 'Uncompiled constant EL ownership requires typed MDA review')
                fields.append(dict(scope=scope, signal=field, bit_low=bounds[0], bit_high=bounds[1],
                    constant_value=0, source_proof=proof,
                    source_sha256=ctx['book'][str(payload_path)],
                    status='HOLD_NO_EXACT_COMPILED_BINARY_TARGET', raw_coordinates=None,
                    candidate_positions=0, EL_overlap=False,
                    compiled_array_parent=[a for a in arrays if a.get('name') == stem]))
    need(len({(r['scope'], r['signal'], r['bit_low'], r['bit_high']) for r in fields}) == len(fields),
         'Duplicate constant leaf/range')
    return dict(group='weight_upper_and_nativeview0', status='HOLD_NO_COMPILED_BINARY_TARGETS',
                source_proof_status='PASS', all_writers=ledger, source_constants=fields,
                source_constant_logical_bits=sum(r['bit_high'] - r['bit_low'] + 1 for r in fields),
                candidate_positions=0, reason='Source constants retained without invented MDA/Toggle coordinates')


def context():
    pins = {}
    def bound(path, sha, structured=True):
        need(native.digest(path) == sha, 'Authority/source pin drift: ' + str(path))
        pins[str(path)] = sha
        return json.loads(path.read_bytes()) if structured else path.read_bytes()
    manifest = bound(BASE / 'admission-manifest.json', BASE_SHA)
    config = bound(REPORT / 'config.json', CONFIG_SHA)
    book = bound(BOOK, BOOK_SHA)
    need(manifest['coverage_admitted'] is True and config['population'] == 796 and
         config['admission'] == dict(path=str(BASE / 'admission-manifest.json'), sha256=BASE_SHA),
         'Exact published796 authority')
    ledger = bound(BASE / 'combined-inputs.txt', manifest['output_pins'][str(BASE / 'combined-inputs.txt')], False).decode().splitlines()
    need(len(ledger) == len(set(ledger)) == 797 and ledger == config['input_ledger'], 'Exact796 membership')
    union_path = BASE / 'combined-toggle-bits.json'
    union = bound(union_path, manifest['output_pins'][str(union_path)])
    el_path = REPORT / 'combined.el'
    need(config['pins'][str(el_path)] == EL_SHA, 'Exact approved EL identity')
    semantic = parse_el(bound(el_path, EL_SHA, False).decode('ascii'), pins)
    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml',
             db / 'shape/tgl.verilog.shape.xml', db / 'auxiliary/verilog.sourceinfo.xml']
    for path in paths:
        bound(path, manifest['input_pins'][str(path)], False)
    checks, definitions = native.definitions(*(native.xml(p) for p in paths[:3]), SCOPES)
    files = {n.get('id'): n.get('name') for n in native.xml(paths[3]).findall('fileinfo')}
    nodes, arrays = {}, {}
    for scope in SCOPES:
        need(checks[scope] == union[scope]['checksum'] == CHECKSUM and
             definitions[scope]['module']['name'] == 'qbs_payload_buffer', 'Compiled module/instance binding')
        nodes[scope], arrays[scope] = typed.typed_nodes(definitions[scope]['shape'], union[scope])
        need(len(nodes[scope]) == 3193 and union[scope]['width'] == 66340, 'Full compiled field inventory')
        for n in nodes[scope]:
            path = files[n['file']]
            need(path in {str(ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'),
                          str(ROOT / 'hardware/include/qbs_pkg.sv')}, 'Compiled source owner')
            if path.endswith('qbs_pkg.sv'):
                need(files.get(n.get('aux_file')) == str(ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'),
                     'Packed member auxiliary declaration owner')
    return dict(pins=pins, book=book, ledger=ledger, manifest=manifest, union=union,
                semantic=semantic, nodes=nodes, arrays=arrays, definitions=definitions)


def suffix_receipt(ctx):
    cache = OUT / 'qbs-engine-full102-residual766-static-agent-20261007-01.json'
    sha = 'b6fefc0d350ed0ca4d3add37f3b6a43fd6cb4a79742dc2384d9f297abd5a8cca'
    need(native.digest(cache) == sha, 'Sealed766 cache identity')
    ctx['pins'][str(cache)] = sha
    old = json.loads(cache.read_bytes())
    prior = next(Path(p) for p in old['pins'] if p.endswith('/combined-inputs.txt'))
    need(native.digest(prior) == old['pins'][str(prior)], 'Sealed766 prefix ledger')
    ctx['pins'][str(prior)] = old['pins'][str(prior)]
    need(prior.read_text().splitlines() == ctx['ledger'][:767], 'Exact766 prefix')
    rows = {r['scope']: r for r in old['scope_summaries'] if r['module'] == 'qbs_payload_buffer'}
    need(set(rows) == set(SCOPES), 'Complete sealed766 banks')
    need(all((r['raw_width'], r['checksum'], r['design_checksum']) ==
             (66340, CHECKSUM, '1651389237') for r in rows.values()), 'Sealed766 compiled identity')
    raw = {s: int(rows[s]['bits'], 16) for s in SCOPES}
    samples = []
    for index, vdb in enumerate(ctx['ledger'][767:], 767):
        paths = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths) == 1, 'One suffix Toggle sample')
        path = paths[0]
        sample, actual = native.rows(path, SCOPES)
        need(actual == ctx['manifest']['input_pins'][str(path)], 'Suffix sample pin')
        ctx['pins'][str(path)] = actual
        for s in SCOPES:
            need((sample[s]['width'], sample[s]['checksum']) == (66340, CHECKSUM), 'Suffix sample compiled width')
            raw[s] |= int(sample[s]['bits'], 16)
        samples.append(dict(index=index, vdb=vdb, path=str(path), sha256=actual))
    need(len(samples) == 30 and all(raw[s] == int(ctx['union'][s]['bits'], 16) for s in SCOPES),
         'Sealed766 plus30 exact raw796 union')
    return dict(sealed_prefix_population=766, prefix_cache_sha256=sha, suffix_samples=samples,
                both_banks_union_equal_raw796=True, historical766_samples_reaudited=False)


def deduplicate_groups(groups):
    seen = set()
    for index, group in enumerate(groups):
        if group['status'] == 'HOLD':
            continue
        current = set()
        try:
            for field in group['targets']:
                for bit in field['unowned_bits']:
                    for coord in bit['raw_zero_coordinates']:
                        key = field['scope'], coord
                        need(key not in current and key not in seen, 'Cross-group duplicate candidate coordinate')
                        current.add(key)
            need(len(current) == group['candidate_positions'], 'Group coordinate count identity')
        except (ValueError, KeyError) as error:
            groups[index] = dict(group=group['group'], status='HOLD', reason=str(error),
                                 targets=[], candidate_positions=0)
            continue
        seen.update(current)
    return seen


def collect():
    try:
        ctx = context()
    except (ValueError, KeyError, OSError) as error:
        return dict(schema=SCHEMA, status='HOLD_AUTHORITY', reason=str(error), groups=[],
                    candidate_positions=0, EDA_started=False, EL_created=False, RTL_changed=False)
    pins = ctx['pins']
    source_group = checked_group('allwriters_source_chain', lambda: source_receipt(ctx))
    samples = checked_group('raw796_sealed_prefix_suffix', lambda: suffix_receipt(ctx))
    groups = []
    source_sha = ctx['book'][str(ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv')]
    def controls(which):
        need(source_group['status'] != 'HOLD' and samples['status'] != 'HOLD', 'Prerequisite group HOLD')
        keys, witnesses, counts = bank1_domain()
        classify = (lambda key, slot, is_side: is_side and slot == 0) if which == 'side' else (
            lambda key, slot, is_side: key[0] == 'activation' and not (is_side and slot == 0) and key not in keys)
        result = partition(SCOPES[1], ctx['nodes'][SCOPES[1]], ctx['union'][SCOPES[1]],
                           ctx['semantic'], classify, source_sha)
        if which == 'mapping':
            result['finite_domain'] = dict(counts=counts, key_count=len(keys),
                key_set_sha256=value_sha(sorted(keys)), keys=[list(k) for k in sorted(keys)],
                witnesses=[dict(mapping_key=list(k), **witnesses[k]) for k in sorted(keys)],
                slots=[0, 1], original_writers=list(range(16)), offset_domain=[0, 4095, 4],
                selected_word_and_strobes_relaxed=True, present_keys_not_a_runtime_reachability_claim=True)
        return result
    groups.append(checked_group('bank1_M8_mapping_zero', lambda: controls('mapping'), 4112))
    groups.append(checked_group('bank1_side_immediately_consumed_zero', lambda: controls('side'), 3500))
    try:
        constants = constant_projection(ctx)
    except (ValueError, KeyError, AssertionError) as error:
        constants = dict(group='weight_upper_and_nativeview0', status='HOLD', reason=str(error),
                         source_constants=[], candidate_positions=0)
    seen = deduplicate_groups(groups)
    for module in (native, typed, congruence, congruence.m, congruence.even,
                   side, side.lexical, route):
        pins[str(Path(module.__file__).resolve())] = native.digest(module.__file__)
    pins[str(Path(__file__).resolve())] = native.digest(__file__)
    test = HERE / 'test_prepare_qbs_payload_zero796.py'
    pins[str(test)] = native.digest(test)
    drift = [p for p, sha in pins.items() if native.digest(p) != sha]
    if drift:
        return dict(schema=SCHEMA, status='HOLD_END_PIN_DRIFT', drift=drift, groups=[],
                    candidate_positions=0, EDA_started=False, EL_created=False, RTL_changed=False)
    return dict(schema=SCHEMA, status='PREPARED_WITH_CONSTANT_BINDING_HOLD' if all(g['status'] != 'HOLD' for g in groups)
                and constants.get('source_proof_status') == 'PASS' else 'HOLD_GROUP_FAILURE',
        population=796, approved_EL_sha256=EL_SHA, source_chain=source_group, raw796_receipt=samples,
        groups=groups, constant_projection=constants, candidate_positions=len(seen), input_pins=pins,
        raw796_scopes={s: ctx['union'][s] for s in SCOPES}, compiled_definitions=ctx['definitions'],
        candidate_identity_sha256=value_sha(sorted(seen)),
        native_qualification=False, application_approval=False, coverage_admitted=False,
        EDA_started=False, EL_created=False, global_EL_created=False, RTL_changed=False,
        new_random_payload_case=False, pending8_deferred=True, official_denominator=None,
        startup_X_excluded=False, MDA_flattened=False,
        protected='All other controls/data/MDA and startup X; only listed unowned paired coordinates are preparation candidates.')


def verify_packet(packet, result):
    need(packet == json.loads(json.dumps(result)), 'Packet differs from full offline recomputation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify', type=Path)
    args = parser.parse_args()
    result = collect()
    if args.verify:
        verify_packet(json.loads(args.verify.read_bytes()), result)
        print(json.dumps(dict(status='OFFLINE_PACKET_RECOMPUTATION_EQUAL', sha256=native.digest(args.verify),
                              candidate_positions=result['candidate_positions'])))
    else:
        path = args.output.resolve()
        need(path.parent == OUT and not path.exists(), 'Fresh independent packet under verification/out')
        with path.open('x') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
        print(json.dumps(dict(path=str(path), sha256=native.digest(path), status=result['status'],
                              candidate_positions=result['candidate_positions'])))


if __name__ == '__main__':
    main()
