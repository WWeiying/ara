import copy
import json
from pathlib import Path
import unittest

import run_akv_tile_range_capture as run
import collect_akv_tile_range_capture as collect


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.sym={'entropy_descriptors':0x80010000,'entropy_sources':0x80020000}
        self.samples=[]
        base={k:0 for k in collect.WIDTHS}; base.update(rst_ni=1,axi_ar_ready_i=1)
        for p in range(6):
            row=dict(base,command_fire=1,command_i=[0,0,0,0,2,3][p],command_tile_start_i=collect.case.INDICES[p] if p<4 else 0)
            self.samples.append((row,dict(row,requested_tile_start_q=row['command_tile_start_i'])))
            ranges=[(0,0,self.sym['entropy_descriptors'],64)] if p<4 else []
            if p==3: ranges += [(s+1,0,self.sym['entropy_sources']+s*256+64,128) for s in range(3)]
            for role,index,addr,size in ranges:
                self.samples.append((dict(base,read_range_fire=1,read_range_tag=role*64+index,read_range_vaddr=addr,read_range_bytes=size),base))
                ar=dict(base,axi_ar_valid_o=1); ar['i_read_engine.ar_addr_q']=addr
                self.samples.append((ar,base))
            row=dict(base,fault_valid_o=int(p<3),success_valid_o=int(p>=3),fault_is_validation_o=int(p<3),validation_error_o=11 if p<3 else 0,context_ready_o=int(p in (3,4)))
            self.samples.append((row,base))

    def test_exact_capture(self):
        got=collect.sample_gate(self.samples,self.sym)
        self.assertEqual(got['accepted64_indices'],collect.case.INDICES)

    def mutated(self,key,value,position=0):
        samples=copy.deepcopy(self.samples); samples[position][0][key]=value
        with self.assertRaises(ValueError): collect.sample_gate(samples,self.sym)

    def test_input_truncated(self): self.mutated('command_tile_start_i',0xffff)
    def test_wrong_command(self): self.mutated('command_i',1)
    def test_unknown_input(self): self.mutated('command_tile_start_i',None)
    def test_unknown_handshake(self): self.mutated('command_fire',None)
    def test_mmu_fault_not_validation(self): self.mutated('mmu_exception_valid_i',1)

    def test_postcapture_truncated(self):
        samples=copy.deepcopy(self.samples); samples[0][1]['requested_tile_start_q']=0xffff
        with self.assertRaises(ValueError): collect.sample_gate(samples,self.sym)

    def test_payload_AR_before_fault(self):
        self.mutated('i_read_engine.ar_addr_q',self.sym['entropy_sources']+64,2)

    def test_extra_range(self):
        samples=copy.deepcopy(self.samples); samples.insert(2,copy.deepcopy(samples[1]))
        with self.assertRaises(ValueError): collect.sample_gate(samples,self.sym)

    def test_wrong_validation_code(self): self.mutated('validation_error_o',3,3)
    def test_wrong_context(self): self.mutated('context_ready_o',1,3)

    def test_missing_last_completion(self):
        with self.assertRaises(ValueError): collect.sample_gate(self.samples[:-1],self.sym)

    def test_contract_three_traps(self):
        log='[ARA_CONTRACT] requests=5 responses=5 exceptions=3 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
        self.assertEqual(collect.contract(log,5)['exceptions'],3)
        for old,new in [('exceptions=3','exceptions=1'),('protocol_errors=0','protocol_errors=1'),('responses=5','responses=4')]:
            with self.subTest(old=old),self.assertRaises(ValueError): collect.contract(log.replace(old,new),5)

    def test_native_dry_replay_actual_ELF(self):
        pre=run.life.read_bound(run.PRE/'preflight-manifest.json',run.PRE_SHA)
        model,dry=collect.replay(run.ELF.read_bytes(),pre['symbols'])
        self.assertEqual([c['validation_error'] for c in model.commands],[11,11,11,0,0,0])
        self.assertEqual(dry['traps'],3)

    def test_mul_low_signed_overflow(self):
        mask=(1<<64)-1
        for a,b,want in [(0,mask,0),(mask,2,mask-1),(mask,mask,1),(1<<63,2,0),(3,24,72)]:
            with self.subTest(a=a,b=b): self.assertEqual(collect.mul_low64(a,b),want)
        for a in [-1,1<<64,True]:
            with self.assertRaises(ValueError): collect.mul_low64(a,24)

    def test_mul_register_alias_and_PC(self):
        pre=run.life.read_bound(run.PRE/'preflight-manifest.json',run.PRE_SHA)
        model=collect.Model(run.ELF.read_bytes(),pre['symbols'])
        model.pc=pre['symbols']['tile_handler']+0x34
        model.gpr[6]=2; model.gpr[7]=24
        effect=model.step()
        self.assertEqual((model.gpr[7],effect['rd_wdata']), (48,48))
        # Same opcode at a different PC is not silently modeled as this handler.
        model.pc=pre['symbols']['tile_handler']+0x38
        for i,b in enumerate((0x027303b3).to_bytes(4,'little')): model.memory[model.pc+i]=b
        with self.assertRaises(ValueError): model.step()

    def test_command_uses_only_new_probe_and_ELF(self):
        cmd=run.command(run.life.OUT/'not-launched-tile-range-test')
        self.assertIn('+PRELOAD='+str(run.ELF),cmd)
        self.assertEqual(cmd[-1],str(run.PROBE)); self.assertIn('+NO_FSDB',cmd)

    def test_probe_fields_exact(self):
        text=run.PROBE.read_text()
        words=text.split('foreach name {',1)[1].split('}',1)[0].split()
        self.assertEqual(set(words),set(collect.WIDTHS)); self.assertEqual(len(words),len(collect.WIDTHS))


if __name__=='__main__': unittest.main()
