import copy
import unittest
from unittest.mock import patch
import collect_itlb_asid_exec as collect


def trap_rows():
    rows=[];symbols=dict(itm_handler=0x80002000,itm_resume=0x80003000)
    for p in range(3):
        for e in range(16):
            pc=collect.pre.address(p,e)+8
            for addr,insn,trap,value in ((pc,0x73,1,0),(symbols['itm_handler'],0x342022f3,0,9),
                (symbols['itm_handler']+16,0x341022f3,0,pc),(symbols['itm_resume']-4,0x30200073,0,0),
                (symbols['itm_resume'],0x30059073,0,0)):
                rows.append(dict(event='retire',order=str(len(rows)),pc=hex(addr),insn=hex(insn),trap=str(trap),
                    rd='0' if trap else '5',rd_wdata=hex(value),mem_rmask='0',mem_wmask='0'))
    return rows,symbols


class Collector(unittest.TestCase):
    def test_exact_pc_trap_return(self):
        rows,s=trap_rows();self.assertEqual(len(collect.trap_contract(rows,s)),48)

    def test_wrong_virtual_ecall_pc(self):
        rows,s=trap_rows();rows[0]['pc']=hex(collect.pre.address(0,0))
        with self.assertRaisesRegex(ValueError,'Exact ECALL'):collect.trap_contract(rows,s)

    def test_wrong_cause(self):
        rows,s=trap_rows();rows[1]['rd_wdata']='2'
        with self.assertRaisesRegex(ValueError,'cause9'):collect.trap_contract(rows,s)

    def test_missing_or_extra_trap(self):
        rows,s=trap_rows();rows[0]['trap']='0'
        with self.assertRaisesRegex(ValueError,'Exactly48'):collect.trap_contract(rows,s)

    def test_trap_memory_effect_rejected(self):
        rows,s=trap_rows();rows[0]['mem_wmask']='ff'
        with self.assertRaisesRegex(ValueError,'no effect'):collect.trap_contract(rows,s)

    def test_retirement_gap_rejected(self):
        rows,s=trap_rows();rows[-1]['order']='99999'
        with self.assertRaisesRegex(ValueError,'contiguous'):collect.trap_contract(rows,s)

    def test_scalar_no_unknown_skip(self):
        counts=dict(matched_instructions=1,matched_scalar_writes=0,matched_floating_writes=0,matched_scalar_memory_accesses=1)
        r=dict(counts,status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',rvfi_store_data_layout='unshifted',
            skipped_unobservable_register_values=0,stopped_at_unobservable=None,aligned_vector_faults=[],
            ara_trap_events=48,mismatch=None,terminal_ecall=None,vector_state_compared=False,
            ara_retired_instructions=49,ara_committed_instructions=1,
            terminal_tohost=dict(address='0x0000000080001000',write_value='0x1'))
        collect.exact_scalar(r,counts);r['skipped_unobservable_register_values']=1
        with self.assertRaisesRegex(ValueError,'skipped'):collect.exact_scalar(r,counts)

    def test_waveform_requires_real_slot_visits(self):
        pre=collect.pre;names=['ara_tb.clk','ara_tb.rst_n']+[pre.SCOPE+'.'+n for n in (
            'update_i.valid','update_i.asid','update_i.vpn','replace_en','lu_hit_o','lu_access_i','lu_asid_i',
            'lu_vaddr_i','plru_tree_q','flush_i','s_st_enbl_i')]
        widths=[1,1,1,16,27,16,1,1,16,64,30,1,1]
        for ch in ('ar','aw','w','r','b'):
            names.extend([collect.CORE+'.'+p+'.'+ch+suffix for p,suffix in (
                ('noc_req_o' if ch in ('ar','aw','w') else 'noc_resp_i','_valid'),
                ('noc_resp_i' if ch in ('ar','aw','w') else 'noc_req_o','_ready'))]);widths.extend([1,1])
        decl={n:dict(width=w,code=n) for n,w in zip(names,widths)}
        def rows(bad):
            yield 'declarations',decl
            for p in range(3):
                for e in range(16):
                    before={n:'0' for n in names};before['ara_tb.rst_n']='1'
                    values={'update_i.valid':1,'update_i.asid':[0x5555,0xaaaa,0x5555][p],
                        'update_i.vpn':pre.shared.vpn(p,e),'replace_en':1<<(0 if bad else e),
                        'plru_tree_q':e,'lu_vaddr_i':pre.address(p,e)}
                    for n,v in values.items():before[pre.SCOPE+'.'+n]=bin(v)[2:]
                    after=dict(before,**{'ara_tb.clk':'1'})
                    yield (p*16+e)*4,before,after
                    before=dict(before);before[pre.SCOPE+'.update_i.valid']='0'
                    for n,v in {'lu_hit_o':1,'lu_access_i':1,'s_st_enbl_i':1,'lu_asid_i':[0x5555,0xaaaa,0x5555][p]}.items():
                        before[pre.SCOPE+'.'+n]=bin(v)[2:]
                    yield (p*16+e)*4+2,before,dict(before,**{'ara_tb.clk':'1'})
        with patch.object(collect,'FunctionType',return_value=lambda path:rows(False)):
            result=collect.waveform(None);self.assertEqual(result['entry_visits'],[list(range(16))]*3)
        with patch.object(collect,'FunctionType',return_value=lambda path:rows(True)):
            with self.assertRaisesRegex(ValueError,'all16 slots'):collect.waveform(None)


if __name__=='__main__':unittest.main()
