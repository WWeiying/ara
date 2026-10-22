"""Prepare only: separate explicit population six-policy plus exact60cond plan."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import prepare_six_policy_population_v2 as population
import lzc_selector_native_four_state_proof as proof
from lzc_native_records import parse_records

frozen, require, sha = population.frozen, population.require, population.frozen.sha
PROOF_SEAL = '41a01351a3c8c966cb4eaffc31f39f418fbf9a450c0107c319ad754f44c08da0'
OUT = frozen.OUT


def split_seven(raw, six_config, cond_records):
    owners = six_config['scope_owners']
    scopes = {r['scope'] for r in cond_records}
    require(not scopes & owners.keys(), 'Seventh/six-policy scope ownership overlap')
    six, seventh = [], []
    require(raw.endswith(b'\n') and not re.search(rb'[^\x0a\x20-\x7e]', raw), 'Noncanonical native bytes')
    for chunk in re.split(r'(?m)(?=^CHECKSUM:)', raw.decode('ascii')):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        require(len(lines) >= 4 and re.fullmatch(r'CHECKSUM: "[0-9]+ [0-9]+"', lines[0]), 'Invalid header')
        match = re.fullmatch(r'INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)', lines[1])
        require(match and match[1] in (set(owners) | scopes), 'Extra native scope')
        (seventh if match[1] in scopes else six).append(chunk)
    six_bytes, seventh_bytes = ''.join(six).encode('ascii'), ''.join(seventh).encode('ascii')
    require(parse_records(seventh_bytes.decode('ascii')) == cond_records, 'Exact60 native signature set differs')
    return six_bytes, seventh_bytes


def latest_binding(review, bitmap, design):
    nodes, targets = {}, set()
    visible_counts = Counter((r['scope'], r['metric']) for r in review['exact_protection_rows'])
    for row in review['exact_protection_rows']:
        scope, metric = row['scope'], row['metric']
        if (scope, metric) not in nodes:
            node, points = proof.compiled_points(design, scope, metric)
            record = bitmap['metrics'][metric][scope]
            require(node.get('chksum') == record['checksum'] and len(points) == record['width'],
                    'Latest protection shape/checksum drift')
            nodes[scope, metric] = points
        if metric == 'branch':
            # Protected GUI IDs have no expression binding: preserve observed tokens,
            # not an invented XML->GUI mapping. Full compiled layout is hash-bound.
            require(visible_counts[scope, metric] == len(nodes[scope, metric])
                    and row['native_id'].isdigit() and row['vector'] in ('0', '1')
                    and row['expression'] is None, 'Observed protected branch inventory drift')
        else:
            matches = [p for p in nodes[scope, metric] if p['attributes']['optype'] != '16'
                       and p['expression'] == row['expression'] and p['vector'] == row['vector']]
            require(len(matches) == 1 and row['native_id'] is None,
                    'Exact visible condition expression/vector binding ambiguous or absent')
    keys = [(r['scope'], r['metric'], r['native_id'], r['expression'], r['vector'])
            for r in review['exact_protection_rows']]
    require(len(set(keys)) == len(keys) == 4200, 'Duplicate/incomplete observed protection inventory')
    for item in review['candidates']:
        candidate, native = item['candidate'], item['native_record']
        require(candidate['metric'] == 'cond' and native['vector'] == '1'
                and candidate['xml_provenance']['attributes']['optype'] == '23', 'Only op23 true cond allowed')
        require(design.hierarchy[candidate['scope']].get('chksum') == candidate['module_checksum']
                and proof.compiled_parameters(design.definition(candidate['scope'], 'tgl')) == candidate['parameters'],
                'Latest exact child module/parameters drift')
        point = nodes[candidate['scope'], 'cond'][candidate['xml_provenance']['raw_index']]
        require(point == candidate['xml_provenance'], 'Latest complete expression/spec signature drift')
        row = bitmap['metrics']['cond'][candidate['scope']]
        index = point['raw_index']
        require(not (int(row['bits'], 16) & (1 << (row['width'] - 1 - index))), 'New population hits candidate: RETAIN')
        require((candidate['scope'], index) not in targets, 'Duplicate candidate')
        targets.add((candidate['scope'], index))
    require(len(targets) == 60 and len(review['exact_protection_rows']) == 4200, 'Not exact60/4200')
    return targets


def prepare(six_output, six_seal, proof_output, output):
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh independent output required')
    six = frozen.load_sealed(six_output / 'config.json', six_seal)
    require(six['schema'] == population.prior.SCHEMA and six['population'] >= 723
            and six['targets'] == 5808 and six['protected'] == 13562 and not six['application_approval'],
            'Explicit latest sealed six-policy config required')
    review = frozen.load_sealed(proof_output / 'review.json', PROOF_SEAL)
    require(review['source_four_state_closure_proved'] and not review['frozen_four_state_initialization_qualified']
            and review['branch_hold'] == 60 and review['op16'] == 'HOLD' and not review['application_approval']
            and not review['native_instrumentation_X_semantics_measured'], 'Exact explicit source proof gates required')
    admission = Path(six['admitted_base'])
    manifest = frozen.load_sealed(admission / 'admission-manifest.json', six['admission_manifest_sha256'])
    pins = {}
    for group in (six['pins'], review['pins'], manifest['output_pins']):
        for path, expected in group.items():
            require(path not in pins or pins[path] == expected, 'Pin conflict: ' + path)
            pins[path] = expected
    bits_path = admission / 'combined-bits.json'
    require(sha(bits_path) == manifest['output_pins'][str(bits_path)], 'Sealed bitmap differs')
    bits = json.loads(bits_path.read_bytes())
    status = json.loads((admission / 'status.json').read_bytes())
    inputs = (admission / 'combined-inputs.txt').read_text().splitlines()
    population.prior.validate_population(bits, status, inputs, six['population'])
    require(inputs == six['inputs'], 'Exact selected population snapshot mismatch')
    design = proof.Design(Path(inputs[0]))
    for relative, expected in bits['design'].items():
        require(pins.get(str(design.db / relative)) == expected, 'Latest/proof compiled design hash drift')
    latest_binding(review, bits, design)
    for item in review['candidates']:
        require(proof.prove_candidate(item['candidate']) in review['proofs'], 'Four-state per-cone proof drift')
    native = [r['native_record'] for r in review['candidates']]
    six_bytes = (six_output / 'combined.el').read_bytes()
    cond_bytes = (proof_output / 'candidate60.el').read_bytes()
    combined = six_bytes + cond_bytes
    actual_six, actual_cond = split_seven(combined, six, native)
    require(actual_six == six_bytes and actual_cond == cond_bytes, 'Original6/extra60 native bytes changed')
    for path in (six_output / 'config.json', proof_output / 'review.json', proof_output / 'review.sha256.json',
                 admission / 'admission-manifest.json', Path(__file__).resolve(),
                 Path(__file__).with_name('test_lzc_selector_native_seven_policy_plan.py'),
                 Path(proof.__file__).resolve(), Path(population.__file__).resolve()):
        pins[str(path)] = sha(path)
    for path, expected in pins.items():
        require(sha(path) == expected, 'Sealed input drift: ' + path)
    output.mkdir()
    frozen.write(output / 'combined-seven-proposal.el', combined.decode('ascii'))
    pins[str(output / 'combined-seven-proposal.el')] = sha(output / 'combined-seven-proposal.el')
    plan = dict(status='PREPARED_SEVEN_POLICY_REVIEW_ONLY_NOT_EXECUTABLE_EDA_APPLICATION',
                population=six['population'], admission=str(admission), admission_sha256=six['admission_manifest_sha256'],
                six_config=str(six_output / 'config.json'), six_config_sha256=six_seal,
                source_proof=str(proof_output / 'review.json'), source_proof_sha256=PROOF_SEAL,
                original_six_targets=5808, original_six_protected=13562, extra_cond_targets=60,
                extra_cond_protected=2940, extra_branch_protected=1200,
                total_targets=5868, total_protected=17702, total_audited_positions=23570,
                condition_native_records=native, exact_lzc_protection_rows=review['exact_protection_rows'],
                branch_hold=60, op16='HOLD', source_four_state_closure_proved=True,
                frozen_four_state_initialization_qualified=False, native_X_semantics_measured=False,
                parent_acceptance_of_explicit_source_monitor_contract_required=True,
                frozen_lifecycle_budget_seconds=10800,
                gates=[
                    'Freeze new actual Tcl/runner/verifier dependencies before any launch; this plan has no launch entry.',
                    'Fresh same-session raw snapshot from exact sealed admission; no historical percentages inherited.',
                    'Combined-seven DVE reload must reproduce exact original6 native records plus only measured60 cond true vectors; current concatenation is parser-verified proposal, not measured reload.',
                    'Same-session before/selected/reset/reloaded/final plus after-root complete23570-native-visible-position audits. LZC4200 includes all native-visible branch and condition vectors. XML-only op16 remains HOLD/unaddressable, never certified by these audits. Never infer GUI IDs from XML.',
                    'Use sealed product discovery native branch meta/binding tokens for protected branch audits; all60 unqualified branch candidates remain included.',
                    'Only60cond may change inclusion; protect all line/FSM/toggle and other scopes. Permit seventh-condition summary/score changes only beneath exact target scopes; raw/reset reports identical bytes.',
                    'Exact combined EL roundtrip/signature and empty initial/reset/final global EL. Failure/incomplete gate means NOT_QUALIFIED, no automatic retry.',
                    'Parent reviews source X/0 closure and its initialization/force limits explicitly; preserve frozen false flag, never waive transientX or op16.'
                ], fresh_same_session_combined_reload_verified=False, launched=False,
                active_six_run_modified=False, application_approval=False,
                official_denominator_verified=False, new_RTL_signoff=False, pins=pins)
    frozen.write(output / 'application-plan.json', plan)
    frozen.write(output / 'application-plan.sha256.json',
                 {str(output / 'application-plan.json'): sha(output / 'application-plan.json')})
    print(json.dumps(dict(output=str(output), seal=sha(output / 'application-plan.json'),
                         population=six['population'], targets=5868, protected=17702, launched=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--six-output', type=Path, required=True)
    parser.add_argument('--six-seal', required=True)
    parser.add_argument('--proof-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.six_output.resolve(strict=True), args.six_seal, args.proof_output.resolve(strict=True), args.output.absolute())


if __name__ == '__main__':
    main()
