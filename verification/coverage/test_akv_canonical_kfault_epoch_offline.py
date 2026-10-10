import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_akv_canonical_kfault_epoch_offline as c


class TestEpoch(unittest.TestCase):
    def test_frozen_sources(self): self.assertTrue(c.source_gate())

    def test_eof_token_not_change_frame(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            path = Path(temp)/'wave.vcd'; path.write_text('$timescale\n100fs\n$end\n#0\n0a\n#165000\n1a\n#175000\n')
            self.assertEqual(c.terminal_time(path,'$finish at simulation time 175000\nTime: 17500000 fs\n',2),175000)

    def test_truncated_wave(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            path = Path(temp)/'wave.vcd'; path.write_text('$timescale\n100fs\n$end\n#0\n#165000\n')
            with self.assertRaises(Exception): c.terminal_time(path,'$finish at simulation time 175000\nTime: 17500000 fs\n',2)

    def test_wrong_epoch(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            path = Path(temp)/'wave.vcd'; path.write_text('$timescale\n100fs\n$end\n#0\n#175000\n')
            with self.assertRaises(Exception): c.terminal_time(path,'$finish at simulation time 175000\nTime: 17500000 fs\n',3)

    def test_wrong_report_time(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            path = Path(temp)/'wave.vcd'; path.write_text('$timescale\n100fs\n$end\n#0\n#175000\n')
            with self.assertRaises(Exception): c.terminal_time(path,'$finish at simulation time 175000\nTime: 17500100 fs\n',2)

    def test_duplicate_finish(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            path = Path(temp)/'wave.vcd'; path.write_text('$timescale\n100fs\n$end\n#0\n#175000\n')
            with self.assertRaises(Exception): c.terminal_time(path,'$finish at simulation time 175000\n'*2+'Time: 17500000 fs\n',2)

    def test_actual_both_waves(self):
        for i,last in ((0,175232),(1,175033)):
            capture=c.life.OUT/('akv-canonical-kfault-phase%d-qualified-agent-20261008-01'%i)
            run=c.life.OUT/('akv-canonical-kfault-phase%d-old-image-agent-20261008-01'%i)
            result=c.wave_gate(capture/'focused.vcd',last,i,(run/'run.vcs.log').read_text())
            self.assertEqual(result['sampled_edges'],333)
            self.assertEqual(result['accepted_AR'],6)
            self.assertTrue(result['global_terminal_evidence']['held_idle_until_EOF'])

    def test_wrong_timescale(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            path = Path(temp)/'wave.vcd'
            path.write_text('$timescale\n1ns\n$end\n#0\n#175000\n')
            with self.assertRaisesRegex(Exception, '100fs timescale'):
                c.terminal_time(path,'$finish at simulation time 175000\nTime: 17500000 fs\n',2)

    def test_bad_owner_still_rejected(self):
        import test_akv_canonical_kfault_run_collect as fixture
        frames=fixture.frames()[:5]; frames[0][1]['planner_fault_tag.role']=3
        with self.assertRaises(Exception): c.original.cycle_gate(frames,0,(c.original.p.ADDRESSES[0],))


if __name__ == '__main__': unittest.main()
