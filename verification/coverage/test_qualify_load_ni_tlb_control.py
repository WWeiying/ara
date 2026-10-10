import copy
import re
import tempfile
from pathlib import Path
import unittest
import qualify_load_ni_tlb_control as q


class Qualification(unittest.TestCase):
    def fixture(self):
        rows = {str(i):dict(width=1,checksum='1',bits='0x0') for i in range(6162)}
        base = dict(design={'shape':'sealed'},tests=['old'+str(i) for i in range(761)],
                    input_hashes={},metrics={'fsm':rows})
        single = copy.deepcopy(base); single['tests']=['new']; single['metrics']['fsm']['0']['bits']='0x1'
        return base,single

    def test_full_or_and_exact_prefix(self):
        b,s=self.fixture(); result=q.union(b,s,761)
        self.assertEqual(result['tests'],b['tests']+['new'])
        self.assertEqual(result['metrics']['fsm']['0']['bits'],'0x1')

    def test_duplicate_rejected(self):
        b,s=self.fixture(); s['tests']=[b['tests'][0]]
        with self.assertRaises(ValueError): q.union(b,s,761)

    def test_shape_rejected(self):
        b,s=self.fixture(); s['metrics']['fsm']['0']['checksum']='2'
        with self.assertRaises(ValueError): q.union(b,s,761)

    def test_incomplete_universe_rejected(self):
        b,s=self.fixture(); del s['metrics']['fsm']['0']
        with self.assertRaises(ValueError): q.union(b,s,761)

    def test_native_store_unshifted(self):
        row=dict(mem_addr='80004e04',mem_wmask='f0',mem_wdata='000000000000000e',insn='00a2a023')
        self.assertEqual(q.run.architecture.scalar_store(row),(0x80004e04,b'\x0e\x00\x00\x00'))

    def test_actual_waveform_complete(self):
        a=q.waveform(q.run.RUN/'load-ni-tlb.vcd')
        self.assertEqual(a['ctrl_reads'],1)
        self.assertGreater(a['channels']['ar'],0)
        self.assertGreaterEqual(a['channels']['r'],a['channels']['ar'])
        self.assertEqual(a['channels']['aw'],a['channels']['b'])
        self.assertGreater(a['sampled_edges'],0)
        self.assertTrue(a['pre_timebucket_handshake'])

    def test_clock_width_rejected(self):
        text=(q.run.RUN/'load-ni-tlb.vcd').read_text().replace('$var reg        1 #    clk','$var reg        2 #    clk',1)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'changed.vcd'; p.write_text(text)
            with self.assertRaises(ValueError): q.waveform(p)

    def changed_field(self, full, value):
        a=q.waveform(q.run.RUN/'load-ni-tlb.vcd')
        code=a['declarations'][full]['code']
        text=(q.run.RUN/'load-ni-tlb.vcd').read_text()
        text=re.sub(r'^b[01xz]+ '+re.escape(code)+r'$',lambda _: 'b'+value+' '+code,text,flags=re.M)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'changed.vcd'; p.write_text(text)
            with self.assertRaises(ValueError): q.waveform(p)

    def test_axi_error_response_rejected(self):
        self.changed_field(q.CORE+'.noc_resp_i.r.resp','10')

    def test_ctrl_data_change_rejected(self):
        self.changed_field(q.CORE+'.noc_resp_i.r.data','1')

    def test_unknown_active_data_rejected(self):
        self.changed_field(q.CORE+'.noc_resp_i.r.data','x')


if __name__ == '__main__': unittest.main()
