import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import run_qbs_k2_row_pending782 as run
import collect_qbs_k2_row_pending782 as collect


class RuntimeTests(unittest.TestCase):
    def test_actual_fixture_and_elf(self):
        pre=run.life.read_bound(run.PRE/'preflight-manifest.json',run.SEAL);run.validate(pre)
        symbols,data,sites,items=collect.elf_view()
        self.assertEqual(len(sites[0]),8)
        self.assertEqual(len(collect.custom_expected(items[0])),512)
        self.assertEqual(len(collect.regions(0,symbols,data,items)['frame']),4224)

    def test_drift_rejected(self):
        pre=run.life.read_bound(run.PRE/'preflight-manifest.json',run.SEAL)
        for key,value in [('k_blocks',1),('m',8),('ap',4),('binary_sha256','a'*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):run.validate(dict(pre,**{key:value}))

    def test_focused_command(self):
        cmd=run.command(run.life.OUT/'test-only-not-run')
        self.assertEqual(cmd[0],str(run.life.IMAGE));self.assertIn('+NO_FSDB',cmd)
        self.assertEqual(cmd[-3:],['-ucli','-do',str(run.PROBE)])
        self.assertIn('+PRELOAD='+str(run.ELF),cmd)

    def test_native_tail_and_mask_negative(self):
        _,_,_,items=collect.elf_view();expected=collect.custom_expected(items[0])
        self.assertEqual(expected[8,127],0)
        writes=[SimpleNamespace(lane=l,addr=4*r+w,be=255) for r in range(8,12) for w in range(4) for l in range(4)]
        a=SimpleNamespace(instruction=collect.WORD,vd=8,vl=128,writes=writes)
        with patch.object(collect.native.support,'activity_bytes'):
            collect.activity_bytes(a,expected,1,2,True)
            writes[-1].be=127
            with self.assertRaises(ValueError):collect.activity_bytes(a,expected,1,2,True)

    def test_existing_directory_reject(self):
        with self.assertRaises(ValueError):run.prepare(run.PRE)

    def test_terminal_failure_reject(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);run.life.save(p/'simulation-status.json',dict(status='SIMULATION_NOT_ADMITTED',returncode=0,coverage_admitted=False))
            with self.assertRaises(ValueError):collect.native.terminal(p)


if __name__=='__main__':unittest.main()
