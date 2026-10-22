import copy
from dataclasses import replace
import json
import subprocess
import unittest

import build_scalar_fpu_fma_arbiter792 as b


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = b.life.OUT/'scalar-fpu-fma-arbiter792-preflight-agent-20261008-01'
        cls.pre = json.loads((cls.out/'preflight.json').read_bytes())
        b.life.check(cls.pre['pins'])
        cls.commits = list(b.build.parse_spike_commits(cls.out/'spike.trace'))

    def audit(self, commits):
        return b.validate(commits, self.pre['symbols'])

    def test_actual_complete_reference(self):
        self.assertEqual(self.audit(self.commits), self.pre['counts'])

    def test_complement_values_are_finite_nonzero(self):
        self.assertEqual(b.C_VALUES[0] ^ b.C_VALUES[1], (1<<64)-1)
        for v in b.C_VALUES:
            self.assertNotIn((v >> 52) & 2047, (0,2047))

    def test_fma_wrong_result_rejected(self):
        rows = copy.deepcopy(self.commits)
        i = next(i for i,c in enumerate(rows) if c.instruction & 127 == 0x43)
        rows[i] = replace(rows[i], fpr_writes={5:b.C_VALUES[0]^1})
        with self.assertRaises(AssertionError): self.audit(rows)

    def test_wrong_rounding_mode_rejected(self):
        rows = list(self.commits)
        i = next(i for i,c in enumerate(rows) if c.instruction & 127 == 0x43)
        rows[i] = replace(rows[i], instruction=rows[i].instruction | (1<<12))
        with self.assertRaises(AssertionError): self.audit(rows)

    def test_missing_owner_rejected(self):
        rows = list(self.commits)
        i = next(i for i,c in enumerate(rows) if c.instruction & 127 == 0x43)
        del rows[i]
        with self.assertRaises(AssertionError): self.audit(rows)

    def test_signature_corruption_rejected(self):
        rows = list(self.commits)
        addr = self.pre['symbols']['g75_result']
        i = next(i for i,c in enumerate(rows) if (addr,56) in c.memory_accesses)
        rows[i] = replace(rows[i], memory_accesses=tuple((a,55 if a==addr else v)
                                                        for a,v in rows[i].memory_accesses))
        with self.assertRaises(AssertionError): self.audit(rows)

    def test_no_uninitialized_callee_saved_fpr_spills(self):
        saved = {8,9,*range(18,28)}
        for c in self.commits:
            if c.instruction & 127 == 0x27:
                self.assertNotIn((c.instruction>>20)&31, saved)

    def test_preflight_does_not_claim_runtime_collision(self):
        self.assertFalse(self.pre['EDA_started'])
        self.assertIn('UNPROVEN', self.pre['status'])
        self.assertIn('no guarantee', self.pre['runtime_gate'])

    def test_real_probe_tcl_names_and_one_run(self):
        probe = b.ROOT/'verification/coverage/scalar_fpu_fma_arbiter792_probe.tcl'
        script = '''
set observed {}
set runs 0
proc show {args} {return}
proc dump {args} {
    if {[lindex $args 0] eq "-add"} {lappend ::observed [lindex $args 1]}
    return 1
}
proc run {} {incr ::runs}
source {%s}
if {$runs != 1 || [llength $observed] != 33} {error "Incomplete probe"}
set wanted [format {%%s.gen_operation_groups[0].i_opgroup_block.fmt_out_ready} $ft]
if {[lsearch -exact $observed $wanted] < 0} {
    error "Generate scope quoting differs"
}
''' % probe
        p = subprocess.run(['tclsh'],input=script,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stderr,'')
        self.assertEqual(p.stdout.strip(),'FMA_ARB_PROBE_READY')

    def test_missing_probe_object_rejected(self):
        probe = b.ROOT/'verification/coverage/scalar_fpu_fma_arbiter792_probe.tcl'
        script = '''
proc show {args} {return}
proc dump {args} {return 0}
proc run {} {error "Must not run"}
source {%s}
''' % probe
        p = subprocess.run(['tclsh'],input=script,text=True,capture_output=True)
        self.assertEqual(p.returncode,1)
        self.assertIn('FMA_ARB_PROBE_ERROR Unavailable object',p.stdout)


if __name__ == '__main__':
    unittest.main()
