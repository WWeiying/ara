"""The correction is startup-only and cannot replace the Attention workload."""
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent


class InitializedAttentionTest(unittest.TestCase):
    def test_wrapper_preserves_original_body(self):
        text=(HERE/'attention_initialized_main.c').read_text()
        self.assertIn('#include "attention_main.c"',text)
        self.assertIn('#define main quantized_attention_body',text)
        body=text.split('int main(void) {',1)[1]
        self.assertLess(body.index('vsetivli zero,1,e32,m1,ta,ma'),
                        body.index('return quantized_attention_body();'))
        self.assertEqual(body.count('__asm__'),1)
        self.assertNotIn('memcpy',body)
        self.assertNotIn('TOKENS',body)

    def test_probe_discriminates_reset_vill(self):
        text=(HERE/'attention_startup_probe.c').read_text()
        self.assertLess(text.index('csrr %0,vtype'),text.index('qbs_device_query'))
        self.assertIn('!(before>>63)',text)
        self.assertIn('after!=0xd0 || vl!=1 || fc!=0 || vc!=5',text)
        self.assertLess(text.index('vsetivli'),text.index('vmv.x.s zero,v8'))

    def test_probe_emits_both_independent_event_streams(self):
        text=(HERE/'run_attention_startup.py').read_text()
        self.assertIn("'+ARA_CONTRACT_TRACE_LIMIT=2000000'",text)
        self.assertIn("'+ARA_UVM_TRACE_LIMIT=2000000'",text)
        self.assertIn("'--require-events','--require-backend'",text)
        self.assertIn("vlsu_memory_work_in_probe=False",text)
        full=(HERE/'run_attention.py').read_text()
        self.assertIn("'--require-backend', '--require-axi', '--require-axi-write'",full)


if __name__=='__main__':
    unittest.main()
