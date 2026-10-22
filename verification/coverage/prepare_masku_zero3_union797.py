"""Exact MaskU union handoff only; no launcher, reporter, or population admission."""
import argparse
import json
from pathlib import Path

import report_global777_compact as stable
import run_masku_zero3_native796_v2 as native
import targeted_toggle_evidence as raw

q = native.qualification
OUT, need, digest = q.OUT, q.need, q.digest
BASE = OUT / 'vsmul-saturation-offline-admitted797-parent-20261008-01'
BASE_SHA = '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'
OLD_BASE = OUT / 'akv-canonical-alias-offline-admitted796-parent-20261008-01'
OLD_BASE_SHA = '1aa18b04d4b1f3a4a2d8182c0457e240f43e0538bbeabe1b0385724e5a56400d'
REPORT796 = OUT / 'current-population796-alua137-ptw156-agent-20261008-01'
CONFIG796_SHA = '062daf585d00ef170942b36f5a631dee7f4676af32fcbb4e5d8af86a8159badf'
QUAL796_SHA = 'f439bae9092c0a787ee8fb8177ee33277e6ec25f61ef0c198f5a8dce50807270'
EL796_SHA = '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9'
REPORT797 = OUT / 'current-population797-inherited796-agent-20261008-01'
CONFIG797_SHA = '4145a211520006ec00b04c6ba18ffdf1acdd700bf761774c0fad69bc523a1fc0'
LAUNCH = OUT / 'masku-zero3-native796-v2-launcher-prepared-agent-20261008-01'
LAUNCH_SHA = '214e3834edbc0b01756b894c8873d61cef78f30fa537a1e87a4a638c7fd3a873'
STRICT_SHA = 'd2d8801b46fdfe18fe950dc0ac2e5fefa93f6fae5065d73ed876231855b09c01'
STABLE_SHA = 'b39dfde1c08ad61c7d85e875607cea255f20cfcff6e81f5c9f484f6310c2a28b'
SCHEMA = 'MASKU_ZERO3_FORMAL797_EXACT_EL_UNION_PREPARE_ONLY_V1'


def zero_row(row, positions, width=4390, checksum='1400516067'):
    need(type(row['width']) is int and row['width'] == width and row['checksum'] == checksum,
         'Exact compiled MaskU raw width/checksum')
    bits = int(row['bits'], 16)
    need(0 <= bits < 1 << width and len(positions) == len(set(positions)) == 1536 and
         all(type(p) is int and 0 <= p < width for p in positions), 'Exact physical pair positions')
    need(all(not(bits >> (width - 1 - p) & 1) for p in positions), 'Raw hit counterexample: HOLD')


def population_gate(oldledger, ledger, status, before, suffix, after, positions):
    need(len(oldledger) == len(set(oldledger)) == 797 and len(ledger) == len(set(ledger)) == 798 and
         ledger[:-1] == oldledger, 'Exact admitted796 prefix and one unique797 suffix')
    need(status['coverage_admitted'] is True and type(status['aggregate_passed']) is int and
         status['aggregate_passed'] == 797 and status['full_OR_metric_instances'] == 6162 and
         status['full_OR_Toggle_instances'] == 2989, 'Formal797 complete admission status')
    for row in (before, suffix, after): zero_row(row, positions)
    need(raw.union({q.SCOPE: before}, {q.SCOPE: suffix})[q.SCOPE] == after,
         'Actual797 MaskU OR differs from formal admitted union')


def union_gate(base, local, c):
    q.records(local, c)
    before, extra = stable.semantic(base), stable.semantic(local)
    need(not extra[0] and len(extra[1]) == 6 and all(v == (1 << 256) - 1 for v in extra[1].values()),
         'Only exact three full paired direction vectors')
    for row in before[0]:
        need(not(row[3] == 'WHOLE_SCOPE' and (q.SCOPE == row[0] or q.SCOPE.startswith(row[0] + '.'))),
             'Inherited whole-scope/ancestor overlaps target')
        need(not(row[0] == q.SCOPE and row[3].startswith('Toggle ')), 'Opaque same-scope Toggle HOLD')
    masks = before[1]
    additions = []
    already = []
    for name in q.NAMES:
        keys = [k for k in extra[1] if k[2] == name]
        need(len(keys) == 2, 'Two exact source-bound directions')
        for k in masks:
            if k[0] != q.SCOPE: continue
            need(k[1] == keys[0][1], 'Inherited same-scope checksum conflict')
            need(not(name.startswith(k[2] + '.') or k[2].startswith(name + '.')),
                 'Inherited packed parent/child overlap')
            if k[2] == name:
                need(k in keys, 'Inherited target kind/declaration/range conflict')
        values = [masks.get(k, 0) for k in keys]
        if values == [0, 0]:
            additions.append(name)
        else:
            need(values == [(1 << 256) - 1] * 2, 'Partial/single-direction overlap HOLD; do not guess ownership')
            already.append(name)
    inst = next(i for i in c['instances'] if i['scope'] == q.SCOPE)
    delta = ''
    if additions:
        delta = 'CHECKSUM: "%s %s"\nINSTANCE: %s\nANNOTATION: "%s"\n' % (
            inst['design_checksum'], inst['toggle_checksum'], q.SCOPE, q.ANNOTATION)
        delta += ''.join('Toggle %s "logic %s[255:0]"\n' % (n, n) for n in additions)
        q.parse_records(delta, q.SCOPE, '%s %s' % (inst['design_checksum'], inst['toggle_checksum']),
                        {n: 'logic %s[255:0]' % n for n in additions}, q.ANNOTATION)
    need(not base or base.endswith('\n'), 'Truncated inherited EL')
    combined = base + delta
    expected = dict(masks)
    for key, mask in extra[1].items(): expected[key] = expected.get(key, 0) | mask
    need(stable.semantic(combined) == (before[0], expected), 'Only exact physical union; complement changed')
    need(combined[:len(base)] == base, 'All inherited rules must remain byte-identical')
    return combined, delta, dict(added_objects=additions, already_inherited_objects=already,
                                added_physical_bits=len(additions) * 256,
                                added_toggle_direction_members=len(additions) * 512,
                                base_semantic_sha256=stable.semantic_seal(before),
                                union_semantic_sha256=stable.semantic_seal((before[0], expected)))


def evidence():
    pins = {}
    def bound(path, sha, as_json=True):
        need(digest(path) == sha, 'Evidence pin drift: ' + str(path))
        pins[str(path)] = sha
        return json.loads(path.read_bytes()) if as_json else path.read_text()
    base = bound(BASE / 'admission-manifest.json', BASE_SHA)
    oldbase = bound(OLD_BASE / 'admission-manifest.json', OLD_BASE_SHA)
    need(base['coverage_admitted'] is True and base['baseline'] == str(OLD_BASE) and
         base['baseline_seal'] == OLD_BASE_SHA and oldbase['coverage_admitted'] is True,
         'Exact formal796->797 admission')
    c796 = bound(REPORT796 / 'config.json', CONFIG796_SHA)
    qualified = bound(REPORT796 / 'qualification.json', QUAL796_SHA)
    need(qualified['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         qualified['config_seal'] == CONFIG796_SHA and qualified['population'] ==
         qualified['actual_selected_tests'] == 796 and qualified['source_design_native_pins'] == c796['pins'],
         'Exact qualified796 report')
    for key in ('complete_approved_EL_bitmask_union', 'all_other_bits_protected', 'raw_reset_final_equal',
                'applied_reloaded_equal', 'raw_hierarchy_vs_rooted_six_metrics_equal',
                'supported_roots_all_six_metrics_present'):
        need(qualified[key] is True, 'Qualified796 global gate: ' + key)
    c797 = bound(REPORT797 / 'config.json', CONFIG797_SHA)
    need(c797['population'] == 797 and c797['admission'] == dict(path=str(BASE / 'admission-manifest.json'),
         sha256=BASE_SHA), 'Exact pending report797 config')
    base_el = bound(REPORT796 / 'combined.el', EL796_SHA, False)
    need(stable.semantic_seal(stable.semantic(base_el)) == c796['expected_EL_semantic_sha256'], '796 EL semantic seal')
    need(bound(REPORT797 / 'combined.el', EL796_SHA, False) == base_el, 'Pending797 inherited EL must be unchanged')
    pins = stable.merge(pins, c796['pins'], qualified['output_pins'], c797['pins'],
                        base['input_pins'], base['output_pins'], oldbase['input_pins'], oldbase['output_pins'])
    def admitted(directory, name, is_json=True):
        path = directory / name
        return bound(path, pins[str(path)], is_json)
    oldledger = admitted(OLD_BASE, 'combined-inputs.txt', False).splitlines()
    ledger = admitted(BASE, 'combined-inputs.txt', False).splitlines()
    need(oldledger == c796['input_ledger'] and ledger == c797['input_ledger'], 'Exact admitted/report ledger identities')
    oldtoggle = admitted(OLD_BASE, 'combined-toggle-bits.json')
    toggle = admitted(BASE, 'combined-toggle-bits.json')
    need(len(oldtoggle) == len(toggle) == 2989, 'Complete admitted Toggle scope sets')
    paths = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(paths) == 1 and str(paths[0]) in pins, 'One formally bound797 suffix Toggle sample')
    need(digest(paths[0]) == pins[str(paths[0])], 'Actual797 suffix pin')
    sample, sha = raw.rows(paths[0], [q.SCOPE])
    need(sha == pins[str(paths[0])], 'Native797 sample unchanged while reading')
    review = bound(q.REVIEW, q.REVIEW_SHA)
    positions = [p for obj in review['objects'] for bit in obj['bits'] for p in bit['serialized_pair']]
    population_gate(oldledger, ledger, admitted(BASE, 'status.json'), oldtoggle[q.SCOPE],
                    sample[q.SCOPE], toggle[q.SCOPE], positions)
    c = native.load_launch(native.OUT, native.NATIVE_SHA, LAUNCH / 'launch-manifest.json', LAUNCH_SHA)
    receipt = bound(LAUNCH / 'strict-inspection-receipt.json', STRICT_SHA)
    result = bound(native.OUT / 'capture-result.json', receipt['native_result_sha256'])
    need(receipt['status'] == 'MASKU_ZERO3_V2_STRICT_NATIVE_QUALIFIED_NOT_APPLIED' and
         receipt['native_config_sha256'] == native.NATIVE_SHA and receipt['launch_manifest_sha256'] == LAUNCH_SHA and
         receipt['population_application'] is False and result['targets'] == 3 and result['physical_bits'] == 768 and
         result['protected'] == 984 and result['five_stages'] is True and result['population_application'] is False,
         'Exact independent local native qualification, no parent alias inheritance')
    native.terminal_gate(json.loads((native.OUT / 'terminal.json').read_bytes()), c,
                         json.loads((native.OUT / 'live-identity.json').read_bytes()),
                         json.loads((native.OUT / 'process-witness.json').read_bytes()),
                         json.loads((native.OUT / 'execution.json').read_bytes()))
    need(digest(native.OUT / 'terminal.json') == receipt['terminal_sha256'] and
         digest(native.OUT / 'process-witness.json') == receipt['process_witness_sha256'], 'Strict terminal/witness seals')
    for stage in q.STAGES:
        q.check_el(native.OUT, c, stage)
        for index in range(26): q.inventory(native.OUT, c, stage, index)
    local = (native.OUT / 'first.el').read_text()
    need(q.records(local, c) == q.records((native.OUT / 'second.el').read_text(), c), 'Actual local semantic reload')
    pins = stable.merge(pins, c['pins'], result['pins'])
    for path in (Path(__file__).resolve(), Path(raw.__file__).resolve(), Path(stable.__file__).resolve(),
                 Path(stable.inventory.__file__).resolve(), Path(native.__file__).resolve(), Path(q.__file__).resolve(),
                 Path(__file__).with_name('test_prepare_masku_zero3_union797.py')):
        pins[str(path)] = digest(path)
    need(digest(stable.__file__) == STABLE_SHA, 'Frozen native EL semantic parser')
    return pins, ledger, c, base_el, local, dict(scope=q.SCOPE, compiled_width=4390, checksum='1400516067',
        physical_bits=768, serialized_direction_slots=1536, positions=positions, suffix=str(paths[0]), suffix_sha256=sha,
        suffix_raw_zero=True, raw796_zero=True, full797_zero=True, exact_scope_OR=True,
        official_denominator_claim=False)


def prepare(out):
    need(out.parent == OUT and not out.exists(), 'Fresh independent handoff directory')
    pins, ledger, c, base, local, zero = evidence()
    combined, delta, union = union_gate(base, local, c)
    need(union['added_objects'] == list(q.NAMES) and not union['already_inherited_objects'],
         'Current796 EL must have exactly zero prior target ownership; no silently stale gain')
    q.check_pins(pins)
    out.mkdir()
    for name, data in (('combined.el', combined), ('masku-delta.el', delta), ('inputs.txt', '\n'.join(ledger) + '\n')):
        with (out / name).open('x') as stream: stream.write(data)
        pins[str(out / name)] = digest(out / name)
    config = dict(schema=SCHEMA, status='PREPARED_EXACT_MASKU_UNION_NOT_APPLIED_WAIT_REPORT797', output=str(out),
                  population=797, admission_manifest_sha256=BASE_SHA, input_ledger=ledger,
                  qualified796_config_sha256=CONFIG796_SHA, inherited_EL_sha256=EL796_SHA,
                  report797_config_sha256=CONFIG797_SHA, report797_directory=str(REPORT797),
                  strict_MASKU_receipt_sha256=STRICT_SHA, raw_zero=zero, union=union,
                  protected_complement=dict(scopes=26, full_objects=987, target_objects=3, retained_other_objects=984,
                      policy='Only exact new target Toggle physical members; every inherited rule retained byte-for-byte.'),
                  requires_completed_report797_before_application=True, report797_completion_claimed=False,
                  EDA_started=False, population_application=False, official_denominator=None, official_percentage=None,
                  local_native_qualification_only=True, pins=pins)
    q.save(out / 'config.json', config)
    q.save(out / 'prepare-receipt.json', dict(status=config['status'], config_sha256=digest(out / 'config.json'),
                  added_objects=union['added_objects'], physical_bits=768, direction_members=1536,
                  base_EL_byte_prefix_preserved=True, exact_physical_dedup=True, suffix_raw_zero=True,
                  protected_other_objects=984, EDA_started=False, population_application=False,
                  wait_for_report797_qualification=True, official_percentage=None))
    return config


def check(out, seal):
    config = q.read_bound(out / 'config.json', seal)
    need(config['schema'] == SCHEMA and config['output'] == str(out) and config['population'] == 797 and
         config['requires_completed_report797_before_application'] is True and
         config['population_application'] is False and config['EDA_started'] is False, 'Exact prepare-only contract')
    q.check_pins(config['pins'])
    pins, ledger, c, base, local, zero = evidence()
    combined, delta, union = union_gate(base, local, c)
    need(config['input_ledger'] == ledger and config['raw_zero'] == zero and config['union'] == union and
         all(config['pins'].get(p) == sha for p, sha in pins.items()), 'Prepared evidence/union replay drift')
    need((out / 'combined.el').read_text() == combined and (out / 'masku-delta.el').read_text() == delta and
         (out / 'inputs.txt').read_text() == '\n'.join(ledger) + '\n', 'Exact retained+new EL and formal797 ledger')
    return config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    else:
        need(args.seal, 'Exact handoff config seal')
        check(out, args.seal)
    print(json.dumps(dict(mode=args.mode, output=str(out), seal=digest(out / 'config.json'), EDA_started=False)))
