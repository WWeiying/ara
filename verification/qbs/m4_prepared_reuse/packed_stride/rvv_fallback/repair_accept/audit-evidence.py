#!/usr/bin/env python3
"""Read-only successor audit. Missing tensor identity cannot become acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
from accept import ROOT, HERE, BASE, ACTIVE, ACTIVE_SHA, digest, read, merge, verify, require
from check import check as strict_check, fields

RUN = ROOT/'verification/out/m4-stride-rvv-repair-20261027-03'
PREPARED = ROOT/'verification/out/m4-stride-rvv-repair-20261027-02'
OUT = RUN/'evidence-audit'
TRAIT = 'ggml::cpu::repack::tensor_traits<block_q4_K, 1l, 32l, (ggml_type)15>'
QBS = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs.cpp')
REPACK = QBS.parents[2]/'repack.cpp'


def detailed_check(log):
    # Only split the combined selection assertion for diagnostic collection.
    # All numerical/ownership/stride checks remain byte-for-byte unchanged.
    # This function alone never grants acceptance: identity audit below is required.
    source = (HERE/'check.py').read_text()
    before = 'require(current["repacks"] >= 1 and current["decisions"] >= 1, "Missing actual fallback selection")'
    after = 'require(current["repacks"] == 1, "Expected exactly one ordinary repack per case")'
    require(source.count(before) == 1, 'Frozen selection assertion structure')
    scope = {}
    exec(compile(source.replace(before, after), str(HERE/'check.py')+':diagnostic-successor', 'exec'), scope)
    return scope['check'](log)


def inputs():
    return dict(log=(RUN/'qemu.log').read_text(), command=read(RUN/'qemu.command.json'),
                mapping=(PREPARED/'link.map').read_text(),
                private=(RUN/'private-symbols.log').read_text(), linked=(RUN/'linked-symbols.log').read_text(),
                qbs=QBS.read_text(), repack=REPACK.read_text(),
                driver=(HERE.parent/'test.cpp').read_text())


def audit(data):
    qbs, repack, driver = data['qbs'], data['repack'], data['driver']
    for snippet in ('static std::unordered_set<const void *> traced_tensors;',
                    'if (!traced_tensors.insert(tensor_identity).second) {\n            return;',
                    'counters.candidate_tensors.fetch_add(1, std::memory_order_relaxed);'):
        require(snippet in qbs, 'Dedup source semantics changed')
    require('ggml_riscv_qbs_trace_tensor_decision(\n        cur, cur->name' in repack, 'Wrong dedup key')
    require('void *const weight_extra = w->extra;' in driver and 'void *const weight_data = w->data;' in driver,
            'Logged pointer semantics changed')
    expected = read(BASE/'qemu.command.json')['argv']
    expected[expected.index('-initrd')+1] = str(RUN/'initramfs.cpio')
    require(data['command']['argv'] == expected and data['command']['limit_seconds'] == 180, 'QEMU command changed')
    require(expected[expected.index('-cpu')+1].endswith('xaraqbs=false'), 'QBS CPU enabled')
    mapping = data['mapping'].splitlines()
    for symbol in (TRAIT+'::compute_forward(ggml_compute_params*, ggml_tensor*)', 'vtable for '+TRAIT):
        for label in ('private', 'linked'):
            matches = [l for l in data[label].splitlines() if l.split(' ',2)[-1] == symbol]
            require(len(matches) == 1, 'Exact ordinary symbol missing')
        indexes = [i for i,l in enumerate(mapping) if l.strip() and l.strip().split(None,1)[-1] == symbol]
        require(len(indexes) == 1, 'Ambiguous/missing ordinary provider')
        i = indexes[0]
        require(i > 0 and mapping[i-1].split()[-1] == str(PREPARED/'repack.o'), 'Wrong private provider')
        require(int(mapping[i-1].split()[0],16) == int(mapping[i].split()[0],16), 'Provider address mismatch')
    measured = detailed_check(data['log'])
    require(measured['completed_cases'] == 4 and all(c['mismatches'] == 0 for c in measured['cases']), 'Numerical failure')
    case_id, decision_ids, weights = None, [], []
    for line in data['log'].splitlines():
        if line.startswith('RF_BEGIN '):
            case_id = int(fields(line)['id'])
        elif line.startswith('GGML_RISCV_QBS_TENSOR '):
            require(fields(line) == dict(name='rvv_q4k', type='q4_K', dims='2', k='512', rows='32', matrices='1',
                                        decision='runtime_disabled', segmented='0'), 'Unexpected decision or unrecorded trace address')
            decision_ids.append(case_id)
        elif line.startswith('RF_WEIGHT '):
            w = fields(line)
            require(set(w) == {'id','buffer','qbs_supported','owned','extra','data','captured'}, 'Unsupported identity/address claim')
            weights.append(w)
    require(decision_ids == [0,1], 'Changed observed decision pattern')
    coverage, = [fields(l) for l in data['log'].splitlines() if l.startswith('GGML_RISCV_QBS_COVERAGE ')]
    require(coverage['type'] == 'Q4_K' and coverage['candidate_tensors'] == coverage['fallback_runtime'] == '2'
            and coverage['candidate_elements'] == '32768' and coverage['selected_tensors'] == coverage['selected_elements'] ==
            coverage['segmented_tensors'] == '0', 'Dedup coverage accounting')
    require(all(v == '0' for k,v in coverage.items() if k.startswith('fallback_') and k != 'fallback_runtime'), 'Other fallback reason')
    try:
        strict_check(data['log'])
    except ValueError as exc:
        require(str(exc) == 'Missing actual fallback selection', 'Different strict failure')
    else:
        raise ValueError('Original strict failure unexpectedly absent')
    return dict(state='INCOMPLETE', acceptance=False, numerical_checks='PASS', outputs=704,
                retained_checks=measured, ordinary_provider=str(PREPARED/'repack.o'), native_qbs_calls=0,
                observed_decision_case_ids=decision_ids, observed_missing_case_ids=[2,3],
                expected_missing_case_ids_from_recorded_tensor_addresses=None,
                tensor_identity_addresses_recorded=False, same_address_prior_runtime_disabled_proven=False,
                raw_weight_records=weights,
                dedup_key='ggml_tensor * cur, not w->extra and not w->data',
                reason='Tensor-object addresses are absent from both driver and decision records; exact earlier-address mapping cannot be proven.',
                inference='Observed two decisions and coverage count two are consistent with address dedup, but do not prove which tensor addresses were reused.',
                strict_result_preserved=True, scope='Independent evidence audit only; no boot, rebuild or relabeling of strict FAIL')


class AuditTests(unittest.TestCase):
    def test_actual_incomplete(self):
        result = audit(inputs())
        self.assertEqual(result['state'], 'INCOMPLETE')
        self.assertFalse(result['acceptance'])
        self.assertIsNone(result['expected_missing_case_ids_from_recorded_tensor_addresses'])

    def test_provider_and_runtime_mutations(self):
        original = inputs()
        changed = dict(original, mapping=original['mapping'].replace(str(PREPARED/'repack.o'), '/wrong/provider.o'))
        with self.assertRaisesRegex(ValueError, 'provider'):
            audit(changed)
        changed = dict(original, command=json.loads(json.dumps(original['command'])))
        changed['command']['argv'] = [s.replace('xaraqbs=false','xaraqbs=true') for s in changed['command']['argv']]
        with self.assertRaisesRegex(ValueError, 'command'):
            audit(changed)
        changed = dict(original, qbs=original['qbs'].replace('traced_tensors.insert(tensor_identity)', 'traced_tensors.insert(other_address)'))
        with self.assertRaisesRegex(ValueError, 'Dedup'):
            audit(changed)

    def test_log_mutations(self):
        original = inputs()
        replacements = [
            ('decision=runtime_disabled', 'decision=selected'),
            ('decision=runtime_disabled', 'decision=runtime_disabled tensor=0x2fb080'),
            ('extra=0x22dbb0', 'extra=0x22dbb0 tensor=0x22dbb0'),
            ('owned=1', 'owned=0'), ('same_backing=1', 'same_backing=0'),
            ('nb1=2112', 'nb1=2048'), ('weight_integrity=1', 'weight_integrity=0'),
            ('k=256', 'k=512'), ('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1'),
            ('candidate_tensors=2', 'candidate_tensors=4'), ('fallback_runtime=2', 'fallback_runtime=4'),
            ('selected_tensors=0', 'selected_tensors=1'),
            ('got_bits=bb0ad2de', 'got_bits=7fc00000'),
        ]
        for before,after in replacements:
            with self.subTest(before=before):
                self.assertIn(before, original['log'])
                with self.assertRaises(ValueError):
                    audit(dict(original, log=original['log'].replace(before,after,1)))
        with self.assertRaises(ValueError):
            audit(dict(original, log=original['log']+'\nGGML_RISCV_QBS_CALL type=q4_K'))

    def test_logged_data_reuse_is_not_tensor_identity(self):
        original = inputs()
        # Even making every packed allocation equal cannot establish tensor identity.
        log = original['log'].replace('data=0x2ff9c0','data=0x2fb080').replace('data=0x311640','data=0x2fb080')
        result = audit(dict(original,log=log))
        self.assertFalse(result['acceptance'])
        self.assertFalse(result['same_address_prior_runtime_disabled_proven'])


def main():
    OUT.mkdir(exist_ok=False)
    pins = read(RUN/'manifest.json')
    merge(pins, {str(p):digest(p) for p in RUN.iterdir() if p.is_file()})
    merge(pins, {str(Path(__file__)):digest(__file__)})
    require(str(QBS) in pins and str(REPACK) in pins, 'Source audit not inherited')
    require(digest(ACTIVE) == ACTIVE_SHA and len(read(ACTIVE)) == 1880, 'Active inventory identity')
    verify(pins)
    (OUT/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
    report = audit(inputs())
    command = [sys.executable,'-B',str(Path(__file__).resolve()),'--test']
    (OUT/'tests.command.json').write_text(json.dumps(command,indent=2)+'\n')
    with (OUT/'tests.log').open('x') as log:
        process = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    (OUT/'tests.exit.json').write_text(json.dumps(dict(returncode=process.returncode))+'\n')
    report['mutation_tests_pass'] = process.returncode == 0
    verify(pins)
    report['all_inherited_pins_unchanged'] = True
    (OUT/'result.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report))
    require(process.returncode == 0, 'Audit mutation tests failed')


if __name__ == '__main__':
    if sys.argv[1:] == ['--test']:
        unittest.main(argv=[__file__],verbosity=2)
    else:
        require(len(sys.argv) == 1, 'No arguments expected')
        main()
