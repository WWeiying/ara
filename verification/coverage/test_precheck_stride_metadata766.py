"""Independent finite source/golden tests; neither Spike nor DUT execution."""
import copy
import unittest
import precheck_stride_metadata766 as m


class PrecheckTests(unittest.TestCase):
    def test_all_initial_ring_positions_and_directions(self):
        self.assertEqual(len(m.ring_proof()),4)

    def test_full64_strides_stay_base_only_at_vl1(self):
        for s in m.PATTERNS:self.assertEqual(m.addresses(0x80010040,1,s),[0x80010040])
        self.assertNotEqual(m.addresses(0x80010040,2,m.PATTERNS[0]),[0x80010040]*2)

    def test_complete_independent_regions_and_csrs(self):
        g=m.golden();m.validate(g)
        self.assertEqual((len(g['source']),len(g['stored']),len(g['vrf_guarded'])),(128,544,4128))
        self.assertEqual(g['vrf_guarded'][16+1024:16+1026],bytes([0x3c]*2))
        self.assertEqual(g['checks'],605)

    def test_wrong_vrf_tail_source_destination_and_guards(self):
        for key,index in [('source',0),('stored',0),('stored',16),('vrf_guarded',0),
                          ('vrf_guarded',16+1026),('vrf_guarded',4127)]:
            g=m.golden();value=bytearray(g[key]);value[index]^=1;g[key]=bytes(value)
            with self.assertRaises(ValueError):m.validate(g)

    def test_missing_region_wrong_csr_or_checks(self):
        g=m.golden();del g['source']
        with self.assertRaises(ValueError):m.validate(g)
        for key in m.golden()['csrs']:
            g=m.golden();g['csrs'][key]^=1
            with self.assertRaises(ValueError):m.validate(g)
        g=m.golden();g['checks']-=1
        with self.assertRaises(ValueError):m.validate(g)

    def test_frozen_source_contract(self):
        paths=[m.ROOT/'verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv',
            m.ROOT/'hardware/src/vlsu/vldu.sv',m.ROOT/'hardware/src/vlsu/vstu.sv',
            m.ROOT/'hardware/src/vlsu/vlsu.sv',m.ROOT/'hardware/include/ara_pkg.sv',
            m.ROOT/'hardware/src/lane/operand_requester.sv']
        texts=[p.read_text() for p in paths];m.source_contract(*texts)
        for index,old,new in [(0,'ara_req.stride = acc_req_i.rs2;','ara_req.stride = 0;'),
            (1,'vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt] = pe_req_i;',
               'vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt] = 0;'),
            (2,'vinsn_queue_d.accept_pnt += 1;','vinsn_queue_d.accept_pnt += 0;'),
            (4,'VlduInsnQueueDepth = 4;','VlduInsnQueueDepth = 2;')]:
            changed=list(texts);changed[index]=changed[index].replace(old,new)
            self.assertNotEqual(changed[index],texts[index])
            with self.assertRaises(ValueError):m.source_contract(*changed)


if __name__=='__main__':unittest.main()
