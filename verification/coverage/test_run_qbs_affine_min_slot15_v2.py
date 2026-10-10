import subprocess
import tempfile
import unittest
from pathlib import Path
import run_qbs_affine_min_slot15_v2 as run


class GuardBinding(unittest.TestCase):
    def execute(self,selection):
        c = run.configuration('min_scale')
        mock = '''
set rst 1
set edges 0
proc dump {args} {return 1}
proc show {args} {}
proc stop {args} {puts "STOP $args"}
proc get {path args} {
    if {$path eq "ara_tb.rst_n"} {return $::rst}
    if {$path eq {TARGET}} {return 3}
    if {$path eq {GUARD}} {return 1}
    error "Unexpected observation $path"
}
proc force {path value mode} {
    if {$path ne "ara_tb.rst_n" || $mode ne "-deposit"} {error "Illegal drive"}
    set ::rst $value
    puts "DRIVE $path $value"
}
proc run {args} {
    puts "RUN $args"
    if {[llength $args] == 0} {set ::ext_hit 1; return}
    if {$args ne "-negedge ara_tb.clk"} {error "Bad clock stepping"}
    incr ::edges
}
'''.replace('TARGET',c['ext_target']).replace('GUARD',c['ext_guard'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'external-reset-selection.tcl').write_text(selection)
            driver = run.old.template.old.shared.DRIVER
            return subprocess.run(['tclsh'],input=mock+'\nsource {'+str(driver)+'}\n',
                                  text=True,capture_output=True,cwd=root)

    def test_real_frozen_driver_complete_path(self):
        result = self.execute(run.selection('min_scale'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        run.backend().markers(result.stdout,'min_scale')
        self.assertEqual(result.stdout.count('DRIVE ara_tb.rst_n 0'),1)
        self.assertEqual(result.stdout.count('DRIVE ara_tb.rst_n 1'),1)
        self.assertIn('entry_valid_q[15] == 1',result.stdout)

    def test_actual_previous_missing_guard_reproduced_before_run(self):
        result = self.execute(run.old.selection('min_scale'))
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Missing guard observation',result.stdout)
        self.assertNotIn('RUN ',result.stdout)
        self.assertNotIn('DRIVE ',result.stdout)

    def test_guard_and_full_vector_both_dumped(self):
        c = run.configuration('min_scale')
        self.assertIn(c['ext_guard'],c['ext_dump_objects'])
        self.assertIn(run.SCOPE+'.entry_valid_q',c['ext_dump_objects'])
        self.assertEqual(len(c['ext_dump_objects']),len(set(c['ext_dump_objects'])))
        self.assertEqual(run.STAGES,{'min_scale':(3,284)})
        with self.assertRaises(ValueError): run.configuration('aux')


if __name__ == '__main__': unittest.main()
