"""Probe actual planner, without claiming native execution or graph reuse."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


class ContextProbe(unittest.TestCase):
    def test_decode_and_m4_shapes(self):
        sdk=ROOT/'software/qbs'
        with tempfile.TemporaryDirectory(prefix='decode-context-') as directory:
            exe=Path(directory)/'probe'
            command=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(sdk/'include'),str(HERE/'context_probe.c')]
            command += [str(sdk/'src'/name) for name in ('qbs_runtime.c','qbs_native_riscv.c','qbs_format.c')]
            subprocess.run([*command,'-o',str(exe)],check=True,capture_output=True,timeout=60)
            result=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=10)
            lines=result.stdout.splitlines()
            self.assertEqual(lines[-1],'CONTEXT_PROBE_PASS checks=48')
            self.assertEqual(len(lines),49)
            self.assertEqual(sum(line.endswith('eligible=1') for line in lines),12)


if __name__=='__main__': unittest.main()
