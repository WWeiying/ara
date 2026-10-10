"""Pure positive/negative tests; no artifact mutation, prepare, or simulator."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_gap47_rvv_checked_extension as adapter


class TraceTest(unittest.TestCase):
    def setUp(self):
        self.sites = {name: dict(pc=hex(0x80000100 + 4 * i), word=hex(word))
                      for i, (name, word) in enumerate(adapter.WORDS.items())}
        self.lines = [f"core 0: 1 {s['pc']} ({int(s['word'], 16):#010x})"
                      for s in self.sites.values()]
        self.lines.append('core 0: exception trap_supervisor_ecall, epc 0x80000200')

    def check(self):
        return adapter.trace_check('\n'.join(self.lines), self.sites)

    def test_exact(self):
        self.assertEqual(self.check()['indexed_commits'], 2)

    def test_wrong_privilege(self):
        self.lines[0] = self.lines[0].replace('core 0: 1 ', 'core 0: 3 ')
        with self.assertRaises(ValueError): self.check()

    def test_duplicate_site(self):
        self.lines.append(self.lines[0])
        with self.assertRaises(ValueError): self.check()

    def test_extra_indexed_site(self):
        self.lines.append(self.lines[0].replace('0x80000100', '0x80000300'))
        with self.assertRaises(ValueError): self.check()

    def test_missing_instruction(self):
        del self.lines[0]
        with self.assertRaises(ValueError): self.check()

    def test_missing_expected_trap(self):
        self.lines.pop()
        with self.assertRaises(ValueError): self.check()

    def test_unexpected_page_fault(self):
        self.lines.append('core 0: exception trap_load_page_fault, epc 0x80000100')
        with self.assertRaises(ValueError): self.check()

    def test_wrong_site_word(self):
        next(iter(self.sites.values()))['word'] = '0x13'
        with self.assertRaises(ValueError): self.check()


class SealTest(unittest.TestCase):
    def setUp(self):
        self.result = dict(status='PASS', checks=123, elf_sha256='a' * 64)
        self.files = {'elf': 'a' * 64, 'tool': 'b' * 64}
        self.saved = dict(status='PASS', read_only_validation=True,
                          result=copy.deepcopy(self.result), checked_files=dict(self.files))

    def check(self):
        adapter.require_exact_replay(self.result, self.files, self.saved)

    def test_exact(self): self.check()

    def test_changed_hash(self):
        self.files['tool'] = 'c' * 64
        with self.assertRaises(ValueError): self.check()

    def test_missing_pin(self):
        del self.files['tool']
        with self.assertRaises(ValueError): self.check()

    def test_extra_pin(self):
        self.files['extra'] = 'd' * 64
        with self.assertRaises(ValueError): self.check()

    def test_result_changed(self):
        self.result['checks'] = 122
        with self.assertRaises(ValueError): self.check()

    def test_not_checked(self):
        self.saved['read_only_validation'] = False
        with self.assertRaises(ValueError): self.check()


class HookTest(unittest.TestCase):
    def test_chain_and_script_preservation(self):
        calls = []

        def delegate(item, proof):
            calls.append((item, proof))
            return 'delegated'

        script = adapter.checked.SCRIPT
        with patch.object(adapter.evidence, 'precheck', delegate), patch.object(adapter, '_installed', False):
            adapter.install_hooks()
            hook = adapter.evidence.precheck
            adapter.install_hooks()
            self.assertIs(adapter.evidence.precheck, hook)
            self.assertEqual(adapter.checked.SCRIPT, script)
            item, proof = {'name': 'different-case'}, object()
            self.assertEqual(hook(item, proof), 'delegated')
            self.assertEqual(calls, [(item, proof)])
            with patch.object(adapter, 'sealed_precheck', return_value='sealed') as sealed:
                item = {'name': adapter.NAME}
                self.assertEqual(hook(item, proof), 'sealed')
                sealed.assert_called_once_with(item, proof, delegate)


if __name__ == '__main__':
    unittest.main()
