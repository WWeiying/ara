#!/usr/bin/env python3
"""Host tests for the registered tool-class/reused-input successor, no build."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import plugin_v2 as v2

HERE=Path(__file__).resolve().parent

class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=v2.parent();cls.original=(v2.PARTIAL/'inputs/recipe.py').read_text()
        cls.worker=v2.worker_source(cls.original)

    def test_historical_fail_and_complete_partial_inputs_unchanged(self):
        before=v2.sha(v2.PARTIAL/'prepare.json')
        membership=v2.checked_partial(self.base)
        self.assertGreater(len(membership),3000)
        self.assertEqual(before,v2.FAIL_SHA)
        self.assertEqual(self.base.read(v2.PARTIAL/'prepare.json')['state'],'FAIL')

    def test_plugin_moves_to_program_query_not_target_runtime(self):
        tree=ast.parse(self.worker)
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='pin_toolchain')
        tuples=[tuple(x.value for x in n.iter.elts) for n in ast.walk(function)
            if isinstance(n,ast.For) and isinstance(n.iter,ast.Tuple) and
            all(isinstance(x,ast.Constant) and isinstance(x.value,str) for x in n.iter.elts)]
        program=next(t for t in tuples if 'cc1' in t)
        target=next(t for t in tuples if 'libgcc.a' in t)
        self.assertIn('liblto_plugin.so',program);self.assertNotIn('liblto_plugin.so',target)
        self.assertEqual(len(target),13)
        self.assertIn('pinned_library_dirs.add(directory)',self.worker)
        self.assertIn('for p in list(dict.fromkeys(tools.values())):',self.worker)

    def test_reused_root_covers_inventory_source_sdk_link_validation(self):
        build=self.worker.split('def build(args):',1)[1].split('\ndef main():',1)[0]
        self.assertIn("source=input_prepared/'inputs/llama';sdk=input_prepared/'inputs/sdk'",build)
        self.assertEqual(build.count("inventory(input_prepared/'inputs')"),2)
        self.assertIn('validate_commands(commands,input_prepared,builddir)',build)
        self.assertIn('link_argv(input_prepared,output,archives)',build)
        self.assertIn("pins[str(prepared/'runner/recipe.py')]",build)
        self.assertEqual(build.count("inventory(prepared/'runner')"),2)
        self.assertNotIn("prepared/'inputs/recipe.py'",build)
        self.assertIn("receipt['schema']=='stage5-libraries-prepare-v2'",build)
        self.assertIn("schema='stage5-libraries-build-v1'",build)
        compile(self.worker,'corrected-worker.py','exec')

    def test_unreviewed_anchors_reject(self):
        with self.assertRaises(ValueError):
            v2.worker_source(self.original.replace("'cc1','cc1plus'","'changed','cc1plus'"))

    def test_driver_proves_host_plugin_and_no_requested_lto(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plugin=root/'liblto_plugin.so';plugin.write_bytes(b'host plugin fixture')
            dry=str(root/'collect2')+' -plugin '+str(plugin)+' -static -o /dev/null input.o'
            self.assertEqual(v2.classify('liblto_plugin.so',str(plugin),'--enable-plugins --enable-lto',dry,root),plugin)
            for changed in (dry.replace('-plugin ','-not-plugin '),dry+' -flto',dry.replace(str(plugin),str(root/'other.so'))):
                with self.assertRaises(ValueError):
                    v2.classify('liblto_plugin.so',str(plugin),'--enable-plugins --enable-lto',changed,root)
            with self.assertRaises(ValueError):
                v2.classify('liblto_plugin.so','/etc/passwd','--enable-plugins --enable-lto',dry,root)

    def test_compiler_flags_and_frontend_contract_not_changed(self):
        for name in ('FLAGS','LIMIT','ARCHIVES','PROBE'):
            before=next(n for n in ast.parse(self.original).body if isinstance(n,ast.Assign) and
                any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
            after=next(n for n in ast.parse(self.worker).body if isinstance(n,ast.Assign) and
                any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
            self.assertEqual(ast.dump(before),ast.dump(after))
        for name in ('configure_argv','options','includes','link_argv','validate_commands','service_owner'):
            before=next(n for n in ast.parse(self.original).body if isinstance(n,ast.FunctionDef) and n.name==name)
            after=next(n for n in ast.parse(self.worker).body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(before),ast.dump(after))

    def test_no_archive_extract_or_source_copy_in_reuse_prepare(self):
        source=(HERE/'plugin_v2.py').read_text().split('def prepare(args):',1)[1].split('\ndef main():',1)[0]
        self.assertNotIn('copytree',source);self.assertNotIn('extractall',source)
        self.assertNotIn('check_output',source)
        self.assertIn('source_copied=False',source)
        self.assertIn("'--start-group'",source)

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();base=v2.parent();output=base.fresh(args.output,'stage5_libraries_plugin_host_')
    own,review=v2.identity();pins={}
    for path in [*[HERE/n for n in v2.OWN],v2.PARTIAL/'prepare.json',v2.PARTIAL/'inputs/recipe.py']:
        base.pin(pins,path)
    with (output/'tests.log').open('x') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PluginTests))
    base.verify(pins);base.write(output/'source-pins.json',pins)
    report=dict(state='HOST_PLUGIN_SUCCESSOR_PASS_NO_BUILD' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        source_sha256=review,owned_files=own,source_pins_sha256=v2.sha(output/'source-pins.json'),
        library_build_started=False,provider_registered=False,
        artifacts={str(p):v2.sha(p) for p in output.rglob('*') if p.is_file()})
    base.write(output/'result.json',report);print(json.dumps(report,sort_keys=True))
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__': main()
