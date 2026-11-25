import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('operator_chain',HERE/'chain.py')
chain=importlib.util.module_from_spec(spec); spec.loader.exec_module(chain)


class SuccessorSafety(unittest.TestCase):
    def test_frozen_inputs_and_atomic_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input'; p.write_bytes(b'abc')
            pins={str(p):hashlib.sha256(b'abc').hexdigest()}
            chain.verify(pins)
            chain.save(Path(tmp)/'status.json',dict(state='WAITING'))
            self.assertFalse((Path(tmp)/'status.tmp').exists())
            p.write_bytes(b'abd')
            with self.assertRaisesRegex(ValueError,'drift'):
                chain.verify(pins)

    def failed_prerequisite(self,terminal):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'chain'; out.mkdir(); (out/'inputs').mkdir()
            prior=root/'prior'; prior.mkdir()
            chain.save(out/'source-pins.json',{})
            chain.save(prior/'source-pins.json',{})
            chain.save(out/'plan.json',dict(prerequisite=str(prior),unit='test.service',
                soc=str(root/'soc'),manifest=str(root/'manifest'),campaign=str(root/'new'),parallel=4))
            if terminal:
                chain.save(prior/'result.json',dict(state='INCOMPLETE',post_source_image_pins_match=True))
            calls=[]
            def invoke(argv,**kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv,0,stdout='inactive\n')
            argv=['chain.py','execute','--output',str(out)]
            with patch.object(chain,'__file__',str(out/'inputs/chain.py')), \
                 patch.object(sys,'argv',argv),patch.object(chain.subprocess,'run',side_effect=invoke):
                self.assertEqual(chain.main(),1)
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(result['state'],'FAIL')
            self.assertFalse((root/'new').exists())
            self.assertFalse(any('execute' in c or 'prepare' in c for c in calls))
            self.assertEqual(sum('collect.py' in str(c) for c in calls),int(terminal))
            with patch.object(chain,'__file__',str(out/'inputs/chain.py')),patch.object(sys,'argv',argv):
                with self.assertRaisesRegex(ValueError,'one-shot'):
                    chain.main()

    def test_failed_batch_never_dispatches_successor(self):
        self.failed_prerequisite(True)

    def test_dead_owner_without_result_is_not_restarted(self):
        self.failed_prerequisite(False)


if __name__=='__main__':
    unittest.main()
