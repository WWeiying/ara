"""Independent native/observation rejection fixtures, not simulation evidence."""
import copy
import csv
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import qualify_gap105_native as q
from ara_verify.vector_commit import ArchActivity, VectorWrite
from ara_verify.vector_commit import _deshuffle_byte


class Native(unittest.TestCase):
    def test_actual_rvc_elf_sites_and_seed_snapshot_contract(self):
        symbols,data,sites = q.elf_view()
        self.assertEqual([symbols['gap105_qbexec_site%d'%p][0] for p in (0,1)],
                         [0x8000017a,0x80000252])
        self.assertTrue(all(len(row)==8 for row in sites))
        self.assertEqual(q.independent_native()[2],
            [1132462080,1140850688,1145044992,1149239296,1151336448,1153433600,1155530752,1157627904])
        for phase in (0,1):
            regions = q.regions(phase,symbols,data,q.independent_native())
            self.assertEqual(sum(map(len,regions.values())),12048)
            self.assertEqual(regions['csr_packet'][32:128],struct.pack('<12Q',*([1,16,0,2,8,5]*2)))

    def test_native_bsum_mutation_rejected(self):
        original = Path.read_bytes
        def read(path):
            raw = original(path)
            if path.name=='activation-row-native.bin':
                raw = bytearray(raw); raw[260] ^= 1; return bytes(raw)
            return raw
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(ValueError,'bsums'): q.independent_native()

    def test_native_q5_quant_mutation_rejected(self):
        original = Path.read_bytes
        def read(path):
            raw = original(path)
            if path.name=='weight-native.bin':
                raw = bytearray(raw); raw[48] ^= 1; return bytes(raw)
            return raw
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(ValueError,'MAC'): q.independent_native()


class Readback(unittest.TestCase):
    def setUp(self):
        self.symbols,self.data,self.sites = q.elf_view()
        self.expected = q.regions(0,self.symbols,self.data,q.independent_native())
        self.rows = []
        for name,blob in self.expected.items():
            for offset in range(0,len(blob),8):
                self.rows.append(dict(event='retire',cycle='10',mem_addr=hex(self.symbols[name][0]+offset),
                    mem_rmask='ff',mem_wmask='0',insn='00003283',rd='5',trap='0',
                    rd_wdata=hex(int.from_bytes(blob[offset:offset+8],'little'))))

    def test_all_full_regions_observed(self):
        result = q.readback(self.rows,0,20,self.symbols,self.expected)
        self.assertEqual(result,dict(initial=4224,actual=4224,weights=800,
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
        self.assertEqual(q.scalar_access(0x6002),('read',8))
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
        outputs = q.independent_native()[2]
        writes = [VectorWrite(c,12,1,0,0,4,q.WORD,2,(8+c)*4,15,bits,255)
                  for c,bits in enumerate(outputs)]
        self.a = ArchActivity(q.WORD,1,1,True,8,2,256,0,writes)
        self.expected = {(8+c,b):value for c,bits in enumerate(outputs)
                         for b,value in enumerate(struct.pack('<I',bits))}

    def test_only32_active_bytes_backend_vl256(self):
        q.activity_bytes(self.a,self.expected,10,20,custom=True)

    def test_csr_vl1_is_not_internal_vl(self):
        self.a.vl = 1
        with self.assertRaisesRegex(ValueError,'internal'): q.activity_bytes(self.a,self.expected,10,20,custom=True)

    def test_tail_unknown_wrong_lane_source_or_time_rejected(self):
        for change in (dict(be=255),dict(known_be=7),dict(lane=1),dict(source=0),
                       dict(cycle=21),dict(data=self.a.writes[0].data^1)):
            a = copy.deepcopy(self.a); a.writes[0] = replace(a.writes[0],**change)
            with self.assertRaises(ValueError): q.activity_bytes(a,self.expected,10,20,custom=True)

    def test_duplicate_or_missing_active_bytes_rejected(self):
        for writes in (self.a.writes[:-1],self.a.writes+[self.a.writes[0]]):
            a = copy.deepcopy(self.a); a.writes = writes
            with self.assertRaises(ValueError): q.activity_bytes(a,self.expected,10,20,custom=True)

    def test_incomplete_or_wrong_eew_rejected(self):
        for key,value in [('completions',0),('allocations',2),('eew',1),('use_vd',False),('vstart',1)]:
            a = copy.deepcopy(self.a); setattr(a,key,value)
            with self.assertRaises(ValueError): q.activity_bytes(a,self.expected,10,20,custom=True)


class Software(unittest.TestCase):
    def text(self):
        return '\n'.join(['GAP105 command=0 checks=17 errors=0',
            'GAP105 command=1 checks=17 errors=0',
            'GAP105 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
            'PASSED: qbs_gap105_m8_phase8 checks=41 errors=0','Core Test *** SUCCESS ***',
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
            row.update({k:str(v) for k,v in kw.items()}); self.vector.append(row)
        vector('config',0)
        for phase in (0,1):
            group = self.sites[phase][:4]+[dict(pc=self.symbols['gap105_qbexec_site%d'%phase][0],
                         word=q.WORD,register=8,store=False)]+self.sites[phase][4:]
            for i,site in enumerate(group):
                seq = phase*9+i; cycle = seq*1000+10; word = site['word']; reg = site['register']
                commit('arch_start',cycle,order=seq,trans_id=seq,insn=hex(word))
                commit('cvx_req',cycle+1,trans_id=seq,insn=hex(word))
                commit('uop_alloc',cycle+2,order=seq,insn=hex(word))
                vector('alloc',cycle+2,seq,word,reg,use_vd=int(not site['store']))
                if i<4:
                    seed = q.seed_image(phase)
                    for r in range(reg,reg+8):
                        for w in range(4):
                            for lane in range(4):
                                raw = bytes(seed[r*128+w*32+_deshuffle_byte(lane*8+b,4,2)] for b in range(8))
                                vector('write',cycle+3,seq,word,reg,lane=lane,addr=r*4+w,be='ff',
                                       wdata=hex(int.from_bytes(raw,'little')))
                elif i==4:
                    for c,bits in enumerate(self.native[2]):
                        vector('write',cycle+3,seq,word,reg,addr=(8+c)*4,be='f',wdata=hex(bits))
                vector('done',cycle+4,seq,word,reg)
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
        self.assertEqual(result['custom_write_bytes'],64)

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
        for key,value in [('source','0'),('be','ff')]:
            old = row[key]; row[key] = value
            with self.assertRaises(ValueError): self.execute()
            row[key] = old

    def test_seed_byte_mutation_rejected(self):
        row = next(r for r in self.vector if r['event']=='write')
        row['wdata'] = hex(int(row['wdata'],16)^1)
        with self.assertRaises(ValueError): self.execute()

    def test_commit_vector_done_probe_mismatch_rejected(self):
        row = next(r for r in self.vector if r['event']=='done')
        row['cycle'] = str(int(row['cycle'])+1)
        with self.assertRaises(ValueError): self.execute()


if __name__=='__main__': unittest.main()
