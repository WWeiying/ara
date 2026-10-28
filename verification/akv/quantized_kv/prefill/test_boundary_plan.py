import csv
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


class BoundaryTest(unittest.TestCase):
    def test_compilers_and_costs(self):
        outputs=[]
        with tempfile.TemporaryDirectory(prefix='prefill-boundaries-') as tmp:
            for label,cc,flags in [('gcc','/usr/bin/gcc',[]),('ubsan','/usr/bin/clang',
                    ['-fsanitize=undefined','-fno-sanitize-recover=undefined'])]:
                binary=Path(tmp)/label
                subprocess.run([cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                    '-fno-fast-math',*flags,'-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),
                    HERE/'test_boundary_plan.c','-lm','-o',binary],check=True,timeout=120)
                run=subprocess.run([binary],capture_output=True,text=True,check=True,timeout=60)
                self.assertEqual(run.stderr,'BOUNDARY_PLAN_PASS cases=160 improved=22 runtime_installed=0\n')
                outputs.append(run.stdout)
        self.assertEqual(outputs[0],outputs[1])
        rows=[{k:int(v) for k,v in row.items()} for row in csv.DictReader(io.StringIO(outputs[0]))]
        self.assertEqual(len(rows),160)
        for row in rows:
            for key in ('commands','v','panels'):
                self.assertLessEqual(row['planned_'+key],row['fixed_'+key])
        example=next(r for r in rows if r['queries']==4 and r['gqa']==7 and r['past']==16)
        self.assertEqual((example['fixed_v'],example['planned_v']),(77,74))


if __name__=='__main__':unittest.main()
