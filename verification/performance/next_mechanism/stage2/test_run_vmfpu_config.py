#!/usr/bin/env python3
"""Host mutations for the bounded VMFPU configuration gate; no EDA invocation."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('config_gate', HERE / 'run_vmfpu_config.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


class ConfigGateTests(unittest.TestCase):
    def setUp(self):
        names = (*G.STATIC, 'hardware/include/ara_pkg.sv', 'hardware/src/lane/vmfpu.sv')
        self.texts = {name: (G.ROOT / name).read_text() for name in names}
        self.good = ('STAGE2_VMFPU_CONFIG_DISABLED latency=1 native=8 writes=8 dones=8 '
                     'blocked=180 grant_stalls=40 borrowed=0 returned=0\n')

    def test_current_composition(self):
        self.assertFalse(G.audit_composition(self.texts)['top_vlsu_executed'])

    def test_guard_removal_rejected(self):
        for name in ('hardware/src/ara.sv', 'hardware/src/vlsu/vlsu.sv', 'hardware/src/lane/vmfpu.sv'):
            with self.subTest(name=name):
                texts = dict(self.texts)
                texts[name] = texts[name].replace('&& QbsLaneMulLatencySupported', '', 1)
                with self.assertRaises(ValueError):
                    G.audit_composition(texts)

    def test_explicit_shared_bypass_required(self):
        texts = dict(self.texts)
        name = 'hardware/src/lane/vmfpu.sv'
        texts[name] = texts[name].replace(", .Bypass8(1'b1)", '')
        with self.assertRaises(ValueError):
            G.audit_composition(texts)

    def test_scheduler_forwarding_required(self):
        texts = dict(self.texts)
        name = 'hardware/src/vlsu/vlsu.sv'
        texts[name] = texts[name].replace('.CooperativeWaves(QbsLaneMulSupported)', '.CooperativeWaves(1)')
        with self.assertRaises(ValueError):
            G.audit_composition(texts)

    def test_negative_adaptation_keeps_native_checker(self):
        old = (HERE / 'vmfpu_tb.sv').read_text()
        new = G.disabled_tb(old)
        self.assertEqual(old.split('  initial begin\n')[0], new.split('\n  int disabled_cycles')[0])
        self.assertIn('Native result mismatch', new)
        self.assertNotIn('STAGE2_VMFPU_PASS native=', new)
        self.assertIn('dut.i_simd_mul_ew8.NumPipeRegs != LatMultiplierEW8', new)

    def test_negative_log(self):
        self.assertEqual(G.check_disabled(self.good, 1)['native'], 8)
        self.assertEqual(G.check_disabled(self.good.replace('latency=1', 'latency=2'), 2)['native'], 8)

    def test_bad_logs_rejected(self):
        bad = [self.good * 2, '', self.good + 'Fatal: injected\n',
               self.good.replace('latency=1', 'latency=2'),
               self.good.replace('borrowed=0', 'borrowed=1'),
               self.good.replace('returned=0', 'returned=1'),
               self.good.replace('writes=8', 'writes=7'),
               self.good.replace('dones=8', 'dones=9'),
               self.good.replace('blocked=180', 'blocked=0'),
               self.good.replace('grant_stalls=40', 'grant_stalls=0'),
               self.good.replace('native=8', 'native=8 extra=1')]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    G.check_disabled(text, 1)


if __name__ == '__main__':
    unittest.main()
