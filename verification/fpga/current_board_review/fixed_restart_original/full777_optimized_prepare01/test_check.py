#!/usr/bin/env python3
"""Synthetic negative coverage only; never substitutes for RVFI DUT evidence."""
import json
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
import check as c


def prime():
    o=c.Observer('soc'); o.n=776
    row=o.calls[o.n]
    o.reg[10:18]=[o.sym['a'],o.sym['b'],o.sym['out']+1,row['vl'],512,o.sym['mask'],row['vstart'],row['control']]
    o.known.update(range(10,18))
    o.init_seen=set(range(514)); o.input_store_count=1472
    for name in ('a','b','mask'): o.shadow[name][:]=bytes.fromhex(row[name+'_hex'])
    o.shadow['out'][:]=bytes([0x5b])*514
    return o


def entry(o):
    h=o.helper[0]; o.feed(h['pc'],h['insn'],5,512)


def memory_row(address, width, write=None):
    be=((1<<width)-1)<<(address%8)
    return dict(mem_addr=f'{address:x}',mem_rmask=f'{be if write is None else 0:x}',
                mem_wmask=f'{be if write is not None else 0:x}',mem_wdata=f'{write or 0:x}')


class Tests(unittest.TestCase):
    def test_good_helper_entry(self): entry(prime())

    def test_unknown_zero_cannot_be_used(self):
        o=prime(); o.known.remove(17)
        with self.assertRaisesRegex(AssertionError,'Unknown'): entry(o)

    def test_setup_missing_and_wrong_inputs(self):
        for name in ('a','b','mask'):
            o=prime();o.shadow[name][-1]^=1
            with self.subTest(name=name), self.assertRaises(AssertionError):entry(o)
        for mutate in (lambda o:o.init_seen.remove(513),lambda o:setattr(o,'input_store_count',1471),
                       lambda o:setattr(o,'n',768)):
            o=prime();mutate(o)
            with self.assertRaises(AssertionError):entry(o)

    def test_helper_context_or_middle(self):
        for r in range(10,18):
            o=prime();o.reg[r]^=1
            with self.subTest(register=r), self.assertRaises(AssertionError):entry(o)
        o=prime();h=o.helper[14]
        with self.assertRaises(AssertionError):o.feed(h['pc'],h['insn'],0,0)

    def test_unused_internal_pc(self):
        o=prime(); pc=o.sym['op_2']+4
        pc=next(k for k in o.code if pc<=k<o.sym['op_3'])
        with self.assertRaises(AssertionError):o.feed(pc,o.code[pc][0],0,0)

    def test_actual_rvfi_store(self):
        for bad in (None,'mem_addr','mem_wmask','mem_wdata','unknown_source'):
            o=c.Observer('soc'); pc=next(i['pc'] for i in o.identity['full_init'] if i['asm'].startswith('sd\t'))
            o.reg[15]=o.sym['out'];o.reg[12]=0x5b5b5b5b5b5b5b5b;o.known.update((12,15))
            row=memory_row(o.sym['out'],8,o.reg[12])
            if bad=='unknown_source':o.known.remove(12)
            elif bad:row[bad]=f'{int(row[bad],16)^1:x}'
            if bad:
                with self.subTest(bad=bad), self.assertRaises(AssertionError):o.feed(pc,o.code[pc][0],0,0,row)
            else:
                o.feed(pc,o.code[pc][0],0,0,row)
                self.assertEqual(o.rvfi_checks,1)

    def test_actual_oracle_rvfi_data_and_coverage(self):
        for bad in (None,'data','address','be','missing_read','wrong_rd','unknown_base'):
            o=prime();o.in_oracle=True;o.pending=True
            pc=next(i['pc'] for i in o.identity['full_oracle'] if i['asm'].strip()=='ld\ta1,0(a1)')
            o.reg[11]=o.sym['out'];o.known.add(11)
            value=int.from_bytes(bytes.fromhex(o.calls[o.n]['expected_hex'])[:8],'little')
            row=memory_row(o.sym['out'],8);rd=11
            if bad=='data':value^=1
            if bad=='address':row['mem_addr']=f'{o.sym["out"]+8:x}'
            if bad=='be':row['mem_rmask']='fe'
            if bad=='missing_read':o.reads=1
            if bad=='wrong_rd':rd=12
            if bad=='unknown_base':o.known.remove(11)
            if bad:
                with self.subTest(bad=bad),self.assertRaises(AssertionError):o.feed(pc,o.code[pc][0],rd,value,row)
            else:o.feed(pc,o.code[pc][0],rd,value,row);self.assertEqual(o.reads,1)

    def test_csr_helper_negative(self):
        for index in (5,7,11,13,15,16,19,20):
            o=prime();o.in_helper=True;o.hindex=index;o.saved=[2,1]
            o.reg[7]=o.calls[o.n]['vxrm'] if index==11 else o.calls[o.n]['initial_vxsat']
            o.reg[29]=2;o.reg[30]=1;o.known.update((7,29,30))
            h=o.helper[index];rd=0;value=0
            if index==5:rd,value=5,511
            elif index==7:o.reg[16]^=1
            elif index in (11,13):o.reg[7]^=1
            elif index==15:rd,value=10,1
            elif index==16:rd,value=6,1
            elif index==19:o.reg[29]^=1
            elif index==20:o.reg[30]^=1
            with self.subTest(index=index),self.assertRaises(AssertionError):o.feed(h['pc'],h['insn'],rd,value)

    def test_lifecycle_missing_or_wrong_owner(self):
        def row(event,order=0,vid=0,trans=1,insn='9c880c57'):
            return dict(event=event,order=str(order),port=str(vid),trans_id=str(trans),insn=insn,trap='0')
        for bad in ('done_without_alloc','wrong_owner','request_changed','unknown_event','exception','missing_all'):
            x=c.Lifecycle()
            with self.subTest(bad=bad),self.assertRaises(AssertionError):
                if bad=='done_without_alloc':x.row(row('uop_done'))
                elif bad=='missing_all':x.finish()
                elif bad=='unknown_event':x.row(row('alien'))
                elif bad=='exception':x.row(dict(row('arch_start'),trap='1'))
                else:
                    x.row(row('arch_start'))
                    if bad=='wrong_owner':x.row(row('uop_alloc',trans=2))
                    else:x.row(row('cvx_req',insn='02000407'))

    def test_missing_complete_pair_despite_aggregate_surplus(self):
        x=c.Lifecycle()
        x.arch=[0x02000407]*(777*5);x.requests=x.arch[:];x.retired=x.arch[:]
        x.responses=len(x.arch);x.allocations=x.done=len(x.arch)+20
        x.allocated_owners=set(range(len(x.arch)))-{100}
        with self.assertRaisesRegex(AssertionError,'backend owner'):x.finish()
        x.allocated_owners.add(100)
        self.assertEqual(x.finish()['required_memory_owners'],3885)


if __name__=='__main__':
    unittest.main(verbosity=2)
