import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import collect_scalar_slot_rotation792 as c
import run_scalar_slot_rotation792 as r


def allocation_fixture():
    s={}; edges=[]; cycle=0
    for i,k in enumerate(r.oracle.SLOTS):
        start=0x80003000+i*128; s['slot_landing'+str(i)]=start; s['slot_fault'+str(i)]=start+4*k
        edges.append(dict(cycle=cycle,q=7,n=0,post=0,valid=1,ack=1,flush_unissued=0,flush=1,eret=1)); cycle+=1
        for j in range(k+1):
            edges.append(dict(cycle=cycle,q=j,n=(j+1)%8,post=(j+1)%8,valid=1,ack=1,flush_unissued=0,flush=0,eret=0,
                pc=start+4*j,tid=j,op=(0x00943023 if i%3==1 else 0x00043e83) if j==k else 0x13)); cycle+=1
    return edges,s


def fault_fixture():
    expected=[dict(pc=0x80003000+i*128,cause=6 if i%3==1 else 4,tval=r.oracle.ADDRESSES[i]) for i in range(12)]
    edges=[]; handlers=[]
    for i,w in enumerate(expected):
        data=dict(tid=r.oracle.SLOTS[i],cause=w['cause'],tval=w['tval'])
        edges.append(dict(cycle=i,detector=data,responses=[data],load_fault=w['cause']==4,store_fault=w['cause']==6,
            tag_valid=1,kill_req=1,st_valid=0,commit=dict(w,tid=data['tid']),ack=0)); handlers.append(i+1)
    return edges,expected,handlers


class Runtime(unittest.TestCase):
    def test_allocation_positive_and_flush_veto(self):
        e,s=allocation_fixture(); result=c.allocation_gate(e,s)
        self.assertEqual(len(result['chains']),12); self.assertEqual(result['fullflush_same_cycle_vetoes'],12)

    def test_allocation_mutations(self):
        e,s=allocation_fixture()
        for index,field,value in [(0,'eret',0),(0,'n',1),(1,'post',0),(1,'tid',2),(1,'pc',0x80003004),
                                  (1,'op',0x1),(3,'op',0x13),(2,'flush',1),(2,'flush_unissued',1),(2,'ack',0)]:
            bad=copy.deepcopy(e); bad[index][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): c.allocation_gate(bad,s)

    def test_allocation_missing_chain(self):
        e,s=allocation_fixture()
        with self.assertRaises(ValueError): c.allocation_gate(e[:-1],s)

    def test_nonterminal_missing_NBA_rejected(self):
        e,s=allocation_fixture(); e[1]['post']=e[1]['q']
        with self.assertRaises(ValueError): c.allocation_gate(e,s)

    def test_terminal_NBA_exception_only(self):
        e,s=allocation_fixture(); e[-1]['post']=e[-1]['q']; e[-1]['terminal_no_nba']=True
        self.assertEqual(len(c.allocation_gate(e,s)['chains']),12)
        text=Path(c.__file__).read_text()
        self.assertIn("e['cycle']==terminal_cycle and number(after,original.MONITOR)==terminal_cycle",text)

    def test_fault_positive(self):
        e,w,h=fault_fixture(); self.assertEqual(len(c.owner_gate(e,w,h)['owners']),12)

    def test_fault_mutations(self):
        e,w,h=fault_fixture()
        for mode in ('wrongPC','wrongVID','wrongTval','storeenqueue','loadunkilled','extraresponse','nohandler','ack'):
            bad=copy.deepcopy(e); hh=list(h)
            if mode=='wrongPC': bad[0]['commit']['pc']+=4
            elif mode=='wrongVID': bad[0]['responses'][0]=dict(bad[0]['responses'][0],tid=1)
            elif mode=='wrongTval': bad[0]['commit']['tval']^=1
            elif mode=='storeenqueue': bad[1]['st_valid']=1
            elif mode=='loadunkilled': bad[0]['kill_req']=0
            elif mode=='extraresponse': bad[-1]['responses']*=2
            elif mode=='nohandler': hh[0]=0
            else: bad[0]['ack']=1
            with self.subTest(mode=mode), self.assertRaises(ValueError): c.owner_gate(bad,w,hh)

    def test_source_closure_actual(self):
        p=c.source_proof(); self.assertEqual(p['layouts']['dcache_req_i_t']['width'],136)
        self.assertEqual(p['layouts']['scoreboard_entry_t']['width'],438)
        self.assertIn('not retire-count',p['slot_contract'])
        r.life.check(p['pins'])

    def test_actual_parent_preflight(self):
        m=r.configure(r.APPROVED_PRE,r.APPROVED_PRE_SEAL)
        s=r.oracle.elf_shape(r.ELF); ref=r.reference(m); w=r.oracle.traps((r.PRE/'spike.trace').read_text(),s)
        self.assertEqual(r.oracle.validate(ref,s,w),m['validation'])
        self.assertEqual(len(ref),1626)

    def test_wrong_parent_preflight(self):
        with self.assertRaises(ValueError): r.configure(r.APPROVED_PRE,'0'*64)
        with self.assertRaises(ValueError): r.configure(r.life.OUT/'scalar-slot-rotation792-preflight-agent-20261008-02',r.APPROVED_PRE_SEAL)

    def test_command_actual(self):
        r.configure(r.APPROVED_PRE,r.APPROVED_PRE_SEAL)
        argv=r.command(r.life.OUT/'slot-command-test-never-run')
        self.assertEqual(argv[0],str(r.life.IMAGE)); self.assertIn(str(r.PROBE),argv)
        self.assertIn('+UVM_TESTNAME='+r.NAME,argv) if any(x.startswith('+UVM_TESTNAME=') for x in argv) else self.assertTrue(any(r.NAME in x for x in argv))
        self.assertTrue(any(str(r.ELF) in x for x in argv))

    def test_actual_prepare_contract(self):
        r.configure(r.APPROVED_PRE,r.APPROVED_PRE_SEAL)
        out=r.life.OUT/'slot-rotation-actual-prepare-test-never-run'
        m=r.manifest(out)
        self.assertEqual(m['timeout_s'],120); self.assertEqual(m['expected_checks'],89)
        self.assertEqual(m['expected_slots'],r.oracle.SLOTS)
        self.assertEqual(m['scalar_reference_counts']['matched_instructions'],1626)
        self.assertEqual(m['scalar_reference_counts']['matched_scalar_memory_accesses'],372)
        self.assertEqual(r.verify_prepared(out,m),m)
        wrong=copy.deepcopy(m); wrong['expected_slots'][0]=1
        with self.assertRaises(ValueError): r.verify_prepared(out,wrong)

    def test_rewrite_uses_actual_function_globals(self):
        m=r.configure(r.APPROVED_PRE,r.APPROVED_PRE_SEAL)
        fn=c.rewrite(c.original.architecture,dict(c.original.architecture.__globals__),{866:1626,226:372,6:12},{'mis_guards':'slot_guards'})
        self.assertIn(1626,fn.__code__.co_consts); self.assertNotIn(866,fn.__code__.co_consts)
        self.assertIn('slot_guards',fn.__code__.co_consts)
        self.assertIs(fn.__globals__['shared'],c.original.shared)

    def test_probe_same_cycle_contract(self):
        text=r.PROBE.read_text()
        for n in ('issue_pointer_q','issue_pointer_n','flush_i','flush_unissued_instr_i','decoded_instr_ack_o','decoded_instr_valid_i','issue_instr_o','orig_instr_i','eret_o'):
            self.assertIn('.'+n,text)
        self.assertNotIn('force ',text); self.assertNotIn('deposit ',text)


if __name__=='__main__': unittest.main()
