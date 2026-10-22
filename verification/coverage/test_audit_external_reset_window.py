import tempfile
from pathlib import Path
import unittest
from audit_external_reset_window import audit


class WindowTests(unittest.TestCase):
    def run_case(self, *, stage=6, guard=1, clocks=4, release=True, duplicate=False, unknown=False):
        text = '''$scope module ara_tb $end
$var reg 1 c clk $end
$var reg 1 r rst_n $end
$scope module dut $end
$var reg 4 s state $end
$var reg 1 g valid $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0c
0r
b0 s
0g
#10
1c
1r
'''
        text += f'#15\nb{stage:b} s\n{guard}g\n#20\n0c\n0r\n'
        for i in range(clocks):
            text += f'#{25+i*10}\n1c\n#{30+i*10}\n0c\n'
            if unknown and i == 0:
                text += '#31\nxr\n#32\n0r\n'
        if release:
            text += '1r\n'
        if duplicate:
            text += f'#{35+clocks*10}\n1c\n#{40+clocks*10}\n0c\n0r\n'
        selection = dict(ext_target='ara_tb.dut.state', ext_value=6,
                         ext_guard='ara_tb.dut.valid')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'wave.vcd'
            path.write_text(text)
            return audit(path, selection)

    def test_actual_phase_and_four_clocks(self):
        result = self.run_case()
        self.assertEqual(result['actual_stage'], 6)
        self.assertEqual(result['clock_period_ticks'], 10)
        self.assertFalse(result['coverage_admitted'])

    def test_wrong_stage(self):
        with self.assertRaises(ValueError): self.run_case(stage=5)

    def test_invalid_guard(self):
        with self.assertRaises(ValueError): self.run_case(guard=0)

    def test_short_or_long_reset(self):
        for n in (3, 5):
            with self.subTest(n=n), self.assertRaises(ValueError): self.run_case(clocks=n)

    def test_no_release(self):
        with self.assertRaises(ValueError): self.run_case(release=False)

    def test_extra_reset(self):
        with self.assertRaises(ValueError): self.run_case(duplicate=True)

    def test_unknown_reset_not_accepted(self):
        with self.assertRaises(ValueError): self.run_case(unknown=True)


if __name__ == '__main__': unittest.main()
