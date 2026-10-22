"""Frozen real source/shape replay and adversarial host gates; never EDA."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import c910_lane23_padding1424_local as m


class Padding1424(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = m.evidence()
        cls.c = dict(instances=cls.proof['instances'])
        cls.el = m.candidate(cls.c)
        cls.texts = {Path(p).name: Path(p).read_text() for p in cls.proof['pins']
                     if Path(p).name in {Path(p).name for p in m.SOURCES}}
        cls.seals = {Path(p).name: s for p, s in cls.proof['pins'].items() if Path(p).name in cls.texts}

    def reject_el(self, text):
        with self.assertRaises(ValueError):
            m.el_gate(text, self.c)

    def test_real_frozen_eight_compiled_8_16(self):
        self.assertEqual(len(self.proof['instances']), 8)
        self.assertEqual(self.proof['directions'], 1424)
        self.assertFalse(self.proof['raw_physical_mapping'])
        self.assertFalse(self.proof['EDA_started'])
        self.assertEqual(len(m.el_gate(self.el, self.c)), 1424)
        for i in self.proof['instances']:
            self.assertEqual(len(i['typed_objects']), 210)
            m.wrapper_gate(i['compiled_wrapper'])

    def test_foreign_width_format_lane_rejected(self):
        for old, new in [('WIDTH=16,', 'WIDTH=32,'), ('FpFmtConfig=8,', 'FpFmtConfig=40,')]:
            with self.assertRaises(ValueError):
                m.wrapper_gate(self.proof['instances'][0]['compiled_wrapper'].replace(old, new))
        for old, new in [('gen_num_lanes[2]', 'gen_num_lanes[1]'), ('gen_lanes[0]', 'gen_lanes[4]'),
                         ('406590228', '406590229'), ('3969040510', '3969040511')]:
            self.reject_el(self.el.replace(old, new))

    def test_source_mutations_any_writer_or_wiring_rejected(self):
        for file, old, new in [
            ('fpnew_divsqrt_th_64_multi.sv', "default:            divsqrt_fmt = 4'b0010;", "default: divsqrt_fmt = 4'b1000;"),
            ('ct_vfdsu_scalar_dp.v', "ex1_double         <= 1'b0;", "ex1_double <= 1'b1;"),
            ('ct_vfdsu_prepare.v', "42'b0", "42'b1"),
            ('ct_vfdsu_ff1.v', "{frac_num[50:0],1'b0}", "{1'b0,frac_num[51:1]}"),
            ('ct_vfdsu_srt.v', "{2'b00,ex1_remainder[59:1]}", "{2'b01,ex1_remainder[59:1]}")]:
            t = dict(self.texts)
            self.assertIn(old, t[file])
            t[file] = t[file].replace(old, new)
            with self.assertRaises(ValueError):
                m.source_guard(t, self.seals)
        for file in self.texts:
            t = dict(self.texts)
            t[file] += '\nassign foreign_override = 1;\n'
            with self.assertRaises(ValueError):
                m.source_guard(t, self.seals)

    def test_every_ff1_case_is_checked_not_only_examples(self):
        for shift in range(1, 52):
            t = dict(self.texts)
            token = "{frac_num[%d:0],%d'b0}" % (51 - shift, shift)
            t['ct_vfdsu_ff1.v'] = t['ct_vfdsu_ff1.v'].replace(token, "{52'b1}")
            # Re-seal fixture deliberately: semantic branch check must still reject.
            seals = dict(self.seals)
            seals['ct_vfdsu_ff1.v'] = m.hashlib.sha256(t['ct_vfdsu_ff1.v'].encode()).hexdigest()
            with self.assertRaises(ValueError):
                m.source_guard(t, seals)

    def test_normal_denormal_remainder_full_writer_semantics(self):
        for old, new in [("42'b0", "42'b1"), ("45'b0", "45'b1"),
                         ('ex1_div_srt_op1[52:0];', 'ex1_div_srt_op0[52:0];'),
                         ("{ex1_oper0_id_frac[51:0],1'b0}", "{1'b0,ex1_oper0_id_frac[51:0]}"),
                         ("{6'b0,ex1_sqrt_srt_op0[52:0],1'b0}", "{6'b0,ex1_sqrt_srt_op0[52:0],1'b1}"),
                         ('(ex1_oper0_frac[51:0]', '(ex1_oper0[51:0]')]:
            t = dict(self.texts)
            file = 'ct_vfdsu_prepare.v'
            self.assertIn(old, t[file])
            t[file] = t[file].replace(old, new)
            seals = dict(self.seals)
            seals[file] = m.hashlib.sha256(t[file].encode()).hexdigest()
            with self.assertRaises(ValueError):
                m.source_guard(t, seals)
        for name in ('ex1_oper0_frac', 'ex1_divisor', 'ex1_remainder', 'sqrt_remainder'):
            for suffix in ('', '[0]'):
                t = dict(self.texts)
                file = 'ct_vfdsu_prepare.v'
                t[file] += '\nassign %s%s = 1;\n' % (name, suffix)
                seals = dict(self.seals)
                seals[file] = m.hashlib.sha256(t[file].encode()).hexdigest()
                with self.assertRaises(ValueError):
                    m.source_guard(t, seals)

    def test_paired_direction_native_exports(self):
        lines = []
        for line in self.el.splitlines():
            if line.startswith('Toggle '):
                lines.extend(line.replace('Toggle ', 'Toggle ' + d + ' ', 1) for d in ('0to1', '1to0'))
            else:
                lines.append(line)
        split = '\n'.join(lines) + '\n'
        self.assertEqual(m.el_gate(split, self.c), m.el_gate(self.el, self.c))
        self.reject_el(split.replace('Toggle 1to0 ', 'Toggle 0to1 ', 1))
        self.reject_el('\n'.join(lines[:-1]) + '\n')

    def test_whole_ip_object_and_adjacent_bits_never_accepted(self):
        line = next(l for l in self.el.splitlines() if l.startswith('Toggle '))
        for bad in ['Toggle initial_divisor_in "logic initial_divisor_in[55:0]"',
                    'Toggle initial_divisor_in [45] "logic initial_divisor_in[55:0]"',
                    'Toggle initial_remainder_in [42] "logic initial_remainder_in[60:0]"',
                    'Toggle initial_remainder_in [58] "logic initial_remainder_in[60:0]"',
                    'Toggle initial_divisor_in [44:0] "logic initial_divisor_in[44:0]"',
                    'Toggle forever_cpuclk "logic forever_cpuclk"', 'Fsm *', 'Line *']:
            self.reject_el(self.el.replace(line, bad, 1))
        self.reject_el('\n'.join(l for l in self.el.splitlines() if not l.startswith('Toggle ')))
        self.reject_el(self.el + line + '\n')
        self.reject_el(self.el.replace(m.ANNOTATION, 'startup X waived'))
        self.reject_el(self.el + 'CHECKSUM: "406590228 3969040510"\n')
        self.reject_el(self.el.replace('ANNOTATION: "' + m.ANNOTATION + '"\n', '', 1))

    def test_existing_whole_parent_partial_ownership(self):
        s = m.scopes()[0]
        for name in ('initial_divisor_in', 'initial_remainder_in'):
            with patch.object(m.policy.stable, 'semantic', return_value=(set(), {(s, '', name, '', (), (), '0to1'): 1})):
                with self.assertRaises(ValueError):
                    m.collision_gate('fixture')
        for scope in (s, s.rsplit('.', 1)[0], 'ara_tb.dut.i_ara_soc'):
            with patch.object(m.policy.stable, 'semantic', return_value=({(scope, '', '', 'WHOLE_SCOPE')}, {})):
                with self.assertRaises(ValueError):
                    m.collision_gate('fixture')

    def bit_text(self, stage):
        rows = ['signal\tbit\tpath\tmeta\tname\tcoverage\t0to1\t1to0']
        for name, w in m.WIDTHS.items():
            for bit in range(w):
                label = '%s[%d]' % (name, bit)
                state = str(int(stage in ('applied', 'reloaded') and bit in m.BITS[name]))
                coverage = '0.00%' if bit in m.BITS[name] else '100.00%'
                rows.append('\t'.join([name, str(bit), label, label, label, coverage, state, state]))
        return '\n'.join(rows) + '\n'

    def test_all117_physical_bits_and_five_phases(self):
        i = self.c['instances'][0]
        before = m.bit_gate(self.bit_text('before'), i, 'before')
        self.assertEqual(len(before), 117)
        for stage in m.STAGES:
            m.bit_gate(self.bit_text(stage), i, stage, before)

    def test_bit_missing_duplicate_range_hit_direction_token_drift(self):
        text = self.bit_text('before')
        for bad in ['\n'.join(text.splitlines()[:-1]) + '\n',
                    text + text.splitlines()[1] + '\n',
                    text.replace('initial_divisor_in[0]', 'initial_divisor_in[56]'),
                    text.replace('0.00%', '50.00%', 1), text.replace('\t0\t0', '\t0\t1', 1)]:
            with self.assertRaises(ValueError):
                m.bit_gate(bad, self.c['instances'][0], 'before')
        previous = m.bit_gate(text, self.c['instances'][0], 'before')
        changed = self.bit_text('applied').replace('initial_divisor_in[45]', 'foreign45')
        with self.assertRaises(ValueError):
            m.bit_gate(changed, self.c['instances'][0], 'applied', previous)
        changed = self.bit_text('applied').replace('100.00%', '50.00%', 1)
        with self.assertRaises(ValueError):
            m.bit_gate(changed, self.c['instances'][0], 'applied', previous)

    def object_text(self, i):
        rows = ['handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay']
        for j, n in enumerate(i['typed_objects']):
            label = n['name'] + ('' if n['kind'] == 'node' else '[%s:%s]' % (n['left'], n['right']))
            role = 'port' if n['portnode'] in ('2', '3') else 'signal'
            rows.append('\t'.join([str(j), 'Item%d' % j, 'Item%d' % j, label, role, '0.00%', '0.00%']))
        return '\n'.join(rows) + '\n'

    def test_full_object_complement_protects_arithmetic_controls_outputs(self):
        i = self.c['instances'][0]
        text = self.object_text(i)
        before = m.ptw.bind(i, text)
        self.assertEqual(len(before), 210)
        with self.assertRaises(ValueError):
            m.ptw.bind(i, '\n'.join(text.splitlines()[:-1]) + '\n')
        for label in set(before) - set(m.ptw.labels(i)):
            changed = copy.deepcopy(before)
            changed[label]['display'] = 'Excluded'
            with self.assertRaises(ValueError):
                m.ptw.soc.stage_gate(i, before, changed, 'applied')

    def test_no_launch_mode_and_hash_drift(self):
        self.assertNotIn('subprocess', vars(m))
        with patch.object(m.life, 'digest', return_value='0' * 64):
            with self.assertRaises(ValueError):
                m.evidence()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                m.prepare(Path(d))

    def test_actual_sourced_tcl_five_phases_host_only(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            sample = out / 'sample.vdb'
            (sample / 'snps/coverage/db/testdata/host').mkdir(parents=True)
            c = dict(self.c, design='host-design', vdb=str(sample), test=str(out / 'sample/host'))
            (out / 'selection.tcl').write_text(m.selection(c))
            (out / 'candidate.el').write_text(self.el)
            for index, i in enumerate(c['instances']):
                (out / ('model_%d.tsv' % index)).write_text(self.object_text(i))
            harness = r'''
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(C1424_CONFIG_SEAL) host-only
set c1424_test_only 1
source {%s}
set calls {}
set phase before
array set expanded {initial_divisor_in 0 initial_remainder_in 0}
proc c1424_gate {args} {lappend ::calls $args}
proc soc_audit {stage} {
    set ::phase $stage
    for {set i 0} {$i < 8} {incr i} {
        file copy [file join $::env(DVE_COVERAGE_OUTPUT) model_$i.tsv] \
            [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_$i.tsv]
    }
}
proc p740_select {scope} {return $scope}
proc p740_root {} {}
proc gui_list_action {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc help {args} {}
proc gui_open_cov {args} {}
proc csr_select {path} {set ::selected $path}
proc csr_rows {args} {
    set rows {}
    foreach name {initial_divisor_in initial_remainder_in} width {56 61} {
        if {$::expanded($name)} {
            for {set b 0} {$b < $width} {incr b} {
                set label "${name}\[$b\]"
                lappend rows [list $label $label $label]
            }
        } else {
            set label "${name}\[[expr {$width-1}]:0\]"
            lappend rows [list $label $label $label]
        }
    }
    return $rows
}
proc gui_cov_tgl_double_click {args} {
    set path [lindex $args end]
    regexp {^(initial_divisor_in|initial_remainder_in)} $path ignored name
    set ::expanded($name) [expr {!$::expanded($name)}]
}
proc target {path} {
    if {![regexp {^(initial_divisor_in|initial_remainder_in)\[([0-9]+)\]$} $path ignored n b]} {error "No bit"}
    return [expr {($n eq "initial_divisor_in" && $b <= 44) || \
        ($n eq "initial_remainder_in" && ($b <= 41 || $b >= 59))}]
}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {return root}
    if {[target [lindex $args end]]} {return 0.00%%} else {return 100.00%%}
}
proc gui_exclusion {args} {
    return [expr {$::phase in {applied reloaded} && [target $::selected]}]
}
proc qc_save {name} {
    set dest [file join $::env(DVE_COVERAGE_OUTPUT) $name]
    if {$name in {first.el second.el}} {
        file copy [file join $::env(DVE_COVERAGE_OUTPUT) candidate.el] $dest
    } else {set f [open $dest w]; close $f}
}
proc qc_reset {} {}
proc mq_load {args} {}
c1424_session
if {$calls ne {check {inventory --stage before} {inventory --stage applied} {el --file first.el} {inventory --stage reset} {inventory --stage reloaded} {el --file second.el} {inventory --stage final}}} {error "Wrong phase order: $calls"}
puts C1424_HOST_PASS_NO_EDA
''' % (out, m.TCL)
            result = subprocess.run(['tclsh'], input=harness, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertIn('C1424_HOST_PASS_NO_EDA', result.stdout)
            for stage in m.STAGES:
                m.inventory(out, c, stage)
            self.assertEqual(m.el_gate((out / 'first.el').read_text(), c),
                             m.el_gate((out / 'second.el').read_text(), c))
            self.assertEqual((out / 'selected_tests.txt').read_text().splitlines(), [c['test']])


if __name__ == '__main__':
    unittest.main()
