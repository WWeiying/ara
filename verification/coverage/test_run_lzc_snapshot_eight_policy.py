import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import run_lzc_snapshot_eight_policy as r


class EntryTests(unittest.TestCase):
    def test_preserves_frozen_single_claim(self):
        import inspect
        s=inspect.getsource(r.claim_once)
        self.assertIn("open('x')",s)

    def test_no_retry_after_failure(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'status.json').write_text('{"status":"FAILED"}')
            with self.assertRaises(ValueError):r.unstarted(p)

    def test_background_requires_parent_pid_receipt(self):
        import inspect
        self.assertIn("launch['runner_pid'] == os.getpid()",inspect.getsource(r.run_reviewed))

    def test_reviewed_entry_uses_eight_counts(self):
        import inspect
        self.assertIn('(5892,17774,23666,frozen.TIMEOUT)',inspect.getsource(r.reviewed_entry))


if __name__=='__main__':unittest.main()
