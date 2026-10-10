from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import resume_akv_repair as resume


class ResumeAKVTests(unittest.TestCase):
    def test_replay_requires_identical_case_and_sources(self):
        old = dict(test='app:test', elf_sha256='hash', oracle='selfcheck+trace-audit',
                   coverage_test='app_test', source_files={'source': 'hash'})
        with patch.object(resume.batch, 'check') as check:
            resume.matching_case(old, old)
            check.assert_called_once_with(old['source_files'])
            for key in ('test', 'elf_sha256', 'oracle', 'coverage_test'):
                with self.assertRaises(ValueError):
                    resume.matching_case(dict(old, **{key: 'different'}), old)


if __name__ == '__main__':
    unittest.main()
