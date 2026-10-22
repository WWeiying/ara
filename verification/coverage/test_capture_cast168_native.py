import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
import capture_cast168_native as m


def fixture():
    review=json.loads(m.REVIEW.read_bytes())
    source=json.loads(Path(review['inventory400']).read_bytes());items=[]
    for i in review['candidate_instances']:
        full=next(x for x in source['instances']if x['scope']==i['scope'])
        names={x['name']for x in i['targets']}
        items.append(dict(i,protected=[x['native_name']for x in full['targets']+full['protected']if x['name']not in names]))
    return dict(instances=items)


def el(c):
    lines=[]
    for i in c['instances']:
        lines += ['CHECKSUM: "1144939760 400336858"','INSTANCE: '+i['scope']]
        lines += ['Toggle '+t['name']+' "logic '+t['native_name']+'"'for t in i['targets']]
    return '\n'.join(lines)+'\n'


class Native(unittest.TestCase):
    def setUp(self):self.c=fixture();self.text=el(self.c)

    def test_exact168_full_vectors_and_arrays(self):
        m.contract(self.c);self.assertEqual(len(m.parse_el(self.text,self.c)),168)

    def test_semantic_order(self):
        chunks=self.text.split('CHECKSUM: ')[1:]
        self.assertEqual(m.parse_el(self.text,self.c),m.parse_el(''.join('CHECKSUM: '+x for x in reversed(chunks)),self.c))

    def test_direction_only_rejected(self):
        with self.assertRaises(ValueError):m.parse_el(self.text.replace('Toggle operands_q ','Toggle 0to1 operands_q ',1),self.c)

    def test_extra_control_rejected(self):
        with self.assertRaises(ValueError):m.parse_el(self.text+'Toggle rnd_mode_q "logic rnd_mode_q[2:0]"\n',self.c)

    def test_wrong_checksum_rejected(self):
        with self.assertRaises(ValueError):m.parse_el(self.text.replace('400336858','400336859',1),self.c)

    def test_missing_rejected(self):
        with self.assertRaises(ValueError):m.parse_el('\n'.join(self.text.splitlines()[:-1]),self.c)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):m.parse_el(self.text+'\n'+self.text.splitlines()[-1],self.c)

    def test_wrong_array_bounds_rejected(self):
        target=next(t for i in self.c['instances']for t in i['targets']if len(t['dimensions'])>1)
        changed=self.text.replace('logic '+target['native_name'],'logic '+target['name']+'[63:0]',1)
        with self.assertRaises(ValueError):m.parse_el(changed,self.c)

    def test_unbound_native_metadata_rejected(self):
        metas={(i['scope'],t['name']):'logic '+t['native_name']for i in self.c['instances']for t in i['targets']}
        m.parse_el(self.text,self.c,metas)
        key=next(iter(metas));metas[key]='logic WRONG[63:0]'
        with self.assertRaises(ValueError):m.parse_el(self.text,self.c,metas)

    def test_protection_native_missing_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);i=self.c['instances'][0]
            names=[t['native_name']for t in i['targets']]+i['protected']
            with (out/'native_before_0.tsv').open('w',newline='') as f:
                w=csv.writer(f,delimiter='\t');w.writerow(['handle','path','meta','name'])
                w.writerows((str(n),'path.'+name,'logic '+name,name)for n,name in enumerate(names))
            self.assertEqual(len(m.inventory(out,self.c,'before',0)),279)
            rows=(out/'native_before_0.tsv').read_text().splitlines()
            (out/'native_before_0.tsv').write_text('\n'.join(rows[:-1])+'\n')
            with self.assertRaises(ValueError):m.inventory(out,self.c,'before',0)

    def test_tcl_full_body_legacy_safe(self):
        t=tkinter.Tcl();t.eval('set ::cast_test_only 1')
        t.eval((m.HERE/'capture_cast168_native.tcl').read_text())
        self.assertEqual(t.eval('info args cast_session'),'')
        text=(m.HERE/'capture_cast168_native.tcl').read_text()
        self.assertNotIn('lassign',text);self.assertNotIn('dict ',text)
        self.assertNotIn('-recursive',text);self.assertIn('cast_reset',text)


if __name__=='__main__':unittest.main()
