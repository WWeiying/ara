from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import resume_timeout_repair as resume


class ReuseTests(unittest.TestCase):
    def test_only_identical_checked_pass_can_be_reused(self):
        case = dict(name='case', test='rvv:case', elf_sha256='hash',
                    oracle='selfcheck+trace-audit', coverage_test='case', source_files={})
        old = dict(image={'simv': 'hash'}, cases=[case])
        record = dict(status='PASS', vdb_valid=True, passed_only=True,
                      files={}, vdb='/vdb', vdb_files={'file': 'hash'})
        with patch.object(resume.batch, 'check'), patch.object(
                resume.batch.base, 'inventory', return_value=record['vdb_files']):
            self.assertTrue(resume.validated_pass(old, old, case, record)['reused'])
            for change in ({'status': 'TIMEOUT'}, {'vdb_valid': False}, {'passed_only': False}):
                with self.assertRaises(ValueError):
                    resume.validated_pass(old, old, case, dict(record, **change))
            with self.assertRaises(ValueError):
                resume.validated_pass(dict(old, image={}), old, case, record)
            with self.assertRaises(ValueError):
                resume.validated_pass(old, old, dict(case, elf_sha256='other'), record)


if __name__ == '__main__':
    unittest.main()
