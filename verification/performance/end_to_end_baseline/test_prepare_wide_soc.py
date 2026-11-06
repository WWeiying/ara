"""Width experiment leaves lane count/capacity and unreviewed sources alone."""
from collections import Counter
from pathlib import Path
import unittest

import prepare_wide_soc as w


class WideSocPreparationTests(unittest.TestCase):
    def source_graph(self):
        return (w.BASE / 'expected-sources.f').read_text()

    def test_real_width_selection_only_in_successor(self):
        text = (w.VERIFY / 'hardware/tb/ara_tb.sv').read_text()
        generated = w.source_transform('hardware/tb/ara_tb.sv', text)
        self.assertNotIn(w.TB_ANCHOR, generated)
        self.assertEqual(generated.replace(w.TB_REPLACEMENT, w.TB_ANCHOR), text)
        self.assertEqual(text.count('\n'), generated.count('\n'))

    def test_only_soc_observation_hook_added(self):
        text = (w.VERIFY / 'hardware/src/ara_soc.sv').read_text()
        generated = w.source_transform('hardware/src/ara_soc.sv', text)
        self.assertEqual(generated.replace('  `include "wide_soc_memory_probe.svh"\n', ''), text)
        self.assertIn('.DataWidth(AxiDataWidth)', generated)
        self.assertIn('.NumWords (L2NumWords', generated)

    def test_exact_source_additions_and_constant_features(self):
        for width in (128, 256):
            text = w.graph(self.source_graph(), Path('/snapshot'), width)
            self.assertEqual(text.count('+define+ARA_QBS_WIDE_MATRIX_DOT=1'), 1)
            self.assertEqual(text.count(w.FEATURE), int(width == 256))
            self.assertEqual(text.count(f'+define+ARA_EXPERIMENT_AXI_DATA_WIDTH={width}'), 1)
            self.assertNotIn(str(w.VERIFY), text)
            self.assertIn('+define+NR_LANES=4', text)
            self.assertIn('+define+SIM_L2_SIZE_BYTES=16777216', text)
            self.assertIn('+define+VLEN=1024', text)
            for path in w.NEW: self.assertEqual(text.splitlines().count('/snapshot/' + path), 1)
            original = [line.strip() for line in self.source_graph().splitlines() if line.strip()]
            restored = []
            for line in text.splitlines():
                if line.startswith(('+define+ARA_QBS_WIDE_', '+define+ARA_EXPERIMENT_', '+incdir+/snapshot/experiment')):
                    continue
                if line in ['/snapshot/' + path for path in w.NEW]: continue
                restored.append(line.replace('/snapshot/', str(w.VERIFY) + '/'))
            self.assertEqual(restored, original)

    def test_graph_drift_rejected(self):
        original = self.source_graph()
        for text in (original + '\n' + w.FEATURE,
                     original.replace(str(w.VERIFY / next(iter(w.ADDITIONS))), '/foreign/module.sv'),
                     original + '\n+define+TARGET_SRAM_MC',
                     original + '\n+define+IDEAL_DISPATCHER'):
            with self.assertRaises(ValueError): w.graph(text, Path('/snapshot'), 256)
        with self.assertRaises(ValueError): w.graph(original, Path('/snapshot'), 512)

    def test_warning_inventory_and_command_are_strict(self):
        argv = ['/tool/vcs', '-f', '/snapshot/sources.f']
        old = 'Warning-[KNOWN] retained\n/old.sv, 1\n\n'
        log = 'Command: vcs -f /snapshot/sources.f\n' + old + 'CPU time: 1 to compile\n'
        self.assertEqual(w.compile_check(log, argv, old, Path('/snapshot'))['known_diagnostic_count'], 1)
        for bad in (log.replace('KNOWN', 'UNKNOWN'), log + 'Error-[NEW] bad\n',
                    log.replace('sources.f', 'other.f'), log.replace('CPU time:', 'nothing:'),
                    log.replace(old, old + old)):
            with self.assertRaises(ValueError): w.compile_check(bad, argv, old, Path('/snapshot'))

    def test_observation_cannot_hide_a_serialized_memory(self):
        text = (w.HERE / 'wide_soc_memory_probe.svh').read_text()
        self.assertIn('$bits(i_dram.init_val[0]) == AxiDataWidth', text)
        self.assertIn('$size(i_dram.init_val) == L2NumWords', text)
        self.assertIn('l2_rvalid === wide_probe_prev_req', text)
        self.assertIn('WIDE_SOC_PROBE_REQUIRES_GENERIC_MEMORY', text)


if __name__ == '__main__':
    unittest.main()
