"""Actual immutable PMP native/EL fixture mutations; no EDA."""
import csv
from pathlib import Path
import tempfile
import unittest
import audit_csr_pmp0_native765 as m


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=m.life.read_bound(m.ORIGIN/'config.json',m.CONFIG_SHA)
        cls.text=(m.ORIGIN/'first.el').read_text()
        with (m.ORIGIN/'native_before_0.tsv').open(newline='') as f:cls.table=list(csv.reader(f,delimiter='\t'))

    def check_rows(self,table):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rows.tsv'
            with p.open('w',newline='') as s:csv.writer(s,delimiter='\t').writerows(table)
            return m.rows(p,self.c)

    def test_actual_five_stages_no_extra(self):
        before=None
        for stage in m.old.STAGES:
            current=m.rows(m.ORIGIN/('native_%s_0.tsv'%stage),self.c)
            if before is None:before=current
            self.assertEqual(current,before)
        self.assertEqual(len(before[0]),2077)
        self.assertEqual(before[1][0]['native'],'pmpaddr_o[0][53:0]')

    def test_extra_container_and_coverage_object_rejected(self):
        for name in ('PMPContainer','pmpcfg_d[64].locked'):
            row=['extra_handle',name,name,name]
            with self.assertRaises(ValueError):self.check_rows(self.table+[row])

    def test_missing_or_substituted_protection_rejected(self):
        with self.assertRaises(ValueError):self.check_rows(self.table[:-1])
        table=[list(r) for r in self.table];table[-1]=['other_handle','other','other','other']
        with self.assertRaises(ValueError):self.check_rows(table)

    def test_duplicate_or_alias_collapse_rejected(self):
        table=[list(r) for r in self.table];table[-1]=table[-2]
        with self.assertRaises(ValueError):self.check_rows(table)

    def test_actual_annotation_identity_reload(self):
        self.assertEqual(m.records(self.text,self.c),m.records((m.ORIGIN/'second.el').read_text(),self.c))
        self.assertEqual(sum(m.records(self.text,self.c).values()),1282)

    def test_changed_missing_annotation_rejected(self):
        changed=self.text.replace(m.ANNOTATION,'arbitrary source annotation',1)
        with self.assertRaises(ValueError):m.records(changed,self.c)
        lines=self.text.splitlines();k=next(k for k,l in enumerate(lines) if l.startswith('ANNOTATION:'))
        del lines[k]
        with self.assertRaises(ValueError):m.records('\n'.join(lines),self.c)

    def test_wrong_array_and_one_direction_rejected(self):
        for text in (self.text.replace('[63:0][53:0]pmpaddr_next','[63:0][52:0]pmpaddr_next',1),
                     self.text.replace('Toggle 1to0 pmpcfg_q[63].locked "logic pmpcfg_q[63].locked"\n','',1)):
            self.assertNotEqual(text,self.text)
            with self.assertRaises(ValueError):m.records(text,self.c)


if __name__=='__main__':unittest.main()
