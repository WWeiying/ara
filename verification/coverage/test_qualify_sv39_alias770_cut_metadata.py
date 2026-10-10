import copy
import unittest
import qualify_sv39_alias770_cut_metadata as q
from test_qualify_sv39_alias770_terminal import frames as base_frames


def fixture():
    frames,codes=base_frames();codes={n:n for n in q.WIDTHS}
    for time,b,a in frames:
        for state in (b,a):
            for n,w in q.WIDTHS.items():state.setdefault(n,'0'*w)
            state[q.REQ+'addr']=format(0x80003040,'0128b')
            state[q.REQ+'len']='00000011';state[q.REQ+'size']='100'
    for start in range(0,len(frames),4):
        earlier=frames[start+2];last=frames[start+3]
        for n in (q.p.FIFO+'push_i',q.p.FIFO+'data_i.vaddr',q.p.FIFO+'data_i.slot',q.REQ+'vaddr'):
            earlier[1][n]=last[1][n]
        pointer=int(earlier[1][q.p.FIFO+'write_pointer_q'],2)
        earlier[2][q.p.FIFO+'write_pointer_q']=format((pointer+1)%16,'04b')
        last[1][q.p.FIFO+'write_pointer_q']=format((pointer+1)%16,'04b')
        last[1][q.p.FIFO+'push_i']='0';last[1][q.p.FIFO+'data_i.vaddr']='0'*128
    return frames,codes


class CutTests(unittest.TestCase):
    def test_delayed_external_final_W_preserves_actual_preedge(self):
        f,c=fixture();r=q.frames(f,c,0x80003040)
        self.assertEqual(len(r['pushes']),48)
        self.assertTrue(all(p['external_last_W_100fs']>p['accepted_at_100fs'] for p in r['pushes']))
        self.assertEqual([p['pointer'] for p in r['pushes'][:16]],list(range(16)))

    def test_actual_original_completed_wave_no_converter_or_EDA(self):
        path=q.life.OUT/'sv39-alias770-known-tail-qualified-agent-20261007-01/metadata.vcd'
        r=q.metadata(path,0x80003040)
        self.assertEqual((r['stores'],r['loads']),(48,48))
        self.assertTrue(r['all16slots_both_virtual_directions'])

    def test_missing_owner(self):
        f,c=fixture();f[2][1][q.p.FIFO+'push_i']='0'
        with self.assertRaises(ValueError):q.frames(f,c,0x80003040)

    def test_wrong_producer_physical_or_virtual_or_unknown(self):
        for name,value in ((q.REQ+'addr','0'*128),(q.REQ+'vaddr','0'*128),
                           (q.REQ+'addr','x'*128)):
            with self.subTest(name=name):
                f,c=fixture();f[2][1][name]=value
                with self.assertRaises(ValueError):q.frames(f,c,0x80003040)

    def test_unknown_or_exceptional_or_skip_producer(self):
        for field in ('is_exception','is_load','is_skip'):
            f,c=fixture();f[2][1][q.REQ+field]='1'
            with self.assertRaises(ValueError):q.frames(f,c,0x80003040)

    def test_bad_target_W_or_R_data(self):
        for field in ('axi_req_o.w.data','axi_resp_i.r.data'):
            f,c=fixture();f[3][1][field]='0'*128
            with self.assertRaises(ValueError):q.frames(f,c,0x80003040)

    def test_bad_pointer_or_flush_or_truncated(self):
        for field,value in ((q.p.FIFO+'write_pointer_q','0010'),(q.p.FIFO+'flush_i','1')):
            f,c=fixture();f[2][1][field]=value
            with self.assertRaises(ValueError):q.frames(f,c,0x80003040)
        f,c=fixture()
        with self.assertRaises(ValueError):q.frames(f[:-1],c,0x80003040)


if __name__=='__main__':unittest.main()
