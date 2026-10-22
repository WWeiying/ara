import os
from pathlib import Path
import subprocess
import sys
import unittest
import fpnew_tied90_childenv as p


class ChildEnvironment(unittest.TestCase):
    def actual_tcl_child(self,path):
        env=dict(os.environ)
        if path is None:env.pop('PYTHONPATH',None)
        else:env['PYTHONPATH']=path
        out=p.frozen.life.OUT/'fpnew-tied90-local-prepared781-agent-20261008-01'
        script='''set tied_env_test_only 1
source {%s}
set tied_python {%s}
set tied_helper {%s}
set tied_seal 60aa913eeb09637030ed08204c57b133a324c7cd4ffc5d3433d2afe839331f57
set env(DVE_COVERAGE_OUTPUT) {%s}
tied_gate before
'''%(p.TCL,sys.executable,Path(p.frozen.__file__).resolve(),out)
        r=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,env=env,timeout=120)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stderr,'')
        self.assertIn('before_PASS',r.stdout)

    def test_missing_parent_path_actual_all70_subprocess(self):self.actual_tcl_child(None)
    def test_hostile_parent_path_actual_all70_subprocess(self):self.actual_tcl_child('/nonexistent/hostile [path];bad')
    def test_same_binder_and_recursive_closure(self):
        p.context()
        self.assertEqual(p.frozen.life.digest(p.frozen.__file__),p.FROZEN_SHA)
        for name in ('fpnew_tied90_local.tcl','mfpu272_five_phase.tcl','apply_points740_v4.tcl'):
            self.assertIn(str(p.HERE/name),p.frozen.tcl_pins(p.TCL))
    def test_original_capture_cannot_be_upgraded(self):
        with self.assertRaises(ValueError):
            p.context()['check'](p.frozen.life.OUT/'fpnew-tied90-local-prepared781-agent-20261008-01',
                                '60aa913eeb09637030ed08204c57b133a324c7cd4ffc5d3433d2afe839331f57')


if __name__=='__main__':unittest.main()
