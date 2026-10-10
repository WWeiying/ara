import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import capture_ff1_native904 as c


class FF1NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        static = json.loads(c.flags.STATIC.read_bytes())
        cls.config = dict(targets=904, plan=dict(scopes={}))
        for scope, group in static['scopes'].items():
            rows = []
            for r in group['rows']:
                p, bit = r['point'], r['calibration']['input_bit']
                rows.append(dict(point=p, target=r['target'], coordinate=p['native_id'] + ',' + p['vector'],
                    module_checksum=group['module_checksum'], metric_checksum=group['metric_checksum'],
                    calibrated_input_bit=bit, case_item=dict(name="52'b" + '0' * (51-bit) + '1' + 'z' * bit + ' ') if r['target'] else None))
            cls.config['plan']['scopes'][scope] = dict(branch=rows)

    def native(self, config=None):
        config = config or self.config
        lines = []
        for scope, metrics in config['plan']['scopes'].items():
            targets = [r for r in metrics['branch'] if r['target']]
            if not targets:
                continue
            lines += ['CHECKSUM: "%s %s"' % (targets[0]['module_checksum'], targets[0]['metric_checksum']), 'INSTANCE: ' + scope]
            for r in targets:
                p = r['point']
                lines += ['ANNOTATION: "' + c.ANNOTATION + '"',
                    'Branch %s "%s" "%s" (%s) "%s %s"' % (p['native_id'], p['attributes']['chksum'], p['expression'],
                        p['vector'], p['expression'], r['case_item']['name'])]
        return ('\n'.join(lines) + '\n').encode()

    def test_exact904_native_binding(self):
        self.assertEqual(len(c.bind_native(self.native(), self.config)), 904)

    def test_missing_extra_duplicate_rejected(self):
        raw = self.native()
        lines = raw.decode().splitlines()
        for changed in ('\n'.join(lines[:-2])+'\n', raw.decode()+lines[-2]+'\n'+lines[-1]+'\n', raw.decode()+'Toggle 0 "x"\n'):
            with self.subTest(), self.assertRaises(ValueError):
                c.bind_native(changed.encode(), self.config)

    def test_full_signature_and_checksums_strict(self):
        raw = self.native()
        for old, new in ((b'3572758954 2352628851', b'3572758954 1'), (b'4021640665', b'1'),
                         (b'frac_num[51:0]', b'frac_num[50:0]'), (b"52'b", b"51'b"),
                         (c.ANNOTATION.encode(), b'other note')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                c.bind_native(raw.replace(old, new, 1), self.config)

    def test_default_zero_target_rejected(self):
        changed = copy.deepcopy(self.config)
        scope = next(s for s, m in changed['plan']['scopes'].items() if any(r['target'] for r in m['branch']))
        r = next(r for r in changed['plan']['scopes'][scope]['branch'] if r['target'])
        r['calibrated_input_bit'] = -1
        with self.assertRaises(ValueError):
            c.bind_native(self.native(), changed)

    def test_compiled_parameters_strict(self):
        self.assertEqual(c.bind_parameters([dict(WIDTH=32, FpFmtConfig=40)], 32, 40)['WIDTH'], 32)
        for variants in ([], [dict(WIDTH=64, FpFmtConfig=40)], [dict(WIDTH=32, FpFmtConfig=56)],
                         [dict(WIDTH=32, FpFmtConfig=40)] * 2):
            with self.subTest(variants=variants), self.assertRaises(ValueError):
                c.bind_parameters(variants, 32, 40)

    def tcl_context(self, corrupt=False):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'sample.vdb/snps/coverage/db/testdata/one').mkdir(parents=True)
            (root / 'live-ready').touch()
            scopes = list(self.config['plan']['scopes'])
            plan = dict(design_vdb='/not-loaded/design.vdb', selected_test_vdb=str(root/'sample.vdb'),
                        scopes=self.config['plan']['scopes'])
            (root/'selection.tcl').write_text(c.common.selection(plan) +
                'set ff1_python {/usr/bin/python3}\nset ff1_driver {/not-run/driver.py}\n' +
                'set ff1_test_identity {' + str(root/'sample/one') + '}\n')
            script = '''set ff1_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
proc help args {return OK}
proc gui_open_cov args {error GATE_REACHED_NOT_EDA}
proc gui_list_action args {}
proc gui_covdetail_query args {return Branch}
proc gui_list_expand args {}
proc gui_list_get args {
    set option [lindex $args 2]
    set item [lindex $args 3]
    if {$option eq "-firstChild"} {
        if {$item eq ""} {return P}
        if {$item eq "P"} {return L0}
        return 0
    }
    if {$option eq "-nextSibling"} {
        if {$item eq "P"} {return 0}
        set n [string range $item 1 end]
        if {$n == 53} {return 0}
        return L[expr {$n + 1}]
    }
    if {$option eq "-childCount"} {return 0}
    if {$option eq "-path" && $item eq "P"} {return Item0}
    set n [string range $item 1 end]
    if {$option eq "-meta"} {return Branch0.$n}
    if {$option eq "-path"} {return Item0.Branch0.$n}
    error "UNEXPECTED $args"
}
set failed [catch {ff1_session} message]
if {!$failed || $message ne "GATE_REACHED_NOT_EDA"} {error "SESSION_CONTEXT $message"}
%s
foreach scope $dbg_scopes {
    array unset result
    array set result [ff1_metadata $scope]
    if {[array size result] != 54} {error INCOMPLETE}
}
puts CONTEXT_1728_PASS
''' % (c.HOOK, root, 'set dbg_keys([lindex $dbg_scopes 0]|branch) {0,0}' if corrupt else '')
            return subprocess.run([shutil.which('tclsh')], input=script, text=True, cwd=root, capture_output=True)

    def test_real_tcl_proc_source_working_dir_and_all1728_metadata(self):
        result = self.tcl_context()
        self.assertIn('CONTEXT_1728_PASS', result.stdout, result.stderr)
        self.assertEqual(result.stderr, '')

    def test_real_tcl_inventory_mismatch_rejected(self):
        result = self.tcl_context(True)
        self.assertNotIn('CONTEXT_1728_PASS', result.stdout)
        self.assertIn('FF1 complete observed/compiled selector inventory differs', result.stderr)


if __name__ == '__main__':
    unittest.main()
