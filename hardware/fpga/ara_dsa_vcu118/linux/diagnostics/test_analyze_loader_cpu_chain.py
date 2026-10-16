import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from analyze_loader_cpu_chain import check_inputs, low_phase_samples, run_result


class RunResultTests(unittest.TestCase):
    def setUp(self):
        self.target = 0x3f869db0dc
        self.success = 'RETIRE cycle=330 pc=0000003f869db0dc\nLOADER_CPU_REACHED_TARGET cycles=330\n'

    def test_success_requires_retirement(self):
        self.assertTrue(run_result(self.success, 0, self.target)['target_reached'])
        self.assertFalse(run_result('LOADER_CPU_REACHED_TARGET\n', 0, self.target)['target_reached'])

    def test_vcs_fatal_with_zero_exit_is_failure(self):
        self.assertFalse(run_result(self.success+'Fatal: late error\n', 0, self.target)['target_reached'])
        self.assertFalse(run_result(self.success, 1, self.target)['target_reached'])

    def test_lost_last_beat(self):
        text = ('COLLISION cycle=286 last=1 rdata=0000000020b93801 '
                'inval_addr=000081031900 capture=0 pop=0\n'
                'RETIRE cycle=329 pc=0000003f869dfb4a\nLOADER_CPU_BOUNDED_STOP\n')
        result = run_result(text, 0, self.target)
        self.assertEqual(result['last_retired_pc'], '0x3f869dfb4a')
        self.assertEqual(result['lost_responses'], [dict(cycle=286, last=1, data='0x20b93801')])
        self.assertFalse(result['target_reached'])


class InputAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dirs = [self.root/'old', self.root/'new']
        for i, directory in enumerate(self.dirs):
            directory.mkdir()
            for name in ('memory.hex', 'boot.bin', 'loader_board_cfg.svh'):
                (directory/name).write_bytes(b'identical')
            name = 'wt_axi_adapter_candidate.sv' if i else 'wt_axi_adapter.sv'
            self.adapter = directory/name
            self.adapter.write_text('axi_rd_rdy        = ~invalidate' + (' & ~inval_valid_i;' if i else ';'))
            source = dict(original={'rtl/adapter': 'old'},
                          compiled={str(self.adapter): hashlib.sha256(self.adapter.read_bytes()).hexdigest(),
                                    'testbench': 'same'})
            (directory/'sources.json').write_text(json.dumps(source))

    def test_one_repair_only(self):
        self.assertIn('boot.bin', check_inputs(*self.dirs))

    def test_input_change_rejected(self):
        (self.dirs[1]/'boot.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Different experimental input'):
            check_inputs(*self.dirs)

    def test_other_compiled_change_rejected(self):
        path = self.dirs[1]/'sources.json'
        data = json.loads(path.read_text())
        data['compiled']['testbench'] = 'different'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Other compiled sources'):
            check_inputs(*self.dirs)

    def test_later_adapter_edit_rejected(self):
        self.adapter.write_text('different')
        with self.assertRaisesRegex(ValueError, 'changed since simulation'):
            check_inputs(*self.dirs)

    def test_low_phase_sampling(self):
        try:
            import vcd.reader  # noqa: F401
        except ImportError:
            self.skipTest('pyvcd required for waveform parsing')
        path = self.root/'trace.vcd'
        path.write_text('$timescale 1 ps $end\n$scope module trace $end\n'
                        '$var reg 1 ! clk $end\n$var reg 1 " rst $end\n'
                        '$var reg 1 # rready $end\n$upscope $end\n$enddefinitions $end\n'
                        '#0\n0!\n1"\n1#\n#10\n1!\n0#\n#20\n0!\n#30\n1!\n')
        samples = list(low_phase_samples(path))
        self.assertEqual([(s['time_ps'], s['rready']) for s in samples], [(0, 1), (20, 0)])


if __name__ == '__main__':
    unittest.main()
