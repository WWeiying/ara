#!/usr/bin/env python3
"""Worker rejection and exact hardware-accounting tests without VCS execution."""
import argparse
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import run_rvv_qbs as r
from check_rvv_qbs import check_work


class WorkerTest(unittest.TestCase):
    def test_reject_before_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            a = argparse.Namespace(build=parent,output=parent/'run',timeout=1,preflight_only=False)
            with self.assertRaises(ValueError):
                r.run(a)
            a.output = parent.parent/(parent.name+'-outside')
            a.timeout = 10801
            with self.assertRaises(ValueError):
                r.run(a)
            a.output = parent/'fresh'
            a.build = parent/'build'
            a.build.mkdir()
            a.timeout = 1
            with mock.patch.object(r,'prepare',side_effect=ValueError('sealed source changed')), \
                 mock.patch.object(r.Execution,'execute') as launch:
                with self.assertRaises(ValueError):
                    r.run(a)
                launch.assert_not_called()
            self.assertEqual(r.s.read_json(a.output/'result.json')['state'],'FAIL')
            self.assertIsNone(r.s.read_json(a.output/'status.json')['child_pid'])

    def test_hardware_sequence_and_mutations(self):
        rtl = (r.ROOT/'hardware/src/vlsu/vlsu.sv').read_text()
        fields = re.findall(r'([a-z][a-z0-9_]*)=%0d',
            re.findall(r'\$display\("\[QBS_PERF\] ([^"\n]+)"',rtl)[0])
        lines = []
        for index in range(16):
            weight = 136 if index < 8 else 72
            row = dict.fromkeys(fields,0)
            row.update(seq=index+1,id=1,m=1,n=1,vlen=1024,lanes=4,success=1,
                busy_cycles=100,read_ranges=9,payload_bytes=16+136+weight,
                weight_bytes=weight,activation_bytes=136,useful_pairs=128,
                ar=12,r_beats=20,read_outstanding_max=2,commit_groups=1)
            lines.extend(['[QBS_PERF] '+' '.join(f'{k}={row[k]}' for k in fields),
                          'QUANT_KV_SCORE placeholder'])
        text = '\n'.join(lines)
        self.assertEqual(check_work(text,rtl)['summed_payload_bytes'],4096)
        changes = [text.replace('payload_bytes=288','payload_bytes=287',1),
                   text.replace('seq=1 ','seq=2 ',1),
                   text.replace('success=1','success=0',1),
                   text.replace('read_fault=0','read_fault=1',1),
                   text.replace('context_reuse_count=0','context_reuse_count=1',1),
                   text.replace('activation_bytes=136','activation_bytes=0',1),
                   text.replace('commit_groups=1','commit_groups=0',1),
                   text+'\n'+lines[0],
                   '\n'.join(lines[1:]),
                   text.replace(' id=1',' id=1 extra=1',1),
                   text.replace(' id=1',' id=1 id=1',1),
                   text+'\n[AKV_PERF] seq=1']
        for i,change in enumerate(changes):
            with self.subTest(mutation=i),self.assertRaises(ValueError):
                check_work(change,rtl)


if __name__ == '__main__':
    unittest.main()
