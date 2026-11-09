import hashlib
from pathlib import Path
import unittest

from prepare_replay import SOURCE_SHA, transform

SOURCE = Path('/home/wangwy/fpga_runs/qbs_akv_mechanism_stage1_20261108_01/build_02/inputs/replay_main.cpp')


class ReplayPreparationTest(unittest.TestCase):
    def test_wrong_input_rejected(self):
        with self.assertRaises(ValueError):
            transform(b'changed source', True)

    @unittest.skipUnless(SOURCE.is_file(), 'Local pinned board frontend unavailable')
    def test_frozen_frontend_changes_are_bounded(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA)
        plain, probe = transform(raw, False), transform(raw, True)
        for text in (plain, probe):
            self.assertIn('requested_steps > 32', text)
            self.assertIn('history.resize(requested_steps)', text)
            self.assertEqual(text.count('llama_decode(ctx,batch)'), 2)
            self.assertEqual(text.count('llama_synchronize(ctx)'), 2)
            self.assertIn('cp.n_threads=cp.n_threads_batch=1', text)
            self.assertIn('cp.type_k=cp.type_v=GGML_TYPE_F16', text)
            self.assertIn('std::fwrite(values,sizeof(float),vocabulary,file)', text)
        self.assertNotIn('stage1_node_probe_', plain)
        self.assertLess(probe.index('const auto prefill_ns=now_ns()-start'),
                        probe.index('probe_finish(0,prefill_rc)'))
        self.assertLess(probe.index('const auto duration=now_ns()-start'),
                        probe.index('probe_finish(step+1,rc)'))
        self.assertIn('inference_window_includes_probe_export', probe)
        self.assertNotIn('callback_eval', probe)


if __name__ == '__main__':
    unittest.main()
