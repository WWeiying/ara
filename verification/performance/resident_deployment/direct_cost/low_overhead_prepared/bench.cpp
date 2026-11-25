#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "resident_attention/executor.h"
#include "resident_attention/dispatch.h"
#include "direct_client.h"
#include "fixture.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
#include <time.h>

static constexpr const char *sdk_commit = "4a7361f51ba5447a616217dad1c8e72e3ee2b45b";
static constexpr unsigned dimension = 128, heads = 2, incoming_flags = 8;
static constexpr size_t stack_prefault_bytes = 256 * 1024;
static constexpr const char *scope = "complete-sdk-attention";
static_assert(sizeof(ara_akv_direct_info) == 64 && sizeof(ara_akv_direct_lease) == 64, "direct ABI");
static_assert(sizeof(akv_attention_v2_workspace_t) == 6272, "pinned workspace ABI");

struct witness {
    uint64_t sdk = 0, info = 0, native_qk = 0, native_pv = 0, resident_qk = 0, resident_pv = 0;
};
static volatile bool measuring;
static volatile witness observed;
static unsigned acquires, releases, hot_client_calls;
static akv_device_t cached_device;

#define LEAF(name, signature, arguments, counter) \
    extern "C" void __real_##name signature; \
    extern "C" void __wrap_##name signature { \
        if (measuring) ++observed.counter; \
        __real_##name arguments; \
    }
LEAF(akv_experimental_qk_f16_pair_panel4,
     (const uint16_t *q, float *s, uint32_t t, size_t stride, uint32_t d), (q, s, t, stride, d), native_qk)
LEAF(akv_experimental_pv_f16_pair,
     (const float *s, uint16_t *a, const float *scale, uint32_t t, uint32_t d), (s, a, scale, t, d), native_pv)
LEAF(akv_experimental_resident_qk_prepared,
     (float *s, uint32_t t, uint32_t h, uint64_t c), (s, t, h, c), resident_qk)
LEAF(akv_experimental_resident_pv_prepared,
     (const float *s, uint16_t *a, const float *scale, uint32_t t, uint32_t d, uint32_t h, uint64_t c),
     (s, a, scale, t, d, h, c), resident_pv)
#undef LEAF

extern "C" uint64_t __real_akv_native_info(void *, unsigned);
extern "C" uint64_t __wrap_akv_native_info(void *context, unsigned index) {
    if (measuring) ++observed.info;
    return __real_akv_native_info(context, index);
}
extern "C" akv_status_t __real_akv_experimental_attention_execute_v2_native(
    const akv_device_t *, const akv_attention_plan_t *, akv_attention_v2_workspace_t *,
    const akv_attention_features_t *, const akv_resident_attention_options_t *, unsigned);
extern "C" akv_status_t __wrap_akv_experimental_attention_execute_v2_native(
    const akv_device_t *device, const akv_attention_plan_t *plan, akv_attention_v2_workspace_t *work,
    const akv_attention_features_t *features, const akv_resident_attention_options_t *options, unsigned automatic) {
    if (measuring) ++observed.sdk;
    return __real_akv_experimental_attention_execute_v2_native(device, plan, work, features, options, automatic);
}

extern "C" int __real_ara_akv_direct_open(ara_akv_direct_info *);
extern "C" long __real_ara_akv_direct_acquire(int, ara_akv_direct_lease *);
extern "C" long __real_ara_akv_direct_release(int);
extern "C" void __real_ara_akv_direct_close(int);
extern "C" int __wrap_ara_akv_direct_open(ara_akv_direct_info *info) {
    if (measuring) { ++hot_client_calls; return -1; }
    return __real_ara_akv_direct_open(info);
}
extern "C" long __wrap_ara_akv_direct_acquire(int fd, ara_akv_direct_lease *lease) {
    if (measuring) { ++hot_client_calls; return -1; }
    ++acquires;
    return __real_ara_akv_direct_acquire(fd, lease);
}
extern "C" long __wrap_ara_akv_direct_release(int fd) {
    if (measuring) { ++hot_client_calls; return -1; }
    ++releases;
    return __real_ara_akv_direct_release(fd);
}
extern "C" void __wrap_ara_akv_direct_close(int fd) {
    if (measuring) { ++hot_client_calls; return; }
    __real_ara_akv_direct_close(fd);
}

template<class T> struct alignas(64) guarded {
    unsigned char before[64];
    alignas(64) T value;
    unsigned char after[64];
};
static guarded<std::array<uint16_t, 256>> query;
static guarded<std::array<float, 256>> output;
static guarded<akv_attention_v2_workspace_t> workspace;

static uint64_t now() {
    timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &time)) std::abort();
    return uint64_t(time.tv_sec) * UINT64_C(1000000000) + uint64_t(time.tv_nsec);
}
static uint64_t hash(const void *pointer, size_t bytes) {
    const auto *p = static_cast<const unsigned char *>(pointer);
    uint64_t value = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < bytes; ++i) value = (value ^ p[i]) * UINT64_C(1099511628211);
    return value;
}
static bool sentinel(const void *pointer, size_t bytes) {
    const auto *p = static_cast<const unsigned char *>(pointer);
    for (size_t i = 0; i < bytes; ++i) if (p[i] != 0xa5) return false;
    return true;
}
template<class T> static bool guards(const guarded<T> &object) {
    return sentinel(object.before, sizeof(object.before)) && sentinel(object.after, sizeof(object.after));
}
static void state(uintptr_t &fcsr, uintptr_t &vcsr, uintptr_t &vstart) {
    asm volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart"
                 : "=r"(fcsr), "=r"(vcsr), "=r"(vstart) : : "memory");
}
static void drain() {
    asm volatile("csrr zero,vl\nfence rw,rw" : : : "memory");
}
static __attribute__((noinline)) void prefault_stack() {
    volatile unsigned char pages[stack_prefault_bytes];
    for (size_t i = 0; i < sizeof(pages); i += 1024) pages[i] = 0;
    pages[sizeof(pages) - 1] = 0;
    asm volatile("" : : "r"(pages) : "memory");
}

static bool finite_fixture(unsigned tokens) {
    for (float value : capture_query) {
        uint32_t bits;
        std::memcpy(&bits, &value, sizeof(bits));
        if ((bits & 0x7fffffffu) > 0x477fe000u) return false;
    }
    for (unsigned i = 0; i < tokens * dimension; ++i)
        if ((capture_key[i] & 0x7c00u) == 0x7c00u || (capture_value[i] & 0x7c00u) == 0x7c00u) return false;
    bool visible = false;
    for (unsigned i = 0; i < tokens; ++i) {
        if ((capture_mask[i] & 0x7c00u) != 0x7c00u) visible = true;
        else if (capture_mask[i] != 0xfc00u) return false;
    }
    return visible;
}

static bool capable(const akv_device_t &device) {
    const auto &c = device.capabilities;
    return c.valid && c.enabled && c.f16_payload && c.context_count && c.max_q_rows >= heads &&
        c.head_dim_128 && c.token_axis_valid && c.token_axis_enabled && c.token_axis_tail &&
        c.token_axis_row_view && c.token_axis_column_panel4 && c.token_axis_tile_tokens == 64 &&
        c.resident_valid && c.resident_capability_version == AKV_RESIDENT_CAPABILITY_VERSION &&
        c.resident_qk_supported && c.resident_pv_supported && c.resident_nr_lanes == 4 && c.resident_vlen_bits == 1024;
}

struct call_context {
    const akv_device_t *device;
    akv_resident_attention_options_t options;
    bool preflight = true;
    unsigned visited = 0;
};
static akv_status_t group(void *opaque, const akv_attention_plan_t *plan, uint32_t batch, uint32_t first) {
    auto &context = *static_cast<call_context *>(opaque);
    if (batch || first || context.visited++ || plan->descriptor.q_rows != heads || plan->descriptor.head_dim != dimension)
        return AKV_STATUS_LAYOUT;
    if (context.preflight) {
        const auto route = akv_resident_attention_select(context.device, plan, &context.options, 0);
        if (route != (context.options.requested ? AKV_RESIDENT_USE_SHARED : AKV_RESIDENT_KEEP_NATIVE))
            return AKV_STATUS_CAPABILITY;
        // Original VCS framing preflights resident tile maps only in the ON arm.
        if (context.options.requested) {
            for (unsigned start = 0; start < plan->descriptor.kv_length; start += 64) {
                akv_resident_attention_tile_t tile;
                if (akv_resident_attention_dispatch_plan(route, &plan->descriptor, start, &tile) != AKV_STATUS_OK)
                    return AKV_STATUS_SHAPE;
            }
        }
        return AKV_STATUS_OK;
    }
    return akv_experimental_attention_execute_v2_native(context.device, plan, &workspace.value,
                                                        nullptr, &context.options, 1);
}

static akv_decode_problem_t problem_for(unsigned tokens) {
    akv_decode_problem_t problem{};
    problem.query = query.value.data(); problem.key = capture_key; problem.value = capture_value;
    problem.mask = capture_mask; problem.output = output.value.data();
    problem.query_bytes = sizeof(query.value); problem.key_bytes = sizeof(capture_key);
    problem.value_bytes = sizeof(capture_value); problem.mask_bytes = sizeof(capture_mask);
    problem.output_bytes = sizeof(output.value);
    problem.q_head_stride = 256; problem.q_batch_stride = 512;
    problem.k_token_stride = problem.v_token_stride = 256;
    problem.k_head_stride = problem.k_batch_stride = sizeof(capture_key);
    problem.v_head_stride = problem.v_batch_stride = sizeof(capture_value);
    problem.mask_batch_stride = 0; problem.output_head_stride = 512; problem.output_batch_stride = 1024;
    problem.batches = problem.kv_heads = 1; problem.query_heads = heads;
    problem.kv_length = tokens; problem.head_dim = dimension; problem.scale = 0x1.6a09e6p-4f;
    return problem;
}

static akv_resident_attention_options_t options_for(bool resident) {
    akv_resident_attention_options_t options{};
    options.requested = resident;
    options.validated_available = options.platform_admitted = options.whole_call_owned = 1;
    options.decode_head_rows = options.query_tokens = options.plain_scores = 1;
    options.vlenb = 128;
    return options;
}

static bool fixture_preflight(const akv_device_t &device, unsigned tokens) {
    const auto problem = problem_for(tokens);
    const uintptr_t work = reinterpret_cast<uintptr_t>(&workspace.value);
    const void *bases[] = {problem.query, problem.key, problem.value, problem.mask, problem.output};
    const size_t sizes[] = {problem.query_bytes, problem.key_bytes, problem.value_bytes,
                           problem.mask_bytes, problem.output_bytes};
    for (unsigned i = 0; i < 5; ++i) {
        const uintptr_t base = reinterpret_cast<uintptr_t>(bases[i]);
        uintptr_t end;
        if (__builtin_add_overflow(base, sizes[i], &end) ||
            !(end <= work || base >= work + sizeof(workspace.value))) return false;
    }
    for (unsigned arm = 0; arm < 2; ++arm) {
        call_context context{&device, options_for(arm != 0), true, 0};
        uint64_t completed = 0;
        if (akv_decode_execute(&device, &problem, group, &context, &completed) != AKV_STATUS_OK ||
            completed != 1 || context.visited != 1) return false;
    }
    return true;
}

static __attribute__((noinline)) akv_status_t full_call(bool resident, unsigned tokens, uint64_t &completed) {
    // Match the original VCS SDK whole-call conversion, including FP flags.
    for (unsigned i = 0; i < heads * dimension; ++i) {
        uintptr_t bits;
        asm volatile("fcvt.h.s ft0,%1\nfmv.x.h %0,ft0" : "=r"(bits) : "f"(capture_query[i]) : "ft0");
        query.value[i] = uint16_t(bits);
    }
    const akv_device_t &device = cached_device; // Initialized once under this lease.
    const auto problem = problem_for(tokens);
    call_context context{&device, options_for(resident), false, 0};
    return akv_decode_execute(&device, &problem, group, &context, &completed);
}

static bool workspace_guards() {
    if (!guards(workspace) || !guards(query) || !guards(output)) return false;
    for (unsigned h = 0; h < AKV_MAX_Q_ROWS; ++h) {
        const unsigned start = h < heads ? dimension : 0;
        if (!sentinel(workspace.value.accumulator[h] + start, (AKV_HEAD_DIM_256 - start) * 2)) return false;
        if (h >= heads && (!sentinel(workspace.value.score[h], sizeof(workspace.value.score[h])) ||
            !sentinel(&workspace.value.maximum[h], 4) || !sentinel(&workspace.value.sum[h], 4) ||
            !sentinel(&workspace.value.old_scale[h], 4))) return false;
    }
    const size_t tail = offsetof(akv_attention_v2_workspace_t, old_scale) + sizeof(workspace.value.old_scale);
    return sentinel(reinterpret_cast<const unsigned char *>(&workspace.value) + tail, sizeof(workspace.value) - tail);
}

int main(int argc, char **argv) {
    const bool probe = argc == 2 && !std::strcmp(argv[1], "--probe");
    unsigned tokens = 0;
    if (!probe && argc == 2) {
        if (!std::strcmp(argv[1], "65")) tokens = 65;
        if (!std::strcmp(argv[1], "128")) tokens = 128;
        if (!std::strcmp(argv[1], "137")) tokens = 137;
    }
    if (!probe && !tokens) {
        std::fprintf(stderr, "usage: resident-direct-pair --probe|65|128|137\n");
        return 2;
    }
    if (std::setvbuf(stdout, nullptr, _IONBF, 0)) return 1;
    ara_akv_direct_info info{};
    const int fd = ara_akv_direct_open(&info);
    if (fd < 0) { std::fprintf(stderr, "DIRECT_FAIL open=%d\n", fd); return 1; }
    // All storage, input scans and prefaulting precede the sole acquire.
    std::memset(&query, 0xa5, sizeof(query)); std::memset(&workspace, 0xa5, sizeof(workspace));
    std::memset(&output, 0xa5, sizeof(output));
    const void *inputs[] = {capture_query, capture_key, capture_value, capture_mask};
    const size_t bytes[] = {sizeof(capture_query), sizeof(capture_key), sizeof(capture_value), sizeof(capture_mask)};
    uint64_t fingerprints[4];
    for (unsigned i = 0; i < 4; ++i) fingerprints[i] = hash(inputs[i], bytes[i]);
    if (!finite_fixture(probe ? 137 : tokens)) { ara_akv_direct_close(fd); return 1; }
    (void)now();
    // Trigger Linux's standard lazy vector first-use before lease/custom INFO.
    asm volatile("fmv.d.x ft0,zero\ncsrw fcsr,zero\nvsetvli zero,zero,e8,m1,ta,ma\n"
                 "csrw vcsr,zero\ncsrwi vstart,0" : : : "ft0", "memory");
    prefault_stack();
    if (mlockall(MCL_CURRENT | MCL_FUTURE)) {
        std::perror("DIRECT_FAIL mlockall");
        ara_akv_direct_close(fd);
        return 1;
    }
    ara_akv_direct_lease lease{};
    long rc = ara_akv_direct_acquire(fd, &lease);
    if (rc) { std::fprintf(stderr, "DIRECT_FAIL acquire=%ld\n", rc); ara_akv_direct_close(fd); return 1; }
    uintptr_t fcsr, vcsr, vstart, vlenb;
    state(fcsr, vcsr, vstart);
    asm volatile("csrr %0,vlenb" : "=r"(vlenb));
    akv_device_t &device = cached_device;
    unsigned errors = vlenb != 128 || vstart != 0 || (fcsr & 0xe0u) ||
        info.abi != 1 || info.bytes != 64 || info.features != 7 || info.online_cpus != 1 ||
        info.gate_signature != ARA_AKV_GATE_SIGNATURE || lease.abi != 1 || lease.bytes != 64 ||
        lease.flags || lease.reserved0 || !lease.generation || !lease.owner_tid || lease.hart;
    if (!errors) errors += akv_device_query(akv_native_info, nullptr, &device) != AKV_STATUS_OK || !capable(device);
    if (!errors) errors += !fixture_preflight(device, probe ? 137 : tokens);
    std::printf("DIRECT_SETUP {\"scope\":\"%s\",\"sdk_commit\":\"%s\",\"tokens\":%u,\"probe\":%s,"
                "\"abi\":%u,\"features\":%u,\"online_cpus\":%u,\"gate_signature\":\"0x%llx\","
                "\"lease_generation\":%llu,\"owner_tid\":%u,\"hart\":%u,\"acquires\":%u,"
                "\"vlenb\":%lu,\"finite_prechecks\":1,\"mlockall\":true,\"stack_prefault_bytes\":%zu,"
                "\"vector_first_use\":true,\"fp_initialized\":true,\"fixture_preflights\":2,\"errors\":%u}\n",
                scope, sdk_commit, tokens, probe ? "true" : "false", info.abi, info.features, info.online_cpus,
                (unsigned long long)info.gate_signature, (unsigned long long)lease.generation,
                lease.owner_tid, lease.hart, acquires, (unsigned long)vlenb, stack_prefault_bytes, errors);
    if (!probe && !errors) {
        const uint32_t *gold = tokens == 65 ? golden_65 : tokens == 128 ? golden_128 : golden_137;
        const unsigned flags = tokens == 65 ? flags_65 : tokens == 128 ? flags_128 : flags_137;
        unsigned trials[2]{};
        // Two first-arm calls, then three ABBA blocks: six warm samples per arm.
        const unsigned order[] = {0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0};
        for (unsigned sequence = 0; sequence < 14 && !errors; ++sequence) {
            const unsigned arm = order[sequence], trial = trials[arm]++;
            state(fcsr, vcsr, vstart);
            if (vstart || (fcsr & 0xe0u)) { errors = 1; break; }
            std::memset(&query, 0xa5, sizeof(query)); std::memset(&workspace, 0xa5, sizeof(workspace));
            std::memset(&output, 0xa5, sizeof(output));
            observed.sdk = observed.info = observed.native_qk = observed.native_pv = 0;
            observed.resident_qk = observed.resident_pv = 0;
            asm volatile("csrw fcsr,%0\ncsrw vcsr,zero" : : "r"(uintptr_t(incoming_flags)) : "memory");
            uint64_t completed = 0;
            const uint64_t begin = now();
            measuring = true;
            const akv_status_t status = full_call(arm != 0, tokens, completed);
            drain(); state(fcsr, vcsr, vstart);
            measuring = false;
            const uint64_t ns = now() - begin;
            const unsigned tiles = (tokens + 63) / 64;
            errors += status != AKV_STATUS_OK || completed != 1 || !ns || !workspace_guards();
            errors += fcsr != (flags | incoming_flags) || vcsr || vstart || hot_client_calls;
            errors += observed.sdk != 1 || observed.info != 0;
            errors += observed.native_qk != (arm ? 0u : tiles) || observed.native_pv != (arm ? 0u : tiles);
            errors += observed.resident_qk != (arm ? tiles : 0u) || observed.resident_pv != (arm ? tiles : 0u);
            for (unsigned i = 0; i < 256; ++i) {
                uint32_t bits;
                std::memcpy(&bits, output.value.data() + i, 4);
                errors += bits != gold[i];
            }
            for (unsigned i = 0; i < 4; ++i) errors += fingerprints[i] != hash(inputs[i], bytes[i]);
            std::printf("DIRECT_SAMPLE {\"sequence\":%u,\"mode\":\"%s\",\"tokens\":%u,\"trial\":%u,"
                        "\"cold\":%s,\"ns\":%llu,\"status\":%u,\"completed_groups\":%llu,"
                        "\"sdk_calls\":%llu,\"info_calls\":%llu,\"native_qk\":%llu,\"native_pv\":%llu,"
                        "\"resident_qk\":%llu,\"resident_pv\":%llu,\"incoming_fflags\":%u,\"fflags\":%lu,"
                        "\"vcsr\":%lu,\"vstart\":%lu,\"hot_client_calls\":%u,\"output_fnv64\":\"%016llx\",\"errors\":%u}\n",
                        sequence, arm ? "resident" : "native-akv", tokens, trial, trial ? "false" : "true",
                        (unsigned long long)ns, unsigned(status), (unsigned long long)completed,
                        (unsigned long long)observed.sdk, (unsigned long long)observed.info,
                        (unsigned long long)observed.native_qk, (unsigned long long)observed.native_pv,
                        (unsigned long long)observed.resident_qk, (unsigned long long)observed.resident_pv,
                        incoming_flags, (unsigned long)(fcsr & 31), (unsigned long)vcsr, (unsigned long)vstart,
                        hot_client_calls, (unsigned long long)hash(output.value.data(), sizeof(output.value)), errors);
            std::fflush(stdout);
        }
    }
    // Invalid VSTART is terminal; clear it only for safe C teardown, never retry.
    asm volatile("csrwi vstart,0" : : : "memory");
    rc = ara_akv_direct_release(fd);
    errors += rc != 0 || acquires != 1 || releases != 1 || hot_client_calls;
    ara_akv_direct_close(fd);
    std::printf("DIRECT_DONE {\"tokens\":%u,\"acquires\":%u,\"releases\":%u,\"hot_client_calls\":%u,\"errors\":%u}\n",
                tokens, acquires, releases, hot_client_calls, errors);
    if (errors) return 1;
    std::puts(probe ? "AKV_DIRECT_PROBE_PASS" : "AKV_DIRECT_PAIR_PASS");
    return 0;
}


