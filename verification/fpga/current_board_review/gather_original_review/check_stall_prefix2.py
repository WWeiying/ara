#!/usr/bin/env python3
"""Read-only strict audit of the two prefix ports, with explicit fresh output."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
import prepare_stall_prefix2 as prep
from prepare_batch import sha, save

DATA = prep.OUT
NAMES = ['gather_prefix_e8_m4_ops1', 'gather_prefix_e8_m4_ops20']


def require(value, reason):
    if not value:
        raise ValueError(reason)


def gate(result, model, console):
    require(result['status'] == 'PASS' and result['returncode'] == 0, 'Non-PASS/exit0')
    require(result['name'] in NAMES, 'Wrong source key')
    require(result['target_hits'] == result['returned_vstart_zero'] == 98, 'Missing target/CSR')
    require(result['fullcap_scalar_checks'] == 50176 and result['both_guard_checks'] == 196 and
            result['actual_output_scalar_loads'] == 50372, 'Incomplete original scalar oracle')
    require(0 < result['firmware_retired_to_htif_store'] <= prep.MAX_RETIRED and
            result['htif_store_value'] == 1, 'Retirement/HTIF gate')
    require(len(result['events']) == 98 and all(
        event['ordinal'] == row['ordinal'] and event['original_tuple'] == row['tuple'] and
        (event['vl'], event['vstart'], event['scalar']) == (row['vl'], row['vstart'], row['scalar'])
        for event, row in zip(result['events'], model['rows'])), 'Wrong original prefix tuple stream')
    require('RVV_GATHER_PREFIX_PASS sew=8 cases=98 errors=0' in console and
            f"BOARD_CASE_PASS {result['name']}" in console and 'BOARD_REPLAY_PASS' in console and
            not re.search(r'FAIL|TRAP|MISMATCH|DETAIL|RVV_PERMUTE_PASS', console), 'Marker veto')


def audit():
    ready = prep.read(DATA/'prepared_ready.json')
    require(ready['status'] == 'PREPARED_TWO_CHILD_PREFIXES_HOST_SPIKE_PASS_NOT_DUT' and
            ready['cases'] == NAMES and ready['prefix_calls_each'] == 98, 'Scope/count differs')
    require(ready['original_stopped_tuple'] is None and not any(ready[k] for k in
        ('exact11_failure_reproduction', 'full_parent_closure', 'vcs_started', 'rtl_modified')),
        'Unjustified closure/DUT claim')
    for pin_file in ('baseline_pins.json', 'prepared_pins.json'):
        for file, digest in prep.read(DATA/pin_file).items():
            require(sha(Path(file)) == digest, 'Input/output pin drift: '+file)
    for field, file in (('source_elf_proof_sha256', 'source_elf_proof.json'),
                        ('host_gate_sha256', 'host/host_gate.json'),
                        ('reference_sha256', 'reference/reference.json'),
                        ('pins_sha256', 'prepared_pins.json')):
        require(ready[field] == sha(DATA/file), 'Ready binding differs')
    provenance = prep.read(DATA/'prepared/provenance.json')
    reference = prep.read(DATA/'reference/reference.json')
    host = prep.read(DATA/'host/host_gate.json')
    proof = prep.read(DATA/'source_elf_proof.json')
    require([c['id'] for c in provenance['cases']] == NAMES and
            [r['name'] for r in reference['results']] == NAMES and
            [r['name'] for r in host['results']] == NAMES, 'Not exactly two')
    sys.path.insert(0, str(prep.base.INTEGRATION))
    from prepare import adapt
    checked = []
    for case, result, host_case, source_proof in zip(
            provenance['cases'], reference['results'], host['results'], proof['results']):
        name, op = case['id'], case['operation']
        model = prep.model(op)
        original = DATA/'prepared'/name/'original'
        require((DATA/'prepared'/name/'case.c').read_text() ==
                prep.prefix(adapt((original/'scenario.c').read_text(), name), 98), 'Source diff changed')
        require(sha(original/'scenario.c') == source_proof['source_sha256'] and
                sha(original/'original_linux.elf') == case['original_linux_elf_sha256'], 'Archive identity')
        require(source_proof['unchanged_all13_routine_encodings'] and
                len(source_proof['original_routine']) == len(source_proof['soc_routine']) == 13 and
                [r['insn'] for r in source_proof['original_routine']] ==
                [r['insn'] for r in source_proof['soc_routine']], 'Original routine encoding changed')
        require(len(host_case['tests']) == 8 and all(t['status'] == 'PASS' for t in host_case['tests']),
                'Host positive/negative gates incomplete')
        console = (DATA/'reference'/(name+'.runtime.log')).read_text()
        gate(result, model, console)
        elf = Path(prep.read(DATA/'spike01/programs.json')['programs'][name]['path'])
        raw = prep.reference_trace(DATA/'reference'/(name+'.commits.log'), elf, name, model)
        require(raw.pop('reconstructed_runtime_console') == console, 'Console not actual committed RAM')
        require(all(result[k] == v for k, v in raw.items()), 'Raw retirement/oracle evidence differs')
        require(sha(Path(prep.read(DATA/'soc01/programs.json')['programs'][name]['path'])) ==
                result['soc_elf_sha256'], 'SoC ELF drift')
        checked.append(dict(name=name, status='PASS_SOURCE_PREFIX_NOT_DUT',
             retired=result['firmware_retired_to_htif_store'], target_hits=98,
             fullcap_checks=50176, guards=196, original_stopped_tuple=None,
             entire_original_linux_elf_rebuild_identical=source_proof['original_c_entire_binary_rebuild_proven']))
    return dict(status='PASS_TWO_SOURCE_PREFIX_IDENTITY_AND_RAW_FULLORACLE_AUDIT_NOT_DUT',
                results=checked, prepared_ready_sha256=sha(DATA/'prepared_ready.json'),
                original11_stall_closure=False, full_parent_closure=False, vcs_started=False)


class NegativeGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = prep.read(DATA/'reference/reference.json')['results'][0]
        cls.model = prep.model(1)
        cls.console = (DATA/'reference'/(NAMES[0]+'.runtime.log')).read_text()

    def rejected(self, key, value):
        item = copy.deepcopy(self.good)
        item[key] = value
        with self.assertRaises(ValueError):
            gate(item, self.model, self.console)

    def test_returncode_veto(self):
        self.rejected('returncode', 1)

    def test_missing_target(self):
        self.rejected('target_hits', 97)

    def test_missing_guard(self):
        self.rejected('both_guard_checks', 195)

    def test_budget(self):
        self.rejected('firmware_retired_to_htif_store', prep.MAX_RETIRED+1)

    def test_wrong_source(self):
        self.rejected('name', 'gather_prefix_e8_m8_ops1')

    def test_failure_marker_after_pass(self):
        with self.assertRaises(ValueError):
            gate(self.good, self.model, self.console+'RVV_GATHER_PREFIX_FAIL\n')

    def test_parent_marker_is_not_prefix(self):
        with self.assertRaises(ValueError):
            gate(self.good, self.model, self.console+'RVV_PERMUTE_PASS cases=2688\n')

    def test_wrong_tuple(self):
        item = copy.deepcopy(self.good)
        item['events'][-1]['vstart'] = 1
        with self.assertRaises(ValueError):
            gate(item, self.model, self.console)

    def test_wrong_shape_endpoint(self):
        with self.assertRaises(ValueError):
            prep.prefix('unused', 66)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Audit output must be fresh; no sealed overwrite')
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(NegativeGates))
    require(result.wasSuccessful(), 'Negative tests failed')
    checked = audit()
    args.output.mkdir()
    checked['negative_tests_passed'] = result.testsRun
    checked['checker_sha256'] = sha(Path(__file__))
    save(args.output/'audit.json', checked)
    print(checked['status'], args.output, flush=True)
