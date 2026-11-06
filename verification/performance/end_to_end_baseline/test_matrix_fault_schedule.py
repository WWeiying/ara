import unittest

from matrix_fault_schedule import late_fault_proof,prefix,probe_bench
from test_projection_resources import VECTOR


class FaultScheduleTests(unittest.TestCase):
    def test_proof(self):
        events=[('START',1,0),('AXI_ERROR',2,1),('REPLAY_LAST',4,1),('REPLAY_IDLE',5,0),('AXI_LAST',7,0),('READ_FAULT',8,0)]
        text='MATRIX_FAULT_SCHEDULE fast=0\n'
        text+='\n'.join(f'MATRIX_REPLAY_EVENT cycle={c} event={e} m=4 access=2 busy={b} offset=0' for e,c,b in events)
        text+='\nFatal: original\nwide context fault did not interrupt active replay\n'
        self.assertEqual(late_fault_proof(text)['state'],'LATE_FAULT_COVERAGE_PRECONDITION_PROVED')
        for old,new in (('cycle=8','cycle=3'),('fast=0','fast=1'),('event=REPLAY_LAST','event=UNKNOWN')):
            with self.assertRaises(ValueError):late_fault_proof(text.replace(old,new))

    def test_prefix_and_probe(self):
        self.assertEqual(prefix(VECTOR,1),VECTOR)
        with self.assertRaises(ValueError):prefix(VECTOR,2)
        source='  initial $display("MATRIX_ENGINE_CONFIG wide=%0d", Wide);\n      else if (axi_r_valid && axi_r_ready) response_delay <= response_gap;'
        result=probe_bench(source)
        self.assertIn('MATRIX_FAST_FAULT_DRAIN',result)
        with self.assertRaises(ValueError):probe_bench(source+source)


if __name__=='__main__':unittest.main()
