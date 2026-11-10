#!/usr/bin/env python3
"""Host-only recipe/closure tests. Never configure, compile, link or run a guest."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode=True
import recipe

HERE=Path(__file__).resolve().parent

class RecipeTests(unittest.TestCase):
    def test_overlay09_authoritative_receipt_and_postpins(self):
        report=recipe.checked_host()
        self.assertEqual(report['akv_sha256'],'656b6e6592316acde7752ea71f953608adf40edc7e4f194e25e6bc061835c0a9')
        self.assertFalse(report['native_execution']);self.assertFalse(report['provider_registered'])

    def test_sdk_archive_revisions_match_without_live_inputs(self):
        p=subprocess.run(['/usr/bin/git','-C',str(recipe.ROOT),'diff','--exit-code',recipe.SDK_MODEL_REV,
            recipe.SDK_REV,'--','software/akv','software/qbs'],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_complete_static_cross_recipe_and_provider_denial(self):
        opts=recipe.options(Path('/source'),Path('/sdk'))
        for key in ('BUILD_SHARED_LIBS','GGML_NATIVE','GGML_LTO','GGML_OPENMP','GGML_BACKEND_DL','LLAMA_BUILD_COMMON'):
            self.assertEqual(opts[key],'OFF')
        for key in ('GGML_RISCV_AKV_RESIDENT','GGML_RISCV_QBS','GGML_RISCV_AKV_QUANT_KV',
                    'GGML_RISCV_AKV_QUANT_PREFILL','GGML_RISCV_AKV_REGISTER_PV'):
            self.assertEqual(opts[key],'ON')
        self.assertEqual(opts['CMAKE_TRY_COMPILE_TARGET_TYPE'],'STATIC_LIBRARY')
        self.assertEqual(recipe.FLAGS,'-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off')
        self.assertNotIn('provider',repr(opts).lower())

    def test_link_order_supports_later_explicit_object_but_no_current_binding(self):
        prepared=Path('/prepared');out=Path('/output');libs={n:out/n for n in recipe.ARCHIVES}
        argv=recipe.link_argv(prepared,out,libs)
        self.assertNotIn('provider.o',' '.join(argv));self.assertIn('-static',argv)
        selected=recipe.link_argv(prepared,out,libs,[Path('/future/provider.o')])
        self.assertLess(selected.index('/future/provider.o'),selected.index('-Wl,--start-group'))
        self.assertEqual(selected[selected.index('-Wl,--start-group')+1:selected.index('-Wl,--end-group')],
                         [str(libs[n]) for n in recipe.ARCHIVES])
        self.assertEqual(len(recipe.includes(prepared)),5)

    def test_source_membership_and_symlinks_are_strict(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)/'inputs';root.mkdir();(root/'file').write_text('data')
            (root/'link').symlink_to('file');inv=recipe.inventory(root)
            self.assertEqual(inv['link']['sha256'],inv['file']['sha256'])
            (root/'added').write_text('unexpected');self.assertNotEqual(inv,recipe.inventory(root))
            (root/'escape').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(ValueError,'Escaping'): recipe.inventory(root)

    def test_authoritative_membership_rejects_unlisted_added_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);source=root/'reviewed.cpp';source.write_text('reviewed')
            artifacts={str(source):recipe.sha(source)}
            recipe.checked_source_membership(root,artifacts)
            (root/'extra.cpp').write_text('not in host09')
            with self.assertRaisesRegex(ValueError,'membership'): recipe.checked_source_membership(root,artifacts)
            (root/'extra.cpp').unlink();source.write_text('changed')
            with self.assertRaises(ValueError): recipe.checked_source_membership(root,artifacts)

    def test_review_identity_and_copy_races_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            copies=Path(raw);own,digest=recipe.identity()
            for name in recipe.OWN: (copies/name).write_bytes((HERE/name).read_bytes())
            recipe.checked_owned(own,digest,copies)
            (copies/'recipe.py').write_text('drift')
            with self.assertRaisesRegex(ValueError,'copies'): recipe.checked_owned(own,digest,copies)
            with mock.patch.object(recipe,'identity',return_value=({},'changed')):
                with self.assertRaisesRegex(ValueError,'during preparation'): recipe.checked_owned(own,digest,copies)

    def test_dependency_parser_real_make_continuations(self):
        self.assertEqual(recipe.dependency_names('file.o: /a/source.c \\\n /b/header.h /c/with\\ space.h\n'),
                         ['/a/source.c','/b/header.h','/c/with space.h'])
        with self.assertRaises(ValueError): recipe.dependency_names('no target')
        with self.assertRaises(ValueError): recipe.dependency_names('a.o: x.h\nx.h:')

    def test_archives_missing_or_ambiguous_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            with self.assertRaises(ValueError): recipe.unique_archives(root)
            for name in recipe.ARCHIVES: (root/name).write_bytes(b'archive')
            self.assertEqual(set(recipe.unique_archives(root)),set(recipe.ARCHIVES))
            (root/'nested').mkdir();(root/'nested/libllama.a').write_bytes(b'duplicate')
            with self.assertRaisesRegex(ValueError,'ambiguous'): recipe.unique_archives(root)

    def test_compile_policy_with_two_real_entry_c_paths_and_mutations(self):
        prepared=Path('/prepared');build=Path('/build');inputs=prepared/'inputs'
        arch=inputs/'llama/ggml/src/ggml-cpu/arch/riscv'
        sdk=inputs/'sdk/software'
        paths=[arch/n for n in ('qbs.cpp','akv.cpp','quant-kv.cpp','platform.c','read_state.S','entry.c')]
        paths += [sdk/'akv/experimental/resident_attention'/n for n in ('qk.S','pv.S')]
        paths += [sdk/'qbs/src'/n for n in ('qbs_runtime.c','qbs_native_riscv.c')]
        paths += [sdk/'akv/src/akv_v2_native_riscv.c',sdk/'akv/experimental/quantized_kv/prefill/ggml_entry.c',
                  sdk/'akv/experimental/quantized_kv/register_pv/entry.c']
        rows=[dict(file=str(p),command='gcc '+recipe.FLAGS+' -DGGML_AKV_RESIDENT=1 '+
            ('-fno-tree-vectorize -fno-tree-slp-vectorize ' if p in [arch/n for n in ('akv.cpp','platform.c','entry.c')] else '')+
            '-I'+str(inputs)+' -c '+str(p)) for p in paths]
        recipe.validate_commands(rows,prepared,build)
        for old,new in (('-march=rv64gcv_zfh_zvfh','-march=rv64gc'),
                        ('-fno-tree-vectorize',''),('-DGGML_AKV_RESIDENT=1',''),
                        ('-I/prepared/inputs','-I/home/wangwy/openproject/ara_dsa/software')):
            mutation=[dict(r) for r in rows];mutation[1]['command']=mutation[1]['command'].replace(old,new)
            with self.assertRaises(ValueError): recipe.validate_commands(mutation,prepared,build)
        with self.assertRaises(ValueError): recipe.validate_commands(rows+[rows[6]],prepared,build)

    def test_direct_owner_rejects_missing_invocation_and_wrong_mainpid(self):
        with mock.patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'invocation'): recipe.service_owner('stage5-libraries-unit.service')
        with mock.patch.dict(os.environ,{'INVOCATION_ID':'a'*32},clear=True), \
             mock.patch.object(Path,'read_text',return_value='0::/user.slice/stage5-libraries-unit.service\n'), \
             mock.patch.object(recipe.subprocess,'check_output',return_value='0'):
            with self.assertRaisesRegex(ValueError,'directly'): recipe.service_owner('stage5-libraries-unit.service')

    def test_global_deadline_four_jobs_and_no_execution_entry(self):
        source=(HERE/'recipe.py').read_text()
        self.assertEqual(recipe.LIMIT,1800)
        self.assertIn("'--target','llama','-j4'",source)
        self.assertIn('signal.alarm(LIMIT)',source)
        self.assertNotIn('qemu-system',source)
        self.assertNotIn('subprocess.run([output',source)
        self.assertNotIn('start_new_session',source)
        self.assertIn('default-NULL probe',(HERE/'README.md').read_text())

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();output=recipe.fresh(args.output,'stage5_libraries_recipe_host_')
    pins={}
    for name in recipe.OWN: recipe.pin(pins,HERE/name)
    recipe.pin(pins,recipe.HOST/'result.json');recipe.pin(pins,recipe.HOST/'source-pins.json')
    with (output/'tests.log').open('x') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecipeTests))
    recipe.verify(pins);recipe.write(output/'source-pins.json',pins)
    own,digest=recipe.identity()
    report=dict(state='HOST_RECIPE_PASS_NO_BUILD' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        source_sha256=digest,owned_files=own,source_pins_sha256=recipe.sha(output/'source-pins.json'),
        library_build_started=False,prepared=False,provider_registered=False,native_execution=False,
        artifacts={str(q):recipe.sha(q) for q in output.rglob('*') if q.is_file()})
    recipe.write(output/'result.json',report);print(json.dumps(report,sort_keys=True))
    raise SystemExit(not result.wasSuccessful())

if __name__=='__main__': main()
