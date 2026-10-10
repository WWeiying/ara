import unittest
from unittest.mock import patch
import run_sv39_rvv_alias770_bounded as r


class BaselineSealTests(unittest.TestCase):
    def test_fixed_seal_and_unchanged_command(self):
        out,m=r.prepare(r.OUT/'never-run-bounded-alias-test')
        self.assertEqual(m['formal770_fixed_seal'],r.BASE_SEAL)
        self.assertEqual(m['baseline_manifest_sha256'],r.BASE_SEAL)
        self.assertEqual(m['timeout_s'],600)
        self.assertEqual(m['command'],r.prior.command(out))
        self.assertEqual(m['wave_byte_limit'],64*1024*1024)
        self.assertFalse(out.exists())

    def test_resigned_baseline_rejected_before_prepare(self):
        with patch.object(r,'BASE_SEAL','a'*64),patch.object(r.prior,'prepare') as prepare:
            with self.assertRaises(ValueError):r.prepare(r.OUT/'never-run-bounded-alias-test')
            prepare.assert_not_called()

    def test_run_wrong_baseline_rejected(self):
        with patch.object(r.prior,'run') as run:
            with self.assertRaises(ValueError):r.run(r.OUT/'never-run-bounded-alias-test',
                {'formal770_fixed_seal':'a'*64})
            run.assert_not_called()


if __name__=='__main__':unittest.main()
