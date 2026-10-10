import csv
import io
import json
import unittest
import audit_fpnew90_before_offline as a


class ActualBefore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads((a.RUN/'config.json').read_bytes())
        cls.instance=cls.c['instances'][0]
        cls.text=(a.RUN/'native_before_0.tsv').read_text()

    def changed(self,mutate):
        reader=csv.DictReader(io.StringIO(self.text),delimiter='\t')
        fields=reader.fieldnames;rows=list(reader);mutate(rows)
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields,delimiter='\t',lineterminator='\n')
        writer.writeheader();writer.writerows(rows);return stream.getvalue()

    def test_actual_all70_inventory(self):
        rows=a.frozen.before_gate(a.RUN,self.c)
        self.assertEqual(sum(map(len,rows)),3286)

    def test_actual_target_wrong_role(self):
        label=a.frozen.labels(self.instance)[0]
        text=self.changed(lambda rows:next(r for r in rows if r['name']==label).__setitem__('type','signal'))
        with self.assertRaises(ValueError):a.frozen.bind(self.instance,text)

    def test_actual_protected_missing(self):
        targets=set(a.frozen.labels(self.instance))
        def remove(rows):rows.remove(next(r for r in rows if r['name'] not in targets))
        with self.assertRaises(ValueError):a.frozen.bind(self.instance,self.changed(remove))

    def test_actual_duplicate(self):
        with self.assertRaises(ValueError):a.frozen.bind(self.instance,self.changed(lambda rows:rows.append(dict(rows[0]))))

    def test_actual_target_range_changed(self):
        label=a.frozen.labels(self.instance)[0]
        def change(rows):next(r for r in rows if r['name']==label)['name']=label.replace('[33:0]','[32:0]')
        with self.assertRaises(ValueError):a.frozen.bind(self.instance,self.changed(change))


if __name__=='__main__':unittest.main()
