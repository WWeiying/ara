#!/usr/bin/env python3
"""Syntax-repair policy plus the unchanged original evidence-checker tests."""
import hashlib
from pathlib import Path
import unittest

import run_wide_clients_checked as checked
from test_wide_clients import WideClientsTests


class SyntaxPolicyTests(unittest.TestCase):
    def bench(self):
        local = Path(__file__).with_name('qbs_wide_clients_tb.sv')
        if local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() == checked.BENCH_SHA:
            return local.read_bytes()
        return (checked.FIRST/'source-snapshot/tests/qbs_wide_clients_tb.sv').read_bytes()

    def test_exact_mechanical_repair(self):
        old = self.bench()
        fixed, audit = checked.repaired_fixture(old)
        self.assertEqual(fixed.replace(checked.NEW_TYPEDEF, checked.OLD_TYPEDEF, 1).encode(), old)
        self.assertEqual(audit['replacement_count'], 1)
        self.assertEqual((audit['declarations_before'], audit['declarations_after']), (5, 6))
        self.assertFalse(any(row['commas'] for row in checked.typedef_inventory(fixed)))

    def test_wrong_fixture_and_already_repaired_rejected(self):
        old = self.bench()
        fixed, _ = checked.repaired_fixture(old)
        for bad in (old+b'\n', old.replace(b'id_t, user_t', b'id_t, user_t, extra_t'), fixed.encode()):
            with self.assertRaises(ValueError):
                checked.repaired_fixture(bad)

    def test_all_combined_declarations_discovered(self):
        text = 'typedef logic [0:0] a_t, b_t;\ntypedef logic [3:0] c_t,d_t;'
        rows = checked.typedef_inventory(text)
        self.assertEqual([len(row['commas']) for row in rows], [1, 1])

    def test_struct_members_comments_and_strings_not_typedef_aliases(self):
        text = ('// typedef logic fake_t, other_t;\n'
                'typedef struct packed {logic [2:0] a,b; logic c;} one_t;\n'
                'initial $display("typedef fake, also_fake;");\n'
                '/* typedef invalid_t, invalid2_t; */\n')
        rows = checked.typedef_inventory(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['commas'], [])

    def test_unterminated_and_unbalanced_typedef_rejected(self):
        for text in ('typedef logic [2:0] x_t', 'typedef logic ] x_t;'):
            with self.assertRaises(ValueError):
                checked.typedef_inventory(text)


if __name__ == '__main__':
    unittest.main()
