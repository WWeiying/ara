"""One genuine-source helper owner combination; no full stream or CSV."""
from copy import copy
import sys
import unittest
import checker as c
import replay as r
from host_records import Builder
class SlideDownOwnerBoundary(unittest.TestCase):
    def test_actual_source_vl1_slidedown_owner_cannot_be_deleted(self):
        c.common.image_context(r.IMAGE);protocol=sys.modules['ara_verify.trace'];spec=c.specification()
        gold=next(g for g in c.model() if (g['op'],g['vl'],g['mode'],g['vstart'])==(20,1,0,0))
        ledger=[];rows=[];builder=Builder(spec);arch=0
        for j,item in enumerate(spec['backend']['helpers']['op_20']):
            row=builder.row(item['pc']);insn=item['insn']
            if c.mature.transport.transport.vector(insn):
                kind='memory' if j in (1,2,3,4,11) else 'target' if j==8 else 'configuration'
                required=kind=='memory' or kind=='target' and c.target_required(insn,gold)
                event=dict(row,order=str(arch),port='-1',trans_id='0')
                rows.extend([dict(event,event='cvx_req'),dict(event,event='arch_start')])
                if required:rows.extend([dict(event,event='uop_alloc',port='0'),dict(event,event='uop_done',port='0')])
                rows.append(dict(event,event='cvx_resp'))
                ledger.append(dict(insn=insn,pc=item['pc'],retire_order=int(row['order']),call=0,
                    helper_index=j,kind=kind,required=required));arch+=1
            rows.append(row)
        class Reader:
            fieldnames=c.mature.transport.transport.FIELDS
            def __iter__(self):return iter(rows)
        observer=c.OwnerObserver(protocol)
        for row in observer.rows(Reader()):pass
        observer.finish()
        fixture=dict(rows=[gold],masks=[gold['mask']]*3)
        coverage=observer.owner_coverage(ledger,fixture)
        target=next(x for x in coverage['owner_ledger'] if x['kind']=='target')
        self.assertEqual(target['insn'],0x3c813c57);self.assertTrue(target['required'])
        self.assertEqual(coverage['required_target_owners'],1)
        changed=copy(observer);changed.owner_alloc=observer.owner_alloc.copy();changed.owner_done=observer.owner_done.copy()
        seq=target['arch_order'];changed.owner_alloc[seq]=changed.owner_done[seq]=0
        with self.assertRaisesRegex(ValueError,'necessary architectural owner'):changed.owner_coverage(ledger,fixture)
        self.assertGreater(observer.owner_alloc[seq],0)
if __name__=='__main__':unittest.main(verbosity=2)
