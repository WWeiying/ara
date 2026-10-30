import copy
import csv
from pathlib import Path
import tempfile
import unittest

import check_reader_handoff as c


class HandoffCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rtl=(c.ROOT/'hardware/src/vlsu/vlsu.sv').read_text()

    def transcript(self):
        lines=[c.BEGIN]
        counts={'qbs':0,'akv':0}
        for owner,cmd in c.sequence():
            counts[owner]+=1
            fields=c.schema(self.rtl) if owner=='qbs' else c.PERF_FIELDS
            row=dict.fromkeys(fields,0)
            row.update(seq=counts[owner],busy_cycles=100,success=1)
            if owner=='qbs':
                fault=int(cmd==1)
                row.update(m=1,n=3,success=1-fault,fault=fault,read_fault=5*fault,
                           activation_access=(0,0,0,1,2,3)[cmd],commit_groups=1-fault,
                           useful_pairs=768*(1-fault),weight_bytes=432*(1-fault))
            else:
                row.update(command=cmd,context_ready=int(cmd!=3),v2_full=int(cmd==4),
                           load=int(cmd==2),v2_row_load=int(cmd==2),release=int(cmd==3),
                           q_external_bytes=256 if cmd==4 else 0,kv_external_bytes=768 if cmd==4 else 0,
                           replay_bytes=128 if cmd==2 else 0,read_ranges=9 if cmd==4 else 0)
                if cmd==4:
                    row.update(ar=9,r_beats=68,read_payload_bytes=1088,read_outstanding_max=2)
            lines.append('['+owner.upper()+'_PERF] '+' '.join(f'{key}={row[key]}' for key in fields))
        # Placement of software resident checks is validated separately from
        # actual hardware command order; synthetic data is not a DUT result.
        lines.extend(c.markers()[1:])
        lines += [c.TERMINAL,'UVM_ERROR : 0','UVM_FATAL : 0']
        return '\n'.join(lines)

    def waves(self):
        base=dict.fromkeys([item['alias'] for item in c.profile()['signals']], '0')
        base.update(reset_n='1',normal_vlsu_idle='1',ar_hold_empty='1')
        rows=[]
        for owner,cmd in c.sequence():
            fire=dict(base,**{owner+'_command_fire':'1',owner+'_counters_clear_i':'1'})
            rows.append(fire)
            busy=dict(base,**{owner+'_active_q':'1'})
            if owner=='qbs' and cmd==1:
                busy.update(qbs_fault_valid_o='1',qbs_fault_ready_i='1',qbs_fault_kind_o='5',
                            qbs_fault_pending_q='1',qbs_busy_o='1',qbs_read_busy='1')
            rows.append(busy)
            if owner=='akv' and cmd==4:
                base['akv_context_ready_q']='1'
                base['akv_context_q_base_q']=str(10+len(rows))
            if owner=='qbs' and cmd==3:
                base['activation_context_valid_q']='1'
            if owner=='qbs' and cmd==5:
                base['activation_context_valid_q']='0'
            terminal=dict(base,**{owner+'_active_q':'1',owner+'_terminal':'1'})
            if owner=='qbs' and cmd==1:
                terminal['qbs_fault_valid']='1'
            rows.append(terminal)
        rows.append(dict(base))
        for i,row in enumerate(rows):
            row.update(cycle=str(i),time_100fs=str(i*10000))
        return rows

    def check_wave(self,rows):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cycles.csv'
            with path.open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            return c.check_cycles(path)

    def test_transcript_and_fault_is_not_validation(self):
        text=self.transcript()
        result=c.check_log(text,self.rtl)
        self.assertEqual(result['commands'],71)
        for before,after in (('read_fault=5','read_fault=0'),('read_fault=5','read_fault=3'),('fault=1','fault=0'),
                             ('qbs_words=192','qbs_words=191'),('seq=6 ','seq=7 '),
                             ('external_poison=1','external_poison=0'),(c.TERMINAL,'')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                c.check_log(text.replace(before,after,1),self.rtl)
        with self.assertRaises(ValueError):
            c.check_log(text+'\n'+c.PASS,self.rtl)
        with self.assertRaises(ValueError):
            c.check_log(text+'\n[QBS_PERF]BOGUS',self.rtl)

    def test_full_wave_and_required_control_failures(self):
        rows=self.waves()
        result=self.check_wave(rows)
        self.assertEqual(len(result['fires']),71)
        self.assertGreater(result['resident_samples']['qbs'],0)
        for index,key,value in ((0,'cut_ar_a_full_q','1'),(0,'qbs_burst_fifo_count_q','1'),
                                (0,'akv_context_write_busy','1'),(0,'akv_counters_clear_i','0'),
                                (1,'qbs_active_q','1'),(0,'akv_plan_state_q','x')):
            changed=copy.deepcopy(rows)
            changed[index][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.check_wave(changed)
        with self.assertRaises(ValueError):
            self.check_wave(rows[:-1])

    def test_other_context_changes_are_not_erased_by_loop_order(self):
        rows=self.waves()
        first=next(i for i,row in enumerate(rows) if row['qbs_active_q']=='1')
        for key,value in (('akv_context_q_base_q','ffff'),('akv_context_ready_q','0')):
            for offset in (0,1):
                changed=copy.deepcopy(rows)
                changed[first+offset][key]=value
                with self.subTest(key=key,offset=offset),self.assertRaises(ValueError):
                    self.check_wave(changed)

    def test_owner_lifecycle_missing_samples_reset_and_fault_kind(self):
        rows=self.waves()
        first=next(i for i,row in enumerate(rows) if row['qbs_active_q']=='1')
        changed=copy.deepcopy(rows)
        changed[first].update(qbs_active_q='0',akv_active_q='1')
        with self.assertRaises(ValueError):
            self.check_wave(changed)
        for key,value in (('qbs_active_q','0'),('reset_n','0')):
            changed=copy.deepcopy(rows)
            changed[first][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.check_wave(changed)
        with self.assertRaises(ValueError):
            self.check_wave(rows[:first]+rows[first+1:])
        fault=next(i for i,row in enumerate(rows) if row['qbs_fault_valid_o']=='1')
        for key,value in (('qbs_fault_kind_o','3'),('qbs_fault_vaddr_o','1000'),
                          ('qbs_ar_stalled_q','1'),('qbs_fault_ready_i','0')):
            changed=copy.deepcopy(rows)
            changed[fault][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.check_wave(changed)


if __name__=='__main__':
    unittest.main()
