"""Full102 QBS typed residuals and source-bounded bit proposals; static only."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import review_srt_radix16_child_residual as f

ROOT, OUT, DB = f.ROOT, f.OUT, f.DB
need, digest, load = f.need, f.digest, f.load
QBS = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine'
BASE = OUT / 'qbs-payload-matrix4-offline-admitted-766-agent-20261007-01'
BASE_SHA = 'bbad20298653af04606493c1e6c6433cf22bb9f532b4cc16f52922fe9b7bfb3b'
IDENTITY = OUT / 'cva6-parent-rvfi-output-source-review763-agent-20261007-01.json'
IDENTITY_SHA = 'f5e448c55889ad9d783a6c718a3d3000a2d39e53d5af9a23d1ef562a74754bbb'
PKG = ROOT / 'hardware/include/qbs_pkg.sv'
SOURCE_DIR = ROOT / 'hardware/src/vlsu/qbs'
MATRIX = OUT / 'qbs-payload-matrix4-preflight764-agent-20261007-02'


def clean(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text, flags=re.S)


def profile_values(text, name, count):
    body = re.search(r'function automatic int unsigned ' + name + r'\(.*?endfunction : ' + name, clean(text), re.S)
    need(body is not None, 'Profile size function missing')
    values = re.findall(r'QBS_\w+\s*:\s*' + name + r'\s*=\s*(\d+)\s*;', body[0])
    need(len(values) == count and name + " = '0;" in body[0] and 'default: ;' in body[0],
         'Incomplete profile domain/default')
    writes = re.findall(r'\b' + name + r'\s*=\s*([^;]+);', body[0])
    need(len(writes) == count + 1 and all(v == "'0" or v.isdecimal() for v in writes),
         'Nonliteral/unreviewed profile size assignment')
    return tuple(map(int, values))


def bound_facts(pkg):
    constants = {m[1]: int(m[2]) for m in re.finditer(r'localparam int unsigned (Qbs\w+)\s*=\s*(\d+)\s*;', clean(pkg))}
    weight = profile_values(pkg, 'qbs_weight_block_bytes', 9)
    activation = profile_values(pkg, 'qbs_activation_block_bytes', 2)
    need((constants['QbsMaxM'], constants['QbsMaxN'], constants['QbsMaxKBlocks'],
          constants['QbsActivationContextCount'], constants['QbsActivationContextMaxM']) == (8, 32, 256, 1, 1),
         'Frozen package dimensions/context binding changed')
    return dict(constants=constants, weight_profile_sizes=list(weight), activation_profile_sizes=list(activation),
                max_weight_size=max(weight), max_activation_size=max(activation),
                all_header_n_max=32, all_header_k_max=256, all_raw_m_max=15,
                weight_storage_all_inputs_max=32 * 256 * max(weight),
                activation_storage_including_invalid_m_max=15 * 256 * max(activation),
                weight_row_max=256 * max(weight), activation_row_max=256 * max(activation))


def source_contract(texts):
    decoder = clean(texts['qbs_descriptor_decoder.sv']); engine = clean(texts['qbs_engine.sv'])
    read = clean(texts['qbs_read_engine.sv'])
    anchors = {
        'qbs_descriptor_decoder.sv': ["n_o = {1'b0, descriptor_header_i[24:20]} + 1'b1;",
            "k_blocks_o = {1'b0, descriptor_header_i[32:25]} + 1'b1;", "padded_rows = (n_o + 3) & 6'h3c;",
            'weight_rows = weight_layout_o == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR', '? padded_rows : n_o;',
            'weight_rows * k_blocks_o * weight_block_bytes_o;', 'm_i * k_blocks_o * activation_block_bytes_o;',
            "(context_id_o != '0 || context_generation_o != '0)",
            "unsigned'(context_id_o) >= QbsActivationContextCount", 'valid_o = error_o == QBS_VALIDATION_OK;'],
        'qbs_engine.sv': ['if (state_q == QBS_ENGINE_VALIDATE && descriptor_valid) begin',
            'context_id_q <= descriptor_context_id;', 'weight_block_bytes_q <= descriptor_weight_block_bytes;',
            'activation_block_bytes_q <= descriptor_activation_block_bytes;',
            'weight_row_bytes_q <= descriptor_k_blocks * descriptor_weight_block_bytes;',
            'activation_row_bytes_q <= descriptor_k_blocks * descriptor_activation_block_bytes;',
            "assign context_m = unsigned'(m_q) <= QbsActivationContextMaxM", "? 3'(m_q) : '0;",
            '.weight_storage_bytes_o       (descriptor_weight_storage_bytes),',
            '.activation_storage_bytes_o   (descriptor_activation_storage_bytes),',
            '.weight_block_bytes_o         (descriptor_weight_block_bytes),',
            '.activation_block_bytes_o     (descriptor_activation_block_bytes),'],
        'qbs_read_engine.sv': ["planned_ar_addr[BeatOffsetWidth-1:0] = '0;", 'ar_addr_q <= planned_ar_addr;',
            "ar_addr_q <= '0;", "translated_addr = AxiAddrWidth'(planner_cursor_q);",
            "translated_addr = AxiAddrWidth'(mmu_paddr_i);", 'span_bytes = first_lane + chunk_bytes;',
            'beat_count = (span_bytes + BeatBytes - 1) / BeatBytes;', 'bytes_to_page = 4096',
            'store_wait_cycles_o <= store_wait_cycles_o + 1\'b1;']}
    for name, tokens in anchors.items(): need(all(token in clean(texts[name]) for token in tokens), 'Source proof anchor changed: ' + name)
    for name in ('weight_block_bytes_q', 'activation_block_bytes_q', 'weight_row_bytes_q', 'activation_row_bytes_q'):
        need(len(re.findall(r'\b' + name + r'\s*<=', engine)) == 2, 'Unreviewed register writer: ' + name)
    need(len(re.findall(r'\bcontext_id_q\s*<=', engine)) == 3, 'Unreviewed context register writer')
    need(len(re.findall(r'\bar_addr_q\s*<=', read)) == 2, 'Unreviewed aligned address writer')
    return dict(anchors=anchors, register_assignment_counts_verified=True,
                induction='Reset zero, command reset zero where present, only VALIDATE&&descriptor_valid latches bounded registered values; errors/abort hold or reset them. Combinational decoder bounds include every invalid profile/layout/m encoding.',
                counterexample='Invalid raw m=15, K=256, activation block292 =>1121280, bit20=1; preserve bit20 of ungated activation-storage nets.',
                all_addresses_above_alignment_retained=True,
                unbounded_wait_backpressure_cycle_counters_retained=True,
                no_unknown_initialization_waiver=True)


def integer_params(definition):
    text = definition.get('param') or definition.get('name', '')
    return {m[1]: int(m[2]) for m in re.finditer(r'\b(\w+)=(\d+)(?=,|\s|\)|$)', text)}


def bind_scopes(design, info, shape):
    hierarchy = {}; nodes = {}
    for module in design.findall('srcdef'):
        for n in module.findall('srcinst'):
            need(n.get('id') not in nodes, 'Duplicate compiled instance')
            nodes[n.get('id')] = (n, module)
    def path(key, seen=()):
        need(key not in seen, 'Compiled hierarchy cycle'); n, _ = nodes[key]
        return (path(n.get('pid'), seen + (key,)) + '.' if n.get('pid') in nodes else '') + n.get('name')
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    shapes = {n.get('chksum'): n for n in shape.findall('tgldef')}
    for key, (n, module) in nodes.items():
        scope = path(key)
        if scope != QBS and not scope.startswith(QBS + '.'): continue
        need(scope not in hierarchy and scope in checks and checks[scope] in shapes, 'Incomplete QBS compiled identity')
        d = shapes[checks[scope]]
        need(d.get('name').split(' ( parameter', 1)[0].strip() == module.get('name') and
             (d.get('id') is None or d.get('id') == module.get('id')), 'Design/Toggle identity differs')
        hierarchy[scope] = dict(module=module.get('name'), design_checksum=module.get('chksum'),
                               compiled_instance=dict(n.attrib), checksum=checks[scope], definition=d)
    need(len(hierarchy) == 102, 'Not exact whole102 QBS instances')
    return hierarchy


def fields(definition, row):
    offset = 0; result = []; arrays = []
    bits = int(row['bits'], 16)
    for n in definition.find('tglshape'):
        need(n.tag in ('node', 'vectornode', 'arrays'), 'Unknown typed object')
        attrs = dict(n.attrib)
        if n.tag == 'arrays':
            arrays.append(dict(kind='arrays', attributes=attrs, complete_shape_xml=ET.tostring(n, encoding='unicode'),
                               missing=None, reason='Interval object has no direct instance_data coordinate; no guessed memory denominator'))
            continue
        width = 1 if n.tag == 'node' else abs(int(n.get('left')) - int(n.get('right'))) + 1
        p = dict(kind=n.tag, attributes=attrs, name=n.get('name'), width=width, raw_offset=offset)
        missing = []; pairs = []; slots = [0, 0]
        for i in range(width):
            pair = tuple(int(not bits >> (row['width'] - 1 - offset - 2 * i - slot) & 1) for slot in (0, 1))
            pairs.append(pair)
            for slot in (0, 1):
                slots[slot] += pair[slot]
                if pair[slot]: missing.append(offset + 2 * i + slot)
        p.update(missing=sum(slots), missing_pair_slots=slots, both_missing_pairs=sum(a and b for a, b in pairs),
                 one_missing_pairs=sum(a != b for a, b in pairs), missing_coordinates=missing)
        offset += 2 * width; result.append(p)
    need(offset == row['width'] and definition.get('chksum') == row['checksum'], 'Full typed local shape/bitmap mismatch')
    need(sum(p['missing'] for p in result) == row['width'] - bin(bits).count('1'), 'Typed missing partition differs')
    return result, arrays


def constant_rules(facts):
    w, a = facts['max_weight_size'], facts['max_activation_size']
    rules = [('', 'descriptor_weight_storage_bytes', 64, facts['weight_storage_all_inputs_max'].bit_length(), 63, 'ALL_INVALID_INPUTS_STORAGE_BOUND'),
             ('', 'descriptor_activation_storage_bytes', 64, facts['activation_storage_including_invalid_m_max'].bit_length(), 63, 'ALL_INVALID_M_STORAGE_BOUND'),
             ('', 'descriptor_weight_block_bytes', 16, w.bit_length(), 15, 'ALL_PROFILE_FUNCTION_BOUND'),
             ('', 'descriptor_activation_block_bytes', 16, a.bit_length(), 15, 'ALL_PROFILE_FUNCTION_BOUND'),
             ('', 'weight_block_bytes_q', 16, w.bit_length(), 15, 'VALID_DESCRIPTOR_REGISTER_INDUCTION'),
             ('', 'activation_block_bytes_q', 16, a.bit_length(), 15, 'VALID_DESCRIPTOR_REGISTER_INDUCTION'),
             ('', 'weight_row_bytes_q', 25, facts['weight_row_max'].bit_length(), 24, 'VALID_DESCRIPTOR_REGISTER_PRODUCT_BOUND'),
             ('', 'activation_row_bytes_q', 25, facts['activation_row_max'].bit_length(), 24, 'VALID_DESCRIPTOR_REGISTER_PRODUCT_BOUND'),
             ('', 'context_id_q', 4, 0, 3, 'VALID_ALL_ACCESS_CONTEXT_COUNT_ONE'),
             ('', 'context_m', 3, 1, 2, 'ALL_RAW_M_CONTEXT_MAX_ONE'),
             ('.i_descriptor_decoder', 'weight_rows', 64, 6, 63, 'ALL_HEADER_N_AND_PADDED_ROWS_BOUND'),
             ('.i_descriptor_decoder', 'padded_rows', 6, 0, 1, 'EXPLICIT_PADDED_ROW_MASK'),
             ('.i_read_engine', 'ar_addr_q', 64, 0, 3, 'RESET_OR_PLANNED_AR_BEAT_ALIGNMENT')]
    return rules


def candidate(record, width, low, high, reason):
    a = record['attributes']
    need(record['kind'] == 'vectornode' and int(a['left']) == width - 1 and int(a['right']) == 0 and
         a['portnode'] == '0' and a['excluded'] == '0' and 0 <= low <= high < width,
         'Not exact internal full bounds / legal candidate range')
    # Existing source-bound QBS bit mapper uses ascending bit index at raw_offset+2*bit.
    coords = [record['raw_offset'] + 2 * bit + slot for bit in range(low, high + 1) for slot in (0, 1)]
    missing = set(record['missing_coordinates'])
    need(set(coords) <= missing, 'Observed toggle contradicts source-bound constant / serialized mapping')
    return dict(scope=record['scope'], module=record['module'], name=record['name'],
                attributes=a, source_binding=record['source_binding'], full_width=width,
                candidate_bit_range=[high, low], value=0, missing_raw_directions=len(coords),
                raw_coordinates=coords, source_reason=reason, entire_object_not_excluded=True,
                native_type_and_direction_qualification_pending=True)


def data_class(module, name):
    if module in ('qbs_payload_sram', 'tc_sram', 'tc_sram_impl') and any(t in name for t in ('data', 'mem')):
        return 'SRAM_DATA_DEFINED_WRITES_REQUIRED_NO_INITIAL_X_WAIVER'
    if name.endswith(('.hit', '.word_match')) or any(t in name for t in ('target', 'location', 'pending_target', 'selected_word')):
        return 'MAPPING_ARBITRATION_METADATA_NOT_DATA_ENTROPY_PROOF'
    if any(t in name for t in ('wdata', 'rdata', 'data', 'window', 'older', 'newer', 'quant', 'scale', 'operand')):
        return 'DATA_OR_NUMERICAL_METADATA_PATTERN_CANDIDATE_NOT_UNREACHABLE'
    if any(t in name for t in ('addr', 'vaddr', 'base', 'descriptor')):
        return 'ADDRESS_DESCRIPTOR_ERROR_PATH_RETAIN'
    if any(t in name for t in ('count', 'cycles', 'occupancy', 'sequence', 'bytes', 'row', 'index', '_k_', 'beat')):
        return 'COUNTER_INDEX_BOUND_REQUIRES_SOURCE_INDUCTION_NOT_CURRENT_CASE_MAX'
    return 'CONTROL_STATUS_FLAGS_VALID_READY_ABORT_RETAIN'


def entropy_header(path):
    text = path.read_text(); arrays = []
    for m in re.finditer(r'const uint64_t ((?:weight|activation)\d+)\[(\d+)\][^=]*=\{([^}]+)\};', text):
        words = re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', m[3])
        need(len(words) == int(m[2]) and not re.sub(r'UINT64_C\(0x[0-9a-f]+\)|[\s,]', '', m[3]), 'Unexpected literal data initializer')
        data = b''.join(int(word, 16).to_bytes(8, 'little') for word in words)
        counts = Counter(data); entropy = -sum(n / len(data) * math.log2(n / len(data)) for n in counts.values())
        arrays.append(dict(name=m[1], bytes=len(data), unique_bytes=len(counts), zero_bytes=counts[0],
                           entropy_bits_per_byte=round(entropy, 5), byte_or=hex(__import__('functools').reduce(int.__or__, data)),
                           byte_and=hex(__import__('functools').reduce(int.__and__, data)),
                           most_common=counts.most_common(8)))
    need(len(arrays) == 8, 'Exact matrix4 weight/activation images required')
    return dict(path=str(path), arrays=arrays,
                limitation='Aggregate byte entropy from one admitted matrix4 fixture, not temporal coverage or proof about all766 tests. High aggregate entropy cannot prove each physical SRAM lane changed; cross-command same-byte variation and accepted write enables must be measured.',
                all_temporal_causes_proven=False)


def collect():
    pins = {}
    def pin(path, expected=None):
        if str(path) in pins:
            need(expected is None or pins[str(path)] == expected, 'Conflicting evidence pin'); return pins[str(path)]
        value = digest(path); need(expected is None or value == expected, 'Input pin drift: ' + str(path))
        pins[str(path)] = value; return value
    manifest = load(BASE / 'admission-manifest.json', BASE_SHA); pin(BASE / 'admission-manifest.json', BASE_SHA)
    ledger_path = BASE / 'combined-inputs.txt'; pin(ledger_path, manifest['output_pins'][str(ledger_path)])
    inputs = ledger_path.read_text().splitlines()
    need(len(inputs) == len(set(inputs)) == 767, 'Not formal766 unique ledger')
    status_path = BASE / 'status.json'; pin(status_path, manifest['output_pins'][str(status_path)])
    status = load(status_path); need(status['aggregate_passed'] == 766 and status['coverage_admitted'], 'Formal766 not admitted')
    cache = load(f.CACHE, f.CACHE_SHA); pin(f.CACHE, f.CACHE_SHA)
    oldledger = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pin(oldledger, cache['input_pins'][str(oldledger)])
    need(inputs[:742] == oldledger.read_text().splitlines() and cache['tests'] == 741, 'Cached741 exact prefix differs')
    identity = load(IDENTITY, IDENTITY_SHA); pin(IDENTITY, IDENTITY_SHA)
    compiled_paths = [DB / name for name in ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml',
                                            'shape/tgl.verilog.shape.xml', 'auxiliary/verilog.sourceinfo.xml')]
    for p in compiled_paths: pin(p, identity['pins'][str(p)])
    design, info, shape, sources = [f.xml(p) for p in compiled_paths]
    scopes = bind_scopes(design, info, shape)
    expected = {s for s in cache['instances'] if s == QBS or s.startswith(QBS + '.')}
    need(set(scopes) == expected, 'Raw/cache compiled full102 scope universe differs')
    book_path = f.BUILD / 'build-source-pins.json'
    pin(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'); book = load(book_path)
    pin(f.BUILD / 'sim/simv', '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3')
    source_files = {n.get('id'): Path(n.get('name')) for n in sources.iter('fileinfo')}
    texts = {}
    for p in [PKG, *SOURCE_DIR.glob('*.sv'), ROOT / 'hardware/src/vlsu/vlsu.sv']:
        pin(p, book[str(p)]); texts[p.name] = p.read_text()
    facts = bound_facts(texts['qbs_pkg.sv']); proof = source_contract(texts)
    params = {s: integer_params(v['definition']) for s, v in scopes.items()}
    need({k: params[QBS][k] for k in ('AxiDataWidth', 'AxiAddrWidth', 'VAddrWidth', 'PAddrWidth', 'NrLanes', 'VLEN')} ==
         dict(AxiDataWidth=128, AxiAddrWidth=64, VAddrWidth=64, PAddrWidth=56, NrLanes=4, VLEN=1024), 'Frozen parent parameters differ')
    need(params[QBS + '.i_read_engine']['BeatBytes'] == 16 and
         params[QBS + '.i_read_engine']['QueueDepth'] == 2 and params[QBS + '.i_descriptor_decoder']['VLEN'] == 1024,
         'Frozen child parameters differ')
    rows = {s: dict(width=cache['instances'][s]['width'], checksum=cache['instances'][s]['checksum'],
                    bits=cache['instances'][s]['bits']) for s in scopes}
    for index, vdb in enumerate(inputs[742:], 1):
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files) == 1, 'Ambiguous suffix native test')
        p = files[0]; pin(p, manifest['input_pins'][str(p)]); found = set()
        with gzip.open(p, 'rb') as stream:
            for _, n in ET.iterparse(stream, events=('end',)):
                if n.tag != 'instance_data': continue
                s = n.get('name')
                if s in rows:
                    value = n.get('value'); need(s not in found and n.get('chksum') == scopes[s]['checksum'] == rows[s]['checksum']
                        and len(value) == rows[s]['width'] and not set(value) - {'0', '1'}, 'Native suffix shape/identity differs')
                    found.add(s); rows[s]['bits'] = hex(int(rows[s]['bits'], 16) | int(value, 2))
                n.clear()
        need(found == set(scopes), 'Missing native suffix QBS scope')
        if index % 5 == 0: print('Readonly full102 union suffix %d/25' % index, flush=True)
    allrecords = []; arrayrecords = []; summaries = []; declarations = {}
    for s, v in sorted(scopes.items()):
        typed, arrays = fields(v['definition'], rows[s])
        for p in typed + arrays:
            a = p['attributes']; path = source_files[a['file']]; pin(path, book[str(path)])
            if str(path) not in declarations: declarations[str(path)] = path.read_text().splitlines()
            p.update(scope=s, module=v['module'], checksum=v['checksum'], design_checksum=v['design_checksum'],
                source_binding=dict(path=str(path), sha256=pins[str(path)], file_id=a['file'], line=int(a['line_num']),
                    declaration=declarations[str(path)][int(a['line_num']) - 1],
                    aux_file=a.get('aux_file'), aux_line=a.get('aux_line_num')),
                classification=data_class(v['module'], a['name']),
                compiled_parameters=v['definition'].get('param') or v['definition'].get('name'))
        allrecords.extend(typed); arrayrecords.extend(arrays)
        summaries.append(dict(scope=s, module=v['module'], checksum=v['checksum'], design_checksum=v['design_checksum'],
            compiled_instance=v['compiled_instance'], integer_parameters=params[s],
            raw_width=rows[s]['width'], missing=sum(p['missing'] for p in typed), scalar_vector_objects=len(typed),
            arrays=len(arrays), bits=rows[s]['bits']))
    by_name = {(p['scope'], p['name']): p for p in allrecords}
    candidates = []
    for suffix, name, width, low, high, reason in constant_rules(facts):
        key = (QBS + suffix, name); need(key in by_name, 'Missing exact source-bound constant object')
        candidates.append(candidate(by_name[key], width, low, high, reason))
    top = sorted((p for p in allrecords if p['missing']), key=lambda p: (-p['missing'], p['scope'], p['name']))[:50]
    data_top = sorted((p for p in allrecords if p['missing'] and p['classification'].startswith(('DATA_', 'SRAM_'))),
                      key=lambda p: (-p['missing'], p['scope'], p['name']))[:50]
    evidence = entropy_header(MATRIX / 'matrix_data.h')
    preflight = load(MATRIX / 'preflight-manifest.json', '04d9e8a86a035f4d30c4f100fea82a80def3f0154c4260e45a4891783f1b700e')
    pin(MATRIX / 'preflight-manifest.json', '04d9e8a86a035f4d30c4f100fea82a80def3f0154c4260e45a4891783f1b700e')
    pin(MATRIX / 'matrix_data.h', preflight['output_pins'][str(MATRIX / 'matrix_data.h')])
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_audit_qbs_engine_residual766.py'), Path(f.__file__).resolve()): pin(p)
    for p, sha in pins.items(): need(digest(p) == sha, 'Input changed during full-engine audit')
    return dict(status='FORMAL766_FULL102_QBS_TYPED_STATIC_REVIEW_NO_EDA', population=766, baseline_seal=BASE_SHA,
        engine_scope=QBS, instances=102, scope_summaries=summaries,
        total_serialized_positions=sum(p['raw_width'] for p in summaries),
        total_raw_missing=sum(p['missing'] for p in summaries),
        typed_scalar_vector_objects=len(allrecords), interval_arrays=len(arrayrecords),
        all_typed_fields=allrecords, all_arrays_without_binary_coordinate=arrayrecords,
        top50_objects=top, top50_data_objects=data_top,
        source_parameter_facts=facts, source_induction=proof, source_constant_candidates=candidates,
        source_constant_candidate_missing=sum(p['missing_raw_directions'] for p in candidates),
        binary_bit_order='Existing source-bound QBS mapper raw_offset+2*bit for descending vectors right0; aligned AR low4 bits crosschecked00. Pair-slot0/1 are NOT claimed 0to1/1to0 until native qualification.',
        entropy_evidence=evidence,
        stimulus_direction=dict(status='ONE_SOURCE_BOUND_PATTERN_DIRECTION_NOT_PREPARED_OR_MEASURED',
            profile='Q6_K weights + Q8_K activation', shape=dict(m=8, n=8, k_blocks=2),
            layouts='R4_BLOCK_MAJOR weights; M8_INTERLEAVED activation; all bases legal aligned',
            temporal_sequence='A, complement of quant payload A, A; same logical payload SRAM addresses, both adapter banks via N8 and K2',
            quant_bytes='A deterministic lane-distinct full-byte PRBS or byte-index permutation; XOR ff only in Q6 ql/qh and Q8 quant bytes, not descriptor/side metadata',
            scales='FP16 weight d=1, FP32 activation d=1; Q6 signed subgroup scales from {-3,-1,1,3}, no zero-only or NaN/Inf. Keep Q8_K bsums recomputed from each signed activation block.',
            independent_oracle='Reuse all-format qbs_ref decoder plus separate integer dot reference, full destination VRF/fflags/guard/source readbacks/terminal protocol. abs bound <=3*32*128*512=6291456 <2^24 gives exact finite FP32 integer accumulation.',
            falsifiable_cause='Low temporal input entropy: ingress strobes and source quant bytes A->~A->A change, same accepted write address/byte lanes change in both banks; then readback/window/quant payload directions improve. If write not accepted or word_match/source_valid/pending prevents it, arbitration/routing rather than entropy is responsible.',
            target_categories=[p['classification'] for p in data_top[:8]],
            predicted_gain=None, no_internal_force=True, no_waiver_for_unwritten_or_initial_X_memory=True),
        protected_rejections=['Unbounded cycles/wait/backpressure/occupancy sums: no finite environment timeout bound',
            'All address upper bits and overflow carry: translation bypass, high bases, invalid/overflow error paths retained',
            'Descriptor raw profile/layout/context/reserved bits: illegal values are meaningful validation inputs',
            'K9 bit8=256, N6 bit5=32, M4 bit3=8 are legal; do not waive their top bits',
            'Metadata/arbitration hit gaps are not evidence that SRAM data bits are unreachable',
            'SRAM interval arrays have no direct serialized coordinate; do not invent missing counts',
            'All profiles9+2, both weight layouts, ROW/M4/M8, DIRECT/FILL/REUSE/error/abort remain'],
        diagnostic_capacity_not_official_denominator=True, official_percentage=None,
        source_candidates_not_native_qualified=True, coverage_admitted=False, no_simulation=True, no_EDA=True,
        formal767_not_read_or_modified=True, pins=pins)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(); need(args.output.parent.resolve() == OUT and not args.output.exists(), 'Fresh independent output required')
    record = collect()
    with args.output.open('x') as stream: json.dump(record, stream, indent=2); stream.write('\n')
    table = args.output.with_suffix('.top50.csv')
    with table.open('x', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['rank', 'scope_relative_to_qbs', 'module', 'name', 'kind', 'left', 'right', 'width', 'missing', 'slot0_missing', 'slot1_missing', 'both_missing_pairs', 'class', 'source', 'line'])
        for i, p in enumerate(record['top50_objects'], 1):
            a = p['attributes']; b = p['source_binding']
            writer.writerow([i, p['scope'][len(QBS):] or '.', p['module'], p['name'], p['kind'], a.get('left', ''), a.get('right', ''), p['width'], p['missing'], *p['missing_pair_slots'], p['both_missing_pairs'], p['classification'], b['path'], b['line']])
    print(json.dumps(dict(output=str(args.output), seal=digest(args.output), table=str(table), table_sha256=digest(table),
                          instances=102, missing=record['total_raw_missing'], constants=record['source_constant_candidate_missing'])), flush=True)
