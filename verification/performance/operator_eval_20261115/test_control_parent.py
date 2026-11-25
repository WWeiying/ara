import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('controls_parent',Path(__file__).with_name('run_controls_parent.py'))
worker=importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)


class StopOnFailure(unittest.TestCase):
    def scenario(self,kind):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'worker'; out.mkdir(); (out/'inputs').mkdir()
            prior=Path(tmp)/'prior'; prior.mkdir()
            stages=[Path(tmp)/f'stage{i}' for i in range(2)]
            for stage in stages:
                stage.mkdir()
            worker.save(out/'source-pins.json',{})
            worker.save(prior/'source-pins.json',{})
            worker.save(out/'plan.json',dict(stages=list(map(str,stages)),prerequisite=str(prior),owner='fake.service'))
            if kind!='dead_owner':
                worker.save(prior/'result.json',dict(state='FAIL' if kind=='prior_fail' else 'PASS',
                                                    post_source_image_pins_match=True))
            calls=[]
            def run(argv,**kwargs):
                calls.append(argv)
                if 'systemctl' in argv:
                    return subprocess.CompletedProcess(argv,0,stdout='inactive\n')
                if 'execute' in argv:
                    self.assertIn(str(stages[0]),argv)
                    worker.save(stages[0]/'result.json',dict(state='INCOMPLETE',post_source_image_pins_match=True))
                    return subprocess.CompletedProcess(argv,1)
                self.assertIn(str(out/'inputs/collect.py'),argv)
                return subprocess.CompletedProcess(argv,0)
            argv=['worker','execute','--output',str(out)]
            with patch.object(worker,'__file__',str(out/'inputs/run_controls_parent.py')), \
                 patch.object(sys,'argv',argv),patch.object(worker.subprocess,'run',side_effect=run):
                self.assertEqual(worker.main(),1)
                with self.assertRaisesRegex(ValueError,'one-shot'):
                    worker.main()
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(result['state'],'FAIL')
            self.assertEqual(result['completed'],[])
            self.assertEqual(sum('execute' in c for c in calls),int(kind=='stage_fail'))
            self.assertFalse((stages[1]/'result.json').exists())

    def test_failed_prerequisite_does_not_dispatch(self):
        self.scenario('prior_fail')

    def test_failed_stage_collects_but_never_dispatches_next(self):
        self.scenario('stage_fail')

    def test_missing_result_and_dead_owner_is_not_restarted(self):
        self.scenario('dead_owner')


if __name__=='__main__':
    unittest.main()
