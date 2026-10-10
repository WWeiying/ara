import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_btb_bit0_132_v3 as c
import test_capture_btb_bit0_132_v2 as prior_tests


class Pipeline(prior_tests.Pipeline):
    def fixture(self,out):
        config,_,names=super().fixture(out)
        previous=c.original.bound(c.V2/'config.json',c.V2_SHA)
        config['pins']=dict(config['pins'],**previous['pins'])
        config.update(previous_config_seal=c.V2_SHA,root_display_aliases=c.ALIASES,
                      display_binding=c.compiled_binding(previous))
        (out/'config.json').write_text(json.dumps(config))
        selection=(out/'selection.tcl').read_text().replace(str(Path(c.prior.__file__).resolve()),
                                                           str(Path(c.__file__).resolve()))
        (out/'selection.tcl').write_text(selection)
        return config,c.digest(out/'config.json'),names

    def pipeline(self,out,mutation='generated'):
        real_run=subprocess.run
        def execute(args,**kwargs):
            script=kwargs['input']
            old='if {$::mutation eq "module"} {return btb}'
            if old in script:
                self.assertEqual(script.count(old),1)
                script=script.replace(old,old+'\n'+
                    'if {$::mutation eq "generated"} {return btb_gen.i_btb}\n'+
                    'if {$::mutation eq "unbound_generated"} {return other_gen.i_btb}')
                script=script.replace('{i_btb btb} [lindex $args end]',
                                      '{i_btb btb btb_gen.i_btb} [lindex $args end]')
            kwargs['input']=script
            return real_run(args,**kwargs)
        with patch.object(c.prior,'HOOK',c.HOOK),patch.object(prior_tests.subprocess,'run',execute):
            return super().pipeline(out,mutation)


class AliasTests(unittest.TestCase):
    def test_compiled_and_source_generation_proof(self):
        config=c.original.bound(c.V2/'config.json',c.V2_SHA)
        binding=c.compiled_binding(config)
        self.assertEqual(binding['instance'],dict(id='-1968',name='btb_gen.i_btb',pid='-466'))
        self.assertEqual(binding['parent']['name'],'i_frontend')
        self.assertEqual(binding['scope'],c.plan.SCOPE)

    def test_actual_generated_alias_full_entry_five_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);_,_,result=Pipeline().pipeline(out)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout.splitlines().count('BTB132_NATIVE_DONE'),1)
            observations=c.root_observations(out)
            self.assertTrue(all(r[4]==r[5]=='btb_gen.i_btb' for r in observations.values()))
            for stage in c.original.STAGES:c.metrics(out,stage)
            self.assertEqual(c.original.native_records((out/'first.el').read_text()),
                             c.original.native_records((out/'second.el').read_text()))
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_foreign_generated_root_and_sibling_remain_rejected(self):
        for mutation in ('unbound_generated','root','sibling'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);_,_,result=Pipeline().pipeline(out,mutation)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertTrue((out/'error.txt').exists())
                self.assertFalse((out/'first.el').exists())
                self.assertNotIn('BTB132_NATIVE_DONE',result.stdout)
                self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_compiled_foreign_instance_rejected(self):
        config=c.original.bound(c.V2/'config.json',c.V2_SHA)
        original=next(Path(p) for p in config['pins'] if p.endswith('/design/verilog.design.xml'))
        tree=c.plan.native.xml(original)
        node=next(n for n in tree.iter('srcinst') if n.get('id')=='-1968')
        node.set('name','foreign_gen.i_btb')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'design/verilog.design.xml';path.parent.mkdir()
            path.write_bytes(c.plan.native.base.ET.tostring(tree))
            config=dict(config,pins=dict(config['pins']))
            del config['pins'][str(original)]
            config['pins'][str(path)]=c.digest(path)
            with self.assertRaises(ValueError):c.compiled_binding(config)

    def test_actual_prepare_unchanged_candidate_and_v2_preserved(self):
        with tempfile.TemporaryDirectory(dir=c.plan.OUT,prefix='btb132-v3-host-') as temp:
            out=Path(temp);out.rmdir()
            seal=c.prepare(out);config=c.read_config(out,seal)
            self.assertEqual(config['root_display_aliases'],c.ALIASES)
            self.assertEqual((out/'candidate.el').read_bytes(),(c.V2/'candidate.el').read_bytes())
            for path in (c.V2/'config.json',c.V2/'terminal.json',c.V2/'root-contract.tsv',
                         c.V2/'error.txt',c.V2/'cleanup-empty.el',c.prior.HOOK):
                self.assertEqual(config['pins'][str(path)],c.digest(path))
            self.assertEqual(len(c.original.complement(config['inventory'])),8860)
            self.assertFalse((out/'execution.json').exists())


def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(AliasTests)
if __name__=='__main__':unittest.main()
