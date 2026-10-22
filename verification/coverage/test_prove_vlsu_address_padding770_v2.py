import unittest
import json
from pathlib import Path
import tempfile
import prove_vlsu_address_padding770_v2 as p


class SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts={rel:(p.old.ROOT/rel).read_text() for rel in p.old.SOURCES|p.EXTRA}

    def test_real_derivation_without_hash_gate(self):
        result=p.semantic_contract(self.texts)
        self.assertEqual(result['largest_addr_t'],dict(width=128,unsigned=True))
        self.assertEqual(result['CVA6Cfg']['PLEN'],56)
        self.assertEqual(len(result['AxiAddrWidth']['instance_chain']),6)

    def reject(self,rel,old,new):
        t=dict(self.texts);self.assertIn(old,t[rel]);t[rel]=t[rel].replace(old,new,1)
        with self.assertRaises(ValueError):p.semantic_contract(t)

    def test_signed128(self):
        self.reject('hardware/deps/axi/src/axi_pkg.sv','typedef logic [127:0] largest_addr_t','typedef logic signed [127:0] largest_addr_t')
    def test_wider128(self):
        self.reject('hardware/deps/axi/src/axi_pkg.sv','[127:0] largest_addr_t','[255:0] largest_addr_t')
    def test_actual_tb_width(self):
        self.reject('hardware/tb/ara_tb.sv','AxiAddrWidth      = 64','AxiAddrWidth      = 128')
    def test_instance_override(self):
        self.reject('hardware/tb/ara_testharness.sv','.AxiAddrWidth(AxiAddrWidth )','.AxiAddrWidth(128 )')
    def test_plen_computation(self):
        self.reject('hardware/deps/cva6/core/include/build_config_pkg.sv','? 34 : 56','? 34 : 128')
    def test_wrong_config_forward(self):
        self.reject('hardware/src/ara_soc.sv','.CVA6Cfg           (CVA6AraConfig        )','.CVA6Cfg           (other_config        )')
    def test_xlen_override(self):
        self.reject('hardware/src/ara_soc.sv','cfg.NrPMPEntries          = 0;','cfg.NrPMPEntries = 0; cfg.XLEN = 32;')
    def test_unsigned_axi_type(self):
        self.reject('hardware/src/vlsu/addrgen.sv','axi_addr_t   = logic [AxiAddrWidth-1:0]','axi_addr_t   = logic signed [AxiAddrWidth-1:0]')
    def test_extra_queue_field_writer(self):
        self.reject('hardware/src/vlsu/addrgen.sv',"axi_addrgen_queue      = '0;","axi_addrgen_queue = '0; axi_addrgen_queue.vaddr = extra;")
    def test_arithmetic128_writer(self):
        self.reject('hardware/src/vlsu/addrgen.sv','vaddr        : axi_addrgen_q.addr',"vaddr        : 128'(axi_addrgen_q.addr) + (128'd1 << 100)")
    def test_signed_writer(self):
        self.reject('hardware/src/vlsu/addrgen.sv','vaddr        : idx_final_vaddr_q','vaddr        : $signed(idx_final_vaddr_q)')
    def test_reset_writer(self):
        self.reject('hardware/deps/common_cells/src/fifo_v3.sv',"mem_q <= {FifoDepth{dtype'('0)}};","mem_q <= '1;")
    def test_hold_writer(self):
        self.reject('hardware/deps/common_cells/src/fifo_v3.sv','mem_n           = mem_q;','mem_n = extra;')
    def test_extra_metadata_producer(self):
        self.reject('hardware/src/vlsu/vstu.sv','b_meta_in.vaddr = axi_addrgen_req_i.vaddr;','b_meta_in.vaddr = axi_addrgen_req_i.vaddr; b_meta_in.vaddr = extra;')

    def test_actual_prepared_only_provenance(self):
        candidate=p.old.OUT/'vlsu-address-padding51-native770-agent-20261007-01/candidate.el'
        prior=json.loads(p.PRIOR.read_bytes())
        self.assertEqual(p.prepared_self_candidate(candidate,prior['candidates'],p.semantic_contract(self.texts)),
                         'd952e88cee7902f826900ccae72cdfd0a55b0dd31dee99b6430199ad7446ae77')

    def test_candidate_name_alone_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate=Path(tmp)/'candidate.el';candidate.write_text('INSTANCE: unknown\nToggle data [127:64]\n')
            with self.assertRaises(ValueError):p.prepared_self_candidate(candidate,[],{})

    def provenance_mutation(self, mutate):
        source=p.old.OUT/'vlsu-address-padding51-native770-agent-20261007-01'
        prior=json.loads(p.PRIOR.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);candidate=root/'candidate.el';candidate.write_bytes((source/'candidate.el').read_bytes())
            c=json.loads((source/'config.json').read_bytes());c['output']=str(root);c['pins'][str(candidate)]=p.old.digest(candidate)
            mutate(c,root);(root/'config.json').write_text(json.dumps(c))
            with self.assertRaises(ValueError):p.prepared_self_candidate(candidate,prior['candidates'],p.semantic_contract(self.texts))

    def test_executed_candidate_not_ignored(self):
        self.provenance_mutation(lambda c,r:(r/'execution.json').write_text('{}'))
    def test_other_schema_not_ignored(self):
        self.provenance_mutation(lambda c,r:c.update(schema='ARBITRARY'))
    def test_missing_proof_pin_not_ignored(self):
        self.provenance_mutation(lambda c,r:c.update(proof_seal='0'*64))
    def test_lost_low64_protection_not_ignored(self):
        self.provenance_mutation(lambda c,r:c['instances'][0].update(retained_target_bits={}))


if __name__=='__main__':unittest.main()
