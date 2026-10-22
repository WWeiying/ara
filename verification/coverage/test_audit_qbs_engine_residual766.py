import copy
import unittest

import audit_qbs_engine_residual766 as m


class WholeQBS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {p.name: p.read_text() for p in [m.PKG, *m.SOURCE_DIR.glob('*.sv')]}
        cls.facts = m.bound_facts(cls.texts['qbs_pkg.sv'])
        cls.scopes = m.bind_scopes(m.f.xml(m.DB / 'design/verilog.design.xml'),
                                  m.f.xml(m.DB / 'shape/tgl.verilog.info.xml'),
                                  m.f.xml(m.DB / 'shape/tgl.verilog.shape.xml'))
        cls.cache = m.load(m.f.CACHE, m.f.CACHE_SHA)

    def test_real102_exact_compiled_source_parameters_and_all_shapes(self):
        self.assertEqual(len(self.scopes), 102)
        for scope, v in self.scopes.items():
            typed, arrays = m.fields(v['definition'], self.cache['instances'][scope])
            self.assertEqual(len(typed) + len(arrays), len(v['definition'].find('tglshape')))
            self.assertEqual(sum(p['missing'] for p in typed), self.cache['instances'][scope]['missing'])
        self.assertEqual(m.integer_params(self.scopes[m.QBS]['definition'])['VLEN'], 1024)
        self.assertEqual(m.integer_params(self.scopes[m.QBS + '.i_descriptor_decoder']['definition']), {'VLEN': 1024})

    def test_source_writer_induction_all_reset_error_paths(self):
        proof = m.source_contract(self.texts)
        self.assertTrue(proof['register_assignment_counts_verified'])
        self.assertTrue(proof['unbounded_wait_backpressure_cycle_counters_retained'])

    def test_added_writer_and_removed_valid_gate_rejected(self):
        for suffix in ('\nweight_row_bytes_q <= 25\'h1000000;\n', '\ncontext_id_q <= 4\'hf;\n'):
            text = dict(self.texts); text['qbs_engine.sv'] += suffix
            with self.assertRaises(ValueError): m.source_contract(text)
        text = dict(self.texts)
        text['qbs_engine.sv'] = text['qbs_engine.sv'].replace('QBS_ENGINE_VALIDATE && descriptor_valid', 'QBS_ENGINE_VALIDATE')
        with self.assertRaises(ValueError): m.source_contract(text)

    def test_all_profiles_including_invalid_default_bound(self):
        self.assertEqual(self.facts['weight_profile_sizes'], [144, 176, 210, 110, 34, 18, 84, 22, 18])
        self.assertEqual(self.facts['activation_profile_sizes'], [292, 34])
        pkg = self.texts['qbs_pkg.sv']
        for changed in (pkg.replace('qbs_weight_block_bytes = 210;', 'qbs_weight_block_bytes = size_i;'),
                        pkg.replace("qbs_activation_block_bytes = '0;", "qbs_activation_block_bytes = '1;"),
                        pkg.replace('QbsMaxKBlocks = 256;', 'QbsMaxKBlocks = 128;')):
            with self.assertRaises(ValueError): m.bound_facts(changed)

    def test_invalid_m_counterexample_legal_largest_shapes_not_discarded(self):
        raw_max = 15 * 256 * 292; legal_max = 8 * 256 * 292
        self.assertEqual(raw_max, self.facts['activation_storage_including_invalid_m_max'])
        self.assertEqual(raw_max.bit_length(), 21); self.assertEqual(legal_max.bit_length(), 20)
        self.assertTrue(raw_max & (1 << 20))
        rules = m.constant_rules(self.facts)
        rule = next(p for p in rules if p[1] == 'descriptor_activation_storage_bytes')
        self.assertEqual(rule[3], 21)
        self.assertFalse(any(p[1] in ('m_q', 'n_q', 'k_blocks_q', 'command_cycles_o', 'fault_sequence_q') for p in rules))
        self.assertEqual((32).bit_length(), 6); self.assertEqual((256).bit_length(), 9)

    def toy(self):
        return dict(scope=m.QBS, module='qbs_engine', name='weight_row_bytes_q', kind='vectornode', width=25,
                    raw_offset=10, attributes=dict(name='weight_row_bytes_q', left='24', right='0', portnode='0', excluded='0'),
                    missing_coordinates=list(range(10, 60)), source_binding=dict(path='frozen-source', line=213))

    def test_exact_partial_range_and_observed_toggle_counterexample(self):
        p = self.toy(); result = m.candidate(p, 25, 16, 24, 'product-bound')
        self.assertEqual(result['candidate_bit_range'], [24, 16]); self.assertEqual(result['missing_raw_directions'], 18)
        self.assertTrue(result['entire_object_not_excluded'])
        changed = copy.deepcopy(p); changed['missing_coordinates'].remove(42)
        with self.assertRaises(ValueError): m.candidate(changed, 25, 16, 24, 'product-bound')
        for key, value in (('left', '25'), ('right', '1'), ('portnode', '3'), ('excluded', '1')):
            changed = copy.deepcopy(p); changed['attributes'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.candidate(changed, 25, 16, 24, 'product-bound')

    def test_arrays_have_no_invented_memory_coordinates(self):
        for scope, v in self.scopes.items():
            _, arrays = m.fields(v['definition'], self.cache['instances'][scope])
            for p in arrays:
                self.assertIsNone(p['missing']); self.assertNotIn('raw_offset', p)

    def test_bitmap_width_checksum_and_missing_scope_rejected(self):
        d = self.scopes[m.QBS]['definition']; raw = self.cache['instances'][m.QBS]
        for key, value in (('checksum', '1'), ('width', raw['width'] - 2)):
            changed = dict(raw); changed[key] = value
            with self.assertRaises(ValueError): m.fields(d, changed)

    def test_data_entropy_is_not_arbitration_or_unreachability_proof(self):
        self.assertTrue(m.data_class('qbs_payload_buffer', 'gen_word[0].hit').startswith('MAPPING'))
        self.assertTrue(m.data_class('qbs_payload_sram', 'wdata_i').startswith('SRAM_DATA'))
        evidence = m.entropy_header(m.MATRIX / 'matrix_data.h')
        self.assertEqual(len(evidence['arrays']), 8); self.assertFalse(evidence['all_temporal_causes_proven'])


if __name__ == '__main__': unittest.main()
