import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import run_btb_target_ring as r


class Gates(unittest.TestCase):
    def record(self):
        out=r.life.OUT/'btb-test-not-run'
        return dict(schema='BTB32_FROZEN600_PREPARED_V1',case=r.CASE,output=str(out),
            preflight=str(r.life.OUT/'btb-test-preflight/preflight.json'),baseline=777,
            baseline_seal=r.pre.BASE_SHA,command=r.command(r.life.OUT/'btb-test-preflight/input.elf',out),
            timeout_s=600,wave_limit_bytes=64*1024*1024,automatic_retry=False,
            coverage_admitted=False,RTL_changed=False,post_terminal_qualification_required=True)

    def test_exact_command(self):
        r.validate_record(self.record())
        self.assertIn('+NO_FSDB',self.record()['command'])
        self.assertNotIn('+FSDB',self.record()['command'])

    def test_foreign_command_timeout_base_retry(self):
        for key,value in [('timeout_s',True),('timeout_s',1200),('baseline',776),('automatic_retry',True),
                          ('coverage_admitted',True),('command',['simv']),('wave_limit_bytes',0)]:
            d=self.record();d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_record(d)

    def test_full_tcl_entry_and_unavailable_object(self):
        text=r.PROBE.read_text()
        for failed in (False,True):
            mock='''proc show {args} {return {}}
proc dump {args} {if {[lindex $args 0] eq "-file"} {return 1}; return COUNT}
proc run {} {puts MOCK_RUN}
'''.replace('COUNT','0' if failed else '1')
            result=subprocess.run(['/usr/bin/tclsh'],input=mock+text,text=True,capture_output=True,timeout=5)
            if failed:
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('MOCK_RUN',result.stdout)
                self.assertIn('BTB_RING_ERROR Unavailable object',result.stdout)
            else:
                self.assertEqual(result.returncode,0)
                self.assertEqual(result.stdout.splitlines().count('BTB_RING_READY'),1)
                self.assertEqual(sum(l.startswith('BTB_RING_OBJECT ') for l in result.stdout.splitlines()),10)
                self.assertIn('MOCK_RUN',result.stdout)

    def test_observation_only_whitelist(self):
        text=r.PROBE.read_text()
        self.assertNotIn('\nforce ',text);self.assertNotIn('stop ',text)
        self.assertNotIn('-depth 1',text)
        self.assertIn('${btb}.update_row_index',text)
        self.assertIn('${core}.i_frontend.resolved_branch_i',text)


if __name__=='__main__':unittest.main()
