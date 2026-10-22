import copy
from pathlib import Path
import tempfile
import unittest
import c910_prepare_pack_native as n


def fixture():
    review=n.life.read_bound(n.REVIEW,n.REVIEW_SHA)
    return dict(instances=n.instances(review),design=str(n.life.IMAGE)+'.vdb',
        vdb=str(n.life.OUT/'gap84-div32-old-image-20261006-01/code.vdb'),
        native_test=str(n.life.OUT/'gap84-div32-old-image-20261006-01/code/unused-mock-test'))


class ExactNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=fixture();cls.el=n.el_text(cls.c)

    def test_actual_source_whole_union(self):
        self.assertEqual(len(n.parse_el(self.el,self.c)),240)
        self.assertEqual(sum(len(i['objects'])-len(i['targets']) for i in self.c['instances']),3740)

    def test_complete_direction_pair(self):
        lines=[]
        for line in self.el.splitlines():
            if line.startswith('Toggle '):
                lines.extend((line.replace('Toggle ','Toggle 0to1 ',1),line.replace('Toggle ','Toggle 1to0 ',1)))
            else:lines.append(line)
        self.assertEqual(n.parse_el('\n'.join(lines),self.c),n.parse_el(self.el,self.c))

    def test_missing_duplicate_mixed_single_direction(self):
        line=next(x for x in self.el.splitlines() if x.startswith('Toggle '))
        for text in (self.el.replace(line+'\n','',1),self.el.replace(line,line+'\n'+line,1),
                     self.el.replace(line,line.replace('Toggle ','Toggle 0to1 ',1),1),
                     self.el.replace(line,line+'\n'+line.replace('Toggle ','Toggle 0to1 ',1),1)):
            with self.assertRaises(ValueError):n.parse_el(text,self.c)

    def test_type_bounds_checksum_othermetric(self):
        for old,new in (('"net ','"wire '),('[51:0]','[50:0]'),('3434235298','3434235299'),
                        ('Toggle ','Line '),('"net ','"signed net ')):
            with self.assertRaises(ValueError):n.parse_el(self.el.replace(old,new,1),self.c)

    def test_scalar_child_interface_special_flags_rejected(self):
        i=self.c['instances'][0];target=i['targets'][0]['name']
        for name in ('ex4_out_result','ex4_rst_qnan','ex4_cor_nx'):
            with self.assertRaises(ValueError):n.parse_el(self.el.replace(target,name,1),self.c)
        for i in self.c['instances']:
            if not i['targets']:
                with self.assertRaises(ValueError):n.parse_el(self.el.replace(self.c['instances'][0]['scope'],i['scope'],1),self.c)
                break

    def test_inventory_requires_exact_every_guard(self):
        with tempfile.TemporaryDirectory(dir=n.life.OUT) as directory:
            path=Path(directory)/'rows.tsv';i=self.c['instances'][0]
            text='handle\tpath\tmeta\tname\n'+''.join('%d\tP%d\tM%d\t%s\n'%(k,k,k,name)
                for k,name in enumerate(i['native_names']))
            path.write_text(text);n.inventory(path,i)
            for wrong in (text.rsplit('\n',2)[0]+'\n',text+text.splitlines()[1]+'\n'):
                path.write_text(wrong)
                with self.assertRaises(ValueError):n.inventory(path,i)

    def test_config_scope_type_and_bounds_not_relaxed(self):
        for key,value in (('portnode','2'),('left','1'),('name','ex4_out_result')):
            c=copy.deepcopy(self.c);c['instances'][0]['targets'][0][key]=value
            with self.assertRaises(ValueError):n.source_bindings(c)

    def test_actual_disk_selection_entry_eval_five_stages(self):
        from c910_prepare_pack_native_mock import qualify
        with tempfile.TemporaryDirectory(dir=n.life.OUT) as directory:
            out=Path(directory)
            (out/'selection.tcl').write_text(n.selection(self.c),encoding='ascii')
            (out/'candidate.el').write_text(self.el,encoding='ascii')
            result=qualify(out,self.c)
            self.assertEqual(len(result['stages']),5)
            self.assertFalse(result['native_qualified'])


if __name__=='__main__':unittest.main()
