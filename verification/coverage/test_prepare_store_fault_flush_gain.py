"""Static/synthetic OR tests only; no actual singleton raw collection/admission."""
import copy
import json
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_store_fault_flush_gain as p


class GainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((p.BASE/'combined-bits.json').read_bytes())
        cls.single=copy.deepcopy(cls.before)
        cls.single['tests']=[str(p.RUN/'code.vdb')];cls.single['input_hashes']={'/synthetic/single.xml':'a'*64}
        for rows in cls.single['metrics'].values():
            for row in rows.values():row['bits']='0x0'
        receipt=json.loads((p.runner.PRE/'target-receipt.json').read_bytes())
        cls.targets=[dict(receipt['primary_target'],role='primary'),
                     dict(receipt['conditional_branch_witness'],role='conditional_witness')]
        cls.qual=p.life.read_bound(p.QUAL,p.QUAL_SEAL)

    def test_full6162_synthetic_zero_gain_exact732_prefix(self):
        combined,delta=p.union(self.before,self.single)
        self.assertEqual(sum(len(x) for x in combined['metrics'].values()),6162)
        self.assertEqual(combined['tests'][:-1],self.before['tests'])
        self.assertEqual(sum(delta['metrics'].values()),0)
        self.assertEqual(p.candidate_status(delta,p.target_hits(self.before,self.single,self.targets)),p.HOLD)

    def test_primary_gain_and_conditional_witness_not_required(self):
        single=copy.deepcopy(self.single);t=self.targets[0]
        single['metrics'][t['metric']][t['scope']]['bits']=hex(1<<(t['width']-1-t['point']['raw_index']))
        _,delta=p.union(self.before,single);hits=p.target_hits(self.before,single,self.targets)
        self.assertTrue(hits[0]['fresh_target_gain']);self.assertFalse(hits[1]['single_hit'])
        self.assertEqual(p.candidate_status(delta,hits),p.POSITIVE)

    def test_incidental_gain_only_remains_HOLD(self):
        self.assertEqual(p.candidate_status({'metrics':{'line':10,'cond':50,'branch':10,'fsm':0}},
                         [{'fresh_target_gain':False},{'fresh_target_gain':True}]),p.HOLD)

    def test_old_population_duplicate_or_wrong_singleton_rejected(self):
        for mode in ('old','duplicate','wrong'):
            before,single=copy.deepcopy(self.before),copy.deepcopy(self.single)
            if mode=='old':before['tests']=before['tests'][:-1]
            elif mode=='duplicate':before['tests'][1]=before['tests'][0]
            else:single['tests']=[before['tests'][0]]
            with self.assertRaises(ValueError):p.union(before,single)

    def test_missing_width_checksum_overflow_rejected(self):
        for mode in ('missing','width','checksum','overflow'):
            single=copy.deepcopy(self.single);scope=self.targets[0]['scope'];row=single['metrics']['line'][scope]
            if mode=='missing':del single['metrics']['line'][scope]
            elif mode=='width':row['width']+=1
            elif mode=='checksum':row['checksum']='foreign'
            else:row['bits']=hex(1<<row['width'])
            with self.assertRaises(ValueError):p.union(self.before,single)

    def test_already_hit_is_not_fresh_and_shape_required(self):
        before=copy.deepcopy(self.before);single=copy.deepcopy(self.single);t=self.targets[0]
        for sample in (before,single):sample['metrics']['line'][t['scope']]['bits']=hex(1<<(t['width']-1-t['point']['raw_index']))
        self.assertFalse(p.target_hits(before,single,self.targets)[0]['fresh_target_gain'])
        single['metrics']['line'][t['scope']]['checksum']='foreign'
        with self.assertRaisesRegex(ValueError,'checksum drift'):p.target_hits(before,single,self.targets)

    def test_exact_two_target_roles(self):
        with self.assertRaises(ValueError):p.target_hits(self.before,self.single,self.targets[::-1])

    def test_real_sealed134_qualification_no_native_promotion(self):
        p.qualification(self.qual)
        for key in ('coverage_admitted','whole_ISA_qualified','native_B_error_plus_addr_fault_timing_measured','target_hit_verified'):
            record=copy.deepcopy(self.qual);record[key]=True
            with self.assertRaises(ValueError):p.qualification(record)

    def test_wrong_checks_UVM_or_unknown_OS_rejected(self):
        for key,value in [('checks',133),('UVM_errors',2),('OS_returncode',None),('OS_returncode',False)]:
            record=copy.deepcopy(self.qual);record[key]=value
            with self.assertRaises(ValueError):p.qualification(record)

    def test_wrong_qualification_seal_rejected_before_reads(self):
        with patch.object(p.life,'read_bound') as read:
            with self.assertRaisesRegex(ValueError,'Exact parent'):p.inputs(p.QUAL,'foreign',p.BASE,p.BASE_SEAL)
            read.assert_not_called()

    def test_inherited_pin_conflict_rejected(self):
        with self.assertRaises(ValueError):p.life.merge_pins({'/x':'a'*64},{'/x':'b'*64})

    def test_real_parser_serialization_fixture_design_vs_data_ownership(self):
        # Exercise the frozen parser on generated files, never the actual DUT singleton.
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
            self.assertEqual(single['input_hashes'],rawpins);self.assertEqual(len(single['design']),5)
            self.assertFalse(any('/shape/' in x or '/design/' in x for x in single['input_hashes']))

    def test_single_hash_inventory_rejects_design_or_foreign_data(self):
        directory=p.RUN/'code.vdb/snps/coverage/db/testdata'/p.p.NAME
        rawpins={str(directory/(m+'.verilog.data.xml')):'a'*64 for m in p.bitmap.METRICS}
        single={'input_hashes':dict(rawpins)};p.single_identity(single,rawpins)
        for mode in ('design','missing','bytes'):
            bad=copy.deepcopy(single)
            if mode=='design':bad['input_hashes']['/foreign/design.xml']='a'*64
            elif mode=='missing':bad['input_hashes'].pop(next(iter(rawpins)))
            else:bad['input_hashes'][next(iter(rawpins))]='b'*64
            with self.assertRaises(ValueError):p.single_identity(bad,rawpins)


if __name__=='__main__':unittest.main()
