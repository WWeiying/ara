from dataclasses import replace
import unittest

import close_qbs_fma_align796_preflight as p


class ActualCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols,_ = p.old.metadata(p.CAPTURE/'reference.elf')
        cls.commits = p.old.mature.shared.spike_trace.parse_spike_commits(p.CAPTURE/'spike.stderr.log')

    def test_original_failure_and_exact_measured_stride_success(self):
        with self.assertRaisesRegex(ValueError,'Exact unique snapshot owner/address'):
            p.old.spike_gate(self.commits,self.symbols)
        result = p.checker()(self.commits,self.symbols)
        self.assertEqual(result['retired'],155000)
        self.assertEqual(result['software_checks'],6705)
        self.assertEqual(result['full_VRF_snapshot_bytes'],16384)
        self.assertEqual(result['scalar_FP_owned_sites'],32)

    def test_wrong_scalar_FP_result_and_missing_owned_site_rejected(self):
        i = next(i for i,c in enumerate(self.commits) if c.pc==self.symbols['qf_scale_mul'])
        wrong = self.commits[:i]+[replace(self.commits[i],fpr_writes={0:0xffffffff00000000})]+self.commits[i+1:]
        with self.assertRaisesRegex(ValueError,'Independent exact nan-boxed scalar FP'):
            p.checker()(wrong,self.symbols)
        with self.assertRaisesRegex(ValueError,'Exact eight ordered'):
            p.checker()(self.commits[:i]+self.commits[i+1:],self.symbols)

    def test_bad_snapshot_tail_and_terminal_rejected(self):
        i = next(i for i,c in enumerate(self.commits) if c.instruction&127==39 and c.vector_sew is not None)
        data = list(self.commits[i].memory_accesses);address,value=data[-1];data[-1]=(address,value^1)
        wrong = self.commits[:i]+[replace(self.commits[i],memory_accesses=tuple(data))]+self.commits[i+1:]
        with self.assertRaisesRegex(ValueError,'Full exact128 byte snapshot store'):
            p.checker()(wrong,self.symbols)
        i = next(i for i,c in enumerate(self.commits) if c.memory_accesses==((self.symbols['tohost'],1),))
        wrong = self.commits[:i]+[replace(self.commits[i],memory_accesses=((self.symbols['tohost'],3),))]+self.commits[i+1:]
        with self.assertRaisesRegex(ValueError,'Exact checks/no failure/success terminal'):
            p.checker()(wrong,self.symbols)

    def test_foreign_shape_rejected(self):
        for size in (True,0,16896,16513):
            with self.assertRaises(ValueError):p.stride(size)
        self.assertEqual(p.stride(16512),4128)


if __name__ == '__main__':unittest.main()
