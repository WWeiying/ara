"""Host-only registered-source, recipe, loader and instruction contract tests."""

import hashlib
import json
from pathlib import Path
import re
import struct
import unittest

import balanced_soc_handoff as b


class BalancedHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (b.BASE / 'archive-input' / b.SOURCE_REL).read_text()
        cls.text, cls.proof = b.transform(cls.original)
        cls.old = json.loads((b.BASE / 'result.json').read_text())

    def test_exact_identity_full_inverse_and_no_live_inputs(self):
        self.assertEqual(b.digest(b.BASE / 'result.json'), b.BASE_SHA)
        self.assertEqual(hashlib.sha256(self.original.encode()).hexdigest(), b.SOURCE_SHA)
        restored = self.text
        for edit in reversed(self.proof['edits']):
            self.assertEqual(restored.count(edit['after']), edit['count'])
            restored = restored.replace(edit['after'], edit['before'])
        self.assertEqual(restored, self.original)
        for bad in (None, b'', '', self.original + '\n', self.original * 2, self.text):
            with self.assertRaises(ValueError):
                b.transform(bad)

    def test_m4_both_branches_vl_and_complete_clobbers(self):
        issue = self.text.split('static void issue_qbs_m4(', 1)[1].split('static void issue_akv_v2_full', 1)[0]
        for token in ('li t0, 128', 'e32, m4, ta, ma', '.word 0x06b5045b',
                      '"t0", "v8", "v9", "v10", "v11", "memory"'):
            self.assertEqual(issue.count(token), 2)
        checked, discard = issue.split('  } else {', 1)
        self.assertIn('vmv.v.i v8, -1', checked)
        self.assertIn('vse32.v v8, (a2)', checked)
        self.assertNotIn('vmv.v.i', discard)
        self.assertNotRegex(discard, r'\bv(?:le|se)[0-9]+\.v\b')
        self.assertNotIn('0x00b5045b', self.text)

    def test_four_distinct_rows_all_128_words_and_zero_tails(self):
        self.assertIn('qbs_activation[4]', self.text)
        self.assertIn('Q8_BLOCK(1), Q8_BLOCK(2), Q8_BLOCK(3), Q8_BLOCK(4)', self.text)
        self.assertIn('qbs_observed[128]', self.text)
        check = self.text.split('static int check_qbs(void) {', 1)[1].split('static int check_rvv', 1)[0]
        initializer = check.split('expected_results[4][3] = {', 1)[1].split('};', 1)[0]
        values = [int(x, 16) for x in re.findall(r'0x([0-9a-f]{8})u', initializer)]
        expected = [struct.unpack('<I', struct.pack('<f', float(256 * row * col)))[0]
                    for row in range(1, 5) for col in range(1, 4)]
        self.assertEqual(values, expected)
        for token in ('index < 128', 'qbs_observed[index] = 0xa5a5a5a5u',
                      'row < 4', 'col < 32', 'col < 3 ? expected_results[row][col] : 0', '32 * row + col'):
            self.assertIn(token, check)
        self.assertNotIn('break;', check)
        self.assertEqual(self.proof['checked_nonzero_words'], 24)
        self.assertEqual(self.proof['checked_zero_tail_words'], 232)
        self.assertEqual(self.proof['checked_qbs_words'], 256)

    def test_existing_akv_rvv_trap_and_descriptor_functions_unchanged(self):
        for begin, end in (
            ('static void issue_akv_v2_full', 'static int check_qbs'),
            ('static int check_rvv', 'int main(void)'),
            ('void __attribute__((naked, used)) mtvec_handler', 'static void issue_qbs_')):
            section = lambda text: text.split(begin, 1)[1].split(end, 1)[0]
            self.assertEqual(section(self.text), section(self.original))
        main = self.text.split('int main(void)', 1)[1]
        old_main = self.original.split('int main(void)', 1)[1]
        self.assertEqual(main.count('check_rvv('), old_main.count('check_rvv('))
        self.assertEqual(main.count('check_rvv('), 3)
        self.assertEqual(main.count('issue_qbs_m4(0);'), 2)
        for sequence in ('issue_qbs_m4(0);\n  issue_akv_v2_full();',
                         'issue_akv_release();\n  issue_qbs_m4(0);'):
            self.assertIn(sequence, main)
        self.assertNotRegex(self.text, r'\b(?:pmpaddr\w*|pmpcfg\w*|satp)\b')

    def test_recipe_changes_only_source_include_object_and_outputs(self):
        rows = json.loads((b.BASE / 'commands.json').read_text())
        out = Path('/new-build')
        for label in ('dependencies', 'compile-main', 'link'):
            old = next(r['argv'] for r in rows if r['label'] == label)
            actual = b.recipe(old, out)
            reverse = [a.replace(str(out / 'source/main.c'), str(b.BASE / 'archive-input' / b.SOURCE_REL))
                       .replace('-I' + str(out / 'source/common'), '-I' + str(b.BASE / 'archive-input/apps/common'))
                       .replace(str(out / 'handoff-main.o'), str(b.BASE / 'handoff-main.o'))
                       .replace(str(out / 'balanced_soc_handoff.elf'), str(b.BASE / 'qbs_akv_handoff_smoke.elf'))
                       .replace('-Map=' + str(out / 'link.map'), '-Map=' + str(b.BASE / 'link.map')) for a in actual]
            self.assertEqual(reverse, old)
            if label == 'link':
                self.assertEqual([a for a in actual if a.endswith('.o')][1:], list(self.old['reused_common_objects']))
                self.assertIn(self.old['reused_linker'], actual)
                self.assertIn('-fno-tree-vectorize', actual)
        objects = b.elf_objects(Path(self.old['elf']).read_bytes())
        self.assertEqual(objects['qbs_activation']['size'], 292)
        self.assertEqual(objects['qbs_weights']['size'], 432)
        with self.assertRaises(ValueError):
            b.payload_proof(Path(self.old['elf']).read_bytes(), Path(self.old['elf']).read_bytes())

    def test_uart_marker_scope_not_old_m1_or_skip(self):
        log = b.SCOPE + '\n' + b.PASS + '\n'
        self.assertEqual(b.check_log(log), b.EXPECTED_CHECKS)
        for bad in (b.parent.PASS + '\n', log + b.PASS + '\n', log + b.SCOPE + '\n',
                    log.replace('traps=0', 'traps=1'), log.replace('PASS', 'SKIP'),
                    log.replace('m=4', 'm=1'), b.PASS + '\n' + b.SCOPE + '\n',
                    log + 'QBS M4 mismatch[row=3 col=31]\n', log + 'Fatal: failure\n'):
            with self.assertRaises(ValueError):
                b.check_log(bad)

    def test_instruction_contract_rejects_old_opcode_wrong_vl_or_vtype(self):
        codes = ['06b5045b', '06b5045b', '0005155b', '0005455b', '00b5605b', '0005345b', '0000505b']
        text = '\n'.join(f'80000000: {code} custom' for code in codes)
        text += '\n' + ('80000000: 08000293 addi t0,zero,128\n'
                         '80000004: 0d22f057 vsetvli zero,t0,e32,m4,ta,ma\n') * 2
        text += '80000008: 3b029073 csrrw zero,pmpaddr0,t0\n'
        self.assertEqual(b.instruction_contract(text)['static_opcode_sites'], 2)
        for bad in (text.replace('06b5045b', '00b5045b', 1), text.replace('zero,128', 'zero,32'),
                    text.replace('e32,m4', 'e32,m1'), text.replace('0005345b', '00000013'),
                    text + 'satp\n', text + 'pmpcfg0\n'):
            with self.assertRaises(ValueError):
                b.instruction_contract(bad)


if __name__ == '__main__':
    unittest.main()
