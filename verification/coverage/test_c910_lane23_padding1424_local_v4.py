"""Real prepare/check through both host interpreter aliases; no native process."""
import json
import shutil
import subprocess
import unittest
import uuid

import c910_lane23_padding1424_launcher_v2 as m


class PersistentPython(unittest.TestCase):
    def test_real_prepare_and_both_interpreters_check_same_packet(self):
        out = m.life.OUT / ('c9101424-v2-host-test-' + uuid.uuid4().hex)
        def run(python, mode, *extra):
            return subprocess.run([python, '-B', str(m.SCRIPT), mode, '--output', str(out), *extra],
                                  capture_output=True, text=True, timeout=900)
        try:
            prepared = run('/usr/bin/python3', 'prepare')
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            seal = json.loads(prepared.stdout)['seal']
            selection = (out / 'selection.tcl').read_text()
            self.assertIn('set tied_python {%s}' % m.core.PYTHON, selection)
            self.assertIn('set tied_helper {%s}' % m.core.SCRIPT, selection)
            for python in ('/usr/bin/python3', '/usr/bin/python3.9'):
                checked = run(python, 'check', '--seal', seal)
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(json.loads(checked.stdout)['status'], 'CHECK_PASS_NO_EDA')
            # Re-pinning a wrong driver cannot bypass the semantic driver guard.
            driver = out / 'selection.tcl'
            driver.write_text(selection.replace(str(m.core.PYTHON), '/foreign/python'))
            config = json.loads((out / 'config.json').read_text())
            config['pins'][str(driver)] = m.life.digest(driver)
            (out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
            altered_seal = m.life.digest(out / 'config.json')
            rejected = run('/usr/bin/python3.9', 'check', '--seal', altered_seal)
            self.assertEqual(rejected.returncode, 1)
            self.assertIn('Exact native driver', rejected.stderr)
            # A real worker precheck failure must be recorded without starting EDA.
            failed = run('/usr/bin/python3.9', 'worker', '--seal', '0' * 64,
                         '--parent-reviewed-seal', '0' * 64)
            self.assertEqual(failed.returncode, 1, failed.stderr)
            error = json.loads((out / 'worker-error.json').read_text())
            terminal = json.loads((out / 'terminal.json').read_text())
            self.assertEqual(error['phase'], 'precheck')
            self.assertEqual(error['returncode'], 1)
            self.assertFalse(error['EDA_started'])
            self.assertEqual(terminal['returncode'], 1)
            self.assertFalse(terminal['EDA_started'])
            self.assertFalse((out / 'execution.json').exists())
            self.assertFalse((out / 'capture-result.json').exists())
        finally:
            if out.exists():
                shutil.rmtree(out)


if __name__ == '__main__':
    unittest.main()
