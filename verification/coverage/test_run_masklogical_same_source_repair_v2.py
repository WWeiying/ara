import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import run_masklogical_same_source_repair_v2 as runner


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name)
        self.image = self.build / 'sim/simv'
        self.image.parent.mkdir()
        self.image.write_bytes(b'new image')
        self.source = self.build / 'source.sv'
        self.source.write_text('module test; endmodule\n')
        self.images = {str(self.image): runner.original.digest(self.image)}
        self.write('build-status.json', {'status': 'PASS', 'unit': 'already-collected.service', 'image': self.images})
        self.write('build-image.json', self.images)
        self.write('build-source-pins.json', {str(self.source): runner.original.digest(self.source)})

    def write(self, name, obj):
        (self.build / name).write_text(json.dumps(obj))

    def test_collected_successful_unit_is_not_a_gate(self):
        with patch.object(runner.subprocess, 'check_output', side_effect=AssertionError('No systemctl')):
            image, pins = runner.bind_build(self.build)
        self.assertEqual(image, self.image)
        self.assertIn(str(self.source), pins)

    def test_image_drift_rejected(self):
        self.image.write_bytes(b'other image')
        with self.assertRaises(ValueError):
            runner.bind_build(self.build)

    def test_source_drift_rejected(self):
        self.source.write_text('changed')
        with self.assertRaises(ValueError):
            runner.bind_build(self.build)

    def test_nonpass_build_rejected(self):
        self.write('build-status.json', {'status': 'RUNNING'})
        with self.assertRaises(ValueError):
            runner.bind_build(self.build)

    def test_invalid_budget_rejected_before_launch(self):
        with patch.object(runner.subprocess, 'Popen', side_effect=AssertionError('No simulation')):
            with self.assertRaises(ValueError):
                runner.execute(self.build, self.build / 'output', 0)

    def test_combined_probe_continues_after_bounded_windows(self):
        # Tcl-only mock: validate control flow, never start VCS or elaborate RTL.
        script = r'''
proc show {args} {}
proc dump {args} {return 1}
proc get {args} {return 250530}
set runs {}
proc run {args} {global runs; lappend runs $args}
'''
        script += 'source {' + str(runner.DEFAULT_PROBE) + '}\nputs [list RUNS $runs]\n'
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True,
                                cwd=self.build, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('MASKLOGICAL_COLD_PROBE_CLOSED', result.stdout.splitlines())
        self.assertIn('MASKLOGICAL_RESTART_CAPTURE_COMPLETE_CONTINUING_FULL_MATRIX', result.stdout.splitlines())
        self.assertIn('RUNS {{250000 ns} {545 ns} {220 ns} {}}', result.stdout.splitlines())


if __name__ == '__main__':
    unittest.main()
