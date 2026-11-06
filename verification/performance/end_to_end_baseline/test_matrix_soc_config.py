import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
VERIFY=ROOT.parent/'ara_dsa_signoff_integration'


class MatrixSocConfigTests(unittest.TestCase):
    def command(self,root,qbs,wide):
        return subprocess.run(['make','-s','--no-print-directory','-C',str(root/'hardware'),
            '--eval=matrix-config-check:;@printf "%s\\n" "$(bender_defs)"','matrix-config-check',
            'config=default','nr_lanes=4','vlen=1024',f'qbs={qbs}',f'qbs_matrix_dot={wide}'],
            capture_output=True,text=True,timeout=30)

    def test_define_and_invalid_combinations(self):
        roots=[ROOT]+([VERIFY] if VERIFY.exists() and VERIFY!=ROOT else [])
        for root in roots:
            for qbs,wide,valid in ((0,0,True),(1,0,True),(1,1,True),(0,1,False),
                                   (1,2,False),(1,'',False),(1,'0 1',False)):
                with self.subTest(root=root,qbs=qbs,wide=wide):
                    result=self.command(root,qbs,wide)
                    self.assertEqual(result.returncode==0,valid,result.stderr)
                    if valid:
                        self.assertEqual(result.stdout.count('ARA_QBS_WIDE_MATRIX_DOT=1'),int(wide==1))

    def test_explicit_configuration_and_hook(self):
        make=(ROOT/'hardware/Makefile').read_text()
        self.assertEqual(make.count("'qbs_matrix_dot=$(qbs_matrix_dot)'"),1)
        source=(ROOT/'hardware/src/vlsu/vlsu.sv').read_text()
        self.assertEqual(source.count("`ifdef ARA_QBS_WIDE_MATRIX_DOT\n    .WideMatrixDot(1'b1),\n`endif"),1)
        self.assertIn("parameter bit WideMatrixDot = 1'b0",(ROOT/'hardware/src/vlsu/qbs/qbs_engine.sv').read_text())


if __name__=='__main__':unittest.main()
