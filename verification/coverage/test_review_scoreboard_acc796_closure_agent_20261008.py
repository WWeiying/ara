"""Offline source/config/EL negative tests only. Never loads an EDA tool."""
import copy
import unittest

import review_scoreboard_acc796_closure_agent_20261008 as m


class ClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = m.collect()
        cls.config = m.config(cls.report)
        cls.el = m.candidate_el(cls.config)

    def reject_config(self, edit):
        bad = copy.deepcopy(self.config)
        edit(bad)
        with self.assertRaises(ValueError):
            m.validate_config(bad, self.config)

    def test_exact57_not59(self):
        self.assertEqual(self.report['physical_bits_per_copy'], 57)
        self.assertEqual(self.report['newly_closed_physical_bits'], 46 * 57)
        self.assertEqual(self.report['newly_closed_slots'], 46 * 114)
        self.assertEqual(m.validate_el(self.el, self.config), 1596)
        m.validate_config(self.config, m.config(self.report))

    def test_archived_compiled_dispatcher_not_live(self):
        binding = next(r for r in self.report['compiled_source_bindings']
                       if r['original'].endswith('/ara_dispatcher.sv'))
        self.assertEqual(binding['sha256'],
            '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43')
        self.assertEqual(binding['evidence'], str(m.ARCHIVE / 'ara_dispatcher.sv'))
        self.assertNotIn(binding['original'], self.report['input_pins'])
        self.assertFalse(self.report['native_qualified'])

    def test_pin_drift(self):
        with self.assertRaises(ValueError):
            m.check_pins({str(m.ARCHIVE / 'ara_dispatcher.sv'): '0' * 64})

    def test_unknown_whole_cause_slice_compound_writers(self):
        expected = {'r': ["'0"], 'r.cause': ['riscv::ILLEGAL_INSTR']}
        text = "r = '0; r.cause = riscv::ILLEGAL_INSTR;"
        m.contract(text, expected)
        for extra in ('r = external;', 'r.cause = external;', "r.cause[62] = 1'b1;",
                      "r.cause |= 64'h100;", "r |= '1;"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                m.contract(text + extra, expected)

    def test_all_branch_contracts_include_inactive_paths(self):
        rows = self.report['complete_ACC_whole_cause_writer_contracts'][m.DISPATCH]
        self.assertEqual(len(rows), 13)
        self.assertEqual(sum(r['rhs'] == 'ara_resp.exception' for r in rows), 11)
        self.assertLess(max(self.report['finite_ACC_LSU_cause_values'].values()), 64)

    def test_low6_bit63_count_mask(self):
        for key, value in [('selected_bits', list(range(5, 63))),
                           ('selected_bits', list(range(6, 64))), ('bits_count', 59),
                           ('physical_mask', '0xffffffffffffffff'), ('protected_bits', [63])]:
            with self.subTest(key=key, value=value):
                self.reject_config(lambda c: c['groups'][0]['targets'][0].__setitem__(key, value))

    def test_whole_cause_exception_CSR_ACC46_rejected(self):
        for name in ('ex_i', 'ex_i.cause[63:0]', 'mcause_q', 'scause_q', 'ex_i[4].cause'):
            with self.subTest(name=name):
                self.reject_config(lambda c: c['groups'][0]['targets'][0].__setitem__('name', name))

    def test_duplicate_missing_target_scope_type_checksum(self):
        edits = [lambda c: c['groups'][0]['targets'].append(c['groups'][0]['targets'][0]),
                 lambda c: c['groups'][0]['targets'].pop(),
                 lambda c: c['groups'][0].__setitem__('scope', 'wrong'),
                 lambda c: c['groups'][0].__setitem__('design_checksum', '0'),
                 lambda c: c['groups'][0].__setitem__('toggle_checksum', '0'),
                 lambda c: c['groups'][0]['targets'][0]['attributes'].__setitem__('right', '6')]
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject_config(edit)

    def test_complement_MDA_ports_directions_and_protocol_protected(self):
        edits = [lambda c: c['groups'][1]['complete_typed_scope_inventory'].pop(),
                 lambda c: next(n for n in c['groups'][1]['complete_typed_scope_inventory']
                                if n['kind'] == 'arrays')['attributes'].__setitem__('packedrange', ''),
                 lambda c: c['groups'][0]['targets'][0].__setitem__('port_native_binding_required', False),
                 lambda c: c['groups'][0]['targets'][0].__setitem__('directions', ['0to1']),
                 lambda c: c['required_future_protocol'].__setitem__('global_reset_all_scopes', False),
                 lambda c: c.__setitem__('native_qualified', True)]
        for edit in edits:
            with self.subTest(edit=edit):
                self.reject_config(edit)

    def test_EL_low6_bit63_whole_wrong_type(self):
        for text in (self.el.replace(' [6] ', ' [5] ', 1),
                     self.el.replace(' [6] ', ' [63] ', 1),
                     self.el.replace(' [6] ', ' ', 1),
                     self.el.replace('[63:0]"', '[62:6]"', 1),
                     self.el.replace('Toggle ', 'WHOLE_SCOPE ', 1)):
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                m.validate_el(text, self.config)

    def test_EL_missing_one_direction_duplicate_extra_acc_scope_checksum(self):
        for text in (self.el.replace('Toggle ', 'Toggle 0to1 ', 1),
                     self.el + next(l for l in self.el.splitlines() if l.startswith('Toggle ')) + '\n',
                     self.el.replace('ex_i.cause', 'ex_i[4].cause'),
                     self.el.replace('INSTANCE: ara_tb.', 'INSTANCE: wrong.', 1),
                     self.el.replace('CHECKSUM: "', 'CHECKSUM: "0 ', 1)):
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                m.validate_el(text, self.config)

    def test_both_explicit_named_directions_supported(self):
        lines = []
        for line in self.el.splitlines():
            if line.startswith('Toggle '):
                lines.extend(line.replace('Toggle ', 'Toggle ' + d + ' ', 1)
                             for d in ('0to1', '1to0'))
            else:
                lines.append(line)
        self.assertEqual(m.validate_el('\n'.join(lines), self.config), 1596)


if __name__ == '__main__':
    unittest.main()
