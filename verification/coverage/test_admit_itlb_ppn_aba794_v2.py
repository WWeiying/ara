import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_itlb_ppn_aba794_v2 as a


class ActualQualifiedAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=a.life.read_bound(a.QUAL/'qualification.json',a.Q_SHA)
        def doc(name):return a.life.read_bound(a.QUAL/name,cls.q['output_pins'][str(a.QUAL/name)])
        cls.wave,cls.native=doc('itlb-axi-observations.json'),doc('native-oracle.json')
        b=a.life.read_bound(a.old.BASE/'admission-manifest.json',a.old.BASE_SHA)
        p=a.old.BASE/'combined-toggle-bits.json';cls.before=a.life.read_bound(p,b['output_pins'][str(p)])
        record=a.life.read_bound(a.old.PREPARED,a.old.PREPARED_SHA)
        p=Path(record['output'])/'code.vdb/snps/coverage/db/testdata'/a.old.runner.CASE/'tgl.verilog.data.xml'
        cls.single,h=a.old.toggle.rows(p,list(cls.before))
        if h!=cls.q['input_pins'][str(p)]:raise ValueError('Actual native sample not qualified')

    def test_actual_parent_qualification_and_full48owners(self):
        a.qualification_gate(self.q,a.QUAL)
        result=a.owners(self.wave,self.native)
        self.assertEqual(len(result['accepted_records']),48)
        self.assertTrue(result['entry_indices_observed_not_inferred'])
        self.assertEqual(result['actual_slots'],16)

    def test_PTE_actual_owner_time_VPN_slot_foreign_rejected(self):
        for key in ('time_100fs','phase','asid','vpn','entry'):
            wave=copy.deepcopy(self.wave);wave['updates'][0][key]^=1
            with self.assertRaises(ValueError):a.owners(wave,self.native)

    def test_wrong_PPN_flags_or_lookup_PC_rejected(self):
        for key in ('pte','ppn'):
            wave=copy.deepcopy(self.wave);wave['accepted_full_PTEs'][16][key]^=1
            with self.assertRaises(ValueError):a.owners(wave,self.native)
        wave=copy.deepcopy(self.wave);wave['updates'][0]['lookup_vaddr']='0x80055040'
        with self.assertRaises(ValueError):a.owners(wave,self.native)

    def test_missing_duplicate_or_reversed_native_observation(self):
        for kind in ('missing','duplicate','reverse'):
            wave=copy.deepcopy(self.wave)
            if kind=='missing':wave['updates'].pop()
            elif kind=='duplicate':wave['updates'][1]=dict(wave['updates'][0])
            else:wave['updates'].reverse()
            with self.assertRaises(ValueError):a.owners(wave,self.native)

    def test_wrong_retired_thunk_PC_or_phase_rejected(self):
        for key,value in [('ecall_pc','0x80055048'),('phase',2),('entry',15)]:
            native=copy.deepcopy(self.native);native['traps'][0][key]=value
            with self.assertRaises(ValueError):a.owners(self.wave,native)

    def test_actual_full2989_OR_and_fresh793_gain(self):
        after,gain=a.rebase(self.before,self.single)
        self.assertEqual(len(after),2989)
        self.assertEqual(gain['full_OR_Toggle_instances'],2989)
        self.assertEqual(gain['baseline'],793)
        self.assertEqual(gain['new_positions'],496)
        self.assertFalse(gain['direction_order_calibrated'])
        self.assertFalse(gain['official_percentage'])

    def test_nonITLB_wrong_OR_still_rejected(self):
        after=a.old.toggle.union(self.before,self.single)
        scope=next(s for s in after if s!=a.old.case.SCOPE and self.before[s]['width'])
        after[scope]['bits']=hex(int(after[scope]['bits'],16)^1)
        with self.assertRaises(ValueError):a.all_toggle_or(self.before,self.single,after)

    def test_missing_foreign_scope_identity_or_overflow(self):
        after=a.old.toggle.union(self.before,self.single)
        scope=next(s for s in after if s!=a.old.case.SCOPE)
        for kind in ('missing','foreign','width','checksum','overflow'):
            bad=copy.deepcopy(after)
            if kind=='missing':del bad[scope]
            elif kind=='foreign':bad['foreign']=bad.pop(scope)
            elif kind=='width':bad[scope]['width']+=1
            elif kind=='checksum':bad[scope]['checksum']='foreign'
            else:bad[scope]['bits']=hex(1<<bad[scope]['width'])
            with self.assertRaises(ValueError):a.all_toggle_or(self.before,self.single,bad)

    def test_wrong_parent_seal_or_path_rejected_before_evaluation(self):
        with patch.object(a.old,'evaluate',side_effect=AssertionError('must not execute')):
            for path,seal in ((a.QUAL,'0'*64),(a.QUAL.with_name('foreign'),a.Q_SHA)):
                with self.assertRaises(ValueError):a.evaluate(path,seal)

    def test_missing_console_receipt_or_wrong_successor_pin_rejected(self):
        for kind in ('receipt','source','preserved'):
            q=copy.deepcopy(self.q)
            if kind=='receipt':del q['output_pins'][str(a.QUAL/'console-csr-contract.json')]
            elif kind=='source':q['input_pins'][str(Path(a.old.case.__file__).with_name('collect_itlb_ppn_aba_v2.py'))]='0'*64
            else:q['original_failure_preserved']=False
            with self.assertRaises(ValueError):a.qualification_gate(q,a.QUAL)


if __name__=='__main__':unittest.main()
