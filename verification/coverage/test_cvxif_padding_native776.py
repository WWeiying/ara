import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

import cvxif_padding_native776 as p


def config():
    proof=p.life.read_bound(p.PROOF,p.PROOF_SHA);instances=[]
    for scope in p.proof.SCOPES:
        targets=[s for s in proof['targets'] if s['scope']==scope]
        signals=[dict(name=s['name'],scalar=False,left=1023,right=0,bits=s['bits'],
                      native_label=s['name']+'[1023:0]') for s in targets]
        others=[]
        for node in proof['protected_by_scope'][scope]:
            if node['kind']=='arrays':others.append(dict(ET.fromstring(node['xml']).attrib,tag='arrays'))
            else:others.append(dict({k:v for k,v in node.items() if k not in ('scope','kind','serialized_offset')},tag=node['kind']))
        labels=[s['native_label'] for s in signals]+[p.labels.label(ET.Element(n['tag'],{k:v for k,v in n.items() if k!='tag'})) for n in others]
        instances.append(dict(scope=scope,design_module_checksum=targets[0]['module_checksum'],toggle_checksum=targets[0]['checksum'],
            signals=signals,protected_shape=others,all_typed_labels=labels,
            retained_target_bits={s['name']:list(range(min(s['bits']))) for s in signals}))
    return dict(schema=p.SCHEMA,baseline=776,timeout_seconds=900,launch_authorized=False,
                owning_service_unit='ara-cvxif-test.service',owner_uid=1002,
                expected_cgroup=p.service_cgroup('ara-cvxif-test.service',1002),
                population_application=False,DUT_functional_gain=False,instances=instances)


def compact_el(c):
    lines=[]
    for i in c['instances']:
        lines+=['CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"','INSTANCE: '+i['scope']]
        for s in i['signals']:
            lines.append('Toggle '+s['name']+' [1023:'+str(min(s['bits']))+'] "logic '+s['native_label']+'"')
    return '\n'.join(lines)+'\n'


def snapshot(i,active=False):
    targets={s['native_label'] for s in i['signals']}
    lines=['handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay']
    for k,label in enumerate(i['all_typed_labels']):
        cov='Excluded' if active and label in targets else '0.00%'
        lines.append('\t'.join([str(k+1),label,label,label,'port' if label in targets else 'signal',cov,'both']))
    return '\n'.join(lines)+'\n'


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=config();cls.text=compact_el(cls.c)

    def test_exact_physical_ranges(self):
        p.contract(self.c);self.assertEqual(len(p.parse_el(self.text,self.c)),18516)

    def test_candidate_both_directions_equivalent(self):
        self.assertEqual(p.parse_el(p.native.primitive.candidate(self.c),self.c),p.parse_el(self.text,self.c))

    def rejected(self,text):
        with self.assertRaises(ValueError):p.parse_el(text,self.c)

    def test_low_bit_with_same_aggregate_rejected(self):
        # A native vector can show Excluded with either bit set: only EL distinguishes them.
        self.rejected(self.text.replace('[1023:98]','[1023:97]',1))

    def test_whole_vector_rejected(self):self.rejected(self.text.replace(' [1023:98]','',1))
    def test_extra_protected_object_rejected(self):self.rejected(self.text+'Toggle req_valid [0] "logic req_valid"\n')
    def test_wrong_bounds_rejected(self):self.rejected(self.text.replace('[1023:98]','[1024:98]',1))
    def test_missing_bit_rejected(self):self.rejected(self.text.replace('[1023:98]','[1022:98]',1))
    def test_missing_direction_rejected(self):self.rejected(self.text.replace('Toggle axi_ar_payload_i','Toggle 0to1 axi_ar_payload_i',1))
    def test_duplicate_direction_rejected(self):
        self.rejected(self.text+'Toggle axi_b_payload [1023:7] "logic axi_b_payload[1023:0]"\n')
    def test_wrong_checksum_rejected(self):self.rejected(self.text.replace('498965595','498965596',1))
    def test_scope_injection_rejected(self):self.rejected(self.text.replace(p.proof.SCOPE,p.proof.SCOPE+'.other',1))
    def test_type_net_not_logic_alias(self):self.rejected(self.text.replace('"logic axi_ar_payload_i','"net axi_ar_payload_i',1))
    def test_signature_bounds_rejected(self):self.rejected(self.text.replace('"logic axi_ar_payload_i[1023:0]"','"logic axi_ar_payload_i[1022:0]"',1))
    def test_unknown_metric_rejected(self):self.rejected(self.text+'Branch 0\n')
    def test_truncation_rejected(self):self.rejected(self.text.rstrip('\n'))

    def stages(self):
        i=self.c['instances'][0]
        return i,{s:snapshot(i,s in ('selected','reloaded')) for s in p.STAGES}

    def test_five_stage_complement(self):
        i,s=self.stages();self.assertEqual(p.audit(i,s),(41,36))

    def test_protected_percentage_changed(self):
        i,s=self.stages();name=i['all_typed_labels'][-1]
        s['selected']=s['selected'].replace(name+'\tsignal\t0.00%',name+'\tsignal\t100.00%')
        with self.assertRaises(ValueError):p.audit(i,s)

    def test_reset_target_not_restored(self):
        i,s=self.stages();s['final']=s['selected']
        with self.assertRaises(ValueError):p.audit(i,s)

    def test_native_extra_row_protected(self):
        i,s=self.stages();extra='999\textra\textra\textra\tsignal\t0.00%\tboth\n'
        s={stage:text+extra for stage,text in s.items()};s['reloaded']=s['reloaded'].replace('extra\tsignal\t0.00%','extra\tsignal\tExcluded')
        with self.assertRaises(ValueError):p.audit(i,s)

    def test_missing_before_object_rejected(self):
        i,s=self.stages();s={stage:'\n'.join(text.splitlines()[:-1])+'\n' for stage,text in s.items()}
        with self.assertRaises(ValueError):p.audit(i,s)

    def test_wrong_low_complement_contract_rejected(self):
        c=copy.deepcopy(self.c);c['instances'][0]['retained_target_bits']['axi_ar_payload_i'].pop()
        with self.assertRaises(ValueError):p.contract(c)

    def test_no_launch_without_seal(self):
        with self.assertRaises(ValueError):p.run(Path('/unused'),None,None)

    def terminal(self):
        c=dict(self.c,identity=dict(executable='/frozen/dve.exe'),pins={'/frozen/dve.exe':'ab'*32})
        t=dict(returncode=0,timeout=False,actual_dve=[dict(pid=123,exe='/frozen/dve.exe',cwd='/out',
            cgroup=c['expected_cgroup'],exe_sha256='ab'*32)])
        return c,t

    def test_strict_terminal_integer0(self):
        c,t=self.terminal();p.terminal_gate(t,c,Path('/out'))

    def test_bool_float_string_return_rejected(self):
        c,t=self.terminal()
        for v in (False,True,0.0,'0',None):
            with self.subTest(v=v),self.assertRaises(ValueError):p.terminal_gate(dict(t,returncode=v),c,Path('/out'))

    def test_timeout_requires_boolfalse(self):
        c,t=self.terminal()
        for v in (True,0,0.0,'false',None):
            with self.subTest(v=v),self.assertRaises(ValueError):p.terminal_gate(dict(t,timeout=v),c,Path('/out'))

    def test_foreign_service_cgroup_rejected(self):
        c,t=self.terminal();t['actual_dve'][0]['cgroup']=c['expected_cgroup']+'-child'
        with self.assertRaises(ValueError):p.terminal_gate(t,c,Path('/out'))

    def test_executable_hash_rejected(self):
        c,t=self.terminal();t['actual_dve'][0]['exe_sha256']='00'*32
        with self.assertRaises(ValueError):p.terminal_gate(t,c,Path('/out'))

    def test_bool_pid_rejected(self):
        c,t=self.terminal();t['actual_dve'][0]['pid']=True
        with self.assertRaises(ValueError):p.terminal_gate(t,c,Path('/out'))

    def test_cgroup_parser_exact_path(self):
        c,_=self.terminal()
        self.assertEqual(p.cgroup_path('0::'+c['expected_cgroup']+'\n'),c['expected_cgroup'])
        self.assertEqual(p.cgroup_path('1:name=systemd:'+c['expected_cgroup']+'\n'),c['expected_cgroup'])

    def test_conflicting_cgroup_rejected(self):
        with self.assertRaises(ValueError):p.cgroup_path('0::/a\n1:name=systemd:/b\n')

    def test_terminal_log_snapshots_ignore_later_tails(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'DVEfiles').mkdir()
            for n in ('launcher.log','DVEfiles/dve_gui.log'):(out/n).write_text('original terminal\n')
            logs=p.terminal_logs(out)
            pins={str(out/'terminal-evidence'/n):p.life.digest(out/'terminal-evidence'/n) for n in logs}
            (out/'capture-result.json').write_text(json.dumps(dict(pins=pins)))
            for n in logs:(out/n).write_text('original terminal\nfuture appended tail\n')
            self.assertEqual(p.terminal_logs(out),logs)
            self.assertNotIn(str(out/'launcher.log'),pins)

    def test_terminal_log_snapshot_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'DVEfiles').mkdir()
            for n in ('launcher.log','DVEfiles/dve_gui.log'):(out/n).write_text('terminal\n')
            logs=p.terminal_logs(out)
            pins={str(out/'terminal-evidence'/n):p.life.digest(out/'terminal-evidence'/n) for n in logs}
            (out/'capture-result.json').write_text(json.dumps(dict(pins=pins)))
            (out/'terminal-evidence/launcher.log').write_text('tampered\n')
            with self.assertRaises(ValueError):p.terminal_logs(out)

    def test_real_tcl_complete_session_one_open_five_stages(self):
        """Execute the actual frozen Tcl procedures, not a synthetic lifecycle."""
        tclsh=shutil.which('tclsh');self.assertIsNotNone(tclsh)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'candidate.el').write_text(self.text)
            selections='set qc_design design\nset qc_vdb sample\nset qc_test test\nset qc_python python\nset qc_helper helper\nset qc_instances {}\n'
            names=''
            for k,i in enumerate(self.c['instances']):
                names+='set names('+str(k)+') [list '+' '.join('{'+n+'}' for n in i['all_typed_labels'])+']\n'
                selections+='lappend qc_instances [list {'+i['scope']+'} [list '+' '.join('{'+s['native_label']+'}' for s in i['signals'])+']]\n'
            (out/'selection.tcl').write_text(selections)
            script='set ::qc_test_only 1\nsource {'+str(p.HERE/'cva6_fixed_fields_native768.tcl')+'}\n'
            script+='set ::env(DVE_COVERAGE_OUTPUT) {'+str(out)+'}\n'+names
            script+='''
set opens 0; set active 0; set loads 0; set resets 0; set audits 0; set checked 0
proc gui_open_cov args {incr ::opens; if {$::opens != 1} {error "second database open"}}
proc gui_list_expand args {}
proc gui_process_events args {}
proc gui_covdetail_query args {return Toggle}
proc gui_list_action args {
    incr ::audits
    set ::owner [expr {[string match *.cvxif [lindex $args end]] ? 1 : 0}]
}
proc gui_list_get_property args {
    set c [lindex $args end]; if {$c >= 4} {error end}
    return [lindex {Variable Type Coverage Display} $c]
}
proc gui_list_get args {
    set op [lindex $args 2]; set handle [lindex $args end]
    set n [llength $::names($::owner)]
    if {$op eq "-firstChild"} {if {[llength $args]==3} {return 1};return 0}
    if {$op eq "-nextSibling"} {if {$handle < $n} {return [expr {$handle+1}]};return 0}
    set name [lindex $::names($::owner) [expr {$handle-1}]]
    if {$op eq "-path" || $op eq "-meta"} {return $name}
    set col [lindex $args 3]
    if {$col==0} {return $name}
    if {$col==1} {return signal}
    if {$col==2} {if {$::active && [string match axi_*_payload* $name]} {return Excluded};return 0.00%}
    return both
}
proc gui_exclusion args {
    if {[lindex $args 0] eq "-reset"} {set ::active 0;incr ::resets}
}
proc gui_cov_excl_review args {return 1}
proc gui_exclusion_file args {
    set mode [lindex $args 0];set path [lindex [lindex $args end] 0]
    if {$mode eq "-load"} {set ::active 1;incr ::loads;return}
    set f [open $path w]
    if {$::active} {
        set in [open [file join $::env(DVE_COVERAGE_OUTPUT) candidate.el] r]
        puts -nonewline $f [read $in];close $in
    }
    close $f
}
proc exec args {incr ::checked;return 18516}
if {[catch {qc_session} reason]} {puts stderr $reason;puts stderr $::errorInfo;exit 1}
if {$opens!=1 || $loads!=2 || $resets!=2 || $audits!=10 || $checked!=2} {puts stderr "lifecycle mismatch";exit 1}
puts HOST_FIVE_STAGE_DONE
'''
            result=subprocess.run([tclsh],input=script,text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
            self.assertIn('HOST_FIVE_STAGE_DONE',result.stdout)
            for name in ('initial-empty.el','reset-empty.el','final-empty.el'):self.assertEqual((out/name).read_bytes(),b'')
            self.assertEqual(p.parse_el((out/'first.el').read_text(),self.c),p.parse_el((out/'second.el').read_text(),self.c))
            for k,i in enumerate(self.c['instances']):p.audit(i,{stage:(out/f'native_{stage}_{k}.tsv').read_text() for stage in p.STAGES})


if __name__=='__main__':unittest.main()
