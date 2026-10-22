import unittest
import review_requester_wdata775 as p


class WdataProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=p.old.REQUESTER.read_text();cls.package=p.old.PACKAGE.read_text()
        cls.lane=(p.ROOT/'hardware/src/lane/lane.sv').read_text()
        cls.vrf=(p.ROOT/'hardware/src/lane/vector_regfile.sv').read_text()

    def test_actual_frozen_writer_closure(self):
        r=p.source_guard(self.source,self.package,self.lane,self.vrf)
        self.assertEqual(r['read_writer_count'],2);self.assertEqual(r['write_indices'],list(range(9,14)))

    def test_nonzero_default(self):
        with self.assertRaises(ValueError):
            p.source_guard(self.source.replace("operand_payload[requester_index] = '0;","operand_payload[requester_index] = '1;"),self.package,self.lane,self.vrf)

    def test_partial_extra_wdata_writer(self):
        with self.assertRaises(ValueError):
            p.source_guard(self.source+'\nassign operand_payload[0].wdata = input_data;\n',self.package,self.lane,self.vrf)

    def test_read_assignment_pattern_override(self):
        with self.assertRaises(ValueError):
            p.source_guard(self.source.replace("opqueue_e'(requester_index),","opqueue_e'(requester_index), wdata: 64'h1,"),self.package,self.lane,self.vrf)

    def test_width_and_role_changes(self):
        with self.assertRaises(ValueError):
            p.source_guard(self.source,self.package.replace('ELEN  = 64;','ELEN  = 32;'),self.lane,self.vrf)
        with self.assertRaises(ValueError):
            p.source_guard(self.source,self.package,self.lane,self.vrf.replace('.we_i   (wen_i[bank]','.we_i   (1\'b1'))

    def test_exact_compiled_subset_and_protection(self):
        rank=p.life.read_bound(p.old.RANK,p.old.RANK_SHA)
        row=next(r for r in rank['scopes'] if r['scope'].endswith('gen_lanes[0].i_lane.i_operand_requester'))
        shape_path=next(p.Path(s) for s in rank['pins'] if s.endswith('/tgl.verilog.shape.xml'))
        shape=p.old.shared.toggle.xml(shape_path)
        targets,protected=p.subset(row['scope'],row,shape)
        self.assertEqual({t['name'] for t in targets},{'operand_payload[%d].wdata'%i for i in range(9)})
        self.assertTrue(any(x.get('name')=='operand_payload[9].wdata' for x in protected))
        self.assertTrue(any(x.get('name')=='operand_payload[0].be' for x in protected))
        self.assertTrue(any(x.get('portnode')!='0' for x in protected if 'portnode' in x))
        root=next(d for d in shape.findall('tgldef') if d.get('chksum')==row['checksum'])
        target=next(n for n in root.find('tglshape') if n.get('name')=='operand_payload[0].wdata')
        target.set('left','62')
        with self.assertRaises(ValueError):p.subset(row['scope'],row,shape)


if __name__=='__main__':unittest.main()
