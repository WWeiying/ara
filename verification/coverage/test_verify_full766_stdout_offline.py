import inspect
import json
import unittest
import verify_full766_stdout_offline as check


class ClosureTests(unittest.TestCase):
    def fixture(self):
        return [check.STDOUT.read_text(),json.loads((check.OUT/'failure.json').read_bytes()),
            json.loads((check.OUT/'live-identity.json').read_bytes()),json.loads(check.RECEIPT.read_bytes()),
            inspect.getsource(check.report.old.frozen.prior.old.base.run)]

    def test_real_stdout_and_zero_guard(self):
        proof=check.evidence(*self.fixture())
        self.assertEqual(proof['launch_process_returncode'],0)
        self.assertFalse(proof['copied_or_synthesized_stdout'])

    def test_wrong_actual_pid_rejected(self):
        args=self.fixture();args[3]['actual_dve_pid']+=1
        with self.assertRaises(Exception):check.evidence(*args)

    def test_wrong_failure_rejected(self):
        args=self.fixture();args[1]['reason']='DVE nonzero exit'
        with self.assertRaises(Exception):check.evidence(*args)

    def test_removed_zero_exit_guard_rejected(self):
        args=self.fixture();args[4]=args[4].replace("require(code == 0, 'DVE nonzero exit')",'pass')
        with self.assertRaises(Exception):check.evidence(*args)


if __name__=='__main__':unittest.main()
