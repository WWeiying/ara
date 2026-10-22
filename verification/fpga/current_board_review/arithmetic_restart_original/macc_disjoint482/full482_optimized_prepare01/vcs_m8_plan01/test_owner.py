"""Constructed protocol rows using actual full482 model and compiled helper PCs."""
from copy import deepcopy
import csv
import io
import unittest
import checker as c


def ledger(spec,gold):
    result=[]
    for call,row in enumerate(gold['rows']):
        for i,r in enumerate(spec['routine']):
            if not c.transport.transport.vector(r['insn']):continue
            kind='memory' if i in (1,2,3,4,11) else 'target' if i==8 else 'configuration'
            result.append(dict(insn=r['insn'],pc=r['pc'],retire_order=call*13+i,
                call=call,helper_index=i,kind=kind,
                required=kind=='memory' or kind=='target' and row['vstart']<row['vl']))
    return result


def transport_rows(entries,drop=None,surplus=None,replay=False):
    rows=[];retire=0;order=0
    def emit(event,item,arch=None):
        rows.append(dict(cycle=str(len(rows)+1),event=event,
            order=str(retire if event=='retire' else order if arch is None else arch),
            port='0',trans_id='0',pc=f'{item["pc"]:016x}',insn=f'{item["insn"]:08x}',
            rd='0',rd_wdata='0000000000000000',mem_addr='0000000000000000',
            mem_rmask='00',mem_wmask='00',mem_wdata='0000000000000000',trap='0'))
    for index,item in enumerate(entries):
        for event in ('cvx_req','cvx_resp','arch_start'):emit(event,item)
        if item['required'] and index!=drop:
            for event in ('uop_alloc','uop_done'):emit(event,item)
        if index==surplus:
            for event in ('uop_alloc','uop_done'):emit(event,item)
        emit('retire',item);retire+=1;order+=1
        if replay and index==next(j for j,x in enumerate(entries) if x['helper_index']==9):
            for event in ('cvx_req','cvx_resp','arch_start'):emit(event,item)
            order+=1
    return rows


def run(rows,entries,gold):
    protocol=c.module('macc482_host_trace',c.G.parents[1]/'ara_verify/trace.py')
    observer=c.OwnerObserver(protocol)
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=c.transport.transport.FIELDS)
    writer.writeheader();writer.writerows(rows);stream.seek(0)
    for _ in observer.rows(csv.DictReader(stream)):pass
    summary=observer.finish();c.protocol_presence(summary)
    return observer.owner_coverage(entries,gold),summary


class Owners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=c.specification();cls.gold=c.read(c.REF/'model.json')
        cls.entries=ledger(cls.spec,cls.gold)

    def test_actual_scope_dynamic_counts(self):
        d,_=run(transport_rows(self.entries),self.entries,self.gold)
        self.assertEqual((d['compulsory_memory_owners'],d['required_target_owners'],
            d['elidable_target_owners'],d['minimum_required_owners']),(2410,182,300,2592))
        self.assertEqual(d['required_alloff_target_owners'],45)

    def test_missing_memory_owner_with_constant_total_surplus(self):
        memory=[i for i,r in enumerate(self.entries) if r['kind']=='memory']
        rows=transport_rows(self.entries,drop=memory[5],surplus=memory[0])
        self.assertEqual(sum(r['event']=='uop_alloc' for r in rows),2592)
        with self.assertRaisesRegex(ValueError,'Missing necessary architectural owner'):
            run(rows,self.entries,self.gold)

    def test_alloff_target_still_required(self):
        index=next(i for i,r in enumerate(self.entries) if r['kind']=='target' and r['required'] and
            not any(self.gold['masks'][self.gold['rows'][r['call']]['mode']]))
        with self.assertRaisesRegex(ValueError,'Missing necessary architectural owner'):
            run(transport_rows(self.entries,drop=index),self.entries,self.gold)

    def test_harmless_csr_replay_not_credited(self):
        d,g=run(transport_rows(self.entries,replay=True),self.entries,self.gold)
        self.assertEqual(len(d['harmless_configuration_replay_arch_orders']),1)
        self.assertEqual(g['cvx_replay_count'],1)
        self.assertEqual(d['minimum_required_owners'],2592)

    def test_memory_replay_rejected(self):
        rows=transport_rows(self.entries)
        index=next(i for i,r in enumerate(rows) if r['event']=='arch_start' and
            int(r['insn'],16)==self.spec['routine'][1]['insn'])
        rows[index]['insn']=f'{self.spec["routine"][2]["insn"]:08x}'
        with self.assertRaises((AssertionError,ValueError)):run(rows,self.entries,self.gold)

    def test_required_owner_done_missing(self):
        rows=transport_rows(self.entries)
        rows.pop(next(i for i,r in enumerate(rows) if r['event']=='uop_done'))
        for i,r in enumerate(rows):r['cycle']=str(i+1)
        with self.assertRaises((AssertionError,ValueError)):run(rows,self.entries,self.gold)

    def test_all_unused_helper_pcs_forbidden(self):
        for n in range(1,8):
            dis=(c.REF/'soc/program.dis').read_text()
            self.assertTrue(set(r['pc'] for r in c.instructions(dis,'op_'+str(n))).issubset(
                set(self.spec['forbidden_pcs'])))


if __name__=='__main__':unittest.main()
