import copy
import json
import unittest

import capture_sldu_two763 as c


class NativeTests(unittest.TestCase):
    def test_bound_actual_owner_and_source(self):
        a,owner,pins=c.bound()
        self.assertEqual(a['targets'],2);self.assertEqual(a['protected'],34)
        self.assertEqual(len(owner['state_writers']),16)
        self.assertEqual(len(owner['descriptor_writers']),3)
        self.assertEqual(owner['slot_induction']['cases'],32)

    def test_free_slot_collision_negative(self):
        with self.assertRaises(ValueError):c.slot_step(0,False,True,False,False,True)
        for owner in (0,1):
            self.assertEqual(c.slot_step(owner,False,True,False,False)['accepted_slot'],1-owner)

    def test_same_cycle_older_commit_cannot_overwrite_owner(self):
        for owner in (0,1):
            self.assertIsNone(c.slot_step(owner,True,True,True,False)['accepted_slot'])
            self.assertEqual(c.slot_step(owner,False,True,True,False)['next_state'],'FIRST_WORD')
            self.assertNotEqual(c.slot_step(owner,False,True,True,True)['next_state'],'FIRST_WORD')

    def test_writer_and_guard_mutations_rejected(self):
        s=c.proof.SOURCE.read_text()
        mutations=[s+'\nstate_d = SLIDE_RUN;',s+'\nvinsn_queue_d.issue_pnt += 1;',
            s.replace('state_q != SLIDE_NP2_COMMIT','state_q == SLIDE_NP2_COMMIT'),
            s.replace('vinsn_queue_q.accept_pnt] = pe_req_i;','vinsn_queue_q.issue_pnt] = pe_req_i;'),
            s.replace('if (vinsn_issue_q.op == VSLIDEDOWN && vinsn_issue_q.use_scalar_op) begin',
                      'if (vinsn_issue_q.use_scalar_op) begin')]
        for text in mutations:
            with self.assertRaises(ValueError):c.owner_contract(text)

    def test_exact_two_shape_and_full_complement(self):
        book=c.life.read_bound(c.proof.BASE/'admission-manifest.json',c.proof.BASE_SHA)
        path=c.proof.BASE/'combined-bits.json';bits=c.life.read_bound(path,book['output_pins'][str(path)])
        design=c.life.IMAGE.with_suffix('.vdb')
        shape=c.native.read_xml(design/'snps/coverage/db/shape/fsm.verilog.shape.xml')
        gs=c.proof.rows(shape,bits)
        self.assertEqual([r['raw_index'] for g in gs for r in g['rows'] if r['target']],[20,32])
        self.assertFalse(any(r['target'] for g in gs if g['mode']=='State' for r in g['rows']))
        self.assertEqual(sum(len(g['rows']) for g in gs),36)
        plan=dict(groups=gs,targets=2,protected=34,strategy='direct-transition-only-66',point_query_authority='saved-native-identity')
        records=c.native.expected_records(plan,c.native.Design(design))
        text=''.join('CHECKSUM: "%s %s"\nINSTANCE: %s\nFsm %s "%s"\nANNOTATION: "%s"\n%s %s "%s"\n'%r for r in records)
        self.assertEqual(c.native.native_records(text),records)
        with self.assertRaises(ValueError):c.native.native_records(text+text)
        token='Transition %s "%s"'%(records[1][7],records[1][8])
        self.assertEqual(text.count(token),1)
        corrupted=text.replace(token,'Transition %s "99->99"'%records[1][7],1)
        self.assertNotEqual(corrupted,text)
        self.assertNotEqual(c.native.native_records(corrupted),records)
        rows=[[stage,g['scope'],g['machine']['name'],g['mode'],r['name'],'0',
               ('NATIVE_EL_AUTHORITY' if r['target'] else 'INHERITED_OBSERVATION')
               if stage in ('applied','reloaded') and (r['target'] or g['mode']=='State') else '0']
              for stage in ('initial','applied','reset','reloaded','final') for g in gs for r in g['rows']]
        c.native.audit_points(rows,plan)
        bad=copy.deepcopy(rows);next(r for r in bad if r[0]=='applied' and r[3]=='Transition' and r[6]=='0')[5]='1'
        with self.assertRaises(ValueError):c.native.audit_points(bad,plan)
        with self.assertRaises(ValueError):c.native.audit_points(rows[:-1],plan)


if __name__=='__main__':unittest.main()
