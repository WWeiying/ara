#!/usr/bin/env python3
"""Compile actual GGML routing helpers with host stubs, not target kernels."""
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LLAMA = Path('/home/wangwy/llama/llama.cpp')
FILE = 'ggml/src/ggml-cpu/arch/riscv/akv.cpp'
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out/akv_pair_ggml_patch_20261107_01'
SDK = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
OLD_SDK = '785084122af984c1dd3fd6318efaf70cdcb017e8'
NATIVE_CALL = 'akv_attention_execute_v2_with_features_native(&plan, &workspace, &features)'
FEATURE_CALL = 'execute_features_native(&plan, &workspace, &features)'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def helper_region(source):
    first = source.index('static akv_status_t execute(')
    last = source.index('\n}  // namespace\n', first)
    return first, last, source[first:last]


def updated_source(original, helpers):
    first, last, _ = helper_region(original)
    result = original[:first]+helpers+original[last:]
    if result.count(NATIVE_CALL) != 1:
        raise ValueError('Expected one unchanged native-only portable call site')
    return result.replace(NATIVE_CALL, FEATURE_CALL, 1)


def clean_patch(head, updated):
    return 'diff --git a/'+FILE+' b/'+FILE+'\n'+''.join(difflib.unified_diff(
        head.splitlines(keepends=True), updated.splitlines(keepends=True),
        fromfile='a/'+FILE, tofile='b/'+FILE))


def portable_region(source):
    first = source.index('        if (portable) {\n            akv_attention_features_t features{};')
    last = source.index(' else\n#endif', first)
    return source[first:last]


HOST = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include "akv/akv.h"
#include "akv/akv_features.h"
#if POLICY_MODE == 0
#ifdef AKV_NATIVE_AUTO_PAIR_POLICY
#error Old SDK must not advertise auto policy
#endif
#elif POLICY_MODE == 1
#if !defined(AKV_NATIVE_AUTO_PAIR_POLICY) || AKV_NATIVE_AUTO_PAIR_POLICY != 1
#error New SDK macro/prototype contract is missing
#endif
#else
#undef AKV_NATIVE_AUTO_PAIR_POLICY
#define AKV_NATIVE_AUTO_PAIR_POLICY 0
#endif
#if PORTABLE
#define GGML_AKV_PORTABLE_FEATURES 1
#endif
#define GGML_ASSERT(x) assert(x)
enum route { none, v1_emu, v1_native, v2_emu, v2_native, v2_auto,
             features_emu, features_native, features_auto };
static route called;
static int calls, device_reads, env_reads, feature_reads;
static bool use_emulation;
static const char * override_value;
static akv_status_t response = AKV_STATUS_OK;
static akv_device_t cached_device;
static const akv_attention_plan_t * expected_plan;
static akv_attention_v2_workspace_t * expected_workspace;
static const akv_attention_features_t * expected_features;
static akv_attention_features_t supplied_features;
static const uint16_t mask[1] = {0};

extern "C" char * getenv(const char * name) noexcept {
    if (std::strcmp(name, "AKV_PAIR_HEADS") == 0) {
        ++env_reads;
        return const_cast<char *>(override_value);
    }
    return nullptr;
}
static bool emulation_enabled() { return use_emulation; }
static const akv_device_t & device() { ++device_reads; return cached_device; }
static akv_status_t mark(route value, const akv_attention_plan_t * plan) {
    assert(plan == expected_plan);
    called = value;
    ++calls;
    return response;
}
static akv_status_t emulate(void *, const akv_descriptor_t *, const uint16_t *, float *, size_t, float) {
    assert(false);
    return AKV_STATUS_EXECUTION;
}
akv_status_t akv_attention_execute(const akv_attention_plan_t * plan, akv_attention_executor_t fn, void * ctx) {
    assert(fn == emulate && ctx == nullptr);
    return mark(v1_emu, plan);
}
akv_status_t akv_attention_execute_native(const akv_attention_plan_t * plan) { return mark(v1_native, plan); }
akv_status_t akv_attention_execute_v2(const akv_attention_plan_t * plan, akv_attention_executor_t fn, void * ctx) {
    assert(fn == emulate && (ctx == nullptr || ctx == expected_features));
    return mark(ctx ? features_emu : v2_emu, plan);
}
akv_status_t akv_attention_execute_v2_native(const akv_attention_plan_t * plan, akv_attention_v2_workspace_t * ws) {
    assert(ws == expected_workspace);
    return mark(v2_native, plan);
}
akv_status_t akv_attention_execute_v2_with_features_reference(const akv_attention_plan_t * plan,
                                                            const akv_attention_features_t * features) {
    assert(features != nullptr && features->softcap == supplied_features.softcap);
    return mark(features_emu, plan);
}
akv_status_t akv_attention_execute_v2_with_features_native(const akv_attention_plan_t * plan,
    akv_attention_v2_workspace_t * ws, const akv_attention_features_t * features) {
    assert(ws == expected_workspace && features != nullptr);
    if (expected_features) assert(features == expected_features);
    assert(features->softcap == supplied_features.softcap);
    return mark(features_native, plan);
}
#if POLICY_MODE == 1
akv_status_t akv_attention_execute_v2_native_auto(const akv_device_t * dev,
    const akv_attention_plan_t * plan, akv_attention_v2_workspace_t * ws) {
    assert(dev == &cached_device && ws == expected_workspace);
    return mark(v2_auto, plan);
}
akv_status_t akv_attention_execute_v2_with_features_native_auto(const akv_device_t * dev,
    const akv_attention_plan_t * plan, akv_attention_v2_workspace_t * ws,
    const akv_attention_features_t * features) {
    assert(dev == &cached_device && ws == expected_workspace && features != nullptr);
    if (expected_features) assert(features == expected_features);
    assert(features->softcap == supplied_features.softcap);
    return mark(features_auto, plan);
}
#endif
#if PORTABLE
static bool decode_features(const void *, uint32_t, uint32_t, uint32_t, akv_attention_features_t * features) {
    *features = supplied_features;
    expected_features = features;
    return true;
}
int akv_attention_can_use_plain_scores(const akv_attention_features_t * features,
                                     const uint16_t * input_mask, uint32_t length) {
    assert(input_mask == mask && length == 137);
    ++feature_reads;
    return features->softcap == 0;
}
#endif
@HELPERS@
#if PORTABLE
static akv_status_t portable_call(akv_attention_plan_t & plan, akv_attention_v2_workspace_t & workspace) {
    const bool portable = true;
    const void * dst = nullptr;
    const uint32_t first_q_head = 0, rows = 2, active_kv = 137;
    akv_status_t execute_status = AKV_STATUS_BAD_ARGUMENT;
@PORTABLE_BODY@
    return execute_status;
}
#endif
static void reset() { called = none; calls = device_reads = env_reads = feature_reads = 0; }
static bool automatic() { return POLICY_MODE == 1 && override_value == nullptr; }
static void expect(route wanted, bool native_v2) {
    assert(called == wanted && calls == 1);
    assert(device_reads == (native_v2 && automatic() ? 1 : 0));
    assert(env_reads == (native_v2 && POLICY_MODE == 1 ? 1 : 0));
}
int main() {
    akv_attention_plan_t plan{};
    akv_attention_v2_workspace_t workspace{};
    plan.mask = mask;
    plan.descriptor.kv_length = 137;
    expected_plan = &plan;
    expected_workspace = &workspace;
    const char * overrides[] = {nullptr, "", "0", "1", "true", "invalid", "01", nullptr};
    const uint32_t dims[] = {64, 96, 128, 256};
    const uint32_t heads[] = {1, 2, 3, 6, 8};
    for (const char * value : overrides) {
        override_value = value;
        for (uint32_t dim : dims) for (uint32_t head : heads) {
            plan.descriptor.head_dim = dim;
            plan.descriptor.q_rows = head;
            for (int emu = 0; emu < 2; ++emu) for (uint32_t version = 1; version <= 2; ++version) {
                use_emulation = emu;
                plan.kernel_version = version;
                reset();
                assert(execute(&plan, &workspace) == response);
                expect(version == 1 ? (emu ? v1_emu : v1_native) :
                       emu ? v2_emu : automatic() ? v2_auto : v2_native, version == 2 && !emu);
            }
        }
#if PORTABLE
        plan.kernel_version = AKV_ATTENTION_KERNEL_VERSION_V2;
        for (float softcap : {0.0f, 0.75f}) {
            supplied_features = {};
            supplied_features.softcap = softcap;
            expected_features = &supplied_features;
            use_emulation = false;
            reset();
            const auto before = supplied_features;
            assert(execute_features_native(&plan, &workspace, &supplied_features) == response);
            expect(automatic() ? features_auto : features_native, true);
            assert(std::memcmp(&before, &supplied_features, sizeof(before)) == 0);
            for (int emu = 0; emu < 2; ++emu) {
                use_emulation = emu;
                expected_features = nullptr;
                reset();
                assert(portable_call(plan, workspace) == response);
                const bool plain = @WIP_PLAIN@ && softcap == 0;
                expect(emu ? (plain ? v2_emu : features_emu) :
                       plain ? (automatic() ? v2_auto : v2_native) :
                       automatic() ? features_auto : features_native, !emu);
            }
        }
#endif
    }
    // Errors are returned unchanged; no retry through another native entry.
    plan.kernel_version = AKV_ATTENTION_KERNEL_VERSION_V2;
    use_emulation = false;
    override_value = nullptr;
    for (auto status : {AKV_STATUS_EXECUTION, AKV_STATUS_RUNTIME_UNAVAILABLE}) {
        response = status;
        reset();
        assert(execute(&plan, &workspace) == status);
        expect(automatic() ? v2_auto : v2_native, true);
    }
    return 0;
}
'''


class GgmlPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = json.loads((OUT/'identity.json').read_text())
        cls.head = (OUT/'head-akv.cpp').read_text()
        cls.before = (OUT/'working-before.cpp').read_text()
        cls.working = (LLAMA/FILE).read_text()
        cls.helpers = helper_region(cls.working)[2]
        cls.clean = updated_source(cls.head, cls.helpers)
        cls.temp = tempfile.TemporaryDirectory(prefix='akv_ggml_policy_host_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.compiler = shutil.which('clang++') or shutil.which('g++')
        if not cls.compiler:
            raise RuntimeError('Host C++ compiler required')

    @staticmethod
    def run_command(argv, **kwargs):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30, **kwargs)
        if result.returncode:
            raise AssertionError(repr(argv)+'\n'+result.stdout+result.stderr)
        return result

    def test_original_identity_and_exact_wip_preservation(self):
        self.assertEqual(digest(self.head.encode()), self.identity['head_sha256'])
        self.assertEqual(digest(self.before.encode()), self.identity['working_before_sha256'])
        self.assertEqual(digest((OUT/'original-wip.patch').read_bytes()), self.identity['original_wip_sha256'])
        self.assertEqual(self.working, updated_source(self.before, self.helpers))
        self.assertEqual(portable_region(self.working), portable_region(self.before).replace(NATIVE_CALL, FEATURE_CALL))
        self.assertIn('akv_attention_can_use_plain_scores', portable_region(self.working))
        self.assertNotIn('akv_attention_can_use_plain_scores', portable_region(self.clean))

    def test_no_environment_mutation_shape_cache_or_lock_change(self):
        for source in (self.working, self.clean):
            helper = helper_region(source)[2]
            for forbidden in ('setenv(', 'putenv(', 'unsetenv(', 'static bool', 'thread_local',
                              'akv_device_query', 'q_rows', 'head_dim', 'context_mutex'):
                self.assertNotIn(forbidden, helper)
            self.assertEqual(source.count('std::lock_guard<std::mutex> context_lock(context_mutex());'),
                             (self.before if source == self.working else self.head).count(
                                 'std::lock_guard<std::mutex> context_lock(context_mutex());'))
            worker = source.index('    if (params->ith != 0) {')
            lock = source.index('    std::lock_guard<std::mutex> context_lock(context_mutex());', worker)
            self.assertLess(worker, lock)
            self.assertLess(lock, source.index('    if (is_prefill)', lock))
            self.assertLess(lock, source.index('    for (int64_t kv_head', lock))

    def test_own_patch_matches_clean_head_and_applies_to_private_index(self):
        patch = (OUT/'own.patch').read_text()
        self.assertEqual(patch, clean_patch(self.head, self.clean))
        self.assertEqual(patch.count('diff --git '), 1)
        self.assertNotIn('quant-kv.h', patch)
        self.assertNotIn('GGML_RISCV_AKV_FALLBACK', patch)
        self.assertNotIn('akv_attention_can_use_plain_scores', patch)
        self.assertIn('-                : '+NATIVE_CALL, patch)
        index = self.directory/'clean.index'
        env = dict(os.environ, GIT_INDEX_FILE=str(index))
        self.run_command(['git', '-C', LLAMA, 'read-tree', self.identity['head']], env=env)
        initial = digest(index.read_bytes())
        self.run_command(['git', '-C', LLAMA, 'apply', '--cached', '--check', OUT/'own.patch'], env=env)
        self.assertEqual(digest(index.read_bytes()), initial)

    def test_compiled_real_helpers_and_portable_branch_all_modes(self):
        for mode in (0, 1, 2):
            commit = OLD_SDK if mode == 0 else SDK
            inputs = self.directory/('sdk-'+str(mode))
            inputs.mkdir(exist_ok=True)
            archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', commit, 'software/akv/include'])
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(inputs, filter='data')
            for name, source in (('working', self.working), ('clean_head', self.clean)):
                for portable in (0, 1):
                    with self.subTest(sdk_mode=mode, source=name, portable=portable):
                        text = HOST.replace('@HELPERS@', helper_region(source)[2]).replace(
                            '@PORTABLE_BODY@', portable_region(source)).replace(
                            '@WIP_PLAIN@', 'true' if name == 'working' else 'false')
                        path = self.directory/('%s-%d-%d.cpp' % (name, mode, portable))
                        path.write_text(text)
                        binary = path.with_suffix('')
                        self.run_command([self.compiler, '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', '-Wno-unused-variable', '-DPOLICY_MODE='+str(mode),
                            '-DPORTABLE='+str(portable), '-I'+str(inputs/'software/akv/include'), path, '-o', binary])
                        self.run_command([binary])


if __name__ == '__main__':
    unittest.main()
