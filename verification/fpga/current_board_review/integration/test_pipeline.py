import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_pipeline as pipeline


class Pipeline(unittest.TestCase):
    def arguments(self, out):
        return ['--snapshot', '/tmp/frozen', '--programs', '/tmp/ports',
                '--smokes', '/tmp/smokes', '--out', str(out), '--execute']

    def test_order_jobs_and_explicit_execution(self):
        stages = pipeline.stages(pipeline.parse_args(self.arguments('/tmp/campaign')))
        self.assertEqual([s['name'] for s in stages],
                         ['build-image', 'singles', 'combined', 'extended', 'gather', 'smokes'])
        self.assertIn('--authorize-build', stages[0]['argv'])
        for stage in stages[1:]:
            self.assertIn('--execute', stage['argv'])
            self.assertEqual(stage['argv'][stage['argv'].index('--jobs') + 1], '4')

    def test_report_gate_requires_exact_runtime_pass(self):
        stage = {'name': 'singles', 'out': '/tmp/results', 'cases': ['one', 'two']}
        good = [dict(name=name, status='PASS', returncode=0) for name in stage['cases']]
        with patch.object(pipeline, 'read', side_effect=[{'status': 'COMPLETE'}, good]):
            pipeline.acceptance(stage)
        for results in (good[:1], good + good[:1],
                        [good[0], dict(name='two', status='DRY_RUN', returncode=0)],
                        [good[0], dict(name='two', status='PASS', returncode=1)]):
            with patch.object(pipeline, 'read', side_effect=[{'status': 'COMPLETE'}, results]):
                with self.assertRaises(ValueError):
                    pipeline.acceptance(stage)

    def test_build_metadata_is_built_not_complete(self):
        stage = {'name': 'build-image', 'out': '/tmp/image'}
        with patch.object(pipeline, 'read', side_effect=[{'status': 'BUILT'},
                          {'files': ['pinned'], 'simv': __file__}]):
            pipeline.acceptance(stage)
        with patch.object(pipeline, 'read', return_value={'status': 'COMPLETE'}):
            with self.assertRaises(ValueError):
                pipeline.acceptance(stage)

    def test_failfast_and_atomic_status(self):
        with tempfile.TemporaryDirectory(dir=pipeline.HERE) as tmp:
            out = Path(tmp) / 'campaign'
            # CLI normally forbids writing under the integration sources.
            args = pipeline.parse_args(self.arguments('/tmp/campaign-test'))
            args.out = out
            with patch.object(pipeline, 'parse_args', return_value=args), \
                    patch.object(pipeline, 'inputs', return_value={}), \
                    patch.object(pipeline, 'execute_stage', side_effect=[0, 1]) as execute, \
                    patch.object(pipeline, 'acceptance') as accept, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pipeline.main(), 1)
            result = pipeline.read(out / 'status.json')
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(accept.call_count, 1)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual([s['status'] for s in result['stages']],
                             ['PASS', 'FAIL', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'])
            self.assertEqual(result['plan_sha256'], pipeline.sha(out / 'plan.json'))
            self.assertFalse(list(out.glob('.status.json*')))


if __name__ == '__main__':
    unittest.main()
