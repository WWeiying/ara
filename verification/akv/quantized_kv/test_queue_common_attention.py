"""Event gate cannot dispatch after failure and uses exec rather than orphan launch."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import queue_common_attention as q


class CommonQueueTest(unittest.TestCase):
    def exercise(self,fail):
        with tempfile.TemporaryDirectory(prefix='common-queue-test-') as tmp:
            root=Path(tmp); build=root/'build'; prior=root/'prior'; control=root/'control'; out=root/'run'
            build.mkdir(); prior.mkdir(); (prior/'source-pins.json').write_text('{}')
            argv=['queue_common_attention.py','--build',str(build),'--prerequisite',str(prior),
                '--control',str(control),'--output',str(out),'--owner-pid','123','--wait-timeout','10']
            with patch.object(q.sys,'argv',argv),patch.object(q,'checked_build',return_value=({},{})), \
                    patch.object(q.s,'hashes',return_value={}),patch.object(q.s,'verify_pins'), \
                    patch.object(q,'wait_owner',side_effect=ValueError('not PASS') if fail else None) as wait, \
                    patch.object(q.os,'execv') as execute:
                if fail:
                    with self.assertRaises(ValueError): q.main()
                    execute.assert_not_called()
                else:
                    q.main()
                    execute.assert_called_once()
                    command=execute.call_args[0][1]
                    self.assertEqual(command[2],str(q.HERE/'run_common_attention.py'))
                    self.assertIn(str(prior),command)
                    self.assertIn(str(out),command)
                wait.assert_called_once_with(prior,123,q.HERE/'run_attention.py',10)
            status=json.loads((control/'status.json').read_text())
            self.assertEqual(status['state'],'FAIL' if fail else 'DISPATCHED')
            self.assertFalse(out.exists())

    def test_failed_predecessor_never_dispatches(self): self.exercise(True)
    def test_success_exec_preserves_owner(self): self.exercise(False)


if __name__=='__main__': unittest.main()
