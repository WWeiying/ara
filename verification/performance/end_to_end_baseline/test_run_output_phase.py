import unittest
from unittest.mock import patch

import run_output_phase as r


class OutputPhaseRunnerTests(unittest.TestCase):
    def test_build_is_frozen_before_consumption(self):
        def fail(pins,path,expected=None):
            self.assertEqual(path,r.BUILD/'build.json')
            self.assertEqual(expected,r.BUILD_SHA)
            raise ValueError('changed build')
        with patch.object(r,'bind',fail):
            with self.assertRaisesRegex(ValueError,'changed build'):r.inputs()

    def test_wrong_scope_rejects_before_loading_inputs(self):
        with patch.object(r,'bind'),patch.object(r.Path,'read_text',return_value='{"state":"FAIL"}'):
            with self.assertRaisesRegex(ValueError,'Wrong phase observation'):r.inputs()

    def test_bounded_and_independent_output_required(self):
        for timeout in (0,10801):
            with self.assertRaises(ValueError):r.run(r.RUNS/'unused',timeout,False)
        with self.assertRaises(ValueError):r.run(r.Path('/tmp/unused'),1,False)


if __name__=='__main__':unittest.main()
