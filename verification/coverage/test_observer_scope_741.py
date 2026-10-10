import unittest
from pathlib import Path

import observer_scope_741 as audit


class Observer741Tests(unittest.TestCase):
    def test_exact_native_roundtrip(self):
        text = ''.join('CHECKSUM: "' + v[1] + '"\nANNOTATION: "observer"\nINSTANCE:' + p + '\n'
                       for p, v in audit.TARGETS.items())
        self.assertEqual(audit.native_entries(text), {p: v[1] for p, v in audit.TARGETS.items()})

    def test_no_point_exclusions(self):
        with self.assertRaises(ValueError):
            audit.native_entries('CHECKSUM: "1"\nINSTANCE:x\nToggle foo\n')

    def test_duplicates_missing_checksum_rejected(self):
        for text in ('INSTANCE:x\n', 'CHECKSUM: "1"\n',
                     'CHECKSUM: "1"\nINSTANCE:x\nCHECKSUM: "1"\nINSTANCE:x\n'):
            with self.assertRaises(ValueError):
                audit.native_entries(text)

    def test_real_frozen_source(self):
        self.assertEqual(len(audit.source_contract()), 6)

    def test_real_native_four_leaves(self):
        design = Path(str(audit.life.IMAGE) + '.vdb') / 'snps/coverage/db/design/verilog.design.xml'
        self.assertEqual(len(audit.compiled_targets(design)), 4)

    def test_tcl_no_recursive_or_new_syntax(self):
        text = (audit.HERE / 'observer_scope_741.tcl').read_text()
        self.assertNotIn('-recursive', text)
        self.assertNotIn('{*}', text)
        self.assertIn('gui_exclusion -reset', text)
        self.assertIn('observers-reloaded.el', text)


if __name__ == '__main__':
    unittest.main()
