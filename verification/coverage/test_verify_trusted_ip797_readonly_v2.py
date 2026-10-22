import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import verify_trusted_ip797_readonly_v2 as r


class ExactTailTests(unittest.TestCase):
    def setUp(self):
        self.q = dict(status='TRUSTED_IP_INTEGRATION797_NATIVE_VERIFIED',
                      reports={'applied': {'ara_tb.dut.i_ara_soc.i_system': {'Toggle': '72.81%'}}})
        self.prefix = b'{"status": "DVE_IDENTITY_OBSERVED"}\n'
        self.sha = hashlib.sha256(self.prefix).hexdigest()
        self.tail = (json.dumps(dict(status=self.q['status'], metrics=self.q['reports']['applied']['ara_tb.dut.i_ara_soc.i_system'])) + '\n').encode()

    def test_exact_single_tail_accepts_and_pins_full_stdout(self):
        proof = r.stdout_tail(self.prefix + self.tail, self.sha, self.q)
        self.assertEqual(proof['complete_stdout_sha256'], hashlib.sha256(self.prefix + self.tail).hexdigest())
        self.assertEqual(proof['prefix_bytes'], len(self.prefix))

    def test_wrong_missing_or_extra_newline_tail_rejected(self):
        for data in (self.prefix, self.prefix + self.tail[:-1], self.prefix + self.tail + b'\n',
                     self.prefix + self.tail + b'other\n', self.prefix + self.tail.replace(b'72.81%', b'99.00%'),
                     self.prefix + self.tail.replace(b'NATIVE_VERIFIED', b'FAKE_VERIFIED')):
            with self.assertRaises(ValueError): r.stdout_tail(data, self.sha, self.q)

    def test_prefix_corruption_insertion_and_duplicate_tail_rejected(self):
        for data in (b'changed\n' + self.prefix + self.tail, self.prefix + b'injected\n' + self.tail,
                     self.prefix + self.tail * 2):
            with self.assertRaises(ValueError): r.stdout_tail(data, self.sha, self.q)

    def test_multiple_known_final_lines_rejected_even_with_matching_prefix_pin(self):
        prefix = self.prefix + self.tail
        with self.assertRaises(ValueError): r.stdout_tail(prefix + self.tail, hashlib.sha256(prefix).hexdigest(), self.q)

    def test_no_relaxation_for_other_native_log(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); stdout = out / 'service-stdout.log'; other = out / 'service-stderr.log'
            stdout.write_bytes(self.prefix + self.tail); other.write_bytes(b'original\n')
            q = dict(self.q, output_pins={str(stdout): self.sha, str(other): r.old.digest(other)})
            self.assertEqual(r.checked_output_pins(q, out)[str(stdout)], r.old.digest(stdout))
            other.write_bytes(b'original\n' + self.tail)
            with self.assertRaises(ValueError): r.checked_output_pins(q, out)

    def test_missing_stdout_original_pin_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): r.checked_output_pins(dict(self.q, output_pins={}), Path(directory))

    def test_exact_private_adaptation_preserves_whole_terminal_markers_and_recursive_logs(self):
        verify = r.context()
        self.assertIs(verify.__globals__['whole_gate'], r.old.whole_gate)
        self.assertIs(verify.__globals__['terminal_markers'], r.old.terminal_markers)
        self.assertIs(verify.__globals__['gui_pins'], r.old.gui_pins)
        self.assertIs(verify.__globals__['checked_output_pins'], r.checked_output_pins)

    def test_actual_completed_stdout_tail_and_all_other25pins(self):
        q = r.old.bound(r.old.OUT / 'qualification.json', r.QUAL_SHA)
        checked = r.checked_output_pins(q, r.old.OUT)
        self.assertEqual(len(checked), 25)
        changed = [path for path in checked if checked[path] != q['output_pins'][path]]
        self.assertEqual(changed, [str(r.old.OUT / 'service-stdout.log')])


if __name__ == '__main__':
    unittest.main()
