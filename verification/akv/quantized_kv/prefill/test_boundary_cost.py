from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent


class BoundedCostTest(unittest.TestCase):
    def test_exact_reference(self):
        outputs=[]
        with tempfile.TemporaryDirectory(prefix='bounded-cost-') as tmp:
            for label,cc,flags in [('gcc','/usr/bin/gcc',[]),('ubsan','/usr/bin/clang',
                    ['-fsanitize=undefined','-fno-sanitize-recover=undefined'])]:
                binary=Path(tmp)/label
                subprocess.run([cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',*flags,
                    HERE/'test_boundary_cost.c','-o',binary],check=True,timeout=120)
                run=subprocess.run([binary],capture_output=True,text=True,check=True,timeout=60)
                self.assertTrue(run.stdout.startswith('BOUNDED_COST_PASS cases=2256 '))
                self.assertIn('context_max=65536 exact_reference=1',run.stdout)
                outputs.append(run.stdout)
        self.assertEqual(outputs[0],outputs[1])
        print(outputs[0],end='')


if __name__=='__main__':unittest.main()
