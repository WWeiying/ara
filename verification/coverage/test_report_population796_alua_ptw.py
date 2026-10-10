"""Actual native receipts, complete796 data and exact-union mutation tests."""
import copy
import unittest
from unittest.mock import patch
import report_population796_alua_ptw as r


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=r.old.prior.prior.inherited.Reader()
        cls.ac,cls.pc,cls.packet,cls.blobs,cls.pins=r.qualification(cls.reader)
        m=cls.reader.read(r.BASE,r.BASE_SHA,True)
        cls.pins=r.stable.merge(cls.pins,m['input_pins'],m['output_pins'])
        cls.bits=cls.reader.read(r.BASE.parent/'combined-bits.json',cls.pins[str(r.BASE.parent/'combined-bits.json')],True)
        cls.toggle=cls.reader.read(r.BASE.parent/'combined-toggle-bits.json',cls.pins[str(r.BASE.parent/'combined-toggle-bits.json')],True)
        cls.previous=cls.reader.read(r.REPORT/'config.json',r.REPORT_CONFIG_SHA,True)
        cls.base=(r.REPORT/'combined.el').read_text()
        cls.design=r.alua.source.Design(r.Path(cls.ac['plan']['design_vdb']))
        cls.ledger=(r.BASE.parent/'combined-inputs.txt').read_text().splitlines()
        cls.source={k:cls.previous[k] for k in ('hierarchy_roots','tool_identity')}
        cls.source['input_ledger']=cls.ledger
        cls.chain=cls.previous['genealogy']+[dict(population=796,manifest=str(r.BASE),seal=r.BASE_SHA,new_vdb=cls.ledger[-1])]

    def zero(self,bits=None,toggle=None):
        return r.added_zero(self.bits if bits is None else bits,self.toggle if toggle is None else toggle,
                            self.ac,self.pc,self.packet,self.design)

    def test_actual796_source_zero(self):
        result=self.zero()
        self.assertTrue(result['ALUA137_zero']);self.assertTrue(result['PTW156_zero'])
        self.assertFalse(result['PTW_local_excluded_flags_observed'])
        self.assertFalse(result['local_official_denominator_proven'])

    def test_actual_AKV796_single_source_zero(self):
        p=r.BASE.parent/'single-bits.json'
        single=self.reader.read(p,self.pins[str(p)],True)
        paths=list((r.Path(self.ledger[-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        self.assertEqual(len(paths),1)
        rows,sha=r.old.prior.prior.suffix.native.rows(paths[0],{self.pc['instances'][0]['scope']})
        self.assertEqual(sha,self.pins[str(paths[0])])
        result=r.added_zero(single,rows,self.ac,self.pc,self.packet,self.design)
        self.assertTrue(result['ALUA137_zero'] and result['PTW156_zero'])

    def test_actual_native_exact_union_and_protection(self):
        text=r.union_gate(self.base,*self.blobs)
        before,after=map(r.stable.semantic,(self.base,text))
        self.assertEqual(len(after[0]-before[0]),137)
        self.assertEqual(sum(bin(x).count('1') for x in r.physical(after).values())-
                         sum(bin(x).count('1') for x in r.physical(before).values()),156)

    def test_existing_and_ancestor_overlap_rejected(self):
        for addition in self.blobs:
            with self.assertRaises(ValueError):r.union_gate(self.base+'\n'+addition,*self.blobs)
        scope=next(iter(self.ac['plan']['scopes']))
        value=r.stable.semantic(self.blobs[0]);row=next(t for t in value[0] if t[0]==scope)
        mocked=(value[0]|{(scope,row[1],'','WHOLE_SCOPE')},{})
        original=r.stable.semantic
        with patch.object(r.stable,'semantic',side_effect=lambda t:mocked if t=='WHOLE' else original(t)):
            with self.assertRaises(ValueError):r.union_gate('WHOLE',*self.blobs)

    def test_missing_branch_and_extra_toggle_rejected(self):
        branch='\n'.join(line for i,line in enumerate(self.blobs[0].splitlines()) if i!=3)+'\n'
        with self.assertRaises(ValueError):r.union_gate(self.base,branch,self.blobs[1])
        with self.assertRaises(ValueError):r.union_gate(self.base,self.blobs[0],self.blobs[1]+'Toggle rogue "logic rogue"\n')

    def test_native_annotation_or_protected_field_drift(self):
        with self.assertRaises(ValueError):r.alua.bind_native(self.blobs[0].replace(r.alua.ANNOTATION,'wrong').encode(),self.ac)
        with self.assertRaises(ValueError):r.ptw.el_gate(self.blobs[1].replace('ANNOTATION: "'+r.ptw.old.ANNOTATION+'"','ANNOTATION: "wrong"'),self.pc)
        name=self.pc['instances'][0]['signals'][0]['name']
        with self.assertRaises(ValueError):r.ptw.el_gate(self.blobs[1].replace(name,'protected_dynamic'),self.pc)

    def test_ALUA_zero_counterexample(self):
        bits=copy.deepcopy(self.bits)
        scope,metrics=next(iter(self.ac['plan']['scopes'].items()))
        target=next(e for e in metrics['branch'] if e['target']);row=bits['metrics']['branch'][scope]
        row['bits']=hex(int(row['bits'],16)|(1<<(row['width']-1-target['point']['raw_index'])))
        with self.assertRaises(ValueError):self.zero(bits=bits)

    def test_PTW_zero_or_checksum_counterexample(self):
        for kind in ('hit','checksum'):
            toggle=copy.deepcopy(self.toggle);instance=self.pc['instances'][0];row=toggle[instance['scope']]
            if kind=='hit':row['bits']=hex(int(row['bits'],16)|(1<<(row['width']-1-instance['signals'][0]['missing_coordinates'][0])))
            else:row['checksum']='0'
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.zero(toggle=toggle)

    def test_actual796_population(self):
        r.corpus_gate(self.source,self.bits,self.chain,self.previous)

    def test_population_prefix_duplicate_shape_roots_seal(self):
        for kind in ('prefix','duplicate','shape','roots','seal'):
            source=copy.deepcopy(self.source);bits=copy.deepcopy(self.bits);chain=copy.deepcopy(self.chain)
            if kind=='prefix':source['input_ledger'][1:3]=reversed(source['input_ledger'][1:3])
            elif kind=='duplicate':source['input_ledger'][-1]=source['input_ledger'][-2]
            elif kind=='shape':bits['metrics']['fsm'].pop(next(iter(bits['metrics']['fsm'])))
            elif kind=='roots':source['hierarchy_roots']=source['hierarchy_roots'][:-1]
            else:chain[-1]['seal']='0'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.corpus_gate(source,bits,chain,self.previous)

    def test_no_endpoint_fallback(self):
        with self.assertRaises(ValueError):r.approved(None,r.old.BASE,r.old.BASE_SHA)

    def test_five_stage_codes_and_private_bindings_unchanged(self):
        a=r.old.context();b=r.context()
        for i in range(3):self.assertEqual(a[i].__code__,b[i].__code__)
        self.assertIs(b[3].__globals__['check'],b[1]);self.assertIs(b[3].__globals__['verify'],b[2])
        self.assertIs(b[1].__globals__['approved'],r.approved)
        for p,h in r.old.dependencies().items():self.assertEqual(r.dependencies()[p],h)


if __name__=='__main__':unittest.main()
