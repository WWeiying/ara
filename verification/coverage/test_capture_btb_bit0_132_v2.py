import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_btb_bit0_132_v2 as c
import test_capture_btb_bit0_132 as prior_tests


class Pipeline(prior_tests.EntryPipeline):
    # Reuse the original full native-file fixture, not its tests or permissive root mock.
    def fixture(self,out):
        config,_,names=super().fixture(out)
        config.update(protocol=c.PROTOCOL,origin_config_seal=c.ORIGIN_SHA,
                      root_display_aliases=['i_btb','btb'])
        (out/'config.json').write_text(json.dumps(config))
        selection=(out/'selection.tcl').read_text().replace(str(Path(c.original.__file__).resolve()),
                                                           str(Path(c.__file__).resolve()))
        (out/'selection.tcl').write_text(selection)
        return config,c.digest(out/'config.json'),names

    def pipeline(self,out,mutation=''):
        real_run=subprocess.run
        installed=(c.INSTALL/'ucliLoadCci.tcl').read_text()
        start=installed.index('proc exit { args } {')
        end=installed.index(';#YZF:',start)
        exit_proc=installed[start:end]
        def execute(args,**kwargs):
            script=kwargs['input']
            position=script.index('# Source through an actual proc')
            # Override only the earlier mock API implementations, before the real source.
            strict='''
set ::root ara_tb
set ::chosen {}
set ::readback 0
proc gui_list_get_selected {args} {
    if {$::mutation eq "token" && [llength $::chosen]} {return [list [list foreign]]}
    set ::readback 1
    return [list $::chosen]
}
proc gui_list_select {args} {
    if {$::root ne "ara_tb"} {error "Select must follow root restore"}
    if {[lindex $args 2] eq "-unselect"} {set ::chosen {};return}
    if {[lindex $args 2] ne "-select" || [lindex $args 3] ne [list $::btb_scope]} {error "Exact fullscope selection"}
    set ::chosen [list $::btb_scope]
    set ::readback 0
}
proc gui_covtable_setroot {args} {
    set next [lindex $args 2]
    if {$next ne "ara_tb" && ($next ne $::btb_scope || $::chosen ne [list $::btb_scope] || !$::readback)} {
        error "Rooting requires exact selected/readback fullscope"
    }
    set ::root $next
}
proc gui_list_expand {args} {
    if {[lindex $args 1] eq "CoverageTable.1" && $::root ne "ara_tb"} {error "Expand requires restored root"}
}
rename gui_list_get fixture_get
proc gui_list_get {args} {
    if {[lindex $args 1] eq "CoverageTable.1"} {
        set op [lindex $args 2]
        if {$op eq "-path" || ($op eq "-text" && [lindex $args 3] == 0)} {
            if {$::root eq "ara_tb"} {return ara_tb}
            if {$::mutation eq "root"} {return foreign}
            if {$::mutation eq "module"} {return btb}
        }
        if {$op eq "-meta"} {error "No root-wide row scan"}
        if {$op eq "-nextSibling" && $::root ne "ara_tb" && $::mutation eq "sibling"} {return 2}
        if {$op eq "-text" && [lindex $args 3] > 0 && $::root eq "ara_tb"} {error "No full-root metrics"}
    }
    return [eval fixture_get $args]
}
proc gui_list_action {args} {
    if {[lsearch -exact {i_btb btb} [lindex $args end]] < 0 || $::root ne $::btb_scope} {error "Exact rooted Toggle context"}
}
proc guiIsActive {} {return 1}
proc gui_exit {args} {
    if {$args ne "-noprompt"} {error "DVE rejects positional exit status"}
    ucli_exit 0
}
'''+exit_proc
            kwargs['input']=script[:position]+strict+script[position:]
            return real_run(args,**kwargs)
        with patch.object(c.original,'HOOK',c.HOOK),patch.object(prior_tests.subprocess,'run',execute):
            return super().pipeline(out,mutation)


class ProtocolTests(unittest.TestCase):
    def test_real_entry_requires_selected_token_and_accepts_only_compiled_aliases(self):
        for mutation in ('','module'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);_,_,result=Pipeline().pipeline(out,mutation)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(result.stdout.splitlines().count('BTB132_NATIVE_DONE'),1)
                observations=c.root_observations(out)
                self.assertEqual(observations['before'][4], 'btb' if mutation=='module' else 'i_btb')
                for stage in c.original.STAGES:c.metrics(out,stage)
                self.assertEqual(c.original.native_records((out/'first.el').read_text()),
                                 c.original.native_records((out/'second.el').read_text()))
                self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')
                self.assertNotIn('extra positional option',result.stdout+result.stderr)

    def test_foreign_root_sibling_and_token_fail_before_candidate_with_diagnostics(self):
        for mutation in ('root','sibling','token'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);_,_,result=Pipeline().pipeline(out,mutation)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                # GUI shutdown can return zero; completion/error gates must still reject qualification.
                self.assertTrue((out/'error.txt').exists())
                self.assertNotIn('BTB132_NATIVE_DONE',result.stdout)
                self.assertFalse((out/'first.el').exists())
                self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')
                if mutation!='token':
                    self.assertTrue((out/'root-contract.tsv').exists())
                    self.assertIn('BTB132_ROOT_OBSERVED',result.stdout)

    def test_reload_and_review_gates_retained(self):
        for mutation in ('reload','rejected'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);_,_,result=Pipeline().pipeline(out,mutation)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertTrue((out/'error.txt').exists())
                self.assertNotIn('BTB132_NATIVE_DONE',result.stdout)
                self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_observed_root_csv_disagreement_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);Pipeline().pipeline(out)
            file=out/'rooted_before.csv'
            with file.open(newline='') as stream:rows=list(csv.reader(stream))
            rows[1][2]='foreign'
            with file.open('w',newline='') as stream:csv.writer(stream).writerows(rows)
            with self.assertRaises(ValueError):c.metrics(out,'before')

    def test_actual_fresh_prepare_pins_original_failure_and_unchanged_candidate(self):
        with tempfile.TemporaryDirectory(dir=c.plan.OUT,prefix='btb132-v2-host-') as temp:
            out=Path(temp);out.rmdir()
            seal=c.prepare(out);config=c.read_config(out,seal)
            self.assertEqual(config['root_display_aliases'],['i_btb','btb'])
            self.assertEqual((out/'candidate.el').read_bytes(),(c.ORIGIN/'candidate.el').read_bytes())
            for path in (c.ORIGIN/'error.txt',c.ORIGIN/'terminal.json',c.ROOT_HELPER,
                         Path(c.original.__file__).resolve(),c.original.HOOK,
                         c.INSTALL/'ucliLoadCci.tcl',Path(c.__file__).resolve()):
                self.assertEqual(config['pins'][str(path)],c.digest(path))
            self.assertEqual(len(c.original.complement(config['inventory'])),8860)
            self.assertFalse((out/'execution.json').exists())
            self.assertIn(str(Path(c.__file__).resolve()),(out/'selection.tcl').read_text())


# The fixture class is not a unittest collection target: original tests refer to
# the original mock protocol and should not be reinterpreted as successor tests.
def load_tests(loader,tests,pattern):
    return loader.loadTestsFromTestCase(ProtocolTests)


if __name__=='__main__':unittest.main()
