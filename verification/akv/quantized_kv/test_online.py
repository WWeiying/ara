#!/usr/bin/env python3
"""Host scheduling tests, not actual quantized-model or RVV execution."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class OnlineScheduleTest(unittest.TestCase):
    def test_host_order_oracle_and_work(self):
        with tempfile.TemporaryDirectory(prefix='quant-online-host-') as temp:
            binary = Path(temp)/'test'
            subprocess.run([shutil.which('gcc'),'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-ffp-contract=fast','-frounding-math','-I'+str(ROOT),
                str(HERE/'test_online.c'),'-lm','-o',str(binary)],check=True,timeout=120)
            result = subprocess.run([binary],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                    text=True,check=True,timeout=120)
            self.assertEqual(result.stdout,
                'QUANT_ONLINE_HOST_PASS cases=320 exact_order=1 double_oracle=1 callback_work=1 guards=1 errors=0\n')


if __name__ == '__main__':
    unittest.main()
