"""Synthetic resource comparisons and terminal-identity rejection, not RTL evidence."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_real_quantized as a
HASH = 'a'*64


def raw():
    return dict(state='STRIDED_ATTENTION_NUMERICAL_AND_WORK_CHECKED',
        trials=[dict(trial=i, shared=m, cycles=1000+i, fcsr=3, vcsr=5,
                     output_bits=[0x3f800000], qk_calls=128 if m else 768)
                for i, m in enumerate(a.ORDER)],
        hardware_records=[dict(seq=i+1, id=i%8, busy_cycles=90, m=4, n=32) for i in range(16)])


class QuantizedAuditTests(unittest.TestCase):
    def test_identical_complete_calls_and_qbs_records(self):
        result = a.compare(raw(), raw())
        self.assertEqual(result['state'], 'PASS')
        self.assertEqual([r['qbs_commands'] for r in result['calls']], [0, 8, 8, 0])
        self.assertTrue(result['per_call_cycles_identical'])
        self.assertEqual(result['command_comparison']['commands'], 16)

    def test_single_cycle_regression_not_hidden_by_aggregate(self):
        old, new = raw(), raw()
        new['trials'][0]['cycles'] += 1
        new['trials'][3]['cycles'] -= 100
        self.assertEqual(a.compare(old, new)['state'], 'REGRESSION')

    def test_offsetting_command_differences_fail_resource_gate(self):
        old, new = raw(), raw()
        new['hardware_records'][0]['busy_cycles'] += 1
        new['hardware_records'][1]['busy_cycles'] -= 1
        result = a.compare(old, new)
        self.assertEqual(result['state'], 'REGRESSION')
        self.assertEqual(result['command_comparison']['changed_commands'], 2)
        self.assertFalse(result['calls'][1]['command_records_identical'])

    def test_missing_extra_schema_order_and_akv_substitution(self):
        for mutation in ('missing', 'extra', 'schema', 'order', 'akv'):
            new = raw()
            if mutation == 'missing': new['hardware_records'].pop()
            if mutation == 'extra': new['hardware_records'].append(new['hardware_records'][-1])
            if mutation == 'schema': new['hardware_records'][0]['new_field'] = 0
            if mutation == 'order': new['trials'][0]['shared'] = 1
            if mutation == 'akv': new['hardware_records'] = []
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, RuntimeError)):
                a.compare(raw(), new)

    def test_output_flags_and_invalid_cycles(self):
        for field, value in (('output_bits', [0]), ('fcsr', 1), ('vcsr', 0),
                             ('cycles', 0), ('cycles', 1000.0), ('cycles', True)):
            new = raw(); new['trials'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, RuntimeError)):
                a.compare(raw(), new)

    def terminal_fixture(self):
        run, build = Path('/run'), Path('/build')
        status = dict(state='PASS', child_pid=None, running_exit_code=0, checking_exit_code=0,
            kind='quant_q4_0', counter_policy='QBS_PERF_ONLY_NO_AKV_SUMMARY',
            build=str(build), elf='/elf', simv='/simv')
        parsed = raw()
        evidence = {str(run/'work'/n):HASH for n in ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json')}
        report = dict(parsed, state='PASS', kind='quant_q4_0', post_pins_match=True,
            independent_protocol_checked=True, model_execution=False, production_promoted=False,
            source_pins_sha256=HASH, elf_sha256=HASH, evidence_sha256=evidence)
        proof = dict(log_sha256=HASH, vector_trace_sha256=HASH, contract_event_count=1,
            uvm_backend_event_count=1, axi_read_counts=dict(completed=1), axi_write_counts=dict(matched=1))
        pins = {'/elf':HASH, '/simv':HASH}
        files = {'status.json':status, 'result.json':report, 'source-pins.json':pins, 'uvm_result.json':proof}
        return run, build, parsed, files

    def check_terminal(self, fixture):
        run, build, parsed, files = fixture
        with patch.object(a.s, 'read_json', side_effect=lambda p:files[p.name]), \
             patch.object(a.s, 'digest', return_value=HASH), \
             patch.object(a.s, 'verify_pins'), patch.object(a.s, 'check_result'), \
             patch.object(a.s, 'image_files', return_value=[Path('/simv')]), \
             patch.object(a.s, 'hashes', side_effect=lambda paths:{str(p):HASH for p in paths}), \
             patch.object(Path, 'read_text', return_value='synthetic-only'):
            return a.terminal(run, 'q4_0', build, lambda text:parsed, {'/simv':HASH}, True)

    def test_terminal_fixture(self):
        self.assertEqual(self.check_terminal(self.terminal_fixture())[2], raw())

    def test_terminal_identity_and_protocol_mutations(self):
        mutations = [('status.json', 'state', 'RUNNING'), ('status.json', 'child_pid', 123),
            ('status.json', 'kind', 'decode'), ('status.json', 'running_exit_code', 1),
            ('status.json', 'counter_policy', 'AKV_PERF'), ('status.json', 'build', '/wrong'),
            ('result.json', 'source_pins_sha256', 'drift'), ('result.json', 'elf_sha256', 'drift'),
            ('result.json', 'post_pins_match', False), ('uvm_result.json', 'log_sha256', 'drift'),
            ('uvm_result.json', 'contract_event_count', 0), ('uvm_result.json', 'axi_write_counts', {})]
        for filename, field, value in mutations:
            fixture = self.terminal_fixture(); fixture[3][filename][field] = value
            with self.subTest(file=filename, field=field), self.assertRaises((ValueError, RuntimeError)):
                self.check_terminal(fixture)


if __name__ == '__main__': unittest.main()
