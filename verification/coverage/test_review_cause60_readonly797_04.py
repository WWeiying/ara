"""Read-only audit gates: synthetic negatives are not native API evidence."""
import copy
import unittest

import review_cause60_readonly797_04 as m


class Audit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = m.core.read_bound(m.core.OUT / 'config.json', m.CONFIG_SHA)
        cls.copies = c['source_closure']['previously_independent14'] + c['source_closure']['newly_closed46']
        cls.rows = {}
        for t in cls.copies:
            cls.rows[t['scope']] = dict(width=100000, checksum=t['checksum'], bits='0x0')

    def test_exact57_6840_no_direction_mapping(self):
        r = m.zero_gate(self.copies, self.rows, self.rows, self.rows)
        self.assertEqual(r['physical_bits_per_copy'], 57)
        self.assertEqual(r['unnamed_serialized_pairslots_checked_each_population'], 6840)
        self.assertFalse(r['native_direction_IDs_inferred'])

    def test_suffix_counterexample_rejected(self):
        rows = copy.deepcopy(self.rows)
        t = self.copies[0]
        p = t['selected_residual_slots'][0]
        row = rows[t['scope']]
        row['bits'] = hex(1 << (row['width']-1-p))
        with self.assertRaisesRegex(ValueError, 'counterexample'):
            m.zero_gate(self.copies, self.rows, rows, rows)

    def test_OR_width_checksum_rejected(self):
        for key, value in (('bits', '0x1'), ('width', 99999), ('checksum', 'bad')):
            rows = copy.deepcopy(self.rows)
            rows[self.copies[0]['scope']][key] = value
            with self.assertRaises(ValueError):
                m.zero_gate(self.copies, self.rows, self.rows, rows)

    def test_exact_coordinates_duplicate_and_low6_rejected(self):
        for mutation in ('offset', 'duplicate', 'low6'):
            copies = copy.deepcopy(self.copies)
            if mutation == 'offset':
                copies[0]['compiled_attributes']['serialized_offset'] += 1
            elif mutation == 'duplicate':
                copies[-1] = copy.deepcopy(copies[0])
            else:
                copies[0]['selected_physical_bits'][0] = 5
            with self.assertRaises(ValueError):
                m.zero_gate(copies, self.rows, self.rows, self.rows)

    def test_protected_low6_interrupt_are_not_zero_requirements(self):
        rows = copy.deepcopy(self.rows)
        t = self.copies[0]
        offset = t['compiled_attributes']['serialized_offset']
        width = rows[t['scope']]['width']
        rows[t['scope']]['bits'] = hex(sum(1 << (width-1-offset-2*b) for b in (0,1,2,3,4,5,63)))
        m.zero_gate(self.copies, rows, self.rows, rows)

    def test_EL_ownership_parent_whole_single_direction_rejected(self):
        t = self.copies[0]
        for directive in ('WHOLE_SCOPE', 'Toggle ' + t['name'],
                          'Toggle 0to1 ' + t['name'] + ' [62:6]',
                          'Toggle ' + t['name'].rsplit('.', 1)[0]):
            with self.assertRaises(ValueError):
                m.ownership_gate('INSTANCE:' + t['scope'] + '\n' + directive, self.copies)
        m.ownership_gate('INSTANCE:unrelated\nToggle mcause_q', self.copies)

    def test_exact_existing_semantics_reject_bit_direction_scope_changes(self):
        semantic = m.semantic_parser({})
        text = b'CHECKSUM: "123"\nINSTANCE:unit\nToggle cause [62:6] "logic cause[63:0]"\n'
        expanded = text.replace(b'Toggle cause', b'Toggle 0to1 cause') + (
            b'CHECKSUM: "123"\nINSTANCE:unit\nToggle 1to0 cause [62:6] "logic cause[63:0]"\n')
        self.assertEqual(semantic(text), semantic(expanded))
        for changed in (text.replace(b'62:6', b'62:5'), text.replace(b'INSTANCE:unit', b'INSTANCE:other'),
                        text.replace(b'Toggle cause', b'Toggle 0to1 cause')):
            self.assertNotEqual(semantic(text), semantic(changed))


if __name__ == '__main__':
    unittest.main()
