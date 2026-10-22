import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_six_policy_population_729 as p


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof=p.cc_ancestry(p.ADMISSION,p.ADMISSION_SEAL)
        cls.context=p.Context(p.ADMISSION,p.ADMISSION_SEAL,729)
        cls.ledger=cls.context.ledger()

    def test_actual_recursive_cc_proof_without_latest_cc(self):
        self.assertNotIn(p.v2.CC,self.ledger)
        self.assertEqual(self.ledger['/usr/bin/gcc'],p.v2.CC_SHA)
        self.assertEqual([n['population'] for n in self.proof['chain']],list(range(729,722,-1)))
        self.assertEqual(self.proof['identity'],dict(link_target='gcc',resolved='/usr/bin/gcc',sha256=p.v2.CC_SHA))
        self.assertEqual(self.proof['pins'][str(p.R1_PREFLIGHT/'input-pins.json')],
                         'c08463653315abf1507e62b8bd5693860d384053ef8e61fe60ba2abfca30c781')
        self.assertEqual(self.proof['pins'][str(p.R1_PREFLIGHT/'host-command.json')],
                         '78b658ea93f80df39be861736ccbeff1a5e7eb8e680cff87e5b8f4fdabcba5a6')
        self.assertFalse(self.proof['top_ledger_cc_required'])
        self.assertFalse(self.proof['history_identity_fabricated'])

    def test_actual_five_llvm_entries_and_resolved_identity(self):
        pins={}
        for path,spec in p.ALIASES.items():
            identity=p.llvm_identity(path)
            self.assertEqual(identity['sha256'],self.ledger[path])
            self.assertEqual(identity['link_target'],spec[0])
            self.context.pin(pins,path,self.ledger[path])
            self.assertEqual(pins[path],pins[identity['resolved']])
        self.assertEqual(len(p.ALIASES),5)

    def test_scope_formal729_only(self):
        for path,seal,n in ((p.ADMISSION,'0'*64,729),(p.ADMISSION,p.ADMISSION_SEAL,728),
                            (p.ADMISSION,p.ADMISSION_SEAL,True),
                            (p.frozen.OUT/'other',p.ADMISSION_SEAL,729)):
            with self.assertRaises(ValueError):p.Context(path,seal,n)

    def test_alias_expected_missing_wrong_or_conflicting_rejected(self):
        context=p.Context(p.ADMISSION,p.ADMISSION_SEAL,729)
        name=next(iter(p.ALIASES));expected=p.ALIASES[name][2]
        context._ledger={}
        with self.assertRaises(ValueError):context.pin({},name,expected)
        context._ledger={name:'0'*64}
        with self.assertRaises(ValueError):context.pin({},name,expected)
        context._ledger={name:expected}
        with self.assertRaises(ValueError):context.pin({},name,'0'*64)
        with patch.object(p,'llvm_identity',return_value=dict(resolved='/unused',sha256=expected)),\
             self.assertRaises(ValueError):context.pin({name:'0'*64},name,expected)

    def test_alias_target_endpoint_hash_and_unknown_rejected(self):
        path=str(p.WORKSPACE/'clang')
        with patch.object(Path,'readlink',return_value=Path('other')),self.assertRaises(ValueError):
            p.llvm_identity(path)
        with patch.object(Path,'resolve',return_value=p.CANONICAL/'other'),self.assertRaises(ValueError):
            p.llvm_identity(path)
        with patch.object(p.frozen,'sha',return_value='0'*64),self.assertRaises(ValueError):
            p.llvm_identity(path)
        with self.assertRaises(ValueError):p.llvm_identity(p.WORKSPACE/'clang++')
        with self.assertRaises(ValueError):p.tool_link_identity('/usr/bin/c++')
        with patch.object(Path,'is_symlink',return_value=True),self.assertRaises(ValueError):
            p.llvm_identity(p.WORKSPACE/'llvm-readobj')

    def test_cc_needs_actual_ancestor_expected_and_proof(self):
        context=p.Context(p.ADMISSION,p.ADMISSION_SEAL,729)
        for value in (None,'0'*64):
            with self.assertRaises(ValueError):context.pin({},p.v2.CC,value)
        with patch.object(context,'cc_proof',side_effect=ValueError('missing ancestor')),\
             self.assertRaises(ValueError):context.pin({},p.v2.CC,p.v2.CC_SHA)
        context._cc_proof=self.proof;pins={}
        context.pin(pins,p.v2.CC,p.v2.CC_SHA)
        self.assertEqual(pins[p.v2.CC],pins['/usr/bin/gcc'])

    def test_original_admission_gates_and_nonalias_pin_unchanged(self):
        self.assertIs(p.Context.admission_inputs,p.base.Context.admission_inputs)
        self.assertIs(p.Context.qualification,p.base.Context.qualification)
        self.assertIs(p.Context.check_config,p.base.Context.check_config)
        with patch.object(p.base.Context,'pin',return_value='sentinel') as inherited:
            self.assertEqual(self.context.pin({},'/ordinary/metric.xml','abc'),'sentinel')
            inherited.assert_called_once_with({},Path('/ordinary/metric.xml'),'abc')

    def test_namespace_adds_only_three_actual_links_no_universal_cc(self):
        original=dict(p.frozen.INHERITED_TOOL_LINKS)
        added=set(self.context.namespace()['INHERITED_TOOL_LINKS'])-set(original)
        self.assertEqual(added,{str(p.WORKSPACE/n) for n in ('clang','ld.lld','llvm-readelf')})
        self.assertNotIn(p.v2.CC,self.context.namespace()['INHERITED_TOOL_LINKS'])
        self.assertEqual(p.frozen.INHERITED_TOOL_LINKS,original)

    def test_recursive_seal_drift_rejected(self):
        real=p.frozen.load_sealed
        def changed(path,seal):
            if str(path).endswith('fence-t-u-padding-offline-admitted-728-parent-20261006-01/admission-manifest.json'):
                raise ValueError('ancestor hash mismatch')
            return real(path,seal)
        with patch.object(p.frozen,'load_sealed',side_effect=changed),self.assertRaises(ValueError):
            p.cc_ancestry(p.ADMISSION,p.ADMISSION_SEAL)

    def test_wrong_prefix_status_cc_or_origin_command_rejected(self):
        real=p.bound
        def run_mutation(which):
            def changed(path,seal,pins):
                data=copy.deepcopy(real(path,seal,pins));path=Path(path)
                if which=='status' and path==p.ADMISSION/'status.json':data['status']='FAILED'
                if which=='bool_population' and path==p.ADMISSION/'status.json':data['aggregate_passed']=True
                if which=='cc' and path.parent.name.startswith('narrow-reject-r1-cached-offline-admitted-723') and path.name=='evidence-pins.json':data[p.v2.CC]='0'*64
                if which=='origin_missing' and path.parent.name.startswith('narrow-reject-r1-cached-offline-admitted-723') and path.name=='evidence-pins.json':del data[str(p.R1_PREFLIGHT/'host-command.json')]
                if which=='command' and path==p.R1_PREFLIGHT/'host-command.json':data[0]='/usr/bin/gcc'
                if which=='schema' and path==p.ADMISSION/'admission-manifest.json':data['schema']='arbitrary'
                return data
            return changed
        for kind in ('status','bool_population','cc','origin_missing','command','schema'):
            with self.subTest(kind=kind),patch.object(p,'bound',side_effect=run_mutation(kind)),self.assertRaises(ValueError):
                p.cc_ancestry(p.ADMISSION,p.ADMISSION_SEAL)
        original=Path.read_text
        def reorder(path,*a,**k):
            text=original(path,*a,**k)
            if path==p.ADMISSION/'combined-inputs.txt':
                rows=text.splitlines();rows[1],rows[2]=rows[2],rows[1];return '\n'.join(rows)+'\n'
            return text
        with patch.object(Path,'read_text',reorder),self.assertRaises(ValueError):
            p.cc_ancestry(p.ADMISSION,p.ADMISSION_SEAL)

    def test_sealed_document_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);file=root/'file';file.write_text('{}');alias=root/'alias';alias.symlink_to(file)
            with self.assertRaises(ValueError):p.bound(alias,p.frozen.sha(file),{})

    def test_source_binding_uses_base_and_pins_real_provenance(self):
        context=p.Context(p.ADMISSION,p.ADMISSION_SEAL,729)
        pins={}
        with patch.object(p.base.Context,'source_binding',return_value={'unchanged_source_gate':True}):
            record=context.source_binding(pins)
        self.assertTrue(record['unchanged_source_gate'])
        self.assertFalse(record['current_admission_cc_present'])
        self.assertEqual(record['historical_r1_cc'],self.proof)
        self.assertTrue(set(self.ledger)&set(p.ALIASES)<=pins.keys())
        self.assertEqual(pins[p.v2.CC],p.v2.CC_SHA)
        self.assertTrue(self.proof['pins'].items()<=pins.items())


if __name__=='__main__':unittest.main()
