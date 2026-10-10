#!/usr/bin/env python3
"""Source-bound independent selector semantics and native identity evidence."""
import argparse
import json
from pathlib import Path
import re

import lzc_selector_native_prepare as native
import lzc_selector_native_run as runner


def summarize(prepared, evidence):
    calibration = json.loads((evidence / 'calibration.json').read_bytes())
    batch = json.loads((evidence / 'native-batch.json').read_bytes())
    native.require(calibration['status'] == 'STANDALONE_SELFCHECK_PASS_8' and
                   batch['status'] == 'STANDALONE_NATIVE_CAPTURES_VERIFIED_8', 'Eight completed calibrations/captures required')
    binding = json.loads((prepared / 'binding.json').read_bytes())
    runner.check_pins(binding['pins'])
    rows, pins = [], dict(binding['pins'])
    for experiment in calibration['results']:
        top = experiment['top']
        case = prepared / top
        report_path = evidence / (top + '-native.json')
        report = json.loads(report_path.read_bytes())
        runner.check_pins(report['artifact_sha256'])
        scope = top + '.dut'
        design = native.Design(case / 'simv.vdb')
        metadata = {}
        for metric in ('branch', 'cond'):
            definition, population = native.compiled_points(design, scope, metric)
            data_path = design.db / 'testdata' / top / f'{metric}.verilog.data.xml'
            data = native.read_xml(data_path)
            instances = [n for n in data.iter('instance_data') if n.get('name') == scope]
            native.require(len(instances) == 1 and instances[0].get('chksum') == definition.get('chksum'),
                           'Standalone raw checksum differs')
            bits = instances[0].get('value')
            native.require(len(bits) == len(population) and set(bits) <= {'0', '1'}, 'Raw vector shape differs')
            for point in population:
                coord = (point['attributes'].get('generate_info') if metric == 'branch'
                         else point['spec'].get('generate_info'))
                if point['line'] == '95' and coord == 'level=0,l=0':
                    family = 'branch' if metric == 'branch' else 'op' + point['attributes']['optype']
                    metadata.setdefault(family, {})[point['vector']] = dict(
                        hit=bits[point['raw_index']] == '1', xml_monitored_id=point['native_id'],
                        raw_index=point['raw_index'], checksum=point['attributes']['chksum'])
            pins[str(data_path)] = native.sha(data_path)
        native_branch = {}
        for line in report['native_pre_exclusion_observations']:
            match = re.fullmatch(r'LSN_NATIVE_BRANCH id=0 vector=([01]) columns=(0\.00|100\.00)', line)
            if match:
                native_branch[match[1]] = match[2] == '100.00'
        native.require(set(native_branch) == {'0', '1'}, 'Missing exact native root arm coverage')
        selector = experiment['selector']
        native.require(native_branch == {'0': bool(selector), '1': not bool(selector)},
                       'Native arm calibration differs')
        native.require({v: p['hit'] for v, p in metadata['op23'].items()} ==
                       {'0': not bool(selector), '1': bool(selector)}, 'Ternary vectors do not track selector')
        native.require(metadata['op16']['1']['hit'] == bool(selector), 'Boolean true row differs')
        # This coverage includes time zero; the selfcheck observes settled values at 1ns.
        native.require(metadata['op16']['0']['hit'], 'Unexpected boolean initialization evidence')
        conditions = [r['native'] for r in report['captured_records'] if r['metric'] == 'cond']
        native.require({(r['native_id'], r['vector_id'], r['vector']) for r in conditions} ==
                       {('2', '1', '0'), ('2', '2', '1')}, 'Measured native condition identity differs')
        row = dict(top=top, width=experiment['width'], selector=selector, result_index=experiment['index'],
                   result_parity=experiment['parity'], selfcheck=experiment['selfcheck'],
                   native_branch_hit=native_branch, xml_root_observations=metadata,
                   native_condition_records=conditions,
                   protected_native_rows=report['protected_rows_per_audit'],
                   complete_native_audits=report['complete_audits'],
                   singleton_roundtrips=report['singleton_roundtrips'],
                   final_global_empty=report['global_final_empty'],
                   xml_only_rows_not_individually_native_audited=len(report['xml_only_rows']))
        rows.append(row)
        pins[str(report_path)] = native.sha(report_path)
    native.require({(r['width'], r['selector'], r['result_parity']) for r in rows} ==
                   {(w, s, p) for w in (10, 23) for s in (0, 1) for p in (0, 1)}, 'Incomplete independent cross')
    for path in (evidence / 'calibration.json', evidence / 'native-batch.json', Path(__file__).resolve()):
        pins[str(path)] = native.sha(path)
    runner.check_pins(pins)
    return dict(status='STANDALONE_ROOT_NATIVE_SEMANTIC_CALIBRATION_COMPLETE_NOT_705_APPLICATION_APPROVAL',
                source_sha256=native.SOURCE_SHA256, independent_calibration_cases=8, rows=rows,
                mapping=dict(branch=dict(native_id='0', false_arm='1', true_arm='0'),
                             ternary=dict(xml_monitored_id='3', optype='23', native_id='2',
                                          false_vector='0', false_native_vector_id='1',
                                          true_vector='1', true_native_vector_id='2',
                                          follows='selector, not result parity'),
                             boolean=dict(xml_monitored_id='2', optype='16',
                                          native_independently_addressable=False,
                                          true_row='1', false_row='0',
                                          false_row_hits_in_true_cases='Observed before/including settled selfcheck; consistent with initialization/instrumentation, exact delta cause not traced')),
                protection=dict(native_rows_across_cases=sum(r['protected_native_rows'] for r in rows),
                                all_position_checks=sum(r['protected_native_rows'] * r['complete_native_audits'] for r in rows),
                                singleton_roundtrips=sum(r['singleton_roundtrips'] for r in rows),
                                all_final_global_files_empty=True,
                                every_saved_el_is_one_exact_branch_arm_or_ternary_vector=True,
                                xml_only_op16_individual_native_state_not_claimed=True),
                input_artifact_sha256=pins, old_processor_exclusions_applied=False,
                processor_test_admission=False, original_prepare_source_modified=False,
                pending=['Parent review before any old705 native capture/application.',
                         'op16 independent native identity/state is still unqualified.',
                         'Root semantic calibration is not a completed padded-node old-image native-ID inventory.',
                         'op16 false-row hits in stable-true cases include time zero; no cycle/delta-level waveform attribution was performed.',
                         'No four-state padded-node initialization proof.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    native.require(not output.exists() and (args.seal is None or not args.seal.exists()),
                   'Fresh summary and seal required')
    native.write(output, summarize(args.prepared.absolute(), args.evidence.absolute()))
    if args.seal is not None:
        native.write(args.seal.absolute(), {str(output): native.sha(output)})
    print(native.sha(output), str(output))
