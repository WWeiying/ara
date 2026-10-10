import copy
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_akv_canonical_kfault as r
import collect_akv_canonical_kfault as c


def sample(**kwargs):
    value = {k:0 for k in r.PROBE_NAMES}
    value.update({'rst_ni':1, 'planner_fault_tag.role':2,
        'mmu_exception_i.cause':0,'mmu_exception_i.tval':0,
        'planner_fault_mmu_exception.cause':0,'planner_fault_mmu_exception.tval':0,
        'fault_mmu_exception_o.cause':0,'fault_mmu_exception_o.tval':0})
    value.update(kwargs)
    return value


def frames():
    result = []
    for a in r.p.ADDRESSES:
        fault = sample(en_ld_st_translation_i=1,plan_state_q=2,mmu_req_o=1,
            mmu_vaddr_o=a,mmu_exception_valid_i=1,planner_fault_event=1,
            planner_fault_kind=2,planner_fault_vaddr=a)
        fault.update({'mmu_exception_i.cause':13,'mmu_exception_i.tval':a,
            'planner_fault_mmu_exception.cause':13,'planner_fault_mmu_exception.tval':a})
        ack = sample(fault_pending_q=1,fault_valid_o=1,fault_ready_i=1,fault_kind_o=2,fault_vaddr_o=a)
        ack.update({'fault_mmu_exception_o.cause':13,'fault_mmu_exception_o.tval':a})
        retry = sample(mmu_req_o=1,mmu_vaddr_o=a,mmu_valid_i=1,physical_check_valid_o=1,
            physical_range_allowed_i=1,axi_ar_valid_o=1,axi_ar_ready_i=1)
        retry['axi_ar_o.addr'] = 0x80044000
        done = sample(burst_fifo_count_q=1,axi_r_valid_i=1,axi_r_ready_o=1)
        done['axi_r_i.last'] = 1
        result.extend([fault,ack,retry,done,sample()])
    return list(enumerate(result))


class TestAKVRuntime(unittest.TestCase):
    def test_real_preflight(self):
        r.preflight_gate(r.life.read_bound(r.PRE,r.PRE_SHA))

    def test_preflight_wrong_address(self):
        pre = r.life.read_bound(r.PRE,r.PRE_SHA); pre['phases'][0]['address'] = '0x40002080'
        with self.assertRaises(Exception): r.preflight_gate(pre)

    def test_no_early_qualification(self):
        pre = r.life.read_bound(r.PRE,r.PRE_SHA); pre['EDA_launched'] = True
        with self.assertRaises(Exception): r.preflight_gate(pre)

    def test_native_gold_all_three_streams(self):
        for i,a in enumerate(r.p.ADDRESSES):
            pages = r.p.pages(0x80040000,i,False); rows = c.outputs(i)
            self.assertEqual(rows[0],[r.p.audit.seed(k) for k in range(512)])
            self.assertEqual(rows[1][128:144],pages[5][16:32])
            off = (a & 4095)//8
            self.assertEqual(rows[2][128:144],pages[4][off:off+16])
            self.assertEqual(rows[3][128:144],pages[4][64:80])

    def test_legacy_owner_bound_to_new_pages(self):
        for i,a in enumerate(r.p.ADDRESSES):
            oracle = c.owner_oracle(i)
            self.assertEqual(oracle['pages'](0x80040000,True,False)[3][4],a)
            self.assertEqual(oracle['outputs']('gap71_akv_fault'),c.outputs(i))

    def test_two_fault_cycle_success(self):
        result = c.cycle_gate(frames())
        self.assertEqual(len(result['faults']),2)
        self.assertEqual(result['accepted_AR'],2)

    def test_wrong_fault_address(self):
        data = frames(); data[0][1]['mmu_exception_i.tval'] ^= 8
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_wrong_owner(self):
        data = frames(); data[0][1]['planner_fault_tag.role'] = 3
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_exception_copy(self):
        data = frames(); data[0][1]['planner_fault_mmu_exception.tval'] ^= 8
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_fault_axi_leak(self):
        data = frames(); data[0][1]['axi_ar_valid_o'] = 1
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_outside_ram(self):
        data = frames(); data[2][1]['axi_ar_o.addr'] = 0x80200000
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_incomplete_wave(self):
        with self.assertRaises(Exception): c.cycle_gate(frames()[:5])

    def test_missing_return(self):
        data = frames(); data[3][1]['axi_r_valid_i'] = 0
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_unknown_active(self):
        data = frames(); data[0][1]['mmu_req_o'] = None
        with self.assertRaises(Exception): c.cycle_gate(data)

    def test_probe_exact_objects(self):
        text = r.PROBE.read_text()
        self.assertIn('set base '+r.SCOPE,text)
        for name in r.PROBE_NAMES: self.assertIn(name,text)
        self.assertNotIn('force ',text.replace('# Exact AKV read-owner profile; no force or source/image changes.',''))
        self.assertIn('132120576',text)

    def test_budget_command(self):
        command = r.command(r.life.OUT/'test-not-created')
        self.assertIn('+PRELOAD='+str(r.ELF),command)
        self.assertIn('+AKV_PERF',command)
        self.assertEqual(r.BUDGET,480)

    def test_terminal_gate(self):
        out = r.life.OUT/'test-not-created'
        manifest = dict(command=r.command(out),elf_sha256='a',image_sha256='b',phase=0)
        started = dict(pid=123,command=r.command(out),budget_s=480,input_elf=str(r.ELF),elf_sha256='a',image_sha256='b')
        status = dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,pid=123)
        c.terminal_gate(status,started,manifest,out)
        for key,value in [('returncode',None),('returncode',False),('timeout',True),('pid',124)]:
            changed = dict(status); changed[key] = value
            with self.assertRaises(Exception): c.terminal_gate(changed,started,manifest,out)

    def test_real_prepare_no_eda(self):
        manifest = r.prepare(r.life.OUT/'akv-canonical-kfault-unit-no-directory')
        self.assertEqual(manifest['old_image_files_checked'],66)
        for module in (r,c,r.p,r.inherited):
            self.assertIn(str(Path(module.__file__).resolve()),manifest['pins'])
        self.assertIn(str(r.PROBE),manifest['pins'])
        self.assertFalse(manifest['coverage_admitted'])

    def test_historical_dedup(self):
        evidence,pins = r.historical_gate()
        self.assertEqual(evidence['old_AKV_K_fault_address'],'0x40002080')
        self.assertEqual(evidence['matched_single_phase_wall_seconds'],347.675922696013)
        self.assertTrue(pins)

    def test_single_phase_wave(self):
        self.assertEqual(len(c.cycle_gate(frames()[:5],addresses=(r.p.ADDRESSES[0],))['faults']),1)
        self.assertEqual(len(c.cycle_gate(frames()[5:],addresses=(r.p.ADDRESSES[1],))['faults']),1)

    def test_wrong_phase(self):
        with self.assertRaises(Exception): r.elf_path(2)
        with self.assertRaises(Exception): c.cycle_gate(frames()[:5],addresses=(r.p.ADDRESSES[1],))

    def test_real_native_eoc_not_spike_tohost(self):
        symbols = r.life.read_bound(r.PRE,r.PRE_SHA)['phases'][0]['dut']['symbols']
        rows = []
        def row(pc,addr=0,value=0,mask=0,trap=0,insn=0):
            rows.append(dict(event='retire',order=str(len(rows)),cycle=str(len(rows)+1),
                pc=format(pc,'016x'),mem_addr=format(addr,'016x'),mem_wdata=format(value,'016x'),
                mem_wmask=format(mask,'02x'),trap=str(trap),insn=format(insn,'08x')))
        row(0,symbols['akvc0_records'],0,255)
        row(symbols['akvc0_s_begin'])
        for j,(cause,pc,tval) in enumerate(((13,symbols['akvc0_site'],r.p.ADDRESSES[0]),(9,symbols['akvc0_s_exit'],0))):
            values=[cause,pc,tval,0x6e00,(8<<60)|(0x71<<44)|(symbols['akvc0_pages']>>12),16,24,0,5,0,j+1,1]
            for k,value in enumerate(values): row(symbols['akvc0_handler_entry']+32,symbols['akvc0_records']+j*96+k*8,value,255)
        row(symbols['akvc0_s_exit'],trap=1,insn=0x73)
        row(symbols['akvc0_restore_end'])
        row(symbols['_eoc']+8,0xd0000000,0,255)
        row(symbols['_eoc']+12)
        self.assertEqual(c.native_contract(rows,symbols)['traps'],2)
        rows[-2]['mem_wdata']='0000000000000001'
        with self.assertRaises(Exception): c.native_contract(rows,symbols)


if __name__ == '__main__': unittest.main()
