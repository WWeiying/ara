import inspect
from pathlib import Path
import unittest

import collect_qbs_k2_row_pending782_echo as successor


class EchoGuardTests(unittest.TestCase):
    def test_actual_frozen_echo_accept(self):
        text=(successor.old.life.OUT/'qbs-k2-row-pending-old-image782-agent-20261008-01/console.log').read_text()
        self.assertIn('puts stderr "QBS_PENDING_PROBE_REJECT $failure"',text)
        self.assertEqual(text.splitlines().count('QBS_PENDING_PROBE_READY'),1)
        self.assertFalse(successor.actual_error(text))

    def test_actual_errors_reject(self):
        for line in ('QBS_PENDING_PROBE_REJECT Missing object',' UCLI_ERROR unsupported','\tError-[UNKNOWN]'):
            with self.subTest(line=line):self.assertTrue(successor.actual_error('echo\n'+line+'\n'))

    def test_echo_not_just_substring(self):
        self.assertFalse(successor.actual_error('puts stderr "UCLI_ERROR bad"\nif {Error-} {}'))
        self.assertFalse(successor.actual_error('QBS_PENDING_PROBE_REJECTED_NOT_DIAGNOSTIC'))

    def test_exact_frozen_one_replacement(self):
        self.assertEqual(successor.old.life.digest(Path(successor.old.__file__)),successor.OLD_SHA)
        self.assertEqual(inspect.getsource(successor.old.collect).count(
            "re.search(r'QBS_PENDING_PROBE_REJECT|UCLI_ERROR|Error-',console)"),1)


if __name__=='__main__':unittest.main()
