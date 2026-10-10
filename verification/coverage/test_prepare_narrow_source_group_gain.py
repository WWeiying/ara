"""Real sealed metadata and synthetic raw OR; never collect the DUT singleton."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_narrow_source_group_gain as p


class GainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((p.BASE/'combined-bits.json').read_bytes())
        cls.single=copy.deepcopy(cls.before)
        cls.single['tests']=[str(p.RUN/'code.vdb')]
        cls.single['input_hashes']={'/synthetic/readonly-csr-single.xml':'a'*64}
        for rows in cls.single['metrics'].values():
            for row in rows.values():row['bits']='0x0'
        cls.targets=json.loads((p.qualifier.runner.preflight.FAILED/'target-receipt.json').read_bytes())['targets']
        cls.qual=p.life.read_bound(p.QUAL,p.QUAL_SEAL)

    def test_exact735_full6162_zero_gain_HOLD(self):
        combined,delta=p.union(self.before,self.single)
        self.assertEqual(len(self.before['tests']),735)
        self.assertEqual(combined['tests'][:-1],self.before['tests'])
        self.assertEqual(sum(len(v) for v in combined['metrics'].values()),6162)
        self.assertEqual(sum(delta['metrics'].values()),0)
        self.assertEqual(p.candidate_status(delta,p.target_hits(self.before,self.single,self.targets)),p.HOLD)

    def test_all2_source_targets_synthetic_gain(self):
        single=copy.deepcopy(self.single)
        for t in self.targets:
            row=single['metrics'][t['metric']][t['scope']]
            row['bits']=hex(int(row['bits'],16)|(1<<(t['width']-1-t['point']['raw_index'])))
        combined,delta=p.union(self.before,single)
        hits=p.target_hits(self.before,single,self.targets)
        self.assertEqual(delta['metrics'],dict(line=1,cond=1,branch=0,fsm=0))
        self.assertTrue(all(h['fresh_target_gain'] for h in hits))
        self.assertEqual(p.candidate_status(delta,hits),p.POSITIVE)
        for metric,rows in self.before['metrics'].items():
            for scope,row in rows.items():
                self.assertEqual(int(combined['metrics'][metric][scope]['bits'],16),
                                 int(row['bits'],16)|int(single['metrics'][metric][scope]['bits'],16))

    def test_incidental_gain_is_not_bound_target_gain(self):
        self.assertEqual(p.candidate_status(dict(metrics=dict(line=8,cond=1,branch=1,fsm=0)),
                         [dict(fresh_target_gain=False)]*2),p.HOLD)

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
        for field,value in (('raw_index',225),('file_id','other'),('line','1967'),
                            ('native_id','92'),('vector','0'),('expression',"1'b0")):
            targets=copy.deepcopy(self.targets);targets[0]['point'][field]=value
            with self.assertRaises(ValueError):p.validate_targets(targets)
        for mode in ('missing','reorder','scope','module'):
            targets=copy.deepcopy(self.targets)
            if mode=='missing':targets.pop()
            elif mode=='reorder':targets[0],targets[1]=targets[1],targets[0]
            elif mode=='scope':targets[0]['scope']='foreign'
            else:targets[0]['module_checksum']='foreign'
            with self.assertRaises(ValueError):p.validate_targets(targets)

    def test_real2130check_qualification_no_scope_promotion(self):
        p.qualification(self.qual)
        for key in ('coverage_admitted','whole_ISA_qualified','raw_gain_collected',
                    'native_cycle_qualified','simulation_retried'):
            record=copy.deepcopy(self.qual);record[key]=True
            with self.assertRaises(ValueError):p.qualification(record)

    def test_wrong_checks_traps_UVM_OS_memory_reference_rejected(self):
        for key,value in (('checks',2129),('illegal_traps',2),('UVM_errors',2),('OS_returncode',None),
                          ('OS_returncode',False),('native_known_write_bytes',1031),
                          ('full_memory_bytes',2111),('software_reference_is_Spike',False)):
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

    def test_future736_precise_prefix_then_full_OR(self):
        before=copy.deepcopy(self.before)
        before['tests'].append('/synthetic/formal736/code.vdb')
        before['input_hashes']['/synthetic/formal736/cond.xml']='b'*64
        p.anchor_contract(before,self.before)
        combined,delta=p.union(before,self.single)
        self.assertEqual(len(combined['tests']),737)
        self.assertEqual(combined['tests'][:-1],before['tests'])
        self.assertEqual(sum(delta['metrics'].values()),0)

    def test_anchor_reordered_prefix_design_inherited_pin_and_bit_loss_rejected(self):
        for mode in ('order','design','pin','loss'):
            before=copy.deepcopy(self.before)
            if mode=='order':before['tests'][0],before['tests'][1]=before['tests'][1],before['tests'][0]
            elif mode=='design':before['design']={}
            elif mode=='pin':before['input_hashes'].pop(next(iter(before['input_hashes'])))
            else:
                rows=before['metrics']['line']
                scope=next(s for s,row in rows.items() if int(row['bits'],16))
                rows[scope]['bits']='0x0'
            with self.assertRaises(ValueError):p.anchor_contract(before,self.before)

    def test_qualification_target_readback_not_fresh_gain_assumption(self):
        record=copy.deepcopy(self.qual);record['all_primary_targets_hit']=False
        p.qualification(record)
        record['target_hits_verified']=False
        with self.assertRaises(ValueError):p.qualification(record)

    def test_rejected_backend_or_VRF_activity_and_counter_types_rejected(self):
        good=dict(exceptions=1,rejected_backend_uops=0,rejected_vrf_activities=0,
                  exact_SID_owner_checked=True,rejected_arch_seqs=[3],requests=12,responses=12)
        p.rejected_proof(good)
        for key,value in (('rejected_backend_uops',1),('rejected_vrf_activities',1),('exceptions',0),
                          ('responses',11),('exact_SID_owner_checked',False),('rejected_backend_uops',False)):
            record=copy.deepcopy(good);record[key]=value
            with self.assertRaises(ValueError):p.rejected_proof(record)


if __name__=='__main__':unittest.main()
