import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('m4_actual_work',Path(__file__).with_name('audit_model_preparations.py'))
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


class WorkTest(unittest.TestCase):
    def log(self):
        lines=[]
        for mode in (0,1):
            lines.append(f'Q8K_MODEL_BEGIN enabled={mode}')
            for i in range(2):
                if mode:lines.append(f'GGML_RISCV_QBS_M4_CACHE epoch=1 group=0 event={"hit" if i else "compute_rvv"} fill=1')
                else:lines.append('GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=1 path=rvv k=256')
                lines.append('GGML_RISCV_QBS_LIFETIME m=4 k=256 graph_epoch=1')
            lines.append(f'Q8K_MODEL_END enabled={mode}')
        return '\n'.join(lines)
    def test_balance(self):
        r=audit.analyze(self.log());self.assertEqual(r['modes']['1']['executed_m4_computations'],1)
    def test_reject(self):
        for a,b in [('group=0','group=1'),('epoch=1 group','epoch=2 group'),
                    ('event=hit','event=unknown'),('k=256 graph_epoch=1','k=512 graph_epoch=1'),
                    ('m=4','m=1')]:
            with self.subTest(change=a),self.assertRaises(ValueError):audit.analyze(self.log().replace(a,b,1))
    def test_incomplete(self):
        with self.assertRaises(ValueError):audit.analyze(self.log().rsplit('\n',1)[0])


if __name__=='__main__':unittest.main()
