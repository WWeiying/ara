"""Finite gold, full snapshot corruption, and real Tcl execution of exact reset profile."""
import copy
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
import run_vmfpu_ured_reset763 as m


class ResetTests(unittest.TestCase):
    def memory(self):
        values={('g75_result',0):680,('g75_result',4):0,('num_failed',0):0,
                ('tohost',0):1,('reduction_scalar',0):0x4060400000000000}
        values.update({('fpar_vrf',8*i):m.expected_word(i) for i in range(512)})
        values.update({('fpar_csr',8*i):v for i,v in enumerate([128,27,0,0,0])})
        return values

    def test_full_oracle(self):
        values=self.memory();m.oracle(lambda n,o=0,size=8:values[n,o])
        self.assertEqual(struct.unpack('<Q',struct.pack('<d',128.0+2.0))[0],m.expected_word(32))
        self.assertEqual(sum([1]*128)+2,130)

    def test_each_full_snapshot_word_protected(self):
        for i in range(512):
            values=self.memory();values['fpar_vrf',8*i]^=1
            with self.assertRaises(ValueError):m.oracle(lambda n,o=0,size=8:values[n,o])

    def test_flags_and_terminal_rejected(self):
        for key in [('fpar_csr',32),('g75_result',4),('num_failed',0),('reduction_scalar',0)]:
            values=self.memory();values[key]^=1
            with self.assertRaises(ValueError):m.oracle(lambda n,o=0,size=8:values[n,o])

    def test_selection_exact(self):
        for key in ('ext_value','ext_guard','ext_states','ext_dump_objects'):
            value=copy.deepcopy(m.selection());value[key]=0
            with self.assertRaises(ValueError):m.selection_text(value)

    def tcl(self,state=1,guard=1):
        mock='''
set rst 1
set edges 0
proc dump {args} {return 1}
proc show {args} {}
proc stop {args} {puts "CONDITION [lindex $args 4]"}
proc get {path args} {
  if {$path eq "ara_tb.rst_n"} {return $::rst}
  if {[string match *.mfpu_state_q $path]} {return STATE}
  return GUARD
}
proc force {path value mode} {
  if {$path ne "ara_tb.rst_n" || $mode ne "-deposit"} {error "Illegal drive"}
  set ::rst $value
  puts "DRIVE $path $value"
}
proc run {args} {
  if {[llength $args]==0} {set ::ext_hit 1;return}
  incr ::edges
  puts "EDGE $::edges"
}
'''.replace('STATE',str(state)).replace('GUARD',str(guard))
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'external-reset-selection.tcl').write_text(m.selection_text(m.selection()))
            return subprocess.run(['tclsh'],input=mock+'\nsource {'+str(m.TCL)+'}\n',
                                  text=True,capture_output=True,cwd=directory)

    def test_actual_generated_body_four_clocks(self):
        result=self.tcl();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([s for s in result.stdout.splitlines() if s.startswith('DRIVE ')],
                         ['DRIVE ara_tb.rst_n 0','DRIVE ara_tb.rst_n 1'])
        self.assertEqual([s for s in result.stdout.splitlines() if s.startswith('EDGE ')],
                         ['EDGE 1','EDGE 2','EDGE 3','EDGE 4'])
        for path in m.states():self.assertIn(path,result.stdout)
        self.assertIn('EXT_RESET_DONE',result.stdout)

    def test_wrong_actual_state_no_drive(self):
        result=self.tcl(state=2);self.assertNotEqual(result.returncode,0)
        self.assertNotIn('DRIVE ',result.stdout)

    def test_missing_positive_owner_no_drive(self):
        result=self.tcl(guard=0);self.assertNotEqual(result.returncode,0)
        self.assertNotIn('DRIVE ',result.stdout)

    def test_epoch0_exact_seed_bytes(self):
        pre={'symbols':{'ured_seed2':0x100,'ured_ones':0x200}}
        commits=[{'event':'retire','order':'1','pc':'100'}]
        rows=[dict(event='alloc',arch_seq='1',insn='5e02c0d7',vd='1',eew='3'),
              dict(event='write',arch_seq='1',be='ff',wdata='4000000000000000')]
        self.assertEqual(m.initial_bytes(commits,rows,pre),8)
        rows[1]['wdata']='4000000000000001'
        with self.assertRaises(ValueError):m.initial_bytes(commits,rows,pre)


if __name__=='__main__':unittest.main()
