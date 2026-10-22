"""Interface tests only: no reader closure, preparation, actual qualification or GUI."""
import ast
import copy
import inspect
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import qbs_eight735_runtime_v8 as p


class V8Interfaces(unittest.TestCase):
    def test_pin_conflict_rejected_not_last_writer_wins(self):
        a={'/interface/source':'a'*64}; b={'/interface/source':'b'*64}
        self.assertEqual(p.merge_pins(a,a),a)
        with self.assertRaisesRegex(ValueError,'Pin conflict'):p.merge_pins(a,b)
        with self.assertRaisesRegex(ValueError,'Pin conflict'):p.merge_pins(b,a)
        self.assertEqual(a,{'/interface/source':'a'*64})

    def test_pin_union_and_malformed_entries(self):
        self.assertEqual(p.merge_pins({'/interface/a':'a'*64},{'/interface/b':'b'*64}),
                         {'/interface/a':'a'*64,'/interface/b':'b'*64})
        for ledger in ({'/interface/a':'A'*64},{'/interface/a':'a'*63},{'/interface/a':None},{3:'a'*64}):
            with self.subTest(ledger=ledger),self.assertRaises(ValueError):p.merge_pins(ledger)

    def reader_shape(self):
        # Shape-only dictionary, never serialized, sealed, or passed to real reader_context.
        deps=(p.reader.SCRIPT,p.reader.TEST,p.reader.AUDIT,*p.reader.prior.COMPILED_READS)
        pins={str(x):'a'*64 for x in deps}
        pins.update(p.reader.TOOL_READS);pins[str(p.reader.AUDIT)]=p.READER_AUDIT_SHA
        return dict(output=str(p.reader.ROOT),population=735,admission_seal=p.ADMISSION_SHA,
            targets=5892,protected=17774,audited=23666,pins=pins,
            byte_paths=list(p.reader.TOOL_READS),json_paths=[],
            isolated_worker_boundary=p.reader.BOUNDARY,child_worker_reads_captured=False)

    def test_reader_version_population_and_admission_rejected(self):
        plan=self.reader_shape();path=p.reader.ROOT/p.reader.PLAN
        for key,value in (('population',738),('admission_seal','b'*64),('targets',5891),
                          ('protected',17773),('audited',23665),('output','/interface/other')):
            bad=copy.deepcopy(plan);bad[key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):p.validate_reader(path,'a'*64,bad)
        for path in (p.reader.ROOT/'epoch-readiness-735-v5-plan.json',
                     p.reader.ROOT/'epoch-readiness-735-v7-plan.json',Path('/interface')/p.reader.PLAN):
            with self.subTest(path=path),self.assertRaises(ValueError):p.validate_reader(path,'a'*64,plan)

    def test_missing_v8_mask_compiled_authorities_and_roles_rejected(self):
        plan=self.reader_shape();path=p.reader.ROOT/p.reader.PLAN
        for dep in (p.reader.SCRIPT,p.reader.TEST,p.reader.AUDIT,*p.reader.prior.COMPILED_READS):
            bad=copy.deepcopy(plan);del bad['pins'][str(dep)]
            with self.subTest(dep=dep),self.assertRaises(ValueError):p.validate_reader(path,'a'*64,bad)
        for bad in (dict(plan,json_paths=['/interface/unsealed']),dict(plan,byte_paths=['/interface/unsealed'])):
            with self.assertRaises(ValueError):p.validate_reader(path,'a'*64,bad)
        for seal in (None,'','a'*63,'A'*64):
            with self.assertRaises(ValueError):p.validate_reader(path,seal,plan)

    def test_v8_worker_boundary_tool_role_and_actual_audit_drift(self):
        plan=self.reader_shape();path=p.reader.ROOT/p.reader.PLAN
        for key,value in (('child_worker_reads_captured',True),('isolated_worker_boundary','v7 closure only')):
            bad=copy.deepcopy(plan);bad[key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):p.validate_reader(path,'a'*64,bad)
        bad=copy.deepcopy(plan);bad['pins'][str(p.reader.AUDIT)]='b'*64
        with self.assertRaises(ValueError):p.validate_reader(path,'a'*64,bad)
        for tool in p.reader.TOOL_READS:
            for mutation in ('hash','missing_pin'):
                bad=copy.deepcopy(plan)
                if mutation=='hash':bad['pins'][tool]='b'*64
                else:del bad['pins'][tool]
                with self.subTest(tool=tool,mutation=mutation),self.assertRaises(ValueError):
                    p.validate_reader(path,'a'*64,bad)
        measured=copy.deepcopy(plan);measured['byte_paths']=[]
        self.assertTrue(set(p.reader.TOOL_READS)<=set(p.reader.tool_roles(measured['pins'],[])))

    def runtime_shape(self):
        return dict(schema=p.SCHEMA,output='/interface/runtime',population=735,
            stages=list(p.design.STAGES),source_control_boundary=p.f.SCOPE_BOUNDARY,targets=7684,
            protected_audited=19566,audited=27250,payload_condition_protected=41214,
            budget_seconds=14400,kill_after_seconds=10,terminal_backend='V8_OWNER_BOUND_EIGHT_AND_QBS_FIXED_WORKER_IPC',
            application_approval=False,launch_approved=False,automatic_retry=False,
            isolated_worker_boundary=p.reader.BOUNDARY,child_worker_reads_captured=False,
            reader_audit_sha256=p.READER_AUDIT_SHA,fresh_tail_required=True)

    def test_runtime_interface_keeps735_bounds_and_no_approval(self):
        plan=self.runtime_shape();p.validate_runtime(Path('/interface/runtime'),plan)
        for key,value in (('population',738),('targets',7683),('protected_audited',19565),('audited',27249),
            ('payload_condition_protected',41213),('budget_seconds',3600),('kill_after_seconds',11),
            ('terminal_backend','GLOBAL_EIGHT'),('source_control_boundary',{}),('application_approval',True),
            ('launch_approved',True),('automatic_retry',True),('stages',list(p.design.STAGES)[:-1]),
            ('child_worker_reads_captured',True),('isolated_worker_boundary','unrestricted'),
            ('reader_audit_sha256','b'*64),('fresh_tail_required',False)):
            bad=copy.deepcopy(plan);bad[key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):p.validate_runtime(Path('/interface/runtime'),bad)

    def test_dependencies_use_v8_and_preserve_existing_Tcl(self):
        deps=p.dependencies()
        self.assertEqual(p.TCL,p.frozen.TCL)
        for path in (p.reader.SCRIPT,p.reader.TEST,p.reader.AUDIT,p.reader.prior.prior.CONFIG,p.reader.prior.prior.FIRST):
            self.assertIn(path,deps)
        for audit in (p.reader.prior.AUDIT,p.reader.prior.prior.AUDIT,p.reader.prior.prior.prior.AUDIT):
            self.assertNotIn(audit,deps)
        self.assertEqual(p.BUDGET,14400)

    def test_8group_dispatch_only_owner_backend_and_protection_callback(self):
        calls=[]
        class InterfacePath:
            def __init__(self,value):self.value=str(value)
            def read_bytes(self):calls.append(('read',self.value));return self.value.encode()
            def __truediv__(self,value):return InterfacePath(self.value+'/'+value)
        def blocks(raw):return [(('old8',),raw)]
        def split_bind(raw,cfg,sources,candidates,states):
            calls.append(('owner.split_bind',raw,states));return {'interface_only':True}
        def factory(namespace,allowed):
            calls.append(('owner.verifier',namespace['TIMEOUT']))
            namespace['bindings'](b'interface-native',{},'interface-states')
            self.assertTrue(allowed('interface-scope','Condition',{'old-scope'}))
            return 'interface-verifier'
        def allowed(scope,metric,active,condition_scopes):
            calls.append(('owner.protection',condition_scopes));return metric=='Condition'
        backend=SimpleNamespace(SOURCE_PROOF=InterfacePath('/interface/lzc'),MASK_EL=InterfacePath('/interface/mask'),
            metric=SimpleNamespace(blocks=blocks),split_bind=split_bind,
            prior=SimpleNamespace(seven_verifier=factory,change_allowed=allowed))
        owner=SimpleNamespace(Path=InterfacePath,fixed=SimpleNamespace(eight=backend))
        context=SimpleNamespace(namespace=lambda:{})
        runtime=dict(six_output='/interface/six',snapshot_candidates=[{'scope':'snapshot'}])
        plan=dict(condition_native_records=[{'scope':'lzc'}])
        with patch.object(p,'load',return_value={'scope_protection':{'qbs':{}}}):
            got=p.old_eight_verifier(owner,context,runtime,plan,lambda raw:calls.append(('union',raw)))
        self.assertEqual(got,'interface-verifier')
        self.assertIn(('owner.verifier',14400),calls)
        self.assertIn(('owner.split_bind',b'interface-native','interface-states'),calls)
        self.assertIn(('union',b'interface-native'),calls)
        self.assertIn(('owner.protection',{'snapshot','lzc','qbs'}),calls)

    def test_terminal_source_no_global_native_backend(self):
        # Structural guard catches a return to the frozen/global verifier path.
        for function in (p.inspect,p.old_eight_verifier,p.qbs_rows,p.records,p.union_checker):
            tree=ast.parse(inspect.getsource(function))
            bad=[n for n in ast.walk(tree) if isinstance(n,ast.Attribute) and
                 isinstance(n.value,ast.Name) and n.value.id=='frozen' and
                 n.attr in ('eight','inspect','qbs_rows','check_union')]
            self.assertEqual(bad,[],function.__name__)
        tree=ast.parse(inspect.getsource(p.reader_context))
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr=='DiagnosticWiring' for n in ast.walk(tree)))

    def test_json_reads_use_owner_Path_and_json(self):
        calls=[]
        class InterfacePath:
            def read_bytes(self):calls.append('owner.bytes');return b'interface-bytes'
        owner=SimpleNamespace(Path=lambda path:InterfacePath(),json=SimpleNamespace(
            loads=lambda raw:(calls.append(('owner.json',raw)) or {'interface_only':True})))
        self.assertEqual(p.load(owner,'/interface/file'),{'interface_only':True})
        self.assertEqual(calls,['owner.bytes',('owner.json',b'interface-bytes')])

    def test_terminal_native_parser_uses_owner_pinned_library(self):
        calls=[]
        class InterfacePath:
            def read_text(self):
                calls.append('owner.native.library')
                # Parser dispatch sentinel, not a real native record or qualified fixture.
                return 'proc nem_records {raw} {return [list [list scope module metric kind id checksum expr selector vector annotation]]}'
        owner=SimpleNamespace(Path=lambda path:InterfacePath())
        rows=p.records(owner,b'interface-only')
        self.assertEqual(len(rows),1);self.assertEqual(calls,['owner.native.library'])


if __name__=='__main__':unittest.main()
