"""Independent hostile fixtures; never edits receipts or runs native tools."""
import csv
import io
import unittest
from pathlib import Path
from unittest.mock import patch
import observer789_point_binding as owner
from test_observer789_point_binding import actual_rows
import test_observer788_readonly_counterexamples as frozen_fields
import test_observer788_readonly_branch_points as frozen_points


def mutate(text, change):
    rows = list(csv.reader(io.StringIO(text), delimiter='\t'))
    change(rows)
    stream = io.StringIO()
    csv.writer(stream, delimiter='\t', lineterminator='\n').writerows(rows)
    return stream.getvalue()


class IndependentPointNegatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = owner.binding()['gold']
        cls.ob, cls.old, _, _, _ = frozen_fields.fixtures()
        frozen_points.BranchPointCounterexample.setUpClass()
        cls.full = frozen_points.BranchPointCounterexample.full

    def reject(self, metric, text, columns=None):
        with self.assertRaises(ValueError):
            owner.snapshot_gate(metric,text,self.gold[metric]['columns'] if columns is None else columns)

    def test_line_aggregate_not_invented_bb_rows(self):
        self.reject('Line',actual_rows('Line').replace('Block','Line0'))

    def test_branch_foreign_meta_with_valid_path_name(self):
        text = mutate(actual_rows('Branch'),lambda rows: rows[2].__setitem__(1,'Branch999999'))
        self.reject('Branch',text)

    def test_branch_source_line_mutation_same_count(self):
        def change(rows):
            values = list(owner.cells(rows[2][4])); values[2] = '999999'
            interp = owner.tkinter.Tcl(); interp.tk.wantobjects(False)
            rows[2][4] = interp.call('list',*values)
        self.reject('Branch',mutate(actual_rows('Branch'),change))

    def test_branch_condition_value_mutation(self):
        def change(rows):
            values = list(owner.cells(rows[2][4])); values[3] = '0' if values[3] == '1' else '1'
            interp = owner.tkinter.Tcl(); interp.tk.wantobjects(False)
            rows[2][4] = interp.call('list',*values)
        self.reject('Branch',mutate(actual_rows('Branch'),change))

    def test_duplicate_and_missing_actual_leaf(self):
        for change in (lambda rows:rows.append(rows[2][:]),lambda rows:rows.pop(2)):
            self.reject('Branch',mutate(actual_rows('Branch'),change))

    def test_column_identity_mutation(self):
        self.reject('Branch',actual_rows('Branch'),self.gold['Branch']['columns'].replace('Line No.','Unknown'))

    def test_unobserved_not_exclusion_flag(self):
        self.reject('Line',actual_rows('Line').replace('\t0\t','\tUNOBSERVED\t'))

    def test_same_mutated_conditions_all_stages_rejected(self):
        data = frozen_fields.inventory_fixture(self.ob)
        for stage in frozen_fields.STAGES:
            for metric in ('Line','Branch'):
                flag = '1' if stage in ('selected','reloaded') else '0'
                data[stage+'_'+metric+'_0.tsv'] = actual_rows(metric,flag)
                data[stage+'_'+metric+'_0.columns'] = self.gold[metric]['columns']
            data[stage+'_Branch_0.tsv'] = data[stage+'_Branch_0.tsv'].replace('Item0.Branch0.0','Item0.Branch0.999999')
        with patch.object(Path,'read_text',lambda path,*a,**k:data[path.name]):
            with self.assertRaises(ValueError): owner.observer_audit(Path('/read-only-fixture'),dict(observer=self.ob))

    def test_real_branch_crc_cannot_accept_foreign_id(self):
        extra = 'CHECKSUM: "2332976182 2887169998"\nINSTANCE: '+owner.SCOPES[0]+'\nBranch 999999\n'
        with self.assertRaises(ValueError): owner.native_gate(self.full+extra,self.old,self.ob)

    def test_existing_typed_positive_and_wrong_metric_crc(self):
        owner.native_gate(self.full,self.old,self.ob)
        extra = 'CHECKSUM: "2332976182 1382966637"\nINSTANCE: '+owner.SCOPES[0]+'\nBranch 999999\n'
        with self.assertRaises(ValueError):
            owner.native_gate(self.full+extra,self.old,self.ob)


if __name__ == '__main__': unittest.main()
