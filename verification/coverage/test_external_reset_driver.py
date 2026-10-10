"""Host Tcl contract checks; not a replacement for the waveform audit."""
from pathlib import Path
import subprocess
import tempfile
import unittest

DRIVER = Path(__file__).with_name('external_reset_driver.tcl')
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
TARGET = ARA + '.lane[0].i_div.div_cur_state'
GUARD = ARA + '.lane[0].i_div.vfdsu_ex2_half'


class DriverTests(unittest.TestCase):
    def run_tcl(self, *, target=TARGET, value='6', guard=GUARD,
                missing=False, reached=True, dump_ok=True):
        objects = ['ara_tb.clk', 'ara_tb.rst_n', ARA+'.axi_req_o',
                   ARA+'.axi_resp_i', target, guard]
        settings = (f'set ext_target {{{target}}}\nset ext_value {{{value}}}\n'
                    f'set ext_guard {{{guard}}}\nset ext_dump_objects {{{" ".join(objects)}}}\n')
        mock = '''
set rst 1
set edges 0
proc dump {args} {return DUMP_OK}
proc show {args} {}
proc stop {args} {}
proc get {path args} {
    if {$path eq "ara_tb.rst_n"} {return $::rst}
    if {[string match *.div_cur_state $path]} {return 6}
    return 1
}
proc force {path value mode} {
    if {$path ne "ara_tb.rst_n" || $mode ne "-deposit"} {error "Illegal drive"}
    set ::rst $value
    puts "DRIVE $path $value"
}
proc run {args} {
    if {[llength $args] == 0} {set ::ext_hit REACHED; return}
    incr ::edges
    puts "EDGE $::edges"
}
'''.replace('DUMP_OK', '1' if dump_ok else '0').replace('REACHED', '1' if reached else '0')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if not missing:
                (root/'external-reset-selection.tcl').write_text(settings)
            return subprocess.run(['tclsh'], input=mock+f'\nsource {{{DRIVER}}}\n',
                                  text=True, capture_output=True, cwd=root)

    def test_real_stage_four_clocks_external_pin_only(self):
        result = self.run_tcl()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual([x for x in lines if x.startswith('DRIVE ')],
                         ['DRIVE ara_tb.rst_n 0', 'DRIVE ara_tb.rst_n 1'])
        self.assertEqual([x for x in lines if x.startswith('EDGE ')],
                         ['EDGE 1', 'EDGE 2', 'EDGE 3', 'EDGE 4'])
        self.assertEqual(lines.count('EXT_RESET_ASSERT'), 1)
        self.assertLess(lines.index('EDGE 4'), lines.index('EXT_RESET_RELEASE'))

    def test_bad_target_rejected_before_drive(self):
        for target in ('ara_tb.rst_n', TARGET+';force', 'other.div_cur_state'):
            with self.subTest(target=target):
                result = self.run_tcl(target=target)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('DRIVE ', result.stdout)

    def test_invalid_values(self):
        for value in ('-1', '16', '6;run', 'x'):
            self.assertNotEqual(self.run_tcl(value=value).returncode, 0)

    def test_invalid_guard(self):
        self.assertNotEqual(self.run_tcl(guard='ara_tb.rst_n').returncode, 0)

    def test_unreached_no_reset(self):
        result = self.run_tcl(reached=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('DRIVE ', result.stdout)

    def test_missing_selection(self):
        self.assertNotEqual(self.run_tcl(missing=True).returncode, 0)

    def test_dump_failure_no_reset(self):
        result = self.run_tcl(dump_ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('DRIVE ', result.stdout)


if __name__ == '__main__':
    unittest.main()
