import tempfile
from pathlib import Path
import unittest
import audit_gap115_axi as m


class Audit(unittest.TestCase):
    def test_echo_is_not_execution(self):
        actual = '\n'.join('GAP115_AXI_OBJECT '+m.ROOT+'.'+n for n in ('clk_i', 'rst_ni', 'axi_req_o', 'axi_resp_i'))
        text = 'puts "GAP115_AXI_FOUR_OBJECTS_READY"\nputs stderr "GAP115_AXI_CAPTURE_ERROR $m"\n'+actual+'\nGAP115_AXI_FOUR_OBJECTS_READY\n'
        m.markers(text)
        for suffix in ('GAP115_AXI_FOUR_OBJECTS_READY\n', 'GAP115_AXI_CAPTURE_ERROR failure\n'):
            with self.assertRaises(ValueError): m.markers(text+suffix)
        with self.assertRaises(ValueError): m.markers(text.replace('.axi_resp_i', '.foreign'))

    def fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.vcd'
            header = '$timescale 100fs $end\n'
            scopes = m.ROOT.split('.')
            header += ''.join('$scope module '+s+' $end\n' for s in scopes)
            names = list(m.WIDTHS); codes = {n: 'id'+str(i) for i, n in enumerate(names)}
            header += ''.join('$var wire %d %s %s $end\n'%(m.WIDTHS[n], codes[n], n) for n in names)
            header += '$upscope $end\n'*len(scopes)+'$enddefinitions $end\n'
            values = {n: 0 for n in names}; values['rst_ni'] = 1
            changes = ['#0', '$dumpvars']+['b%s %s'%(bin(v)[2:], codes[n]) for n, v in values.items()]+['$end']
            # One aborted burst, four-cycle reset, then one complete64-beat read.
            changes += ['#1', 'b1 '+codes['axi_req_o.ar_valid'], 'b1 '+codes['axi_resp_i.ar_ready'],
                        'b111111 '+codes['axi_req_o.ar.len'], 'b100 '+codes['axi_req_o.ar.size'],
                        'b1 '+codes['axi_req_o.ar.burst'], '#2', '1'+codes['clk_i'],
                        '#3', '0'+codes['clk_i'], '0'+codes['rst_ni'], '0'+codes['axi_req_o.ar_valid']]
            for time in range(4, 11): changes += ['#'+str(time), str(int(time%2 == 0))+codes['clk_i']]
            changes += ['#11', '0'+codes['clk_i'], '1'+codes['rst_ni'], '1'+codes['axi_req_o.ar_valid'],
                        '#12', '1'+codes['clk_i'], '#13', '0'+codes['clk_i'], '0'+codes['axi_req_o.ar_valid'],
                        '1'+codes['axi_req_o.r_ready'], '1'+codes['axi_resp_i.r_valid'],
                        'b101 '+codes['axi_resp_i.r.data']]
            for beat in range(64):
                time = 14+beat*2
                if beat == 63: changes += ['1'+codes['axi_resp_i.r.last']]
                changes += ['#'+str(time), '1'+codes['clk_i'], '#'+str(time+1), '0'+codes['clk_i']]
            changes += ['0'+codes['axi_resp_i.r_valid'], '#142', '1'+codes['clk_i'],
                        '#143', '0'+codes['clk_i'], '#144', '1'+codes['clk_i']]
            path.write_text(header+'\n'.join(changes)+'\n')
            yield path

    def test_reset_abort_drain_and_preedge(self):
        for path in self.fixture():
            a = m.read_bursts(path, 0, 5)
            self.assertEqual(a['phases'], [dict(ar=1, r_beats=0, completed=0, aborted=1),
                                          dict(ar=1, r_beats=64, completed=1, aborted=0)])

    def test_wrong_RLAST_ID_data_and_missing_drain(self):
        for mutate in ('last', 'id', 'data', 'truncate'):
            for path in self.fixture():
                text = path.read_text()
                if mutate == 'last': text = text.replace('1id12', '0id12')
                elif mutate == 'id': text = text.replace('b0 id11', 'b1 id11')
                elif mutate == 'data': text = text.replace('b101 id14', 'b110 id14')
                else: text = text[:text.index('#100\n')]
                path.write_text(text)
                with self.assertRaises(ValueError): m.read_bursts(path, 0, 5)


if __name__ == '__main__': unittest.main()
