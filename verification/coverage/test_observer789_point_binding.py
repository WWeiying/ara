import csv
import io
import unittest
from unittest.mock import patch
from pathlib import Path
import observer789_point_binding as owner
import test_observer788_readonly_counterexamples as fixtures


def actual_rows(metric, flag='0', reverse=False):
    data = owner.binding()['gold'][metric]
    stream = io.StringIO(); writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
    writer.writerow(['path','meta','name','excluded','cells'])
    items = list(data['identities'].items())
    if reverse: items.reverse()
    interp = owner.tkinter.Tcl(); interp.tk.wantobjects(False)
    for key, values in items:
        writer.writerow([*key, flag, interp.call('list', *values)])
    return stream.getvalue()


class SourceBoundPoints(unittest.TestCase):
    def test_actual_aggregate_line_and_branch_schema(self):
        data = owner.binding()
        self.assertEqual(len(data['line_schema']['blocks']), 8)
        self.assertEqual(len(data['line_schema']['statements']), 10)
        self.assertEqual(data['line_schema']['nonignored_statements'], 7)
        self.assertEqual(len(data['gold']['Line']['identities']), 2)
        self.assertEqual(len(data['gold']['Branch']['identities']), 6)

    def test_valid_observed_collections_and_permutation(self):
        for metric in ('Line','Branch'):
            for reverse in (False,True):
                owner.snapshot_gate(metric, actual_rows(metric, reverse=reverse), owner.binding()['gold'][metric]['columns'])

    def test_foreign_label_missing_row_and_metadata_reject(self):
        for metric in ('Line','Branch'):
            text = actual_rows(metric)
            label = 'Block' if metric == 'Line' else 'Item0'
            for bad in (text.replace(label, 'foreign999999'), '\n'.join(text.splitlines()[:-1])+'\n'):
                with self.assertRaises(ValueError):
                    owner.snapshot_gate(metric, bad, owner.binding()['gold'][metric]['columns'])
        text = actual_rows('Branch').replace(' 56 ', ' 999999 ')
        with self.assertRaises(ValueError):
            owner.snapshot_gate('Branch', text, owner.binding()['gold']['Branch']['columns'])

    def test_all_five_stages_actual_identity_inventory_pass(self):
        ob, _, _, _, _ = fixtures.fixtures()
        data = fixtures.inventory_fixture(ob)
        for stage in fixtures.STAGES:
            for metric in ('Line','Branch'):
                data[stage+'_'+metric+'_0.tsv'] = actual_rows(metric, '1' if stage in ('selected','reloaded') else '0')
                data[stage+'_'+metric+'_0.columns'] = owner.binding()['gold'][metric]['columns']
        with patch.object(Path, 'read_text', lambda path,*a,**k: data[path.name]):
            owner.observer_audit(Path('/host-fixture'), dict(observer=ob))


if __name__ == '__main__': unittest.main()
