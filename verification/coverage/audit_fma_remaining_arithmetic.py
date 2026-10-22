"""Frozen static FMA ownership/overlap audit; no simulator or native launch."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

import review_srt_radix16_child_residual as frozen

ROOT, OUT, DB = frozen.ROOT, frozen.OUT, frozen.DB
need, digest, load = frozen.need, frozen.digest, frozen.load
SOURCE = ROOT / 'hardware/deps/fpnew/src/fpnew_fma.sv'
REVIEW = OUT / 'fma-internal-arithmetic-source-review-agent-20261007-01/source-review.json'
REVIEW_SHA = '22e2698705134cf14acf40a14c76385f8e253dfa295c605871e80ef168814dec'
FROZEN_IDENTITY = OUT / 'cva6-parent-rvfi-output-source-review763-agent-20261007-01.json'
FROZEN_IDENTITY_SHA = 'f5e448c55889ad9d783a6c718a3d3000a2d39e53d5af9a23d1ef562a74754bbb'
SCALAR_ALLOW = {'exponent_a': (281, 287, 287), 'exponent_b': (281, 288, 288),
                'exponent_c': (281, 289, 289), 'exponent_addend': (282, 292, 292),
                'sum_raw': (369, 375, 375)}
SCALAR_CHECKS = {'3893821548': (10, 77), '2370198160': (13, 164)}
CAPTURES = {'fma612': ('fma_expanded_native_612-agent-20261007-04', 612,
                     'EXACT_612_FMA_EXPANDED_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS'),
            'half816': ('half-fma816-native-agent-20261007-01', 816,
                       'EXACT_HALF_FMA816_NATIVE_FIVE_STAGE_QUALIFIED_NOT_APPLIED'),
            'scalar22': ('scalar-fma22-native-agent-20261007-01', 22,
                        'EXACT_SCALAR_FMA22_NATIVE_ROUNDTRIP_QUALIFIED')}


def baseline_bytes(source, expected, baseline):
    need(digest(source) == expected and source.read_bytes() == baseline,
         'Frozen source is not byte-identical to import baseline')


def hierarchy(design):
    defs = {n.get('id'): n for n in design.iter('srcdef')}
    instances = {n.get('id'): (n, d) for d in defs.values() for n in d.findall('srcinst')}
    def scope(key):
        n, _ = instances[key]
        return (scope(n.get('pid')) + '.' if n.get('pid') in instances else '') + n.get('name')
    rows = [dict(scope=scope(key), module=d.get('name'), design_checksum=d.get('chksum'),
                 compiled_instance=dict(n.attrib), definition_id=d.get('id')) for key, (n, d) in instances.items()]
    roots = [p for p in rows if p['module'] == 'fpnew_fma']
    need(len(roots) == 32 and all(p['scope'].endswith('.i_fma') for p in roots), 'Frozen32 FMA roots differ')
    children = [p for p in rows if any(p['scope'].startswith(s['scope'] + '.') for s in roots)]
    need(len(children) == 96 and Counter(p['module'] for p in children) ==
         Counter(lzc=32, fpnew_classifier=32, fpnew_rounding=32),
         'FMA child universe changed; arithmetic helper absence not proven')
    return roots, children, rows


def scalar_partition(scope, checksum, nodes, prior):
    need('.i_ariane.' in scope and checksum in SCALAR_CHECKS, 'Not evidence-bound scalar F/D instance')
    need(len(nodes) == len({n['attributes']['name'] for n in nodes}), 'Duplicate compiled shape')
    need(prior.isdisjoint(SCALAR_ALLOW), 'Numerical proposal duplicates qualified objects')
    exponent_width, sum_width = SCALAR_CHECKS[checksum]
    target, protected = [], []
    for p in nodes:
        a = p['attributes']; name = a['name']
        if name not in SCALAR_ALLOW:
            protected.append(p); continue
        line, first, last = SCALAR_ALLOW[name]
        width = sum_width if name == 'sum_raw' else exponent_width
        need(p['kind'] == 'vectornode' and a == dict(name=name, file='381', line_num=str(line),
             type='1', portnode='0', excluded='0', left=str(width - 1), right='0'),
             'Exact internal whole arithmetic shape differs')
        target.append(dict(p, source_definition_lines=[first, last],
                           source_class='COMBINATIONAL_SIGNED_EXPONENT_VALUE' if name != 'sum_raw'
                           else 'COMBINATIONAL_FULL_RAW_ADD_VALUE_CARRY_DECISION_RETAINED'))
    need({p['attributes']['name'] for p in target} == set(SCALAR_ALLOW), 'Missing source-selected arithmetic object')
    return target, protected


def shape_fields(definition, raw):
    rows = []; offset = 0
    for n in definition.find('tglshape'):
        need(n.tag in ('arrays', 'node', 'vectornode'), 'Unknown compiled shape')
        width = None if n.tag == 'arrays' else 1 if n.tag == 'node' else abs(int(n.get('left')) - int(n.get('right'))) + 1
        p = dict(kind=n.tag, attributes=dict(n.attrib), width=width, raw_offset=None if width is None else offset,
                 complete_shape_xml=__import__('xml.etree.ElementTree', fromlist=['tostring']).tostring(n, encoding='unicode'))
        if width is not None:
            p['missing_raw741'] = frozen.direction_missing(int(raw['bits'], 16), raw['width'], p)
            offset += 2 * width
        else:
            p['missing_raw741'] = None
        rows.append(p)
    need(offset == raw['width'] and raw['checksum'] == definition.get('chksum'), 'Local binary shape/bitmap differs')
    return rows


def collect():
    pins = {}
    def pin(path, expected=None):
        if str(path) in pins:
            need(expected is None or pins[str(path)] == expected, 'Conflicting source/evidence pin')
            return pins[str(path)]
        value = digest(path); need(expected is None or value == expected, 'Pin drift: ' + str(path))
        pins[str(path)] = value; return value
    book_path = frozen.BUILD / 'build-source-pins.json'
    pin(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    sourcebook = load(book_path)
    pin(frozen.BUILD / 'sim/simv', '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3')
    review = load(REVIEW, REVIEW_SHA); pin(REVIEW, REVIEW_SHA)
    frozen_identity = load(FROZEN_IDENTITY, FROZEN_IDENTITY_SHA); pin(FROZEN_IDENTITY, FROZEN_IDENTITY_SHA)
    cache = load(frozen.CACHE, frozen.CACHE_SHA); pin(frozen.CACHE, frozen.CACHE_SHA)
    compiled = [DB / s for s in ('design/verilog.design.xml', 'shape/tgl.verilog.shape.xml',
                                'shape/tgl.verilog.info.xml', 'auxiliary/verilog.sourceinfo.xml')]
    for path in compiled: pin(path)
    # Bind all metadata, including sourceinfo, to the independently reviewed frozen image.
    for path in compiled:
        need(str(path) in frozen_identity['pins'] and pins[str(path)] == frozen_identity['pins'][str(path)],
             'Compiled frozen source identity pin differs')
        if str(path) in review['pins']:
            need(pins[str(path)] == review['pins'][str(path)], 'Prior FMA compiled pin differs')
    design, shape, info, sources = [frozen.xml(p) for p in compiled]
    roots, children, allrows = hierarchy(design)
    scope_rows = {p['scope']: p for p in allrows}
    module_sources = {n.get('id'): n.get('name') for n in sources.iter('fileinfo')}
    vendor = []; unchanged = []
    source_list = [Path(name) for name in module_sources.values() if '/vendor/openc910/' in name]
    need(len(source_list) == 11 and all('/vfdsu/rtl/' in str(p) for p in source_list),
         'Frozen C910 source universe changed')
    source_list += [SOURCE, ROOT / 'hardware/deps/fpnew/src/fpnew_rounding.sv',
                    ROOT / 'hardware/deps/fpnew/src/fpnew_classifier.sv']
    for path in source_list:
        rel = str(path.relative_to(ROOT / 'hardware/deps/fpnew'))
        baseline = subprocess.run(['git', '-C', str(ROOT / 'hardware/deps/fpnew'), 'show', frozen.UPSTREAM + ':' + rel],
                                  cwd=ROOT, check=True, capture_output=True).stdout
        pin(path, sourcebook[str(path)])
        equal = path.read_bytes() == baseline
        if equal:
            baseline_bytes(path, sourcebook[str(path)], baseline)
        else:
            need(path.name == 'ct_vfdsu_round.v', 'Unexpected modified source; candidate proof must stop')
        proof = dict(path=str(path), sha256=pins[str(path)], import_commit=frozen.UPSTREAM,
                     import_path=rel, baseline_sha256=__import__('hashlib').sha256(baseline).hexdigest(), bytes_equal=equal,
                     eligibility='UNCHANGED_SOURCE_ONLY_NOT_AUTOMATIC_WAIVER' if equal else
                                 'MODIFIED_ROUND_FLAGS_SOURCE_ALL_OBJECTS_PROTECTED')
        if not equal:
            old = baseline.decode().splitlines(); new = path.read_text().splitlines()
            import difflib
            proof['changed_source_spans'] = [dict(operation=op, import_lines=[a + 1, b], frozen_lines=[c + 1, d],
                import_text=old[a:b], frozen_text=new[c:d])
                for op, a, b, c, d in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes() if op != 'equal']
        unchanged.append(proof)
        if '/vendor/openc910/' in str(path): vendor.append(proof)
    source_text = SOURCE.read_text(); lines = source_text.splitlines()
    need(lines[331].strip() == 'assign product = mantissa_a * mantissa_b;' and
         lines[374].strip() == 'assign sum_raw = product_shifted + addend_shifted + inject_carry_in;',
         'FMA multiplier/adder actual source anchors differ')
    lzc = ROOT / 'hardware/deps/common_cells/src/lzc.sv'; pin(lzc, sourcebook[str(lzc)])
    commit = subprocess.run(['git', '-C', str(lzc.parents[1]), 'rev-parse', 'HEAD'], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout.strip()
    original_lzc = subprocess.run(['git', '-C', str(lzc.parents[1]), 'show', commit + ':src/lzc.sv'], cwd=ROOT,
                                  check=True, capture_output=True).stdout
    baseline_bytes(lzc, sourcebook[str(lzc)], original_lzc)
    unchanged.append(dict(path=str(lzc), sha256=pins[str(lzc)], import_commit=commit,
                          baseline_sha256=__import__('hashlib').sha256(original_lzc).hexdigest(),
                          bytes_equal=True, baseline_kind='Dependency git HEAD, not C910'))
    qualified = {}; capture_evidence = []
    for policy, (directory, expected, status) in CAPTURES.items():
        output = OUT / directory; result_path = output / 'capture-result.json'
        result = load(result_path); pin(result_path)
        need(result['status'] == status and result['objects'] == expected, 'Not exact native predecessor')
        config = load(output / 'config.json'); pin(output / 'config.json', result.get('config_seal'))
        count = 0
        for i in config['instances']:
            need(i['scope'] in scope_rows and scope_rows[i['scope']]['module'] == 'fpnew_fma', 'Prior scope not actual FMA')
            points = i['signals'] if policy == 'scalar22' else i['targets']
            for p in points:
                key = (i['scope'], p['name']); need(key not in qualified, 'Duplicate qualified arithmetic object')
                qualified[key] = policy; count += 1
        need(count == expected, 'Exact predecessor object union differs')
        capture_evidence.append(dict(policy=policy, path=str(result_path), sha256=pins[str(result_path)],
                                     status=status, objects=count))
    evidence = []
    for ev in review['evidence']:
        for p in ev['pins']: pin(ROOT / p['path'], p['sha256'])
        need(ev['vector_overall_status'] == 'PASS' and ev['scalar_status'] == 'TERMINAL_MATCH' and
             all(p['status'] == 'PASS' and p['mismatch_count'] == 0 and p['skipped_unknown_bytes'] == 0
                 for p in ev['selected_exact_requests']), 'Selected F/D architectural evidence differs')
        evidence.append(ev)
    scalarq = OUT / 'scalar-fpu-finite-qualified-agent-20261007-01/qualification.json'
    scalar = load(scalarq); pin(scalarq, 'df01c882f68fe9035a4563421c76d19cfe17cd7e07f7037967c6f101472f5569')
    need(scalar['status'] == 'EXACT20_SCALAR_FP_RATIONAL_SPIKE_DUT_QUALIFIED' and
         (scalar['operations'], scalar['result_flags_checks'], scalar['guard_checks']) == (20, 40, 35),
         'Scalar actual result/flag evidence differs')
    for group in ('input_pins', 'output_pins'):
        for path, sha in scalar[group].items(): pin(Path(path), sha)
    halfq = OUT / 'half-fma-source-tail-qualified-agent-20261007-01/qualification.json'
    half = load(halfq); pin(halfq, 'c80479bddc7569c3e6d36afc958121a52e50476b8f2bfdb5c79bbfc78821c568')
    need(half['status'] == 'FOUR_PHASE_HALF_FMA_FUNCTIONALLY_QUALIFIED_NOT_ADMITTED' and
         half['FMA_observations']['accepted'] == half['FMA_observations']['completed'] == 224 and
         half['FMA_observations']['raw_results_and_flags_checked_even_when_mask_zero'], 'Half result/flags contract differs')
    for path, sha in half['pins'].items(): pin(Path(path), sha)
    tgldefs = {p.get('chksum'): p for p in shape.findall('tgldef')}
    native_info = {p.get('name'): p.get('chksum') for p in info.iter('instance_data')}
    arithmetic_bases = {name for names in review['source_groups'].values() for name in names}
    records = []; proposals = []; complements = []; child_records = []; declarations = {}
    for row in roots + children:
        scope = row['scope']; raw = cache['instances'][scope]; checksum = raw['checksum']
        need(native_info[scope] == checksum, 'Compiled specialization differs')
        definition = tgldefs[checksum]
        need(definition.get('id') == row['definition_id'], 'Design/Toggle module identity differs')
        fields = shape_fields(definition, raw)
        for f in fields:
            a = f['attributes']; name = a['name']; prior = qualified.get((scope, name))
            if prior:
                need(a['file'] == '381' and a['portnode'] == '0' and a['excluded'] == '0', 'Prior target shape differs')
                f['classification'] = 'ALREADY_QUALIFIED_' + prior.upper()
            elif a['portnode'] != '0': f['classification'] = 'PROTECTED_ALL_INTERFACES'
            elif row['module'] == 'fpnew_rounding': f['classification'] = 'PROTECTED_ROUNDING_FLAGS_BOUNDARY'
            elif row['module'] == 'fpnew_classifier': f['classification'] = 'PROTECTED_SPECIALCASE_CLASSIFICATION'
            elif row['module'] == 'lzc': f['classification'] = 'PROTECTED_NORMALIZATION_PRIORITY_SELECT_EMPTY_BOUNDARY'
            elif scope in {p['scope'] for p in roots if '.i_ariane.' in p['scope']} and checksum in SCALAR_CHECKS and name in SCALAR_ALLOW:
                f['classification'] = 'SOURCE_PURE_OPTIONAL_SCALAR_PROPOSAL_NOT_APPROVED'
            elif name.split('.', 1)[0] in arithmetic_bases:
                f['classification'] = 'HELD_NUMERICAL_FAMILY_NO_NEW_SCOPE_OR_EVIDENCE_AUTHORIZATION'
            else: f['classification'] = 'PROTECTED_CONTROL_PIPELINE_METADATA_ROUND_FLAGS_SPECIALCASE'
            f['source_file'] = module_sources[a['file']]
            pin(Path(f['source_file']), sourcebook[f['source_file']])
            if f['source_file'] not in declarations:
                declarations[f['source_file']] = Path(f['source_file']).read_text().splitlines()
            f['declaration'] = declarations[f['source_file']][int(a['line_num']) - 1]
        entry = dict(row, toggle_checksum=checksum, compiled_parameters=definition.get('name'),
                     local_serialized_width=raw['width'], raw741_local_missing=raw['missing'], fields=fields)
        if row['module'] == 'fpnew_fma':
            if checksum in SCALAR_CHECKS and '.i_ariane.' in scope:
                prior = {name for s, name in qualified if s == scope}
                targets, protection = scalar_partition(scope, checksum, fields, prior)
                for p in targets:
                    first, last = p['source_definition_lines']; p['source_definition'] = '\n'.join(lines[first - 1:last])
                    proposals.append(dict(p, scope=scope, toggle_checksum=checksum,
                                          design_checksum=row['design_checksum'], source_baseline_commit=frozen.UPSTREAM))
                complements.append(dict(scope=scope, protected=protection))
            records.append(entry)
        else: child_records.append(entry)
    need(len(qualified) == 1450 and len(proposals) == 10, 'Qualified/proposed exact object count differs')
    # Qualified objects have no overlap with the optional proposals; no hit-selected fields.
    need(not {(p['scope'], p['attributes']['name']) for p in proposals} & set(qualified), 'Overlap with prior native waivers')
    child_rank = sorted([dict(scope=p['scope'], module=p['module'], missing=p['raw741_local_missing'],
                             serialized_width=p['local_serialized_width'], all_fields_protected=True)
                         for p in child_records], key=lambda p: p['missing'], reverse=True)
    pin(Path(__file__).resolve()); pin(Path(__file__).with_name('test_audit_fma_remaining_arithmetic.py'))
    pin(Path(frozen.__file__).resolve())
    for path, sha in pins.items(): need(digest(path) == sha, 'Evidence changed during static audit')
    return dict(status='STATIC_FMA_OWNERSHIP_AND_EXACT_REMAINING_SCOPE_REVIEW_NO_EDA',
        frozen_image_sha256=pins[str(frozen.BUILD / 'sim/simv')], baseline_population=741,
        no_C910_FMA_compiled=True, C910_compiled_sources=vendor,
        actual_FMA_owner='fpnew_fma:32 scopes, multiplication source line332, addition line375, no separate arithmetic child',
        source_baseline_comparisons=unchanged,
        unchanged_baseline_proofs=[p for p in unchanged if p['bytes_equal']],
        modified_C910_round_source_protected=[p for p in vendor if not p['bytes_equal']],
        actual_FMA_roots=records, protected_FMA_children=child_records,
        child_missing_ranking=child_rank, already_qualified_objects=1450, previous_native_evidence=capture_evidence,
        FP32_FP64_architectural_evidence=evidence, scalar_result_flag_evidence=str(scalarq),
        half_result_flag_evidence=str(halfq), scalar_evidence_limit='20 finite F/D operations RNE/RUP; not all IEEE values/modes; no scalar FP16 evidence',
        new_C910_FMA_arithmetic_children_candidates=[], new_C910_FMA_candidate_missing=0,
        optional_FPnew_scalar_whole_object_candidates=proposals,
        optional_candidate_objects=10, optional_candidate_logical_bits=sum(p['width'] for p in proposals),
        optional_candidate_raw741_missing=sum(p['missing_raw741']['total'] for p in proposals),
        optional_scalar_full_complements=complements,
        recommendation='No C910 FMA child exists in frozen image. Do not launch new FMA EDA: optional source-pure scalar10 has only28 historical missing positions and raw adders have0. Preserve rounding/classifier/LZC/controls; choose another source-bound high-gain block.',
        missing_semantics='Exact raw741 local pair-slot positions, diagnostic capacity only; NOT current population residual, official denominator or official percentage. Arrays have no direct binary coordinate and are not assigned a guessed missing count.',
        whole_module_waiver=False, EDA_started=False, RTL_modified=False, exclusions_applied=False,
        native_qualified=False, no_full_IEEE_claim=True, pins=pins)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(); need(args.output.parent.resolve() == OUT and not args.output.exists(), 'Fresh output required')
    result = collect()
    with args.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(path=str(args.output), seal=digest(args.output), no_C910_FMA=True,
                         optional_candidates=result['optional_candidate_objects'],
                         optional_raw741_missing=result['optional_candidate_raw741_missing'])))
