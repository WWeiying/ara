"""Host-only controller/VLSU source identity, inverse and wiring tests."""
import hashlib
import json
import re
import unittest
from unittest.mock import patch

import balanced_engine_source as b


def connections(source, instance):
    marker = r'\b' + re.escape(instance) + r'\s*\('
    if len(re.findall(marker, source)) != 1:
        raise ValueError('Missing/duplicate instance')
    return re.search(marker + r'(.*?)\n\s*\);', source, re.S).group(1)


class BalancedEngineSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine_original = b.ENGINE_SOURCE.read_text()
        cls.vlsu_original = b.VLSU_SOURCE.read_text()
        cls.engine_text, cls.engine_report = b.engine(cls.engine_original)
        cls.vlsu_text, cls.vlsu_report = b.vlsu(cls.vlsu_original)

    def test_inputs_are_bound_to_accepted_snapshot_inventory(self):
        prepared = b.SOURCE_ROOT.parent
        receipt = prepared / 'result.json'
        self.assertEqual(hashlib.sha256(receipt.read_bytes()).hexdigest(),
                         'dad1e64aaa814f3fa4c5cf2d2bf3bb1ea105ca12aa1448ec3e8f0ae310942e29')
        record = json.loads(receipt.read_text())
        self.assertEqual(record['state'], 'PHYSICAL_WIDE_SOC_INPUTS_PREPARED')
        inventory_file = prepared / 'source-pins.json'
        self.assertEqual(hashlib.sha256(inventory_file.read_bytes()).hexdigest(), record['source_pins_sha256'])
        inventory = json.loads(inventory_file.read_text())
        for path, expected in ((b.ENGINE_SOURCE, b.ENGINE_SHA), (b.VLSU_SOURCE, b.VLSU_SHA)):
            self.assertEqual(inventory[str(path)], expected)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_complete_inverse_including_names_guards_and_parameters(self):
        for original, text, report in ((self.engine_original, self.engine_text, self.engine_report),
                                       (self.vlsu_original, self.vlsu_text, self.vlsu_report)):
            self.assertEqual(b.sha(original), report['original_sha256'])
            self.assertEqual(b.sha(text), report['generated_sha256'])
            for edit in reversed(report['edits']):
                self.assertEqual(edit['count'], 1)
                self.assertEqual(text.count(edit['after']), 1)
                text = text.replace(edit['after'], edit['before'], 1)
            self.assertEqual(text, original)
            self.assertTrue(report['source_reversible'])
            json.dumps(report, allow_nan=False)

    def test_drift_wrong_type_wrong_source_and_double_transform_rejected(self):
        for fn, original, clone in ((b.engine, self.engine_original, self.engine_text),
                                    (b.vlsu, self.vlsu_original, self.vlsu_text)):
            for bad in (None, b'', '', original + '\n', original * 2, clone,
                        original.replace('\n', '\r\n')):
                with self.subTest(function=fn.__name__, value=type(bad)), self.assertRaises(ValueError):
                    fn(bad)
        with self.assertRaises(ValueError):
            b.engine(self.vlsu_original)
        with self.assertRaises(ValueError):
            b.vlsu(self.engine_original)

    def test_anchor_count_gate_independent_of_input_digest(self):
        engine_anchor = next(edit['before'] for edit in self.engine_report['edits']
                             if edit['label'] == 'balanced-compute-instance')
        vlsu_anchor = next(edit['before'] for edit in self.vlsu_report['edits']
                           if edit['label'] == 'balanced-engine-instance')
        cases = ((b.engine, 'ENGINE_SHA', self.engine_original, engine_anchor),
                 (b.vlsu, 'VLSU_SHA', self.vlsu_original, vlsu_anchor))
        for fn, constant, original, anchor in cases:
            for changed in (original.replace(anchor, '  other_engine #(', 1), original + '\n' + anchor):
                with patch.object(b, constant, b.sha(changed)), self.assertRaisesRegex(ValueError, 'anchor'):
                    fn(changed)

    def test_engine_default_off_requires_wide_and_preserves_hierarchy(self):
        text = self.engine_text
        self.assertIn('module qbs_engine_balanced\n', text)
        self.assertIn('endmodule : qbs_engine_balanced', text)
        self.assertIn("parameter bit BalancedMatrixDot = 1'b0,", text)
        self.assertIn('assert (!BalancedMatrixDot || WideMatrixDot)', text)
        self.assertIn('.BalancedMatrixDot(BalancedMatrixDot)', text)
        self.assertEqual(text.count('  qbs_compute_engine_balanced #('), 1)
        self.assertEqual(connections(text, 'i_compute_engine'), connections(self.engine_original, 'i_compute_engine'))

    def test_engine_seed_and_other_compute_parameter_passthrough(self):
        for token in ('.SeedRestoreEnable(SeedRestoreEnable)', '.WideMatrixDot(WideMatrixDot)',
                      '.WideWeightIngress(WideWeightIngress)', '.command_seed_i                 (seeded_q)',
                      '.seed_valid_i                   (seed_valid)', '.seed_ready_o                   (seed_ready)',
                      'if (SeedRestoreEnable) begin : gen_seed_route', 'qbs_vrf_seed_mapper i_seed_mapper'):
            self.assertEqual(self.engine_text.count(token), self.engine_original.count(token))
        self.assertEqual(connections(self.engine_text, 'i_seed_mapper'),
                         connections(self.engine_original, 'i_seed_mapper'))

    def test_engine_external_ports_and_controller_body_unchanged(self):
        ports = lambda text: text.split('  ) (', 1)[1].split('\n  );', 1)[0]
        self.assertEqual(ports(self.engine_original), ports(self.engine_text))
        begin = '  assign compute_command_valid ='
        end = '  qbs_compute_engine'
        self.assertEqual(self.engine_original.split(begin, 1)[1].split(end, 1)[0],
                         self.engine_text.split(begin, 1)[1].split(end, 1)[0])
        self.assertTrue(self.engine_report['reader_context_commit_and_fault_logic_unchanged'])

    def test_vlsu_default_macro_guard_and_explicit_enable(self):
        text = self.vlsu_text
        expected = ('`ifndef ' + b.EXPERIMENT_DEFINE + '\n`define ' + b.EXPERIMENT_DEFINE + ' 0\n`endif\n\n')
        self.assertEqual(b.MACRO_GUARD, expected)
        self.assertEqual(text.count(expected), 1)
        self.assertLess(text.index(expected), text.index('module vlsu import'))
        self.assertIn('.BalancedMatrixDot(`' + b.EXPERIMENT_DEFINE + '),', text)
        self.assertNotIn('`undef ' + b.EXPERIMENT_DEFINE, text)
        # Exercise just the emitted ifndef/define guard, not an SV compiler.
        for supplied in (None, '0', '1'):
            defines = {} if supplied is None else {b.EXPERIMENT_DEFINE: supplied}
            lines = expected.splitlines()
            macro = lines[0].split()[1]
            if macro not in defines:
                directive, name, value = lines[1].split()
                self.assertEqual((directive, name), ('`define', macro))
                defines[name] = value
            self.assertEqual(defines[macro], '0' if supplied is None else supplied)
        self.assertEqual(self.vlsu_report['enable_flag'], '+define+ARA_EXPERIMENT_BALANCED_MATRIX_DOT=1')

    def test_vlsu_hierarchy_ports_and_seed_wiring_preserved(self):
        self.assertEqual(self.vlsu_text.count('  qbs_engine_balanced #('), 1)
        self.assertNotIn('module vlsu_balanced', self.vlsu_text)
        self.assertEqual(connections(self.vlsu_text, 'i_qbs_engine'),
                         connections(self.vlsu_original, 'i_qbs_engine'))
        for token in ('.SeedRestoreEnable(QbsVrfContinuationEnable && NrLanes == 4 && VLEN == 1024)',
                      '.command_seed_i(QbsVrfContinuationEnable && pe_req_i.use_vs1)',
                      '.clk_i(qbs_clk)', '.seed_lane_valid_i(qbs_seed_lane_valid)',
                      '.seed_lane_ready_o(qbs_seed_lane_ready)', '.seed_lane_data_i(qbs_seed_lane_data)'):
            self.assertEqual(self.vlsu_text.count(token), self.vlsu_original.count(token))

    def test_vlsu_only_adds_one_named_parameter_and_keeps_probes(self):
        original = self.vlsu_original.split('  qbs_engine #(', 1)[1].split(') i_qbs_engine (', 1)[0]
        changed = self.vlsu_text.split('  qbs_engine_balanced #(', 1)[1].split(') i_qbs_engine (', 1)[0]
        changed = changed.replace('    .BalancedMatrixDot(`ARA_EXPERIMENT_BALANCED_MATRIX_DOT),\n', '', 1)
        self.assertEqual(changed, original)
        probe = lambda text: [line for line in text.splitlines() if 'i_qbs_engine.' in line]
        self.assertTrue(probe(self.vlsu_original))
        self.assertEqual(probe(self.vlsu_text), probe(self.vlsu_original))
        ports = lambda text: text.split('  ) (', 1)[1].split('\n  );', 1)[0]
        self.assertEqual(ports(self.vlsu_text), ports(self.vlsu_original))

    def test_no_new_dependency_or_abi_or_protocol_transform(self):
        for old, new in ((self.engine_original, self.engine_text), (self.vlsu_original, self.vlsu_text)):
            self.assertEqual(re.findall(r'`include[^\n]*', old), re.findall(r'`include[^\n]*', new))
            for token in ('qbs_akv_shared_reader', 'qbs_commit', 'qbs_activation_context',
                          'success_valid_o', 'fault_valid_o', 'qbs_info', '[QBS_PERF]'):
                self.assertEqual(old.count(token), new.count(token))
        self.assertFalse(self.engine_report['rtl_compiled'])
        self.assertFalse(self.vlsu_report['target_executed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
