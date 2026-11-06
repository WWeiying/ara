import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from full_projection import check, N
from collect_full_projection import compare
from test_full_projection import fixture
from watch_projection_pair import collector_path, wait_for_results


class FullProjectionCollectionTests(unittest.TestCase):
    def test_complete_operator_pair(self):
        reports=[]
        for wide in (0,1):
            text,golden=fixture(wide)
            activity=[dict(counters={k:1 for k in ('payload_bytes','weight_bytes','activation_bytes',
                       'useful_pairs','fp_uop_issue','accumulator_updates')}) for _ in range(3)]
            reports.append(dict(wide=wide,build='same',elf_sha256='same',measured=check(text,wide,golden),activity=activity))
        result=compare(*reports)
        self.assertEqual([p['n'] for p in result['parts']],list(N))
        self.assertGreater(result['region_ratio'],1.6)
        changed=copy.deepcopy(reports); changed[1]['activity'][0]['counters']['weight_bytes']+=1
        with self.assertRaises(ValueError): compare(*changed)

    def test_waiter_scope_is_explicit(self):
        self.assertEqual(collector_path(False).name,'collect_projection_native.py')
        self.assertEqual(collector_path(True).name,'collect_full_projection.py')
        with self.assertRaises(ValueError): collector_path('full')

    def test_waiter_handles_directory_creation_and_already_done_workers(self):
        with tempfile.TemporaryDirectory() as d:
            roots = [Path(d)/name for name in ('base','wide')]
            def finish():
                for root in roots:
                    time.sleep(0.02); root.mkdir()
                    tmp = root/'result.tmp'; tmp.write_text(json.dumps(dict(state='PASS')))
                    tmp.replace(root/'result.json')
            thread = threading.Thread(target=finish); thread.start()
            try: wait_for_results(roots, timeout=3)
            finally: thread.join()
            wait_for_results(roots, timeout=3)


if __name__=='__main__': unittest.main()
