"""Check production planner policy; no native hardware capability claim."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class PlanProbe(unittest.TestCase):
    def test_preparation_payload_and_command_policy(self):
        sdk = ROOT / 'software/qbs'
        with tempfile.TemporaryDirectory(prefix='qbs-m4-planner-') as directory:
            executable = Path(directory) / 'probe'
            command = ['gcc', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                       '-I' + str(sdk / 'include'), str(HERE / 'plan_probe.c')]
            command += [str(sdk / 'src' / name) for name in
                        ('qbs_runtime.c', 'qbs_native_riscv.c', 'qbs_format.c')]
            subprocess.run([*command, '-o', str(executable)], check=True,
                           capture_output=True, timeout=60)
            result = subprocess.run([str(executable)], check=True, text=True,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.stdout.splitlines(), [
                'PLAN m=4 n=1536 k=512 activation_bytes=2336 context_eligible=1 commands=48',
                'PLAN m=4 n=1536 k=1024 activation_bytes=4672 context_eligible=1 commands=48',
                'PLAN m=4 n=1536 k=1536 activation_bytes=7008 context_eligible=0 commands=48'])


if __name__ == '__main__':
    unittest.main()
