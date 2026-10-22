import copy
import csv
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_rvh_branch_full_726 as subject


class FullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan=json.loads((subject.PLAN_ROOT/'native-plan.json').read_bytes())
        cls.config=dict(schema='RVH_FULL247_NATIVE_MEASUREMENT_V1',source_plan_seal=subject.PLAN_SHA,
            pilot_result_seal=subject.PILOT_RESULT_SHA,
            plan=dict(scopes=plan['full_scopes'],selected_test_vdb=str(subject.SAMPLE),design_vdb=plan['design_vdb']),
            targets={'branch':247},protected={'branch':1533},annotation=subject.ANNOTATION,
            timeout_seconds=10500,application_approval=False,launch_approved=False,
            automatic_retry=False,full247_authorized=False)

    def raw(self, config):
        lines=[]
        for scope,metrics in config['plan']['scopes'].items():
            rows=[r for r in metrics['branch'] if r['target']]
            if not rows:continue
            lines+=['CHECKSUM: "%s %s"' % (rows[0]['module_checksum'],rows[0]['metric_checksum']), 'INSTANCE: '+scope]
            for row in rows:
                p=row['point'];gen=p['attributes'].get('generate_info')
                annotation=subject.ANNOTATION if gen is None else 'vcs_gen_start:'+gen+':vcs_gen_end:'+subject.ANNOTATION
                lines+=['ANNOTATION: "'+annotation+'"', 'Branch %s "%s" "%s" (%s) "SYNTHETIC_NOT_NATIVE_MEASUREMENT"' % (
                    p['native_id'],p['attributes']['chksum'],subject.pilot.quoted(p['expressions'][0]['exprstr']),p['vector'])]
        return ('\n'.join(lines)+'\n').encode()

    def test_exact_full_contract_reject_scope_protection_target_drift(self):
        subject.validate_config(self.config)
        for key in ('targets','protected'):
            c=copy.deepcopy(self.config);c[key]['branch']-=1
            with self.assertRaises(ValueError):subject.validate_config(c)
        c=copy.deepcopy(self.config);next(iter(c['plan']['scopes'].values()))['branch'].pop()
        with self.assertRaises(ValueError):subject.validate_config(c)

    def test_all247_native_source_fields_and_generate_annotations(self):
        self.assertEqual(len(subject.bind_native(self.raw(self.config),self.config)),247)
        for change in ('checksum','expr','generate','scope'):
            raw=self.raw(self.config)
            if change=='checksum':raw=raw.replace(b'CHECKSUM: "',b'CHECKSUM: "1',1)
            elif change=='expr':raw=raw.replace(b'"1\'b0"',b'"1\'b1"',1)
            elif change=='generate':raw=raw.replace(b'i=0:vcs_gen_end:',b'i=1:vcs_gen_end:',1)
            else:raw=raw.replace(b'INSTANCE: ara_tb.',b'INSTANCE: wrong.',1)
            with self.subTest(change=change),self.assertRaises(ValueError):subject.bind_native(raw,self.config)
        with self.assertRaises(ValueError):subject.bind_native(self.raw(self.config)+b'Toggle x "x"\n',self.config)

    def test_generate_not_fixed_i0_but_exact_compiled_group(self):
        c=copy.deepcopy(self.config)
        for metrics in c['plan']['scopes'].values():
            for row in metrics['branch']:
                if row['target'] and row['point']['attributes'].get('generate_info'):
                    row['point']['attributes']['generate_info']='i=3,j=12'
        raw=self.raw(c)
        self.assertEqual(len(subject.bind_native(raw,c)),247)
        with self.assertRaises(ValueError):subject.bind_native(raw.replace(b'i=3,j=12',b'i=3,j=13'),c)
        for unsafe in ('x\nEL','x"','x\\','vcs_gen_end:', 'x\0'):
            self.assertFalse(subject.generate_valid(unsafe))

    def test_all1780_five_stages_protection_missing_identity_rejection(self):
        with tempfile.TemporaryDirectory(dir=subject.prepared.static.OUT) as d:
            path=Path(d)/'audit.tsv'
            rows=[(scope,r) for scope,m in self.config['plan']['scopes'].items() for r in m['branch']]
            def write(stage,missing=False,protected=False,identity=False):
                with path.open('w',newline='') as f:
                    w=csv.writer(f,delimiter='\t');w.writerow(['scope','metric','coordinate','meta','path','excluded'])
                    for scope,r in (rows[:-1] if missing else rows):
                        sid,vid=r['coordinate'].split(',');meta='Branch'+sid+'.'+vid
                        state=int(stage in ('selected','reloaded') and r['target'])
                        if protected and not r['target']:state=1
                        w.writerow([scope,'branch',r['coordinate'],meta,('WRONG' if identity else 'Item'+sid+'.'+meta),state])
            identities=None
            for stage in subject.STAGES:
                write(stage);identities=subject.audit_states(path,self.config,stage,identities)
            self.assertEqual(len(identities),1780)
            for bad in ('missing','protected','identity'):
                write('selected',**{bad:True})
                with self.assertRaises(ValueError):subject.audit_states(path,self.config,'selected')

    def test_exact_lifecycle_budget_only_and_no_authorization_launch(self):
        original=subject.lifecycle.capture.__code__
        adapted=subject.full_capture().__code__
        self.assertEqual(original.co_code,adapted.co_code)
        from types import CodeType
        for before,after in zip(original.co_consts,adapted.co_consts):
            if isinstance(before,CodeType):
                self.assertEqual(before.co_code,after.co_code)
                self.assertEqual(before.co_consts,after.co_consts)
            else:self.assertEqual(10500 if before==1800 else before,after)
        with patch.object(subject,'config_read') as read:
            with self.assertRaises(ValueError):subject.run(Path('/unused'),None,False)
            read.assert_not_called()

    def test_one_shot_no_second_launch(self):
        with tempfile.TemporaryDirectory(dir=subject.prepared.static.OUT) as d:
            out=Path(d);(out/'status.json').write_text('{"status":"PREPARED_NO_DVE"}')
            with patch.object(subject,'config_read'),patch.object(subject,'full_capture'),patch.object(subject.pilot,'private') as invoke:
                invoke.return_value=lambda *args:None
                subject.run(out,'UNIT_ONLY',True)
                with self.assertRaises(FileExistsError):subject.run(out,'UNIT_ONLY',True)
                self.assertEqual(invoke.call_count,1)

    def test_host_tcl_full_five_stages_scope_isolation_reset_reload(self):
        # Reuse the frozen pilot's host-only GUI stub, adapting its scope-keyed state.
        import test_capture_rvh_branch_pilot_725 as tests
        source=inspect.getsource(tests.PilotTests.test_tcl_five_stage_reset_reload_existing_audit)
        source='\n'.join(line[4:] if line.startswith('    ') else line for line in source.splitlines())+'\n'
        substitutions={
            'subject.branch_library()':'subject.pilot.branch_library()',
            'set parts [split $key ,]':'set ::current_scope $scope\n        set parts [split $key ,]',
            '$::current)':'$::current_scope|$::current)',
            "'DBG_AUDIT '+stage+' 100'":"'DBG_AUDIT '+stage+' 1780'",
        }
        for before,after in substitutions.items():
            self.assertIn(before,source);source=source.replace(before,after)
        namespace={'subject':subject,'tempfile':tempfile,'Path':Path,'subprocess':subprocess}
        exec(compile(source,'HOST_STUB_FULL247_ONLY','exec'),namespace)
        namespace['test_tcl_five_stage_reset_reload_existing_audit'](self)


if __name__=='__main__':unittest.main()
