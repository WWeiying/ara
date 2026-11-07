#!/usr/bin/env python3
"""Host-only wrapper/recipe/evidence tests. No RISC-V compiler or RTL execution."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('integration_test_'+name, HERE/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build, check, runner = load('build'), load('check'), load('run')

HOST_STUB = r'''
#include "akv/akv.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
extern int integration_main(void);
extern const float native_golden[];
static int mode, calls, legacy_calls, auto_calls, info_calls;
static unsigned long flags, ticks;
int printf_(const char *fmt, ...) {
  va_list ap; va_start(ap, fmt); int n = vprintf(fmt, ap); va_end(ap); return n;
}
unsigned long pair_host_initialize(void) { return 128; }
unsigned long pair_host_cycles(void) { return ++ticks*100000; }
void pair_host_drain(void) {}
void pair_host_reset(void) { flags = 0; }
void pair_host_csr(unsigned long *f, unsigned long *v, unsigned long *s) {
  *f = flags; *v = *s = 0;
}
static int no_environment(void) {
  return !getenv("AKV_PAIR_HEADS") && !getenv("AKV_QK_PANEL4") &&
         !getenv("AKV_PREFILL_PAIR_PV") && !getenv("UNRELATED");
}
unsigned long akv_native_info(void *ctx, unsigned index) {
  (void)ctx; ++info_calls;
  unsigned long word = akv_capability_word(index, 1);
  return word ? word : akv_v2_capability_word(index, 1);
}
static akv_status_t execute(const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w, int auto_mode) {
  const int expected[] = {0,1,1,0};
  if (calls >= 4 || expected[calls] != auto_mode || !no_environment() ||
      !akv_attention_plan_v2_is_valid(p) || p->descriptor.q_rows != 2 ||
      p->descriptor.head_dim != 128 || p->descriptor.kv_length != 137) return AKV_STATUS_EXECUTION;
  memcpy(p->output, native_golden, 1024);
  flags = 3;
  if (calls == 1) {
    if (mode == 1) return AKV_STATUS_EXECUTION;
    if (mode == 2) flags = 8;
    if (mode == 3) { unsigned bits; memcpy(&bits,p->output,4); ++bits; memcpy(p->output,&bits,4); }
    if (mode == 4) w->accumulator[0][128] ^= 1;
    if (mode == 5) ((unsigned short *)(unsigned long)p->descriptor.q_base)[0] ^= 1;
  }
  ++calls;
  return AKV_STATUS_OK;
}
akv_status_t akv_attention_execute_v2_native(const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w) {
  ++legacy_calls;
  return execute(p,w,0);
}
akv_status_t akv_attention_execute_v2_native_auto(const akv_device_t *d,
    const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w) {
  ++auto_calls;
  akv_device_t reference;
  if (!d || akv_device_init_reference(&reference) != AKV_STATUS_OK ||
      memcmp(&reference,d,sizeof(reference)) || !no_environment()) return AKV_STATUS_EXECUTION;
  return execute(p,w,1);
}
int main(int argc, char **argv) {
  mode = argc > 1 ? atoi(argv[1]) : 0;
  if (!no_environment()) return 98;
  int status = integration_main();
  if (!mode && (calls != 4 || legacy_calls != 2 || auto_calls != 2 || info_calls != 16 || !no_environment())) return 99;
  return status;
}
'''


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='akv_auto_integration_host_')
        cls.directory = Path(cls.temp.name)
        cls.old, cls.original, cls.base, cls.pins = build.base_inputs()
        cls.sdk, cls.raw, cls.members = build.sdk_contract()
        cls.inputs = cls.directory/'inputs'
        cls.inputs.mkdir()
        cls.old.unpack_archive(cls.raw, cls.inputs)
        cls.fixture = build.load(build.PRIMARY/'test_eval.py', 'auto_integration_original_fixtures')
        cls.native = Path(cls.base['golden']['native_tile64']).read_bytes()
        cls.golden = Path(cls.base['golden']['captured']).read_bytes()
        (cls.directory/'stub.c').write_text(HOST_STUB)
        common, sdk = cls.inputs/'apps/common', cls.inputs/'software/akv'
        flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-fno-fast-math', '-ffp-contract=off',
                 '-ffunction-sections', '-fdata-sections', '-I'+str(sdk/'include'),
                 '-I'+str(common), '-I'+str(build.BASE)]
        cls.host([cls.old.HOST_CC, *flags, '-DAKV_PAIR_HOST_TEST', '-Dmain=integration_main',
                  '-c', HERE/'main.c', '-o', cls.directory/'caller.o'])
        cls.host([cls.old.HOST_CC, *flags, cls.directory/'caller.o', build.BASE/'data.S',
                  cls.directory/'stub.c', sdk/'src/akv_decode.c', sdk/'src/akv_runtime.c',
                  '-Wl,--gc-sections', '-lm', '-o', cls.directory/'caller'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def host(argv):
        proc = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise AssertionError(repr(argv)+'\n'+proc.stdout+proc.stderr)
        return proc.stdout

    def test_exact_sdk_archive_and_default_commit(self):
        self.assertEqual(build.SDK_COMMIT, 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1')
        self.assertEqual(self.sdk['sdk_new'], build.SDK_COMMIT)
        self.assertEqual(self.sdk['baseSDK'], build.BASE_SDK)
        self.assertEqual(self.sdk['sdk_diffset'], build.SDK_DIFF)
        self.assertEqual(self.members['software/akv/src/akv_v2_attention_rvv.S'],
                         (build.BASE/'inputs/software/akv/src/akv_v2_attention_rvv.S').read_bytes())
        self.assertEqual(set(build.OWN_FILES), {'build.py','main.c','check.py','test_integration.py','run.py'})

    def test_real_sdk_decode_wrapper_null_getenv_and_cached_device(self):
        text = self.host([self.directory/'caller']) + self.fixture.hardware_log()
        result = self.original.check_log(text, self.golden, self.native, self.old.MEMORY)
        self.assertEqual(result['output_values_checked'], 1024)
        self.assertEqual(result['fcsr'], 3)
        self.assertEqual(self.original.check_hardware_work(text)['commands'], 2566)

    def test_firmware_status_flags_exact_bits_guard_and_query_errors_return_nonzero(self):
        for mode in range(1, 6):
            with self.subTest(mode=mode):
                proc = subprocess.run([str(self.directory/'caller'), str(mode)],
                                      capture_output=True, text=True, timeout=5)
                self.assertEqual(proc.returncode, 1, proc.stdout[-400:]+proc.stderr)

    def test_structured_recipe_recompiles_all_objects_and_reuses_only_sealed_data(self):
        output = self.directory/'new-build'
        recipe = build.target_recipe(output)
        compiles = [r['argv'] for r in recipe if r['label'].startswith('compile-')]
        self.assertEqual(len(compiles), 16)
        self.assertEqual(compiles[0][compiles[0].index('-c')+1], str(HERE/'main.c'))
        self.assertEqual(compiles[1][compiles[1].index('-c')+1], str(build.BASE/'data.S'))
        original = json.loads((build.BASE/'commands.json').read_text())
        before = [c['argv'] for c in original if c['label'].startswith('compile-')]
        for old, new in zip(before, compiles):
            self.assertEqual([x for x in old if x.startswith(('-D','-f','-m','-O','-std'))],
                             [x for x in new if x.startswith(('-D','-f','-m','-O','-std'))])
            self.assertIn('-I'+str(output/'inputs/software/akv/include'), new)
            self.assertIn('-I'+str(build.BASE), new)
            self.assertEqual(Path(new[new.index('-MF')+1]).parent, output)
            self.assertEqual(Path(new[-1]).parent, output)
        link = next(r['argv'] for r in recipe if r['label'] == 'link')
        self.assertEqual([x for x in link if x.endswith('.o')], [c[-1] for c in compiles])
        self.assertEqual(link[link.index('-T')+1], str(build.BASE/'link.ld'))
        self.assertEqual(link[-1], str(output/build.ELF_NAME))

    def test_base_build_every_file_and_sealed_helpers_are_pinned(self):
        for p in build.BASE.rglob('*'):
            if p.is_file():
                self.assertEqual(self.pins[str(p)], build.sha(p))
        for n, digest in build.SEALED.items():
            self.assertEqual(self.pins[str(build.PRIMARY/n)], digest)
        self.assertIn(str(build.PRIMARY/'reference.c'), self.pins)

    def repack(self, members):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as tar:
            for name, raw in members.items():
                info = tarfile.TarInfo(name); info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))
        return buffer.getvalue()

    def test_dirty_assembly_unapproved_file_missing_policy_and_wrong_api_rejected(self):
        old_raw = (build.BASE/'inputs/sdk-785084122.tar').read_bytes()
        for name in ('software/akv/src/akv_v2_attention_rvv.S', 'apps/common/crt0.S',
                     'software/akv/experimental/paired_heads/dispatch.h'):
            members = dict(self.members); members[name] += b'\n/* unapproved */\n'
            with self.subTest(name=name), self.assertRaises(ValueError):
                build.validate_sdk_archive(self.repack(members), old_raw)
        members = dict(self.members)
        del members['software/akv/experimental/paired_heads/auto_policy.h']
        with self.assertRaises(ValueError):
            build.validate_sdk_archive(self.repack(members), old_raw)
        members = dict(self.members)
        name = 'software/akv/include/akv/akv.h'
        members[name] = members[name].replace(b'*device, const akv_attention_plan_t *plan',
                                            b'*device, akv_attention_plan_t *plan')
        with self.assertRaisesRegex(ValueError, 'signature'):
            build.validate_sdk_archive(self.repack(members), old_raw)
        for commit in ('HEAD', build.BASE_SDK):
            with self.assertRaises(ValueError):
                build.sdk_contract(commit)

    def test_new_manifest_cannot_masquerade_as_old_sdk_or_optin_environment(self):
        output = self.directory/'bad-receipt'
        output.mkdir()
        manifest = build.manifest_fields(output, self.sdk, self.base)
        changes = [dict(schema=1), dict(sdk_head=build.BASE_SDK), dict(baseSDK=build.SDK_COMMIT),
                   dict(sdk_diffset={}), dict(all_runtime_objects_recompiled=False),
                   dict(objects_recompiled=15), dict(environment={'AKV_PAIR_HEADS':'1'}),
                   dict(shape={**manifest['shape'], 'valid_tokens':136})]
        for changed in changes:
            (output/'build.json').write_text(json.dumps({**manifest, **changed}))
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'receipt|contract'):
                check.verify_build(output)
        (output/'build.json').write_text(json.dumps(manifest))
        (output/'source-pins.json').write_text('{}')
        manifest['source_pins_sha256'] = build.sha(output/'source-pins.json')
        (output/'build.json').write_text(json.dumps(manifest))
        shutil.copytree(self.inputs, output/'inputs')
        (output/'inputs/sdk-auto.tar').write_bytes(self.raw)
        with self.assertRaisesRegex(ValueError, 'Missing required base/new input pin'):
            check.verify_build(output)
        p = output/'inputs/software/akv/src/akv_v2_attention_rvv.S'
        p.write_bytes(p.read_bytes()+b'\n/* drift */\n')
        with self.assertRaisesRegex(ValueError, 'differs from archive'):
            check.verify_build(output)

    def test_public_numerical_and_vector_apis_keep_original_gates(self):
        log, vector = self.directory/'fixture.log', self.directory/'fixture.csv'
        log.write_text(self.fixture.firmware_log(self.native)+self.fixture.hardware_log())
        vector.write_text(self.fixture.vector_csv())
        manifest = build.manifest_fields(self.directory, self.sdk, self.base)
        manifest.update(elf_sha256='host-fixture', source_pins_sha256='host-fixture', elf_link_checks={})
        (self.directory/'build.json').write_text(json.dumps(manifest))
        with patch.object(check, 'verify_build', return_value=manifest):
            self.assertEqual(check.check_run(log, self.directory)['state'], 'PASS')
            result = check.check_vector_workcounts(vector, self.directory)
            self.assertEqual(result['native_commands_with_lifecycle'], 2566)
            self.assertEqual(result['sdk_new'], build.SDK_COMMIT)
            log.write_text(self.fixture.firmware_log(self.native)+
                           self.fixture.hardware_log(self.fixture.command_rows((0,0,0,0))))
            with self.assertRaises(ValueError):
                check.check_run(log, self.directory)
        good = self.fixture.vector_csv()
        for text in (good.replace('0205745b','0005745b'), good.replace('0205345b','0405345b',1),
                     good.rsplit('\n',2)[0], good+good.splitlines()[-1]+'\n',
                     good.replace(',1024',',2048',1)):
            vector.write_text(text)
            with self.assertRaises(ValueError):
                check.vector_workcounts(vector)
        for text in ('TIMEOUT', 'AKV_PAIR_DONE trials=4 errors=0\nCore Test *** SUCCESS *** (tohost = 0)'):
            log.write_text(text)
            with patch.object(check, 'verify_build', return_value=manifest), self.assertRaises(ValueError):
                check.check_run(log, self.directory)

    def test_private_owner_loader_only_changes_checker_and_keeps_original_root(self):
        private = runner.load_owner()
        self.assertEqual(Path(private.__file__), build.PRIMARY/'run.py')
        self.assertEqual(private.ROOT, build.ROOT)
        path, module = private.load_checker('qwen3_abba')
        self.assertEqual(path, HERE/'check.py')
        self.assertTrue(callable(module.check_run) and callable(module.check_vector_workcounts))
        with self.assertRaises(ValueError):
            private.load_checker('regression')
        untouched = build.load(build.PRIMARY/'run.py', 'integration_test_original_owner_unchanged')
        self.assertEqual(untouched.load_checker('qwen3_abba')[0], build.PRIMARY/'check.py')

    def test_bad_output_or_existing_directory_cannot_start_cross_compiler(self):
        with patch.object(build.subprocess, 'run', side_effect=AssertionError('No cross compiler allowed')):
            with self.assertRaises(ValueError):
                build.build(self.directory)
            with patch.object(build, 'OUT', self.directory):
                existing = self.directory/'akv_pair_integration_build_20261107_host'
                existing.mkdir()
                with self.assertRaisesRegex(ValueError, 'Fresh'):
                    build.build(existing)

    def test_non_native_or_missing_auto_elf_rejected(self):
        path = self.directory/'not-target.elf'
        path.write_bytes((self.directory/'caller').read_bytes())
        with self.assertRaises(ValueError):
            check.check_elf(path)
        # Read the existing target ELF only; crt0's _start is STT_NOTYPE/size zero.
        with self.assertRaisesRegex(ValueError, 'Missing actual native auto link'):
            check.check_elf(self.base['elf'])


if __name__ == '__main__':
    unittest.main()
