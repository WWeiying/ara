import copy
import json
import unittest
import verify_cva6_fixed_fields_native768_offline as adapter


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((adapter.CAPTURE/'config.json').read_bytes())

    def stages(self, index):
        return {stage:(adapter.CAPTURE/('native_'+stage+'_'+str(index)+'.tsv')).read_text()
                for stage in ('before','selected','reset','reloaded','final')}

    def test_actual_complete_five_stages(self):
        counts = [adapter.audit_native(i,self.stages(k)) for k,i in enumerate(self.config['instances'])]
        self.assertEqual(counts,[(186,159),(167,146),(148,128),(511,485),(511,485)])

    def test_actual_single_bit_nonzero_index(self):
        i=self.config['instances'][1]
        rows=adapter.frozen.native_rows(self.stages(1)['before'])
        aliases=adapter.bind_inventory(i,rows)
        self.assertIn(dict(compiled='instr.rvftype.repl[14:14]',native='instr.rvftype.repl',
                           tag='vectornode',left='14',right='14',declaration_line='180'),aliases)

    def test_wide_vector_cannot_scalarize(self):
        i=self.config['instances'][0]; rows=adapter.frozen.native_rows(self.stages(0)['before'])
        name=next(s['native_label'] for s in i['signals'] if s['left']!=s['right'])
        rows[name.split('[')[0]]=rows.pop(name)
        with self.assertRaises(ValueError):adapter.bind_inventory(i,rows)

    def test_array_cannot_flatten(self):
        i=self.config['instances'][0]; rows=adapter.frozen.native_rows(self.stages(0)['before'])
        array=next(n for n in i['protected_shape'] if n['tag']=='arrays')
        name=adapter.frozen.normalized_label(adapter.label(array));self.assertIn(name,rows)
        rows[array['name']]=rows.pop(name)
        with self.assertRaises(ValueError):adapter.bind_inventory(i,rows)

    def test_unknown_missing_and_ambiguous_native(self):
        i=self.config['instances'][0]; original=adapter.frozen.native_rows(self.stages(0)['before'])
        alias=next(a for a in adapter.bind_inventory(i,original) if a['tag']=='vectornode')
        variants=[]
        extra=copy.deepcopy(original);extra['extra']=copy.deepcopy(next(iter(extra.values())));variants.append(extra)
        missing=copy.deepcopy(original);missing.pop(alias['native']);variants.append(missing)
        ambiguous=copy.deepcopy(original);ambiguous[alias['compiled']]=ambiguous[alias['native']];variants.append(ambiguous)
        for rows in variants:
            with self.assertRaises(ValueError):adapter.bind_inventory(i,rows)

    def test_protected_actual_percentage_rejected(self):
        i=self.config['instances'][0];stages=self.stages(0)
        rows=adapter.frozen.native_rows(stages['before'])
        targets={s['native_label'] for s in i['signals']}
        name=next(x for x in rows if x not in targets and rows[x]['coverage']=='100.00%')
        lines=stages['selected'].splitlines()
        for k,line in enumerate(lines):
            fields=line.split('\t')
            if len(fields)==7 and fields[3]==name:fields[5]='99.99%';lines[k]='\t'.join(fields)
        stages['selected']='\n'.join(lines)+'\n'
        with self.assertRaises(ValueError):adapter.audit_native(i,stages)

    def test_scalar_alias_requires_native_meta_and_type(self):
        i=self.config['instances'][1]
        before=adapter.frozen.native_rows(self.stages(1)['before'])
        for key,value in (('meta','instr.rvftype.repl[15]'),('path','alias'),('type','MDA')):
            rows=copy.deepcopy(before);rows['instr.rvftype.repl'][key]=value
            with self.assertRaises(ValueError):adapter.bind_inventory(i,rows)

    def test_actual_global_el_and_empty(self):
        first=adapter.frozen.parse_el((adapter.CAPTURE/'first.el').read_text(),self.config)
        self.assertEqual(len(first),4396)
        self.assertEqual(first,adapter.frozen.parse_el((adapter.CAPTURE/'second.el').read_text(),self.config))
        for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
            self.assertEqual((adapter.CAPTURE/name).read_bytes(),b'')
        for text in ((adapter.CAPTURE/'first.el').read_text()+'Toggle bogus\n',
                     (adapter.CAPTURE/'first.el').read_text().replace('670764694','670764695',1)):
            with self.assertRaises(ValueError):adapter.frozen.parse_el(text,self.config)


if __name__=='__main__':unittest.main()
