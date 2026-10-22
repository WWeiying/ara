import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import report_native_increment770_offline768 as r


class OfflinePredecessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=r.life.read_bound(r.QUALIFICATION,r.QUALIFICATION_SHA)
        cls.book=r.life.read_bound(r.CLOSURE,r.CLOSURE_SHA)
        cls.c=r.life.read_bound(r.closure.OUT/'config.json',r.closure.SEAL)

    def test_foreign_or_old_unit_zero_predecessor_rejected(self):
        for path,seal in [(r.closure.OUT/'qualification.json',r.QUALIFICATION_SHA),
                          (r.QUALIFICATION,'0'*64)]:
            with self.assertRaises(ValueError):r.predecessor_gate(path,seal)
        fields=dict(self.q['terminal_evidence']['systemd_properties'],ExecMainStatus='0')
        receipt=r.life.read_bound(r.closure.launch.UNIT_RECEIPT,r.closure.launch.UNIT_RECEIPT_SHA)
        with self.assertRaises(ValueError):
            r.closure.terminal_evidence((r.closure.OUT/'service.log').read_text(),
                json.loads((r.closure.OUT/'failure.json').read_bytes()),
                json.loads((r.closure.OUT/'live-identity.json').read_bytes()),receipt,
                __import__('inspect').getsource(r.closure.report.base.prior.old.frozen.prior.old.base.run),fields)

    def test_pending_or_changed_closure_rejected(self):
        read=r.life.read_bound
        for field,value in [('status','PENDING'),('qualification_sha256','0'*64),('EDA_launched',True)]:
            bad=dict(self.book);bad[field]=value
            def bound(path,seal):return bad if path==r.CLOSURE else read(path,seal)
            with patch.object(r.life,'read_bound',bound),self.assertRaises(ValueError):
                r.predecessor_gate(r.QUALIFICATION,r.QUALIFICATION_SHA)

    def test_failed_gate_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'absent'
            with patch.object(r,'predecessor_gate',side_effect=ValueError('HOLD')):
                with self.assertRaises(ValueError):r.prepare(out)
            self.assertFalse(out.exists())

    def test_context_preserves_substantive_verify_and_authorization(self):
        ctx=r.context();ns=ctx['namespace']()
        self.assertIs(ctx['predecessor_gate'],r.predecessor_gate)
        self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertEqual(ctx['TCL'],r.frozen.TCL)
        with self.assertRaises(ValueError):r.frozen.frozen.inherited.authorize(True,False)

    def test_actual_predecessor_native_zero_wrapper_one_and_full_pins(self):
        q=r.predecessor_gate(r.QUALIFICATION,r.QUALIFICATION_SHA)
        self.assertEqual(q['observed_terminal_evidence']['wrapper_OS_exit_status'],1)
        self.assertEqual(q['observed_terminal_evidence']['launch_process_returncode'],0)
        self.assertFalse((r.closure.OUT/'qualification.json').exists())

    def test_actual_combined_families_and_host_five_stages(self):
        ctx=r.context();private=ctx['private_namespace']()
        c=copy.deepcopy(self.c);added=ctx['new_families']();c['new_families'].update(added)
        c['output']=str(r.life.OUT/'HOST_ONLY_770_UNWRITTEN_TEMPLATE')
        self.assertFalse((Path(c['output'])/'combined.el').exists())
        text=(r.closure.OUT/'combined.el').read_text()+''.join(v['el'] for v in added.values())
        value=private['records'](text,c)
        for key,item in added.items():self.assertEqual(value.pop(key),item['canonical'])
        self.assertEqual(value,self.c['expected_union'])
        groups=private['merged_observers'](c)
        qbs=next(g for g in groups.values() if g['scope'].endswith('.i_qbs_engine'))
        self.assertIn('accumulator_updates_o[31:0]',qbs['targets'])
        selection=(r.closure.OUT/'selection.tcl').read_text()+r.frozen.frozen.base.prior.selection_tail(
            dict(c,observer_captures=groups))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'selection.tcl';path.write_text(selection)
            result=private['host_hook'](path,c)
        self.assertEqual(result['stages'],list(r.frozen.frozen.base.prior.STAGES))
        self.assertFalse(result['EDA_launched'])

    def test_actual_export_annotations_and_union_remain_exact(self):
        private=r.context()['private_namespace']()
        for name in ('applied.el','reloaded.el'):
            self.assertEqual(private['records']((r.closure.OUT/name).read_text(),self.c),self.c['expected_union'])
        text=(r.closure.OUT/'applied.el').read_text()
        annotation=next(l for l in text.splitlines() if l.startswith('ANNOTATION:'))
        with self.assertRaises(ValueError):private['records'](text.replace(annotation,'ANNOTATION: "FOREIGN"'),self.c)

    def test_recursive_real_tcl_dependencies_and_missing_pin_rejected(self):
        files=r.tcl_dependencies();pins=r.dependency_pins()
        for name in ('report_native_increment769.tcl','report_native_batch768_v3.tcl',
                     'report_native_batch766.tcl','fsm741_transition_batch.tcl',
                     'qualify_dwc_points742.tcl','apply_points740_v4.tcl'):
            path=r.HERE/name
            self.assertIn(path,files);self.assertIn(str(path),pins)
        self.assertIn(str(Path(r.frozen.frozen.__file__).resolve()),pins)
        r.dependency_gate(dict(pins=pins))
        bad=dict(pins);bad.pop(str(r.HERE/'report_native_increment769.tcl'))
        with self.assertRaises(ValueError):r.dependency_gate(dict(pins=bad))

    def test_direct_and_deep_source_tcl_drift_rejected_without_real_edits(self):
        pins=r.dependency_pins();digest=r.life.digest
        for name in ('report_native_increment769.tcl','apply_points740_v4.tcl'):
            path=r.HERE/name
            def changed(p):return '0'*64 if Path(p)==path else digest(p)
            with self.subTest(name=name),patch.object(r.life,'digest',changed),self.assertRaises(ValueError):
                r.dependency_gate(dict(pins=pins))

    def test_unknown_dynamic_source_and_cycle_rejected(self):
        read=Path.read_text;path=r.HERE/'report_native_increment769.tcl'
        for suffix in ('source $foreign_dependency\n','source {'+str(path)+'}\n'):
            def changed(p,*args,**kwargs):
                return read(p,*args,**kwargs)+(suffix if p==path else '')
            with patch.object(Path,'read_text',changed),self.assertRaises(ValueError):r.tcl_dependencies()


if __name__=='__main__':unittest.main()
