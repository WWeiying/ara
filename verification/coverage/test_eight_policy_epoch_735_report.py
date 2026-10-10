"""Host-only735 identity, lifecycle preservation and real native Tcl regressions."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import eight_policy_epoch_735_report as r
import eight_policy_csv_fix_runtime_v2 as semantic


class Context(unittest.TestCase):
    def test_exact735_context_original_complete_checker(self):
        context,_=r.report.preparation_context()
        self.assertEqual((context.admission,context.seal,context.population),(r.ADMISSION,r.SEAL,735))
        self.assertIs(context.check_config.__func__.__code__,r.wiring.population.Context.check_config.__code__)
        with self.assertRaises(Exception):type(context)(r.ADMISSION,r.SEAL,732)
        with self.assertRaises(Exception):type(context)(r.ADMISSION,'0'*64,735)

    def test_integer_rebindings_have_reviewed_roles_no_line_or_coordinate(self):
        for entry in r.REBIND_AUDIT:
            if type(entry['before']) is int:
                self.assertEqual((entry['before'],entry['after']),(732,735))
                self.assertIn((entry['function'],entry['slot']),r.INTEGER_REBINDS)
        code=compile('def unknown():\n return 732\n','/sealed/source.py','exec').co_consts[0]
        with self.assertRaisesRegex(Exception,'Unreviewed732 constant'):r.rebound(code)
        self.assertEqual(r.report.read_six.__code__.co_firstlineno,
                         r.report_original.read_six.__code__.co_firstlineno)

    def test_thirteen_schema_chain_and_actual_precise_prefix(self):
        context,_=r.report.preparation_context()
        proof=context.cc_proof()
        self.assertEqual([row['population'] for row in proof['chain']],list(range(735,722,-1)))
        self.assertEqual(proof['chain'][0]['manifest_sha256'],r.SEAL)
        self.assertEqual(proof['chain'][3]['manifest_sha256'],r.wiring_base.root732.SEAL)
        self.assertFalse(proof['top_ledger_cc_required'])
        self.assertFalse(proof['history_identity_fabricated'])
        schemas=context.cc_proof.__func__.__globals__['SCHEMAS']
        self.assertEqual(schemas[735],r.SCHEMA)
        self.assertEqual(schemas[733],'STORE_FAULT_FLUSH_HISTORICAL_ADMISSION_V1')
        self.assertEqual(schemas[732],r.wiring_base.root732.SCHEMA)

    def test_duplicate_reordered_and_nonpass_population_rejected(self):
        validate=r.wiring.population.validate_population
        names=['vdb%d'%i for i in range(735)]
        bitmap=dict(tests=names)
        status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=735)
        design=str(r.report.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb')
        validate(bitmap,status,[design,*names],735)
        for b,s,inputs in ((dict(tests=names[:-1]+[names[0]]),status,[design,*names]),
                           (bitmap,dict(status='FAILED',aggregate_passed=735),[design,*names]),
                           (bitmap,status,[design,*reversed(names)])):
            with self.assertRaises(Exception):validate(b,s,inputs,735)


class Tcl(unittest.TestCase):
    def run_tcl(self,body):
        script='source {'+str(r.NATIVE_TCL)+'}\n'+body
        script='if {[catch {\n'+script+'\n} detail]} {puts stderr $detail; exit 1}\n'
        return subprocess.run(['/usr/bin/tclsh'],input=script,text=True,capture_output=True,timeout=30)

    def test_actual729_full_records_and_attribute_rejection(self):
        a=semantic.DEFAULT/'applied.el';b=semantic.DEFAULT/'reloaded.el'
        result=self.run_tcl('proc bytes {p} {set f [open $p r]; set raw [read $f]; close $f; return $raw}\n'
            'set a [bytes {'+str(a)+'}]\nset b [bytes {'+str(b)+'}]\n'
            'puts [nem_require_equal $a $b]\n'
            'set mutated [string map {1194113825 1194113826} $b]\n'
            'if {![catch {nem_require_equal $a $mutated}]} {error "attribute mutation accepted"}\n'
            'if {![catch {nem_records "$a$a"}]} {error "duplicates accepted"}\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'5892')

    def test_proc_context_exact_install_preserves_all_other_bytes(self):
        text=r.wiring_base.eight.prior.TCL.read_text()
        start=text.index('lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq')
        stop=text.index('"Combined EL actual reload bytes differ"',start)+len('"Combined EL actual reload bytes differ"')
        needle=text[start:stop]
        result=self.run_tcl('proc seven_replace_once {body needle replacement} {\n'
            'set first [string first $needle $body]\n'
            'if {$first<0 || [string first $needle $body [expr {$first+1}]]>=0} {error "not exactly once"}\n'
            'return [string replace $body $first [expr {$first+[string length $needle]-1}] $replacement]}\n'
            'proc qbsapp_session {} {BEFORE\n'+needle+'\nAFTER}\n'
            'nem_install\nset actual [info body qbsapp_session]\n'
            'if {[string first BEFORE $actual]<0 || [string first AFTER $actual]<0 || [string first nem_require_equal $actual]<0} {error "bad install"}\n'
            'if {![catch {nem_install}]} {error "repeated install accepted"}\n')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_blank_mixed_unknown_and_missing_attribute_rejected(self):
        raw='CHECKSUM: "1 2"\nINSTANCE: dut.q\nANNOTATION: "proof"\nBranch 1 "3" "x" (0) "x 1"\n'
        for malformed in (raw+'PROPERTY: "ignored"\n',raw.replace('ANNOTATION: "proof"\n',''),
                          raw+'\n',raw+'ANNOTATION: "p"\nCondition 2 "4" "y 1 -1" (2 "1")\n'):
            result=self.run_tcl('set raw {'+malformed+'}\nnem_records $raw\n')
            self.assertNotEqual(result.returncode,0)


class Preparation(unittest.TestCase):
    def test_payload_change_is_only_exact_install_hook_and_extra_pinned_helper(self):
        old=r.wiring_base.eight.TCL.read_bytes()
        base=semantic.DEFAULT
        payload=r.payloads(base)
        self.assertEqual(payload['eight-session-v2.tcl'],
                         old.replace(b'eight_initialize; qbsapp_session',b'eight_initialize; nem_install; qbsapp_session'))
        self.assertEqual(payload['native-exclusion-multiset-v2.tcl'],r.NATIVE_TCL.read_bytes())
        self.assertIn(r.NATIVE_TCL,r.dependencies())
        self.assertIn(r.TCL,r.dependencies())

    def test_fresh_output_and_all_stage_catalog_retained(self):
        output=r.report.OUT/'eight-policy-semantic-735-host-only-test'
        self.assertFalse(output.exists())
        paths={p.relative_to(output).as_posix() for p in r.report.generated_catalog(output)}
        for name in ('initial-empty.el','reset-empty.el','final-empty.el','session-final-empty.el',
                     'applied.el','reloaded.el','after-root.el','summary_raw.csv','summary_reset.csv'):
            self.assertIn(name,paths)
        for stage in r.wiring.eight.STAGES:
            self.assertIn('lzc/states_'+stage+'.tsv',paths)
            self.assertIn('snapshot/states_'+stage+'.csv',paths)
        with patch.dict(r.report.prepare.__globals__,OUT=Path('/not-approved')):
            with self.assertRaises(Exception):r.report.prepare(output)
        self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()

