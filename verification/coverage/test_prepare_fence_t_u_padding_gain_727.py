import copy
import json
import unittest
import prepare_fence_t_u_padding_gain_727 as tool


class GainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((tool.BASE/'combined-bits.json').read_bytes())
        db=tool.RUN/'code.vdb/snps/coverage/db/testdata/fence_t_u_padding_successor'
        cls.single=dict(design=cls.before['design'],tests=[str(tool.RUN/'code.vdb')],input_hashes={},
                        metrics={m:tool.bitmap.read_metric(db/(m+'.verilog.data.xml')) for m in tool.bitmap.METRICS})
        cls.post=json.loads(tool.POST.read_bytes())

    def test_real6162_OR_exact727_prefix_positive_delta(self):
        combined,delta,changes=tool.validate_population(self.before,self.single)
        self.assertEqual(delta['metrics'],dict(line=7,cond=11,branch=8,fsm=0))
        self.assertEqual(len(changes),26);self.assertEqual(combined['tests'][:-1],self.before['tests'])

    def test_zero_gain_rejected(self):
        single=copy.deepcopy(self.before);single['tests']=self.single['tests'];single['input_hashes']={}
        with self.assertRaises(ValueError):tool.validate_population(self.before,single)

    def test_duplicate_and_wrong_prefix_population_rejected(self):
        bad=copy.deepcopy(self.single);bad['tests']=[self.before['tests'][0]]
        with self.assertRaises(ValueError):tool.validate_population(self.before,bad)
        before=copy.deepcopy(self.before);before['tests'][1]=before['tests'][0]
        with self.assertRaises(ValueError):tool.validate_population(before,self.single)

    def test_missing_instance_width_checksum_and_overflow_rejected(self):
        name=next(iter(self.single['metrics']['line']))
        for mode in ('missing','width','checksum','overflow'):
            bad=copy.deepcopy(self.single);row=bad['metrics']['line'][name]
            if mode=='missing':del bad['metrics']['line'][name]
            elif mode=='width':row['width']+=1
            elif mode=='checksum':row['checksum']='different'
            else:row['bits']=hex(1<<row['width'])
            with self.assertRaises(ValueError):tool.validate_population(self.before,bad)

    def test_checksum_None_encoding_not_rewritten(self):
        combined,_,_=tool.validate_population(self.before,self.single)
        scope=tool.PREFIX+'controller_i.i_pad_cnt.i_counter'
        self.assertIsNone(combined['metrics']['branch'][scope]['checksum'])
        bad=copy.deepcopy(self.single);bad['metrics']['branch'][scope]['checksum']='2355591505'
        with self.assertRaises(ValueError):tool.validate_population(self.before,bad)

    def test_exact_post_contract_no_qualification_promotion(self):
        tool.post_contract(self.post)
        for key in ('UVM_clean','cyclequalified','application_approval'):
            bad=copy.deepcopy(self.post);bad[key]=True
            with self.assertRaises(ValueError):tool.post_contract(bad)

    def test_pin_conflict_and_drift_rejected(self):
        with self.assertRaises(ValueError):tool.merge({'x':'a'},{'x':'b'})
        with self.assertRaises(ValueError):tool.check({str(tool.POST):'wrong'})


if __name__=='__main__':unittest.main()
