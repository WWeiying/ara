import unittest
import verify_native_combo745_offline as tool


class OfflineBindingTests(unittest.TestCase):
    def test_original_substantive_function_used(self):
        new = tool.verifier()
        old = new.__globals__['old']
        self.assertIs(old.verify, tool.captured.inherited.original_verify)
        self.assertEqual(old.verify.__code__.co_filename.split('/')[-1], 'report_c910_combo742.py')

    def test_frozen_entry_and_module_globals_preserved(self):
        prior = tool.captured.old.verify
        new = tool.verifier()
        self.assertIs(tool.captured.old.verify, prior)
        self.assertIsNot(new.__globals__['old'], tool.captured.old)
        self.assertEqual(new.__globals__['__file__'], tool.captured.__file__)
        self.assertIs(new.__code__, tool.captured.verify.__code__)

    def test_only_result_writer_rebound(self):
        new = tool.verifier()
        self.assertIsNot(new.__globals__['life'], tool.captured.life)
        for name in ('read_bound', 'check', 'digest'):
            self.assertIs(getattr(new.__globals__['life'], name), getattr(tool.captured.life, name))


if __name__ == '__main__':
    unittest.main()
