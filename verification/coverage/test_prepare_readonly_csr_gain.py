"""Real sealed metadata and synthetic raw OR; never collect the DUT singleton."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_readonly_csr_gain as p


class GainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((p.BASE/'combined-bits.json').read_bytes())
        cls.single=copy.deepcopy(cls.before)
        cls.single['tests']=[str(p.RUN/'code.vdb')]
        cls.single['input_hashes']={'/synthetic/readonly-csr-single.xml':'a'*64}
        for rows in cls.single['metrics'].values():
            for row in rows.values():row['bits']='0x0'
        cls.targets=json.loads((p.qualifier.PRE/'target-receipt.json').read_bytes())['targets']
        cls.qual=p.life.read_bound(p.QUAL,p.QUAL_SEAL)

    def test_exact734_full6162_zero_gain_HOLD(self):
        combined,delta=p.union(self.before,self.single)
        self.assertEqual(len(self.before['tests']),734)
        self.assertEqual(combined['tests'][:-1],self.before['tests'])
        self.assertEqual(sum(len(v) for v in combined['metrics'].values()),6162)
        self.assertEqual(sum(delta['metrics'].values()),0)
        self.assertEqual(p.candidate_status(delta,p.target_hits(self.before,self.single,self.targets)),p.HOLD)

    def test_all24_source_targets_synthetic_gain(self):
        single=copy.deepcopy(self.single)
        for t in self.targets:
            row=single['metrics'][t['metric']][t['scope']]
            row['bits']=hex(int(row['bits'],16)|(1<<(t['width']-1-t['point']['raw_index'])))
        combined,delta=p.union(self.before,single)
        hits=p.target_hits(self.before,single,self.targets)
        self.assertEqual(delta['metrics'],dict(line=12,cond=12,branch=0,fsm=0))
        self.assertTrue(all(h['fresh_target_gain'] for h in hits))
        self.assertEqual(p.candidate_status(delta,hits),p.POSITIVE)
        for metric,rows in self.before['metrics'].items():
            for scope,row in rows.items():
                self.assertEqual(int(combined['metrics'][metric][scope]['bits'],16),
                                 int(row['bits'],16)|int(single['metrics'][metric][scope]['bits'],16))

    def test_incidental_gain_is_not_bound_target_gain(self):
        self.assertEqual(p.candidate_status(dict(metrics=dict(line=8,cond=1,branch=1,fsm=0)),
                         [dict(fresh_target_gain=False)]*24),p.HOLD)

    def test_old_duplicate_foreign_singleton_and_already_present_rejected(self):
        for mode in ('old','duplicate','foreign','present'):
            before,single=copy.deepcopy(self.before),copy.deepcopy(self.single)
            if mode=='old':before['tests']=before['tests'][:-1]
            elif mode=='duplicate':before['tests'][1]=before['tests'][0]
            elif mode=='foreign':single['tests']=['/foreign/code.vdb']
            else:before['tests'][0]=single['tests'][0]
            with self.assertRaises(ValueError):p.union(before,single)

    def test_missing_shape_width_checksum_overflow_and_empty_pins_rejected(self):
        for mode in ('missing','width','checksum','overflow','empty'):
            single=copy.deepcopy(self.single);scope=self.targets[0]['scope']
            row=single['metrics']['cond'][scope]
            if mode=='missing':del single['metrics']['cond'][scope]
            elif mode=='width':row['width']+=1
            elif mode=='checksum':row['checksum']='foreign'
            elif mode=='overflow':row['bits']=hex(1<<row['width'])
            else:single['input_hashes']={}
            with self.assertRaises(ValueError):p.union(self.before,single)

    def test_already_hit_is_witness_not_fresh(self):
        before,single=copy.deepcopy(self.before),copy.deepcopy(self.single);t=self.targets[0]
        mask=1<<(t['width']-1-t['point']['raw_index'])
        for sample in (before,single):
            row=sample['metrics'][t['metric']][t['scope']];row['bits']=hex(int(row['bits'],16)|mask)
        self.assertFalse(p.target_hits(before,single,self.targets)[0]['fresh_target_gain'])

    def test_exact_coordinate_scope_source_and_native_vector_rejected(self):
        for field,value in (('raw_index',571),('file_id','other'),('line','4678'),
                            ('native_id','244'),('vector','1'),('expression',"1'b0")):
            targets=copy.deepcopy(self.targets);targets[0]['point'][field]=value
            with self.assertRaises(ValueError):p.validate_targets(targets)
        for mode in ('missing','reorder','scope','module'):
            targets=copy.deepcopy(self.targets)
            if mode=='missing':targets.pop()
            elif mode=='reorder':targets[0],targets[1]=targets[1],targets[0]
            elif mode=='scope':targets[0]['scope']='foreign'
            else:targets[0]['module_checksum']='foreign'
            with self.assertRaises(ValueError):p.validate_targets(targets)

    def test_real733check_qualification_no_scope_promotion(self):
        p.qualification(self.qual)
        for key in ('coverage_admitted','whole_ISA_qualified','target_hits_verified','raw_gain_collected',
                    'native_cycle_qualified','simulation_retried'):
            record=copy.deepcopy(self.qual);record[key]=True
            with self.assertRaises(ValueError):p.qualification(record)

    def test_wrong_checks_traps_UVM_OS_memory_reference_rejected(self):
        for key,value in (('checks',732),('illegal_traps',11),('UVM_errors',2),('OS_returncode',None),
                          ('OS_returncode',False),('native_known_write_bytes',263),
                          ('full_memory_bytes',431),('software_reference_is_Spike',False)):
            record=copy.deepcopy(self.qual);record[key]=value
            with self.assertRaises(ValueError):p.qualification(record)

    def test_wrong_qualification_seal_rejected_before_any_read(self):
        with patch.object(p.life,'read_bound') as read:
            with self.assertRaises(ValueError):p.inputs(p.QUAL,'foreign',p.BASE,p.BASE_SEAL)
            read.assert_not_called()

    def test_invalid_delta_rejected(self):
        for values in (dict(line=-1,cond=1,branch=0,fsm=0),dict(line=True,cond=1,branch=0,fsm=0)):
            with self.assertRaises(ValueError):p.candidate_status(dict(metrics=values),[])

    def test_pin_conflict_rejected(self):
        with self.assertRaises(ValueError):p.life.merge_pins({'/x':'a'*64},{'/x':'b'*64})

    def test_real_parser_serialized_design_vs_data_ownership(self):
        with tempfile.TemporaryDirectory(dir=p.OUT) as temp:
            root=Path(temp);design=root/'design.vdb';sample=root/'sample.vdb'
            db=design/'snps/coverage/db';(db/'design').mkdir(parents=True);(db/'shape').mkdir()
            (db/'design/verilog.design.xml').write_bytes(b'<design/>')
            directory=sample/'snps/coverage/db/testdata'/p.p.NAME;directory.mkdir(parents=True)
            rawpins={}
            for m in p.bitmap.METRICS:
                (db/('shape/'+m+'.verilog.shape.xml')).write_bytes(b'<shape/>')
                path=directory/(m+'.verilog.data.xml')
                path.write_bytes(gzip.compress(b'<covdata><instance_data name="scope" value="0"/></covdata>'))
                rawpins[str(path)]=p.life.digest(path)
            inputs=root/'inputs.txt';inputs.write_text(str(design)+'\n'+str(sample)+'\n')
            single=p.bitmap.collect(inputs)
            self.assertEqual(single['input_hashes'],rawpins)
            self.assertEqual(len(single['design']),5)

    def test_singleton_data_pins_reject_foreign_design_missing_or_changed_bytes(self):
        directory=p.RUN/'code.vdb/snps/coverage/db/testdata'/p.p.NAME
        rawpins={str(directory/(m+'.verilog.data.xml')):'a'*64 for m in p.bitmap.METRICS}
        p.single_identity(dict(input_hashes=rawpins),rawpins)
        for mode in ('foreign','missing','bytes'):
            bad=dict(rawpins)
            if mode=='foreign':bad['/foreign/design.xml']='a'*64
            elif mode=='missing':bad.pop(next(iter(rawpins)))
            else:bad[next(iter(rawpins))]='b'*64
            with self.assertRaises(ValueError):p.single_identity(dict(input_hashes=bad),rawpins)


if __name__=='__main__':unittest.main()
