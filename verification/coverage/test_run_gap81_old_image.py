import csv
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_gap81_old_image as runner


class RuntimeTests(unittest.TestCase):
    def test_complete_evidence_and_rejection_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit, vector, log = (root/name for name in ('commit.csv', 'vector.csv', 'run.log'))
            rows = [dict(event='cvx_req', insn='06b5045b', trans_id='0', trap='0', pc='80000004'),
                    dict(event='cvx_resp', insn='06b5045b', trans_id='0', trap='0', pc='80000004'),
                    dict(event='retire', insn='06b5045b', trans_id='0', trap='0', pc='80000004')]
            def write_rows(items):
                with commit.open('w') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(items)
            write_rows(rows)
            vector.touch()
            text = ('GAP81 command=0 checks=18 errors=0\n'
                    'GAP81 inspected vrf_words=1024 initial_words=1024 source_bytes=3440 csr_words=12\n'
                    'PASSED: qbs_gap81_m4_phase12 checks=24 errors=0\nCore Test *** SUCCESS ***\n')
            log.write_text(text)
            data = {}
            for context in range(4):
                values = struct.pack('<f', float(256*(context+1)))+bytes(124)
                data.update({(8+context,i):(value,None) for i,value in enumerate(values)})
            activity = SimpleNamespace(instruction=0x06b5045b, allocations=1, completions=1, writes=[])
            with patch.object(runner, 'validate_trace', return_value={}), \
                    patch.object(runner, 'check_contract_log', return_value=[]), \
                    patch.object(runner, '_parse_vector_trace', return_value=(4,1024,{1:activity})), \
                    patch.object(runner, '_architectural_bytes', return_value=data):
                self.assertEqual(runner.runtime(commit,vector,log,0x80000004)['status'], 'PASS')
                data[(8,0)] = (1,None)
                with self.assertRaisesRegex(ValueError, 'VRF bytes'):
                    runner.runtime(commit,vector,log,0x80000004)
                write_rows(rows[1:])
                with self.assertRaisesRegex(ValueError, 'Orphan'):
                    runner.runtime(commit,vector,log,0x80000004)
                write_rows(rows)
                log.write_text(text.replace('checks=24', 'checks=23'))
                with self.assertRaisesRegex(ValueError, 'selfcheck'):
                    runner.runtime(commit,vector,log,0x80000004)


if __name__ == '__main__':
    unittest.main()
