import subprocess
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import observe_cvxif_point_identity789_v3 as owner


class ReadOnlyEntry(unittest.TestCase):
    def execute(self, body):
        return subprocess.run(['tclsh'], input=body, text=True, capture_output=True, timeout=10)

    def test_standalone_entry_exact_two_queries(self):
        # Execute the real entry through source boundaries; GUI command allowlist.
        script = '''
set ::point_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) /not-written
set calls {}
rename source original_source
proc source {path} {
    if {[file tail $path] eq "selection.tcl"} {
        set ::point_library library; set ::point_selector selector
        set ::cv_design design; set ::cv_vdb vdb; set ::cv_test test
        set ::point_scope ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind
    }
}
proc gui_open_cov {args} {lappend ::calls open}
'''+owner.HOOK.read_text()+'''
proc point789_snapshot {metric} {lappend ::calls $metric}
if {[catch {point789_session} message]} {puts stderr $message; exit 1}
if {$calls ne {open Line Branch}} {error "Wrong calls $calls"}
puts HOST_ENTRY_PASS
'''
        result = self.execute(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('HOST_ENTRY_PASS', result.stdout)

    def test_no_mutation_commands_in_entry(self):
        text = owner.HOOK.read_text()
        for command in ('gui_exclude_items', 'gui_exclusion_file', 'gui_exclusion ', 'cv_apply', 'cv_save', 'cv_reset'):
            self.assertNotIn(command, text)

    def test_actual_v2_selector_never_uses_meta_query(self):
        text = (owner.HERE/'capture_cvxif_passive_two_scope770_v2.tcl').read_text()
        text = text[text.index('proc cv_select_detail'):text.rindex('if {!$cv_external_test}')]
        prefix = '''
set selected {}
proc cv_need {ok why} {if {!$ok} {error $why}}
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -meta] >= 0} {error unsupported-meta}
    if {[lsearch -exact $args -count] >= 0} {return [llength $::selected]}
    if {[lsearch -exact $args -first] >= 0} {return [lindex $::selected 0]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {}; return}
    set ::selected [lindex $args end]
}
'''
        result = self.execute(prefix+text+'\ncv_select_detail exact exact\nputs SELECT_PASS\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SELECT_PASS', result.stdout)
        result = self.execute(prefix+text+'''
rename gui_list_get_selected actual_get
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -first] >= 0} {return foreign}
    return [eval actual_get $args]
}
if {![catch {cv_select_detail exact exact}]} {exit 1}
puts FOREIGN_REJECTED
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FOREIGN_REJECTED', result.stdout)

    def test_foreign_service_rejected_before_launch(self):
        with patch.object(owner, 'check', return_value={}), patch.object(Path, 'read_text', return_value='foreign.service'):
            with self.assertRaises(ValueError): owner.run(Path('/not-written'), 'seal', True)

    def test_real_recursive_walk_without_detail_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            script = 'set ::point_test_only 1\n' + owner.HOOK.read_text()+'''
proc cv_need {ok why} {if {!$ok} {error $why}}
proc p740_root {} {}
proc p740_select {scope} {if {$scope ne "exact_scope"} {error foreign_scope}}
proc gui_list_action {args} {set ::metric [lindex $args end-1]}
proc gui_covdetail_query {args} {return $::metric}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_get_property {args} {
    set column [lindex $args end]
    if {$column > 1} {error end}
    return [lindex {Name Identity} $column]
}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {
        if {[lindex $args end] eq "-firstChild"} {return root}
        if {[lindex $args end] eq "root"} {return child}
        return 0
    }
    if {[lsearch -exact $args -nextSibling] >= 0} {return 0}
    set handle [lindex $args end]
    if {[lsearch -exact $args -path] >= 0} {return /$handle}
    if {[lsearch -exact $args -meta] >= 0} {return meta/$handle}
    return label_$handle
}
proc gui_list_select {args} {error forbidden_detail_selection}
proc gui_list_get_selected {args} {error forbidden_selected_query}
set ::point_scope exact_scope
'''+ 'set ::env(DVE_COVERAGE_OUTPUT) '+owner.quote(directory)+'''
if {[catch {point789_snapshot Line; point789_snapshot Branch} message]} {puts stderr $message; exit 1}
puts WALK_PASS
'''
            result = self.execute(script)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('WALK_PASS', result.stdout)
            for metric in ('Line','Branch'):
                rows = owner.observation_rows((Path(directory)/('observed_'+metric+'_0.tsv')).read_text())
                self.assertEqual(len(rows), 2)

    def test_observation_rejects_fake_flags_missing_duplicate(self):
        header = 'path\tmeta\tname\texcluded\tcells\n'
        row = '/a\tmeta/a\tlabel\tUNOBSERVED\tcell\n'
        self.assertEqual(len(owner.observation_rows(header+row)), 1)
        for bad in (header, header+row+row, header+row.replace('UNOBSERVED','0'),
                    header+row.replace('UNOBSERVED','1'), header+'/a\tmeta/a\n'):
            with self.assertRaises(ValueError): owner.observation_rows(bad)

    def test_error_exit_uses_supported_gui_contract(self):
        text = owner.HOOK.read_text()
        self.assertNotIn('    exit 1', text)
        self.assertIn('    gui_exit -noprompt', text)
        self.assertIn('POINT789_READONLY_FAILED', text)

    def test_unsafe_tcl_literal_rejected(self):
        for value in ('bad{scope', 'bad\npath', 'bad\\path'):
            with self.assertRaises(ValueError): owner.quote(value)


class ReceiptBinding(unittest.TestCase):
    def setUp(self):
        self.out = Path('/sealed/output')
        roles = dict(launcher='/sealed/dve', xvfb_run='/sealed/xvfb-run',
                     executable='/sealed/dve.exe', architecture='/sealed/getarch')
        self.c = dict(identity=dict(roles=roles, executable=roles['executable'],
                     files=[dict(path=p, sha256='fixed') for p in roles.values()]))
        self.execution = dict(owner.receipt_base(self.out, 'seal', self.c),
                              command=owner.launch_command(self.out, self.c))
        process = dict(pid=42, exe=roles['executable'], cwd=str(self.out),
                       cgroup='0::/user.slice/'+owner.SERVICE, executable_sha256='fixed',
                       cmdline=['/sealed/dve.exe','-script',str(owner.HOOK)])
        self.live = dict(owner.receipt_base(self.out, 'seal', self.c), actual_dve=[process])
        self.terminal = copy.deepcopy(self.live)

    def gate(self):
        owner.receipt_gate(self.out, 'seal', self.c, self.execution, self.live, self.terminal)

    def test_exact_receipts_pass(self):
        self.gate()
        self.assertEqual(self.execution['command'][0], '/sealed/xvfb-run')

    def test_each_receipt_foreign_seal_rejected(self):
        for record in (self.execution, self.live, self.terminal):
            record['config_seal'] = 'foreign'
            with self.assertRaises(ValueError): self.gate()
            record['config_seal'] = 'seal'

    def test_each_receipt_foreign_tool_identity_rejected(self):
        for key in ('execution', 'live', 'terminal'):
            original = getattr(self, key)
            changed = copy.deepcopy(original)
            changed['identity']['files'][0]['sha256'] = 'foreign'
            setattr(self, key, changed)
            with self.assertRaises(ValueError): self.gate()
            setattr(self, key, original)

    def test_unsealed_role_rejected(self):
        self.c['identity']['roles']['xvfb_run'] = '/foreign/xvfb-run'
        with self.assertRaises(ValueError): owner.launch_command(self.out, self.c)

    def test_foreign_command_rejected(self):
        self.execution['command'][0] = '/foreign/xvfb-run'
        with self.assertRaises(ValueError): self.gate()

    def test_actual_process_mutations_rejected(self):
        for field, value in [('pid', True), ('exe','/foreign/dve.exe'),
                             ('cwd','/foreign'), ('executable_sha256','foreign'),
                             ('cgroup','0::/x/'+owner.SERVICE+'-suffix'), ('cmdline',[]),
                             ('cmdline',['/foreign/dve.exe','-script',str(owner.HOOK)]),
                             ('cmdline',['/sealed/dve.exe','-script','/foreign/entry.tcl'])]:
            original = self.live['actual_dve'][0][field]
            self.live['actual_dve'][0][field] = value
            self.terminal = copy.deepcopy(self.live)
            with self.assertRaises(ValueError): self.gate()
            self.live['actual_dve'][0][field] = original
            self.terminal = copy.deepcopy(self.live)

    def test_missing_or_duplicate_process_rejected(self):
        for processes in ([], self.live['actual_dve']*2):
            self.terminal['actual_dve'] = processes
            with self.assertRaises(ValueError): self.gate()


if __name__ == '__main__': unittest.main()

