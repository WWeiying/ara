import unittest
import verify_fma_lzc_width_calibration as v
import prove_fma_lzc_binary_tree as p


class CalibrationTests(unittest.TestCase):
    def test_real_readonly_replay(self):self.assertEqual(v.verify()['total_checks'],7661)

    def test_source_and_checker_drift_rejected(self):
        source=(v.ROOT/'hardware/deps/common_cells/src/lzc.sv').read_bytes()
        bench=(v.ROOT/'verification/tests/fma_lzc_width_calibration.sv').read_bytes()
        v.source_gate(source,bench)
        with self.assertRaises(ValueError):v.source_gate(source.replace(b'|',b'&',1),bench)
        with self.assertRaises(ValueError):v.source_gate(source,bench.replace(b'MODE(1)',b'MODE(0)',1))

    def test_missing_duplicate_failure_log_rejected(self):
        text=(v.OUT/'simulation.stdout').read_text();v.log_gate(text)
        for bad in (text.replace('FMA_LZC_THREE_WIDTHS_PASS',''),text+'\nLZC_WIDTH_PASS WIDTH=25 MODE=1 CHECKS=330\n',text+'\nFATAL mismatch\n'):
            with self.assertRaises(ValueError):v.log_gate(bad)

    def test_universal_induction_retains_spare(self):
        for width,count in ((25,31),(51,63),(109,127)):
            proof=p.prove_width(width);self.assertEqual(proof['assigned_nodes'],count)
            self.assertEqual(proof['spare_index'],count)
            self.assertNotIn(count,{n['index'] for n in proof['nodes']})

    def test_wrong_priority_and_unmatched_width_rejected(self):
        with self.assertRaises(ValueError):p.merge_law(False)
        with self.assertRaises(ValueError):p.prove_width(23)


if __name__=='__main__':unittest.main()
