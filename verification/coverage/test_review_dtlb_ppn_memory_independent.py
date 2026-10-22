"""Independent read-only review; no simulator/Spike execution or production edits."""
import copy
from types import SimpleNamespace
import unittest
import collect_dtlb_ppn_swap1200 as c


def rtl_expanded(word):
    # Exact concatenations in frozen CVA6 compressed_decoder.sv.
    def part(hi,lo): return (word>>lo)&((1<<(hi-lo+1))-1)
    def cat(*fields):
        value=0
        for width,bits in fields: value=(value<<width)|bits
        return value
    quadrant,funct=word&3,word>>13
    if quadrant==0:
        if funct==2: return cat((5,0),(1,part(5,5)),(3,part(12,10)),(1,part(6,6)),(2,0),(2,1),(3,part(9,7)),(3,2),(2,1),(3,part(4,2)),(7,3))
        if funct==3: return cat((4,0),(2,part(6,5)),(3,part(12,10)),(3,0),(2,1),(3,part(9,7)),(3,3),(2,1),(3,part(4,2)),(7,3))
        if funct==6: return cat((5,0),(1,part(5,5)),(1,part(12,12)),(2,1),(3,part(4,2)),(2,1),(3,part(9,7)),(3,2),(2,part(11,10)),(1,part(6,6)),(2,0),(7,35))
        if funct==7: return cat((4,0),(2,part(6,5)),(1,part(12,12)),(2,1),(3,part(4,2)),(2,1),(3,part(9,7)),(3,3),(2,part(11,10)),(3,0),(7,35))
    if quadrant==2:
        if funct in (2,3) and part(11,7)==0: raise ValueError('Reserved rd=x0')
        if funct==2: return cat((4,0),(2,part(3,2)),(1,part(12,12)),(3,part(6,4)),(2,0),(5,2),(3,2),(5,part(11,7)),(7,3))
        if funct==3: return cat((3,0),(3,part(4,2)),(1,part(12,12)),(2,part(6,5)),(3,0),(5,2),(3,3),(5,part(11,7)),(7,3))
        if funct==6: return cat((4,0),(2,part(8,7)),(1,part(12,12)),(5,part(6,2)),(5,2),(3,2),(3,part(11,9)),(2,0),(7,35))
        if funct==7: return cat((3,0),(3,part(9,7)),(1,part(12,12)),(5,part(6,2)),(5,2),(3,3),(2,part(11,10)),(3,0),(7,35))
    return None


def reference_rows(commits):
    rows=[]; prefix=[]
    for commit in commits:
        if not prefix and commit.pc!=0x80000000: continue
        prefix.append(commit)
        if commit.memory_accesses==((0x80001000,1),): break
    for order,commit in enumerate(prefix):
        word=commit.instruction; expanded=rtl_expanded(word) if word&3!=3 else word
        rd=next((r for r in commit.gpr_writes if r),0); rm=wm=value=address=0
        if commit.memory_accesses:
            if expanded is None or expanded&127 not in (3,35): raise ValueError('Unknown fixture memory opcode')
            funct=expanded>>12&7; size={0:1,1:2,2:4,3:8,4:1,5:2,6:4}[funct]
            address,data=commit.memory_accesses[0]; mask=((1<<size)-1)<<(address&7)
            if expanded&127==3: rm=mask
            else: wm=mask; value=data
        rows.append(dict(event='retire',order=str(order),trap='0',pc=f'{commit.pc:016x}',insn=f'{word:08x}',
            rd=str(rd),rd_wdata=f'{commit.gpr_writes.get(rd,0):016x}',mem_addr=f'{address:016x}',
            mem_rmask=f'{rm:02x}',mem_wmask=f'{wm:02x}',mem_wdata=f'{value:016x}'))
    return rows


class DecodeReview(unittest.TestCase):
    def test_all16256_legal_integer_compressed_encodings(self):
        count=0
        for word in range(65536):
            try: expected=rtl_expanded(word)
            except ValueError:
                with self.assertRaises(ValueError): c.rv64c.decode(word)
                continue
            if expected is not None:
                self.assertEqual(c.rv64c.decode(word)['expanded'],expected); count+=1
        self.assertEqual(count,16256)


class MemoryReview(unittest.TestCase):
    def fixture(self):
        def commit(pc,word,gpr=None,memory=()):
            return SimpleNamespace(pc=pc,instruction=word,gpr_writes=gpr or {},memory_accesses=memory)
        # LW x6,4(x6) must use pre-load x6; SB uses low unshifted data at byte6.
        commits=[commit(0x80000000,0x80000337,{6:0x80000000}),
            commit(0x80000004,0x00432303,{6:0x1234},((0x80000004,None),)),
            commit(0x80000008,0x800002b7,{5:0x80000000}),
            commit(0x8000000c,0x03400393,{7:0x34}),
            commit(0x80000010,(7<<20)|(5<<15)|(6<<7)|0x23,memory=((0x80000006,0x34),)),
            commit(0x80000014,0x800012b7,{5:0x80001000}),
            commit(0x80000018,0x00100393,{7:1}),
            commit(0x8000001c,(7<<20)|(5<<15)|(3<<12)|0x23,memory=((0x80001000,1),))]
        return commits,reference_rows(commits)

    def test_prior_base_load_destination_and_unshifted_subword_store(self):
        commits,rows=self.fixture(); result=c.memory_gate(rows,commits)
        self.assertEqual((result['loads'],result['stores'],result['total']),(1,2,3))

    def test_lane_shifted_store_wrong_mask_or_prior_base_rejected(self):
        for index,key,value in [(4,'mem_wdata','0034000000000000'),(4,'mem_wmask','01'),
                               (1,'mem_addr','0000000000001238'),(3,'rd_wdata','0000000000000035')]:
            commits,rows=self.fixture(); rows[index][key]=value
            with self.assertRaises(ValueError,msg=key): c.memory_gate(rows,commits)

    def test_extra_unknown_memory_and_missing_retirement_rejected(self):
        commits,rows=self.fixture(); rows[0]['mem_wmask']='01'
        with self.assertRaises(ValueError): c.memory_gate(rows,commits)
        with self.assertRaises(ValueError): c.memory_gate(rows[:-1],commits)

    def test_full_existing_reference19071_memory_no_Spike_launch(self):
        q=c.life.read_bound(c.runner.PRE,c.runner.PRE_SHA)
        commits=c.spike_trace.parse_spike_commits(c.runner.PRE.parent/'spike.trace')
        result=c.memory_gate(reference_rows(commits),commits)
        self.assertEqual((result['retired'],result['compressed'],result['uncompressed'],result['loads'],result['stores'],result['total']),
                         (191475,16823,2248,8553,10518,19071))
        self.assertEqual(result['skipped'],0)


if __name__=='__main__': unittest.main()
