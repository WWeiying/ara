import copy
import json
from pathlib import Path
import tkinter
import unittest
import run_sv39_rvv_alias770 as r


class RunnerTests(unittest.TestCase):
    def test_single_frozen_image_full_traces(self):
        out=r.OUT/'never-run-alias-test';c=r.command(out)
        self.assertEqual(c[0],str(r.life.IMAGE));self.assertEqual(c.count('+NO_FSDB'),1)
        self.assertIn('line+cond+fsm+tgl+branch',c)
        self.assertIn('+PRELOAD='+str(r.PRE/'input.elf'),c)
        self.assertEqual(c.count('-ucli'),1);self.assertEqual(c.count('-do'),1)
        self.assertIn('+COMMIT_TRACE='+str(out/'commit_trace.csv'),c)
        self.assertIn('+VECTOR_TRACE='+str(out/'vector_trace.csv'),c)
        self.assertEqual(r.BUDGET,600)

    def test_complete_tcl_readonly_profile(self):
        interp=tkinter.Tcl();calls=[]
        def dump(*args):calls.append(args);return '1'
        interp.createcommand('dump',dump);interp.createcommand('show',lambda *args:'')
        interp.createcommand('run',lambda:'');interp.createcommand('exit',lambda *args:self.fail('Tcl failed'))
        interp.eval(r.TCL.read_text())
        adds=[c for c in calls if '-add' in c]
        self.assertEqual(len(adds),11)
        self.assertEqual(len({c[c.index('-add')+1] for c in adds}),11)
        self.assertTrue(all(c[c.index('-depth')+1]=='0' for c in adds))
        self.assertIn('write_pointer_q',' '.join(str(c) for c in adds))
        self.assertFalse(any(word in r.TCL.read_text() for word in ('force ', 'release ', 'stop -')))

    def test_missing_native_object_rejects(self):
        interp=tkinter.Tcl();interp.createcommand('dump',lambda *args:'0')
        interp.createcommand('show',lambda *args:'');interp.createcommand('run',lambda:self.fail('Invalid profile ran'))
        exits=[];interp.createcommand('exit',lambda *args:exits.append(args))
        interp.eval(r.TCL.read_text());self.assertEqual(exits,[('1',)])

    def test_actual_prepare_contract_pins(self):
        out=r.OUT/'never-run-alias-test'
        unused,m=r.prepare(out)
        self.assertEqual(m['timeout_s'],600);self.assertEqual(m['baseline_tests'],770)
        self.assertEqual(m['preflight_seal'],r.PRE_SEAL)
        self.assertEqual(m['pins'][str(r.PRE/'input.elf')],r.ELF_SEAL)
        self.assertFalse(m['coverage_admitted']);self.assertTrue(m['focused_readonly_VPD'])
        self.assertIn('Actual VPD',m['metadata_gate']);self.assertFalse(out.exists())


class TrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=json.loads((r.PRE/'preflight.json').read_bytes());cls.symbols=cls.pre['symbols']
        commits=r.reference.prior.build.parse_spike_commits(r.PRE/'spike.trace')
        cls.rows=[]
        for c in commits:
            if c.pc==cls.symbols['alias_machine_return']:
                cls.rows.append(dict(event='retire',order=str(len(cls.rows)),trap='1',pc=hex(cls.symbols['alias_s_ecall']),
                    insn='0x73',rd='0',rd_wdata='0x0',mem_rmask='0',mem_wmask='0'))
            rd=next(iter(c.gpr_writes),0)
            cls.rows.append(dict(event='retire',order=str(len(cls.rows)),trap='0',pc=hex(c.pc),
                insn=hex(c.instruction),rd=str(rd),rd_wdata=hex(c.gpr_writes.get(rd,0)),mem_rmask='0',mem_wmask='0'))

    def test_exact_actual_reference_handler_sequence(self):
        self.assertEqual(r.trap_contract(self.rows,self.symbols)['supervisor_ecalls'],48)

    def test_extra_exception(self):
        rows=copy.deepcopy(self.rows);rows.append(next(x for x in rows if x['trap']=='1'))
        with self.assertRaises(ValueError):r.trap_contract(rows,self.symbols)

    def test_wrong_ecall_pc(self):
        rows=copy.deepcopy(self.rows);next(x for x in rows if x['trap']=='1')['pc']='0x80000000'
        with self.assertRaises(ValueError):r.trap_contract(rows,self.symbols)

    def test_wrong_cause(self):
        rows=copy.deepcopy(self.rows)
        next(x for x in rows if int(x['pc'],16)==self.symbols['alias_machine_return'])['rd_wdata']='0x8'
        with self.assertRaises(ValueError):r.trap_contract(rows,self.symbols)

    def test_wrong_mepc(self):
        rows=copy.deepcopy(self.rows)
        next(x for x in rows if int(x['insn'],16)>>20==0x341 and int(x['insn'],16)&0x707f==0x2073)['rd_wdata']='0x0'
        with self.assertRaises(ValueError):r.trap_contract(rows,self.symbols)

    def test_missing_handler_return(self):
        rows=[x for x in self.rows if int(x['pc'],16)!=self.symbols['alias_resume']]
        with self.assertRaises(ValueError):r.trap_contract(rows,self.symbols)

    def test_ecall_memory_side_effect(self):
        rows=copy.deepcopy(self.rows);next(x for x in rows if x['trap']=='1')['mem_wmask']='1'
        with self.assertRaises(ValueError):r.trap_contract(rows,self.symbols)


if __name__=='__main__':unittest.main()
