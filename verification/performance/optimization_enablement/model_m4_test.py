"""Strict synthetic checker rejection tests; never model/producer evidence."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('model_m4',Path(__file__).with_name('model_m4_run.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
    rows=[]
    for mode in (0,1):
        tag=3+mode
        rows+=['M4_ARM_BEGIN mode='+str(mode),
            'Trace 0: 0xaa [0/1000/0/0] qbs',
            'Trace 0: 0xbb [0/1000/0/0] qbs']
        if mode:rows+=['Trace 0: 0xcc [0/2000/0/0] producer']
        rows+=['GGML_RISCV_QBS_M4_SELECTED source=cache tag='+str(tag)+' event='+event+' k=1536' for event in ('compute_rvv','hit')]
        rows+=['GGML_RISCV_QBS_EXEC type='+kind+' native_qbexec=1 emulated_commands=0' for kind in ('Q4_K','Q6_K')]
        for step in (0,1):
            rows+=['M4_DECODE step='+str(step)+' rows='+str(24 if step==0 else 1)+' rc=0 fcsr=17 vcsr=5 vstart=0',
                'M4_TOKEN step='+str(step)+' token=1']
        for step in (0,1):
            rows+=['M4_LOGITS_BEGIN mode='+str(mode)+' step='+str(step)+' values=2',
                'M4_BITS index=0 00000000 3f800000',
                'M4_LOGITS_END mode='+str(mode)+' step='+str(step)]
        rows+=['M4_ARM_END mode='+str(mode)+' status=0']
    return rows+['GUEST_TEST_EXIT=0']


class Checker(unittest.TestCase):
    def check(self,rows):return m.check(rows,{'qbs':0x1000,'producer':0x2000},vocab=2)
    def test_complete(self):self.assertEqual(self.check(fixture())['tag4_cold'],1)
    def reject(self,old,new):
        rows=fixture();i=rows.index(old);rows[i]=new
        with self.assertRaises(ValueError):self.check(rows)
    def test_logits(self):self.reject('M4_BITS index=0 00000000 3f800000','M4_BITS index=0 00000000 40000000')
    def test_csr(self):self.reject('M4_DECODE step=0 rows=24 rc=0 fcsr=17 vcsr=5 vstart=0','M4_DECODE step=0 rows=24 rc=0 fcsr=17 vcsr=5 vstart=1')
    def test_token(self):self.reject('M4_TOKEN step=0 token=1','M4_TOKEN step=0 token=0')
    def test_no_hit(self):self.reject('GGML_RISCV_QBS_M4_SELECTED source=cache tag=4 event=hit k=1536','GGML_RISCV_QBS_M4_SELECTED source=cache tag=4 event=compute_rvv k=1536')
    def test_wrong_k(self):self.reject('GGML_RISCV_QBS_M4_SELECTED source=cache tag=4 event=hit k=1536','GGML_RISCV_QBS_M4_SELECTED source=cache tag=4 event=hit k=576')
    def test_missing_producer(self):self.reject('Trace 0: 0xcc [0/2000/0/0] producer','ignored')
    def test_extra_producer(self):self.reject('Trace 0: 0xaa [0/1000/0/0] qbs','Trace 0: 0xaa [0/2000/0/0] producer')
    def test_native_work(self):self.reject('GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=0','GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=2 emulated_commands=0')
    def test_emulation(self):self.reject('GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=0','GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=1')
    def test_truncation(self):
        with self.assertRaises(ValueError):self.check(fixture()[:-1])
    def test_cancelled(self):
        rows=fixture();i=rows.index('Trace 0: 0xcc [0/2000/0/0] producer')
        rows[i:i]=['Trace 0: 0xdd [0/2000/0/0] producer','Stopped execution of TB chain before 0xdd [2000] ignored']
        self.assertEqual(self.check(rows)['retained_producer_entries'],1)
    def test_unpaired_cancelled(self):self.reject('Trace 0: 0xcc [0/2000/0/0] producer','Stopped execution of TB chain before 0xdd [2000] ignored')


if __name__=='__main__':unittest.main(verbosity=2)
