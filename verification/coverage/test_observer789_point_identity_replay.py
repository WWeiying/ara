"""Reusable read-only point-identity regression, not a population admission.

Select the reviewed successor via OBSERVER_REVIEW_MODULE. Frozen788 source,
compiled scope and inherited mask fixtures remain unchanged. The successor
must explicitly establish the same compiled boundary before using this replay.

PASS requires foreign/missing points to raise ValueError, while the complete
typed Toggle control passes. Synthetic Line/Branch rows are hostile host input,
not a valid native golden inventory. Owner tests must additionally exercise a
source-bound valid Line/Branch inventory and legal ordering variations; rejecting
all nonToggle input is not a fix. No tests here launch tools or write artifacts.
"""
import csv
import importlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_observer788_readonly_counterexamples as fields
import test_observer788_readonly_branch_points as points

consumer = importlib.import_module(os.environ.get(
    'OBSERVER_REVIEW_MODULE', 'report_population788_observers'))
# These are private fixture module references, not edits to consumer files.
fields.owner = consumer
points.owner = consumer


class FieldReplay(fields.ReadonlyCounterexamples):
    pass


class PointReplay(points.BranchPointCounterexample):
    def reject_inventory(self, data):
        with patch.object(Path, 'read_text', lambda path, *a, **k: data[path.name]):
            with self.assertRaises(ValueError):
                consumer.observer_audit(fields.ROOT/'verification/out/readonly-not-created',
                                        dict(observer=self.ob))

    def test_same_count_foreign_branch_identity_must_reject(self):
        data = fields.inventory_fixture(self.ob)
        for stage in fields.STAGES:
            key = stage+'_Branch_0.tsv'
            before = list(csv.DictReader(io.StringIO(data[key]), delimiter='\t'))
            self.assertEqual(len(before), 4)
            data[key] = data[key].replace('host_point_0', 'foreign_branch_999999')
            after = list(csv.DictReader(io.StringIO(data[key]), delimiter='\t'))
            self.assertEqual(len(after), len(before))
            self.assertNotEqual({r['name'] for r in before}, {r['name'] for r in after})
        self.reject_inventory(data)

    def test_missing_line_identity_all_five_stages_must_reject(self):
        data = fields.inventory_fixture(self.ob)
        for stage in fields.STAGES:
            key = stage+'_Line_0.tsv'
            rows = list(csv.reader(io.StringIO(data[key]), delimiter='\t'))
            self.assertEqual(len(rows), 9)
            stream = io.StringIO()
            csv.writer(stream, delimiter='\t', lineterminator='\n').writerows(rows[:-1])
            data[key] = stream.getvalue()
        self.reject_inventory(data)


if __name__ == '__main__':
    unittest.main()
