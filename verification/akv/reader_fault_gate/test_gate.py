"""Synthetic host checks only; no EDA invocation or accepted-log mutation."""
import copy
import csv
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod)
    return mod


render=load('fault_gate_render_test',HERE/'render.py')
wave=load('fault_gate_profile_test',HERE/'profile.py')
c=load('fault_gate_checker_test',HERE/'check.py')
old_tests=load('fault_gate_old_fixture_test',HERE.parent/'reader_handoff/test_check_reader_handoff_v2.py')
TARGET=0x80004000


def samples():
    fields={s['alias']:0 for s in wave.profile(False)['signals']}
    fields.update(reset_n=1,qbs_active_q=1,shim_ordinal_q=2,shim_target=TARGET,
                  normal_vlsu_idle=1,ar_hold_empty=1,akv_context_ready_q=1,
                  akv_context_q_base_q=0x80001000)
    result=[]; outstanding=0

    def emit(state=0,**kwargs):
        nonlocal outstanding
        r=dict(fields,shim_state_q=state,r_burst_fifo_count_q=outstanding,
               time_100fs=(len(result)+1)*10000)
        if state in (1,2,3,4):
            r.update(up_ar_valid=1,up_ar=TARGET+144,up_ar_addr=TARGET+144,up_ar_len=8,
                     up_ar_size=4,up_ar_burst=1,r_ar_stalled_q=1)
        if state in (3,4,5): r['r_fault_pending_q']=1
        if state==3: r['r_response_drain_q']=1
        r.update(kwargs)
        outstanding+=int(bool(r['up_ar_valid'] and r['up_ar_ready']))
        outstanding-=int(bool(r['up_r_valid'] and r['up_r_ready'] and r['up_r_last']))
        result.append(r)

    def accept(addr,state=0,beats=9):
        emit(state,up_ar_valid=1,up_ar_ready=1,down_ar_valid=1,down_ar_ready=1,
             up_ar=addr,down_ar=addr,up_ar_addr=addr,up_ar_len=beats-1,up_ar_size=4,
             up_ar_burst=1,r_ar_stalled_q=int(state==5))

    def bus_ar(addr,state,beats=9):
        emit(state,bus_ar_valid=1,bus_ar_ready=1,bus_ar=addr,bus_ar_id=0,bus_ar_len=beats-1)

    def beat(index,state,inject=False,total=9):
        payload=0x12340000+index; last=int(index==total-1)
        emit(state,bus_r_valid=1,bus_r_ready=1,bus_r_data=payload,bus_r_last=last)
        emit(state,up_r_valid=1,up_r_ready=1,down_r_valid=1,down_r_ready=1,
             up_r_data=payload,down_r_data=payload,up_r_last=last,down_r_last=last,
             up_r_resp=2 if inject else 0)

    emit()
    # Descriptor + Q8_K activation traffic before the two target weight rows.
    for addr,beats in ((TARGET-4096,1),(TARGET-8192,19)):
        accept(addr,beats=beats)
        bus_ar(addr,0,beats)
        for i in range(beats): beat(i,0,total=beats)
    accept(TARGET)
    bus_ar(TARGET,1)
    emit(1)
    beat(0,2,True)
    for i in range(1,9): beat(i,3)
    for _ in range(6): emit(4)
    accept(TARGET+144,5)
    bus_ar(TARGET+144,5)
    for i in range(9): beat(i,5)
    emit(5,r_fault_valid_o=1,r_fault_ready_i=1,r_fault_kind_o=3,r_fault_vaddr_o=TARGET)
    emit(5,qbs_terminal=1,qbs_fault_valid=1,r_fault_pending_q=0)
    emit(6,qbs_active_q=0,akv_command_fire=1)
    emit(6,qbs_active_q=0,akv_active_q=1)
    emit(6,qbs_active_q=0,akv_active_q=1,akv_terminal=1)
    return result


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old_tests.CorrectCommitWordContract.setUpClass()
        cls.rtl=old_tests.CorrectCommitWordContract.rtl

    def transcript(self):
        text=old_tests.CorrectCommitWordContract().transcript()
        text=text.replace('READER_HANDOFF_','READER_DRAIN_').replace('tval=0 qbs_words','tval=weight_base qbs_words')
        lines=[f'READER_FAULT_TARGET address={TARGET:x} ordinal=2 response=2']
        for line in text.splitlines():
            if line.startswith('[QBS_PERF] ') and 'read_fault=5 ' in line:
                line=line.replace('read_fault=5 ','read_fault=3 ')
                line=re.sub(r'\bar=\d+','ar=4',line)
                line=re.sub(r'\br_beats=\d+','r_beats=38',line)
            lines.append(line)
        return '\n'.join(lines+[c.INJECTOR])

    def test_main_exact_inverse_and_assertions_preserved(self):
        original=render.MAIN.read_text()
        candidate=render.render_main(original)
        self.assertEqual(render.restore_main(candidate),original)
        for anchor in ('rows_checked!=62','words_checked!=192','qbs_commands!=6','akv_commands!=65',
                       'guards(&qo)','rh_trap_epc!=(uintptr_t)rh_qbs_site'):
            self.assertEqual(candidate.count(anchor),original.count(anchor))
        with self.assertRaises(ValueError):
            render.render_main(original.replace('descriptor(access,fault ? 0 : (uintptr_t)weights);',''))

    def test_vlsu_original_cut_not_bypassed(self):
        original=(render.ROOT/'hardware/src/vlsu/vlsu.sv').read_text()
        for shared in (False,True):
            candidate=render.render_vlsu(original,shared)
            self.assertEqual(candidate.count('reader_fault_cut #('),1)
            self.assertIn('.mst_req_o (axi_req_o )',candidate)
            self.assertLess(candidate.index('logic [1:0] rf_owner'),candidate.index(') i_axi_cut ('))
            self.assertGreater(candidate.index('assign rf_owner'),candidate.index('logic qbs_active_d'))
        wrapper=(HERE/'reader_fault_cut.sv').read_text()
        self.assertEqual(wrapper.count('  axi_cut #('),1)
        self.assertNotIn('.Bypass',wrapper)
        self.assertNotRegex(wrapper,r'\b(force|release)\s')
        self.assertIn('slv_req_i.ar_valid && !block_ar',wrapper)
        self.assertIn('cut_resp.ar_ready && !block_ar',wrapper)

    def test_profile_distinguishes_three_interfaces(self):
        for shared in (False,True):
            p=wave.profile(shared)
            paths={r['alias']:r['path'] for r in p['signals']}
            self.assertIn('/i_axi_cut/i_cut/i_reg_ar/',paths['cut_ar_a_full_q'])
            self.assertIn('/i_shared_reader/' if shared else '/i_qbs_engine/',paths['r_ar_stalled_q'])
            self.assertNotEqual(paths['up_ar_valid'],paths['bus_ar_valid'])
            self.assertIn('run 250000ns',wave.script(shared))

    def test_complete_raw_protocol(self):
        result=c.check_log(self.transcript(),self.rtl,TARGET)
        self.assertEqual(result['commands'],71)
        self.assertEqual(result['read_fault'],3)

    def test_raw_mutations(self):
        text=self.transcript()
        for old,new in (('read_fault=3 ','read_fault=5 '),('commit_groups=0 ','commit_groups=4 '),
                        ('READER_FAULT_INJECTOR_PASS','READER_FAULT_INJECTOR_PASS_BOGUS'),
                        ('response=2','response=3'),('tval=weight_base','tval=0'),
                        ('context_read_bytes=292','context_read_bytes=0'),('UVM_ERROR : 0','UVM_ERROR : 1')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                c.check_log(text.replace(old,new,1),self.rtl,TARGET)
        for suffix in ('\nREADER_FAULT_UNKNOWN x=0','\n[AKV_PERF]BOGUS','\n'+c.INJECTOR):
            with self.assertRaises(ValueError): c.check_log(text+suffix,self.rtl,TARGET)

    def test_independent_boundary_ledger(self):
        result=c.check_rows(samples(),TARGET)
        self.assertEqual(result['drained_beats'],18)
        self.assertEqual(result['empty_outstanding_held_ar_samples'],6)
        self.assertEqual(result['cut_held_samples'],0)

    def test_wave_mutations(self):
        rows=samples()
        error=next(i for i,r in enumerate(rows) if r['up_r_resp']==2)
        hold=next(i for i,r in enumerate(rows) if r['shim_state_q']==4)
        admission=next(i for i,r in enumerate(rows) if r['akv_command_fire'])
        for index,key,value in ((error,'r_ar_stalled_q',0),(error,'up_r_resp',0),
                                (error,'up_r_data',99),(error,'up_r_last',1),
                                (error,'down_r_ready',0),(hold,'qbs_active_q',0),
                                (hold,'r_fault_valid_o',1),(hold,'akv_context_q_base_q',0),
                                (error,'r_burst_fifo_count_q',2),(hold,'up_ar_valid',2),
                                (admission,'cut_ar_a_full_q',1),(admission,'akv_context_write_busy',1)):
            bad=copy.deepcopy(rows); bad[index][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): c.check_rows(bad,TARGET)
        with self.assertRaises(ValueError): c.check_rows(rows[:hold]+rows[hold+1:],TARGET)
        with self.assertRaises(ValueError): c.check_rows(rows[:-1],TARGET)
        cut_only=copy.deepcopy(rows)
        for r in cut_only:
            r['r_ar_stalled_q']=0
            r['bus_ar_valid']=1; r['bus_ar_ready']=0
        with self.assertRaises(ValueError): c.check_rows(cut_only,TARGET)

    def test_csv_counter_binding_and_invalid_payload_x(self):
        rows=samples()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cycles.csv'
            with path.open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=rows[0].keys())
                writer.writeheader()
                for row in rows:
                    out={k:str(v) if k=='time_100fs' else f'{v:x}' for k,v in row.items()}
                    if not row['up_r_valid']:
                        for field in ('data','id','last','resp','user'): out['up_r_'+field]='x'
                    writer.writerow(out)
            checked=c.check_log_and_cycles(self.transcript(),self.rtl,path,TARGET)
            self.assertEqual(checked['wave']['reader_ar'],4)
            self.assertEqual(checked['wave']['reader_r_beats'],38)
            with self.assertRaises(ValueError):
                c.check_log_and_cycles(self.transcript().replace('ar=4 ','ar=5 ',1),self.rtl,path,TARGET)

    def test_each_fault_drain_cycle_forbids_data_and_completion(self):
        rows=samples()
        first=next(i for i,r in enumerate(rows) if r['up_r_resp']==2)
        hold=[i for i,r in enumerate(rows) if r['shim_state_q']==4]
        self.assertEqual(len(hold),6)
        self.assertTrue(all(not rows[i]['up_r_valid'] for i in hold))
        admission=next(i for i,r in enumerate(rows) if r['akv_command_fire'])
        for i in range(first+1,admission+1):
            for field in ('r_data_valid_o','r_completion_valid_q'):
                bad=copy.deepcopy(rows); bad[i][field]=1
                with self.subTest(index=i,state=rows[i]['shim_state_q'],field=field),\
                        self.assertRaisesRegex(ValueError,'payload/completion|not drained'):
                    c.check_rows(bad,TARGET)
        bad=copy.deepcopy(rows); bad[first]['r_data_valid_o']=1
        with self.assertRaisesRegex(ValueError,'published payload'):
            c.check_rows(bad,TARGET)
        # Do not reject a previously outstanding completion on the first error
        # cycle solely because this cycle will accept the error response.
        old_completion=copy.deepcopy(rows); old_completion[first]['r_completion_valid_q']=1
        c.check_rows(old_completion,TARGET)


if __name__=='__main__': unittest.main()
