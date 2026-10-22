import copy
import json
import subprocess
import sys
import tkinter
import unittest
import capture_c910_fp16_additional8 as n


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = json.loads(n.REVIEW.read_bytes())
        cls.origin = json.loads((n.REFERENCE / 'config.json').read_bytes())
        cls.text = (n.REFERENCE / 'first.el').read_text()

    def test_actual_reference_remap(self):
        text = n.candidate(self.review, self.origin, self.text)
        self.assertEqual(len(n.measured.parse_el(text, dict(instances=self.review['instances']))), 1264)

    def test_wrong_subslot(self):
        review = copy.deepcopy(self.review); review['instances'][0]['simd_subslot'] = 1
        with self.assertRaises(ValueError): n.candidate(review, self.origin, self.text)

    def test_incomplete_oracle(self):
        review = copy.deepcopy(self.review); review['actual_evidence']['observed_halfwords'] = 16
        with self.assertRaises(ValueError): n.candidate(review, self.origin, self.text)

    def test_protected_mutation(self):
        review = copy.deepcopy(self.review); review['instances'][0]['protected'].pop()
        with self.assertRaises(ValueError): n.candidate(review, self.origin, self.text)

    def test_extra_EL(self):
        with self.assertRaises(ValueError): n.candidate(self.review, self.origin, self.text + self.text)

    def test_declaration_changed(self):
        text = self.text.replace('cur_rem[60:0]', 'cur_rem[59:0]')
        self.assertNotEqual(text, self.text)
        with self.assertRaises(ValueError): n.candidate(self.review, self.origin, text)

    def test_host_Tcl_complete(self):
        t = tkinter.Tcl(); t.setvar('fp16_native_test_only', 1)
        t.call('source', str(n.base.TCL))
        self.assertTrue(t.call('info', 'complete', t.call('info', 'body', 'c910_session')))
        body = n.base.TCL.read_text()
        self.assertNotIn('gui_exclude_items', body)
        for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
            self.assertIn('c910_bind ' + stage, body)

    def test_actual_compiled_source_locations(self):
        bindings = n.compiled_contract(self.review)
        self.assertEqual([b['compiled_instance_id'] for b in bindings],
                         ['-1357', '-1358', '-1361', '-1362', '-1365', '-1366', '-1369', '-1370'])

    def test_legacy_Tcl_helper_ABI(self):
        result = subprocess.run([sys.executable, str(n.SCRIPT), '--help'], capture_output=True, text=True, check=True)
        self.assertIn('inventory', result.stdout)
        self.assertIn('--stage', result.stdout)
        self.assertIn('--index', result.stdout)


if __name__ == '__main__': unittest.main()
