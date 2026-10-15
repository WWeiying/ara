#!/usr/bin/env python3
"""Narrow host negatives for numerical persistence, startup and source scope."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import replay


class WorkerTests(unittest.TestCase):
    def test_numeric_types_and_failures(self):
        self.assertTrue(replay.numeric_gate((0,1.0,False,False)))
        for value in ((17,1,False,False),(0,1,True,False),(0,1,False,True),(0,9001,False,False)):
            self.assertFalse(replay.numeric_gate(value))
        with self.assertRaises(ValueError):
            replay.numeric_gate((False,1,False,False))

    def test_two_positive_samples_and_identity(self):
        sample=dict(pid=3,generation='9',command=['simv'],bytes=0,ticks=0)
        positive=dict(sample,bytes=10,ticks=2)
        later=dict(sample,bytes=20,ticks=3)
        self.assertFalse(replay.growth(sample,positive))
        self.assertFalse(replay.growth(positive,positive))
        self.assertTrue(replay.growth(positive,later))
        self.assertFalse(replay.growth(positive,dict(later,generation='10')))

    def test_actual_outcome_survives_generic_exception(self):
        for code,timed_out in ((0,False),(17,False),(0,True)):
            with tempfile.TemporaryDirectory() as folder:
                out=Path(folder);name='runtime';root=out/'replay/tests'/name
                root.mkdir(parents=True)
                abort=replay.threading.Event()
                engine=SimpleNamespace(_run_monitored=lambda *a:(code,1.0,timed_out,False),FAIL_RE=replay.re.compile('NEVER'))
                checkers={replay.KINDS[0]:SimpleNamespace(VETO=replay.re.compile('FAIL'))}
                with replay.hooks(engine,out,[dict(id=name,original_name='source_label')],dict(simv='/simv'),abort,checkers):
                    engine._run_monitored(replay.command_for(root,name,'/simv'),root/'work',root/'console.log',9000,abort)
                    # Frozen generic postchecks can throw, but cannot erase the child wait tuple.
                    try:
                        raise ValueError('generic postcheck')
                    except ValueError:
                        pass
                receipt=json.loads((root/'child_outcome.unvalidated.json').read_text())
                self.assertEqual(receipt['returncode'],code)
                self.assertEqual(receipt['timed_out'],timed_out)
                self.assertEqual(receipt['source_label'],'source_label')
                self.assertEqual(abort.is_set(),code!=0 or timed_out)

    def test_command_mismatch_before_child(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);abort=replay.threading.Event()
            engine=SimpleNamespace(_run_monitored=lambda *a:self.fail('child executed'),FAIL_RE=replay.re.compile('NEVER'))
            checkers={replay.KINDS[0]:SimpleNamespace(VETO=replay.re.compile('FAIL'))}
            with replay.hooks(engine,out,[dict(id='runtime',original_name='source')],dict(simv='/simv'),abort,checkers):
                with self.assertRaises(ValueError):
                    engine._run_monitored(['/wrong','+TESTCASE=runtime'],'/wrong','/wrong',9000,abort)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(WorkerTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    replay.save(replay.HERE/'host02.json',dict(status='PASS' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),DUT_runs=0,
        code_pins={str(p):replay.sha(p) for p in (replay.HERE/'replay.py',replay.HERE/'configure.py',Path(__file__).resolve())}))
    raise SystemExit(not result.wasSuccessful())
