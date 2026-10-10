"""Independent native/observation rejection fixtures, not simulation evidence."""
import copy
import csv
import json
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import qualify_gap110_native as q
from ara_verify.vector_commit import ArchActivity, VectorWrite
from ara_verify.vector_commit import _deshuffle_byte


def custom_writes(item,seq=4,cycle=12,vid=1):
    expected=q.custom_expected(item);writes=[]
    for ctx in range(5):
        for lane in range(4):
            data=bytearray(8);be=0
            for b in range(8):
                offset=_deshuffle_byte(lane*8+b,4,2)
                key=(8+ctx,offset)
                if key in expected:
                    data[b]=expected[key];be|=1<<b
            writes.append(VectorWrite(4,cycle,vid,seq,lane,4,q.WORD,2,
                                     (8+ctx)*4,be,int.from_bytes(data,'little'),255))
    return writes


class Native(unittest.TestCase):
    def test_native_independent_outputs_and_flags(self):
        for phase,item in enumerate(q.independent_native()):
            self.assertEqual(dict(phase=phase,bits=item['result_bits'],flags=item['fflags']),
                             q.runner.oracle_expected(phase))
            self.assertEqual(item['integer_dots'],[256*(ctx+1) for ctx in range(5)
                                                   for _ in range((7,5)[phase])])

    def test_native_mutations_including_padded_rows_and_contexts(self):
        original=Path.read_bytes
        for filename,offset,label in [('activation-native0.bin',2080,'bsum'),
            ('activation-native1.bin',32+7,'quants'),('activation-native0.bin',0,'scale'),
            ('weight-native1.bin',7*110+32,'quant'),('weight-native0.bin',96,'scale/quant'),
            ('weight-native0.bin',108,'scale')]:
            def read(path):
                raw=original(path)
                if path.name==filename:
                    raw=bytearray(raw);raw[offset]^=1;return bytes(raw)
                return raw
            with patch.object(Path,'read_bytes',read):
                with self.assertRaisesRegex(ValueError,label):q.independent_native()

    def test_native_truncation_rejected(self):
        original=Path.read_bytes
        with patch.object(Path,'read_bytes',lambda path: original(path)[:-1]
                          if path.name=='weight-native0.bin' else original(path)):
            with self.assertRaisesRegex(ValueError,'storage'):q.independent_native()

    def test_actual_elf_regions_pointer_phases_and_descriptor(self):
        symbols,data,sites=q.elf_view();native=q.independent_native()
        self.assertEqual([symbols['gap110_qbexec_site%d'%p][0] for p in (0,1)],
                         [0x8000017a,0x80000252])
        for phase,n in enumerate((7,5)):
            self.assertEqual(len(sites[phase]),8)
            values=q.regions(phase,symbols,data,native)
            self.assertEqual(sum(map(len,values.values())),12272)
            header,pointer=struct.unpack_from('<QQ',values['descriptor_packet'],64)
            self.assertEqual(header,2|(5<<4)|(1<<8)|(1<<12)|(2<<16)|((n-1)<<20))
            self.assertEqual(pointer%16,(0,12)[phase])
            self.assertEqual(values['csr_packet'][32:128],struct.pack('<12Q',*([n,16,0,2,8,5]*2)))
            for reg in range(32):
                for offset in range(128):
                    if (reg,offset) not in q.custom_expected(native[phase]):
                        self.assertEqual(values['actual'][64+reg*128+offset],
                                         values['initial'][64+reg*128+offset])

class Readback(unittest.TestCase):
    def setUp(self):
        self.symbols,self.data,self.sites = q.elf_view()
        self.expected = q.regions(0,self.symbols,self.data,q.independent_native())
        self.rows = []
        for name,blob in self.expected.items():
            for offset in range(0,len(blob),8):
                self.rows.append(dict(event='retire',cycle='10',pc='80000300',mem_addr=hex(self.symbols[name][0]+offset),
                    mem_rmask='ff',mem_wmask='0',insn='00003283',rd='5',trap='0',
                    rd_wdata=hex(int.from_bytes(blob[offset:offset+8],'little'))))

    def test_all_full_regions_observed(self):
        result = q.readback(self.rows,0,20,self.symbols,self.expected)
        self.assertEqual(result,dict(initial=4224,actual=4224,weights=1024,
                                    activation=2496,descriptor_packet=144,csr_packet=160))

    def test_each_region_last_byte_negative(self):
        for name,blob in self.expected.items():
            rows = copy.deepcopy(self.rows)
            address = self.symbols[name][0]+len(blob)-8
            row = next(r for r in rows if int(r['mem_addr'],16)==address)
            row['rd_wdata'] = hex(int(row['rd_wdata'],16)^(1<<56))
            with self.assertRaisesRegex(ValueError,'Readback differs'):
                q.readback(rows,0,20,self.symbols,self.expected)

    def test_missing_observation_cannot_be_selfcheck_pass(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            q.readback(self.rows[:-1],0,20,self.symbols,self.expected)

    def test_wrong_phase_preserved_preimage_rejected(self):
        expected = q.regions(1,self.symbols,self.data,q.independent_native())
        with self.assertRaisesRegex(ValueError,'Readback differs'):
            q.readback(self.rows,0,20,self.symbols,expected)

    def test_wrong_window_unobserved_rejected(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            q.readback(self.rows,11,20,self.symbols,self.expected)

    def test_mask_unknown_or_no_gpr_observation_rejected(self):
        for key,value in [('mem_rmask','f'),('rd','0'),('trap','1'),('rd_wdata','xxxxxxxx')]:
            rows = copy.deepcopy(self.rows); rows[0][key] = value
            with self.assertRaises(ValueError): q.readback(rows,0,20,self.symbols,self.expected)

    def test_rvc_load_decoder_supported_without_isa_claim(self):
        self.assertEqual(q.scalar_access(0x6000),('read',8))
        self.assertEqual(q.scalar_access(0x6082),('read',8))
        self.assertIsNone(q.scalar_access(0x6002))
        self.assertIsNone(q.scalar_access(0x0001))

    def test_next_phase_reset_excludes_poisoned_new_phase_reads(self):
        reset = dict(self.rows[0],cycle='11',mem_rmask='0',mem_wmask='ff',
                     mem_addr=hex(self.symbols['descriptor_packet'][0]),insn='00533023')
        poison = dict(self.rows[0],cycle='12',rd_wdata='0')
        self.assertEqual(q.phase_readback(self.rows+[reset,poison],0,20,self.symbols,self.expected),
                         q.readback(self.rows,0,20,self.symbols,self.expected))

    def test_reset_before_complete_observation_fails_closed(self):
        reset = dict(self.rows[0],cycle='9',mem_rmask='0',mem_wmask='ff',
                     mem_addr=hex(self.symbols['descriptor_packet'][0]),insn='00533023')
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            q.phase_readback([reset]+self.rows,0,20,self.symbols,self.expected)

    def test_cross_phase_observation_cannot_fill_missing_previous_bytes(self):
        rows = copy.deepcopy(self.rows); rows[-1]['cycle'] = '12'
        reset = dict(rows[0],cycle='11',mem_rmask='0',mem_wmask='ff',
                     mem_addr=hex(self.symbols['descriptor_packet'][0]),insn='00533023')
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            q.phase_readback(rows+[reset],0,20,self.symbols,self.expected)


class Writebacks(unittest.TestCase):
    def setUp(self):
        self.item=q.independent_native()[0]
        self.a=ArchActivity(q.WORD,1,1,True,8,2,160,0,custom_writes(self.item))
        self.expected=q.custom_expected(self.item)

    def test_exact_m5_n7_and_n5(self):
        q.activity_bytes(self.a,self.expected,10,20,custom=True)
        item=q.independent_native()[1]
        other=ArchActivity(q.WORD,1,1,True,8,2,160,0,custom_writes(item))
        q.activity_bytes(other,q.custom_expected(item),10,20,custom=True)
        self.assertEqual(sum(bin(w.be).count('1') for w in self.a.writes),140)
        self.assertEqual(sum(bin(w.be).count('1') for w in other.writes),100)

    def test_software_vl_is_not_backend_vl(self):
        for value in (5,7,128,256):
            a=copy.deepcopy(self.a);a.vl=value
            with self.assertRaisesRegex(ValueError,'internal'):
                q.activity_bytes(a,self.expected,10,20,custom=True)

    def test_lane_source_be_unknown_time_and_tail_rejected(self):
        for change in (dict(be=15),dict(be=255,lane=3),dict(known_be=7),
                       dict(lane=4),dict(source=0),dict(cycle=21),dict(eew=1)):
            a=copy.deepcopy(self.a);a.writes[0]=replace(a.writes[0],**change)
            with self.assertRaises(ValueError):q.activity_bytes(a,self.expected,10,20,custom=True)
        a=copy.deepcopy(self.a);a.writes[3]=replace(a.writes[3],be=255)
        with self.assertRaises(ValueError):q.activity_bytes(a,self.expected,10,20,custom=True)

    def test_active_output_corruption_rejected(self):
        a=copy.deepcopy(self.a);a.writes[0]=replace(a.writes[0],data=a.writes[0].data^1)
        with self.assertRaises(ValueError):q.activity_bytes(a,self.expected,10,20,custom=True)

    def test_duplicate_or_missing_bytes_rejected(self):
        for writes in (self.a.writes[:-1],self.a.writes+[self.a.writes[0]]):
            a=copy.deepcopy(self.a);a.writes=writes
            with self.assertRaises(ValueError):q.activity_bytes(a,self.expected,10,20,custom=True)

    def test_incomplete_or_wrong_metadata_rejected(self):
        for key,value in [('completions',0),('allocations',2),('eew',1),('use_vd',False),('vstart',1)]:
            a=copy.deepcopy(self.a);setattr(a,key,value)
            with self.assertRaises(ValueError):q.activity_bytes(a,self.expected,10,20,custom=True)

class Software(unittest.TestCase):
    def text(self):
        return '\n'.join(['GAP110 command=0 checks=17 errors=0',
            'GAP110 command=1 checks=17 errors=0',
            'GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',
            'PASSED: qbs_gap110_q3_r4_tail checks=41 errors=0','Core Test *** SUCCESS ***',
            '[ARA_CONTRACT] requests=100 responses=100 exceptions=0 mmu_request_cycles=0 '
            'protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'])+'\n'

    def check(self,text):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'log'; path.write_text(text)
            return q.software(path)

    def test_exact_software_contract(self): self.assertEqual(self.check(self.text())['requests'],100)

    def test_missing_phase_checks_contract_and_exception_rejected(self):
        for text in (self.text().replace('checks=41','checks=40'),
                     self.text().replace('exceptions=0','exceptions=1'),
                     self.text().replace('responses=100','responses=99'),
                     self.text().replace('command=1','command=0'),
                     self.text()+'FAIL injected\n'):
            with self.assertRaises(ValueError): self.check(text)


class CSVIntegration(unittest.TestCase):
    """Synthetic observations use actual parsers, never treated as DUT evidence."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.symbols,self.data,self.sites = q.elf_view(); self.native = q.independent_native()
        self.commit = []; self.vector = []; order = 0
        def commit(event,cycle,**kw):
            row = dict(cycle=str(cycle),event=event,order='-1',port='0',trans_id='-1',pc='0',insn='0',
                       rd='0',rd_wdata='0',mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0',trap='0')
            row.update({k:str(v) for k,v in kw.items()}); self.commit.append(row)
        def vector(event,cycle,seq=-1,word=0,reg=0,**kw):
            row = dict(cycle=str(cycle),event=event,arch_seq=str(seq),vid='0',lane='0',source='4',
                insn=hex(word),use_vd='1',vd=str(reg),eew='2',vl='256',vstart='0',addr='0',
                be='0',wdata='0',nr_lanes='4',vlen_bits='1024')
            row.update({k:str(v) for k,v in kw.items()})
            if row['wdata'].startswith('0x'):
                row['wdata']=format(int(row['wdata'],16),'016x')
            self.vector.append(row)
        vector('config',0)
        for phase in (0,1):
            group = self.sites[phase][:4]+[dict(pc=self.symbols['gap110_qbexec_site%d'%phase][0],
                         word=q.WORD,register=8,store=False)]+self.sites[phase][4:]
            for i,site in enumerate(group):
                seq = phase*9+i; cycle = seq*1000+10; word = site['word']; reg = site['register']
                commit('arch_start',cycle,order=seq,trans_id=seq,insn=hex(word))
                commit('cvx_req',cycle+1,trans_id=seq,insn=hex(word))
                commit('uop_alloc',cycle+2,order=seq,insn=hex(word))
                vector('alloc',cycle+2,seq,word,reg,use_vd=int(not site['store']),vl=160 if i==4 else 256)
                if i<4:
                    seed = q.seed_image(phase)
                    for r in range(reg,reg+8):
                        for w in range(4):
                            for lane in range(4):
                                raw = bytes(seed[r*128+w*32+_deshuffle_byte(lane*8+b,4,2)] for b in range(8))
                                vector('write',cycle+3,seq,word,reg,lane=lane,addr=r*4+w,be='ff',
                                       wdata=hex(int.from_bytes(raw,'little')))
                elif i==4:
                    for write in custom_writes(self.native[phase],seq,cycle+3,0):
                        vector('write',cycle+3,seq,word,reg,vl=160,lane=write.lane,
                               addr=write.addr,be=format(write.be,'x'),wdata=hex(write.data))
                vector('done',cycle+4,seq,word,reg,vl=160 if i==4 else 256)
                commit('uop_done',cycle+4,order=seq,insn=hex(word))
                commit('cvx_resp',cycle+5,trans_id=seq)
                commit('retire',cycle+6,order=order,pc=hex(site['pc']),insn=hex(word)); order += 1
            values = q.regions(phase,self.symbols,self.data,self.native)
            for name,blob in values.items():
                for offset in range(0,len(blob),8):
                    commit('retire',phase*9000+8500,order=order,pc='80000300',insn='00003283',rd=5,
                        mem_addr=hex(self.symbols[name][0]+offset),mem_rmask='ff',
                        rd_wdata=hex(int.from_bytes(blob[offset:offset+8],'little')))
                    order += 1
        (self.run/'run.vcs.log').write_text(Software().text().replace('requests=100 responses=100',
                                                                     'requests=18 responses=18'))

    def execute(self):
        for name,rows in [('commit_trace.csv',self.commit),('vector_trace.csv',self.vector)]:
            with (self.run/name).open('w') as stream:
                writer = csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        return q.runtime(self.run,self.symbols,self.data,self.sites,self.native)

    def test_complete_real_csv_parsers_qualifier_not_scalar_isa(self):
        result = self.execute()
        self.assertFalse(result['full_scalar_isa_verified'])
        self.assertEqual(result['custom_write_bytes'],240)

    def test_wrong_architectural_flags_rejected(self):
        address = self.symbols['csr_packet'][0] + 112
        row = next(r for r in self.commit if r['event'] == 'retire' and
                   int(r['mem_addr'], 16) == address)
        for wrong in (0, 11, 24):
            row['rd_wdata'] = hex(wrong)
            with self.assertRaisesRegex(ValueError, 'Readback differs'):
                self.execute()

    def test_second_phase_wrong_flags_rejected(self):
        address = self.symbols['csr_packet'][0] + 112
        row = next(r for r in self.commit if r['event']=='retire' and
                   int(r['cycle']) > 9000 and int(r['mem_addr'],16)==address)
        row['rd_wdata'] = hex(9)
        with self.assertRaisesRegex(ValueError, 'Readback differs'): self.execute()

    def test_native_sid_binding_allocation_write_done(self):
        for event in ('alloc','write','done'):
            row = next(r for r in self.vector if r['event']==event and
                       int(r['insn'],16)==q.WORD)
            original = row['vid']; row['vid']='1'
            with self.assertRaises(ValueError): self.execute()
            row['vid']=original

    def test_custom_wrong_output_write_rejected(self):
        row = next(r for r in self.vector if r['event'] == 'write' and
                   int(r['insn'], 16) == q.WORD)
        row['wdata'] = format(int(row['wdata'], 16) ^ 1, '016x')
        with self.assertRaises(ValueError): self.execute()

    def test_precise_custom_retire_pc_rejected(self):
        row = next(r for r in self.commit if r['event']=='retire' and int(r['insn'],16)==q.WORD)
        row['pc'] = '8000017c'
        with self.assertRaises(ValueError): self.execute()

    def test_wrong_response_identity_rejected(self):
        row = next(r for r in self.commit if r['event']=='cvx_resp' and r['trans_id']=='4')
        row['trans_id'] = '99'
        with self.assertRaises(ValueError): self.execute()

    def test_custom_native_source_and_be_rejected(self):
        row = next(r for r in self.vector if r['event']=='write' and int(r['insn'],16)==q.WORD)
        for key,value in [('source','0'),('be','f')]:
            old = row[key]; row[key] = value
            with self.assertRaises(ValueError): self.execute()
            row[key] = old

    def test_seed_byte_mutation_rejected(self):
        row = next(r for r in self.vector if r['event']=='write')
        row['wdata'] = hex(int(row['wdata'],16)^1)
        with self.assertRaises(ValueError): self.execute()

    def test_custom_missing_write_rejected(self):
        row = next(r for r in self.vector if r['event']=='write' and int(r['insn'],16)==q.WORD)
        self.vector.remove(row)
        with self.assertRaises(ValueError): self.execute()

    def test_custom_late_write_rejected(self):
        row = next(r for r in self.vector if r['event']=='write' and int(r['insn'],16)==q.WORD)
        done = next(r for r in self.vector if r['event']=='done' and r['arch_seq']==row['arch_seq'])
        row['cycle'] = str(int(done['cycle'])+1)
        with self.assertRaises(ValueError): self.execute()

    def test_target_tail_source_and_csr_readback_corruption_rejected(self):
        for name,offset in [('actual',64+8*128+28),('weights',64+879),
                            ('activation',68+2335),('csr_packet',112)]:
            address=self.symbols[name][0]+(offset//8)*8
            row=next(r for r in self.commit if r['event']=='retire' and
                     int(r['cycle'])<9000 and int(r['mem_addr'],16)==address)
            original=row['rd_wdata']
            row['rd_wdata']=hex(int(original,16)^(1<<((offset%8)*8)))
            with self.assertRaisesRegex(ValueError,'Readback differs'):self.execute()
            row['rd_wdata']=original

    def test_missing_custom_response_rejected(self):
        row=next(r for r in self.commit if r['event']=='cvx_resp' and r['trans_id']=='4')
        self.commit.remove(row)
        with self.assertRaises(ValueError):self.execute()

    def test_duplicate_pending_transaction_rejected(self):
        row=next(r for r in self.commit if r['event']=='cvx_req' and r['trans_id']=='4')
        self.commit.insert(self.commit.index(row),dict(row))
        with self.assertRaises(ValueError):self.execute()

    def test_commit_vector_done_probe_mismatch_rejected(self):
        row = next(r for r in self.vector if r['event']=='done')
        row['cycle'] = str(int(row['cycle'])+1)
        with self.assertRaises(ValueError): self.execute()

    def test_transaction_id_reuse_between_completed_phases(self):
        for seq in (4,13):
            cycle = seq*1000+10
            for row in self.commit:
                if row['event'] in ('arch_start','cvx_req','cvx_resp') and int(row['cycle']) in (cycle,cycle+1,cycle+5):
                    row['trans_id'] = '0'
        self.assertEqual(self.execute()['custom_write_bytes'],240)

    def test_duplicate_custom_response_rejected(self):
        row = next(r for r in self.commit if r['event']=='cvx_resp' and r['trans_id']=='4')
        self.commit.append(dict(row))
        with self.assertRaises(ValueError): self.execute()

    def move_seed_completion(self, done_cycle):
        for row in self.vector:
            if row['arch_seq']=='0' and row['event'] in ('write','done'):
                row['cycle'] = str(done_cycle-1 if row['event']=='write' else done_cycle)
        for row in self.commit:
            if row['event']=='uop_done' and row['order']=='0':
                row['cycle'] = str(done_cycle)
        self.commit.sort(key=lambda row: int(row['cycle']))
        self.vector.sort(key=lambda row: int(row['cycle']))

    def test_seed_accepted_retirement_before_completion(self):
        self.move_seed_completion(18)
        self.assertEqual(self.execute()['initial_vrf_bytes'],8192)

    def test_seed_completion_beyond_custom_consumer_rejected(self):
        self.move_seed_completion(4013)
        with self.assertRaises(ValueError): self.execute()


class Terminal(unittest.TestCase):
    def test_missing_active_or_failed_never_collected(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            with self.assertRaises(ValueError): q.terminal(run)
            for status,code in (('RUNNING',0),('SIMULATION_NOT_ADMITTED',1),
                                ('SIMULATION_EXITED_NOT_ADMITTED',False)):
                (run/'simulation-status.json').write_text(json.dumps(dict(
                    status=status,returncode=code,coverage_admitted=False)))
                with self.assertRaises(ValueError): q.terminal(run)

    def test_clean_terminal_gate_fixture_only(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            path=run/'simulation-status.json'
            path.write_text(json.dumps(dict(status='SIMULATION_EXITED_NOT_ADMITTED',
                                            returncode=0,coverage_admitted=False)))
            self.assertEqual(q.terminal(run),(path,q.life.digest(path)))


class RunBinding(unittest.TestCase):
    def test_actual_parent_run_identity_and_latest_gain_boundary(self):
        self.assertEqual(q.RUN.name,'gap110-q3-r4-old-image-parent-20261006-01')
        self.assertEqual(q.RUN_PID,3280044)
        self.assertEqual(q.RUN_SEAL,'6803bc87380efafecb2d53b3e0688c14dfec175cf573a5d04b0a3d11b8b46387')

    def test_real_prepare_only_no_collect_or_new_output(self):
        with patch.object(q,'runtime',side_effect=AssertionError('Must not collect')):
            config=q.prepare(q.RUN,q.RUN_SEAL)
        self.assertEqual(config['run_pid'],3280044)
        self.assertEqual(config['gain_baseline_required'],733)
        self.assertEqual(config['native_bytes_per_command'],[140,100])
        self.assertEqual(config['preserved_vrf_bytes_per_command'],[3956,3996])
        self.assertFalse(config['coverage_admitted'])
        self.assertIn(str(Path(q.__file__).resolve()),config['pins'])
        self.assertIn(str(Path(__file__).resolve()),config['pins'])

if __name__=='__main__': unittest.main()
