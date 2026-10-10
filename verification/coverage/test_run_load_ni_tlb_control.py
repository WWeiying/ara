import subprocess
import unittest
from pathlib import Path
import run_load_ni_tlb_control as m


class Contract(unittest.TestCase):
    def test_fixed_command(self):
        c = m.make_command(m.PRE / 'input.elf', m.RUN)
        self.assertIn('+NO_FSDB', c)
        self.assertEqual(c.count('-ucli'), 1)
        self.assertEqual(c[-1], str(m.PROBE))
        self.assertIn('+COMMIT_TOHOST=80001000', c)
        self.assertNotIn('-debug_access+all', c)

    def test_independent_expected(self):
        v = m.expected({'lnt_root': 0x80008000}, 0x1800)
        self.assertEqual(v, [0x5555555555555555, 0x123456789abcdef0, 0,
                            0x123456789abcdef0, 0xfedcba9876543210,
                            0x8000000000080008, 0x20800, 0, 0x1800])

    def test_frozen_sources(self):
        pins = m.source_pins()
        self.assertEqual(pins[str(m.BUILD / 'build-source-pins.json')], m.SOURCE_SHA)
        self.assertIn(str(m.ROOT / 'hardware/deps/cva6/core/load_unit.sv'), pins)

    def probe(self, count):
        prefix = ('proc show {args} {return ok}\n'
                  'proc dump {args} {if {[lindex $args 0] eq "-file"} {return 1}; return %d}\n'
                  'proc run {} {puts MOCK_RUN}\n') % count
        return subprocess.run(['tclsh'], input=prefix + m.PROBE.read_text(), text=True,
                              capture_output=True, check=False)

    def test_actual_tcl_readonly_objects(self):
        r = self.probe(1)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(lines.count('LOAD_NI_PROBE_READY'), 1)
        objects = [x for x in lines if x.startswith('LOAD_NI_PROBE_OBJECT ')]
        self.assertEqual(len(objects), 18)
        self.assertEqual(len(set(objects)), 18)
        self.assertIn('MOCK_RUN', lines)
        self.assertIn('LOAD_NI_PROBE_OBJECT ' + m.LOAD + '.stall_ni', lines)

    def test_missing_object_fails_before_run(self):
        r = self.probe(0)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('LOAD_NI_PROBE_ERROR', r.stdout)
        self.assertNotIn('MOCK_RUN', r.stdout)

    def test_no_mutation_or_ecall(self):
        t = m.PROBE.read_text()
        commands = '\n'.join(line for line in t.splitlines() if not line.lstrip().startswith('#'))
        self.assertFalse(any(x in commands.split() for x in ('force', 'deposit', 'stop')))
        app = m.APP.read_text()
        self.assertNotIn('ecall', app)
        self.assertNotIn('nop', app)
        self.assertIn('volatile const struct guarded_word', app)


if __name__ == '__main__':
    unittest.main()
