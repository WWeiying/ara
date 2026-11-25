#include "ggml.h"
#include "ggml-cpu.h"
#include "ggml-cpu-impl.h"
#include "arch/riscv/akv.h"
#include "client.h"
#include "fixture.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/ioctl.h>
#include <time.h>

static unsigned calls, completed, registrations, groups;
static bool profile;
static uint64_t copied;
static void stats(int fd) {
    if (!profile) return;
    ara_resident_stats s{};
    if (ioctl(fd, ARA_RESIDENT_GET_STATS, &s) || s.status) std::abort();
    copied += s.copied_input_bytes;
    std::printf("PHASE bytes=%llu copy_ns=%llu execute_ns=%llu total_ns=%llu allocations=%llu\n",
        (unsigned long long)s.copied_input_bytes, (unsigned long long)s.input_copy_ns,
        (unsigned long long)s.execute_ns, (unsigned long long)s.total_ns,
        (unsigned long long)s.allocated_buffers);
}
extern "C" long __real_ara_resident_linux_execute(int, ara_resident_job *);
extern "C" long __wrap_ara_resident_linux_execute(int fd, ara_resident_job *j) {
    ++calls;
    long rc = __real_ara_resident_linux_execute(fd, j);
    if (!rc) { ++completed; ++groups; stats(fd); }
    return rc;
}
extern "C" long __real_ara_resident_linux_execute_batch(int, ara_resident_batch *);
extern "C" long __wrap_ara_resident_linux_execute_batch(int fd, ara_resident_batch *j) {
    ++calls;
    long rc = __real_ara_resident_linux_execute_batch(fd, j);
    if (!rc) { ++completed; groups += j->completed; stats(fd); }
    return rc;
}
extern "C" long __real_ara_resident_linux_register_kv(int, ara_resident_kv_view *);
extern "C" long __wrap_ara_resident_linux_register_kv(int fd, ara_resident_kv_view *v) {
    long rc = __real_ara_resident_linux_register_kv(fd, v);
    if (!rc) ++registrations;
    return rc;
}
static uint64_t now() {
    timespec t{};
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &t)) std::abort();
    return uint64_t(t.tv_sec) * 1000000000 + t.tv_nsec;
}
static uint64_t hash(const void *ptr, size_t bytes) {
    const auto *p = static_cast<const unsigned char *>(ptr);
    uint64_t h = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < bytes; ++i) h = (h ^ p[i]) * UINT64_C(1099511628211);
    return h;
}
static void tensor(ggml_tensor &t, ggml_type type, void *p, unsigned d, unsigned n, unsigned h, unsigned e) {
    t.type = type; t.data = p;
    t.ne[0] = d; t.ne[1] = n; t.ne[2] = h; t.ne[3] = 1;
    t.nb[0] = e; t.nb[1] = d * e; t.nb[2] = n * t.nb[1]; t.nb[3] = h * t.nb[2];
}
static unsigned number(const char *s) {
    char *end;
    unsigned long n = std::strtoul(s, &end, 10);
    return *s && !*end && n <= 256 ? unsigned(n) : 0;
}
int main(int argc, char **argv) {
    if (argc == 2 && !std::strcmp(argv[1], "--probe")) {
        ara_resident_info info{}; ara_resident_view_caps caps{};
        int fd = ara_resident_linux_open(&info);
        long rc = fd < 0 ? fd : ara_resident_linux_view_caps(fd, &caps);
        ara_resident_linux_close(fd);
        std::printf("VIEW_CAPS rc=%ld abi=%u groups=%u\n", rc, caps.abi, caps.max_groups);
        return rc != 0;
    }
    if (argc != 4 || (std::strcmp(argv[1], "native") && std::strcmp(argv[1], "session") && std::strcmp(argv[1], "views"))) {
        std::fprintf(stderr, "usage: resident-ggml-pair native|session|views 65|128|137|stream 1|4\n");
        return 2;
    }
    bool stream = !std::strcmp(argv[2], "stream");
    unsigned tokens = stream ? 65 : number(argv[2]), kv = number(argv[3]);
    if ((tokens != 65 && tokens != 128 && tokens != 137) || (kv != 1 && kv != 4)) return 2;
    const bool native = !std::strcmp(argv[1], "native"), views = !std::strcmp(argv[1], "views");
    const unsigned capacity = stream ? 256 : tokens;
    profile = std::getenv("RESIDENT_PHASE_STATS") && !std::strcmp(std::getenv("RESIDENT_PHASE_STATS"), "1");
    setenv("GGML_RISCV_AKV", "1", 1); setenv("GGML_RISCV_AKV_EMULATE", "0", 1);
    setenv("GGML_RISCV_AKV_RESIDENT", "0", 1); setenv("GGML_RISCV_AKV_LINUX_PORTAL", native ? "0" : "1", 1);
    setenv("GGML_RISCV_AKV_LINUX_SESSION", "1", 1); setenv("GGML_RISCV_AKV_LINUX_VIEWS", views ? "1" : "0", 1);
    setenv("GGML_RISCV_ACCEL_AUTO", "1", 1); setenv("GGML_RISCV_AKV_TRACE", "0", 1);
    setenv("GGML_RISCV_AKV_PORTABLE", "0", 1); unsetenv("GGML_RISCV_AKV_KERNEL"); unsetenv("AKV_PAIR_HEADS");
    ggml_context *ctx = ggml_init({4096, nullptr, true});
    if (!ctx) return 2;
    ggml_cpu_init();
    alignas(64) static uint16_t key[256 * 4 * 128], value[256 * 4 * 128], mask_data[256];
    alignas(64) static float query[8 * 128];
    struct alignas(64) { unsigned char before[64]; float data[8 * 128]; unsigned char after[64]; } out;
    ggml_tensor q{}, k{}, v{}, mask{}, dst{};
    tensor(q, GGML_TYPE_F32, query, 128, 1, kv * 2, 4);
    tensor(k, GGML_TYPE_F16, key, 128, capacity, kv, 2);
    tensor(v, GGML_TYPE_F16, value, 128, capacity, kv, 2);
    k.nb[1] = v.nb[1] = kv * 256; k.nb[2] = v.nb[2] = 256;
    tensor(mask, GGML_TYPE_F16, mask_data, capacity, 1, 1, 2);
    tensor(dst, GGML_TYPE_F32, out.data, 128, kv * 2, 1, 4);
    dst.op = GGML_OP_FLASH_ATTN_EXT; dst.src[0] = &q; dst.src[1] = &k; dst.src[2] = &v; dst.src[3] = &mask;
    dst.op_params[0] = 0x3db504f3;
    ggml_compute_params params{}; params.nth = 1;
    for (unsigned trial = 0; trial < 7; ++trial) {
        if (stream) tokens = trial % 3 == 0 ? 65 : trial % 3 == 1 ? 128 : 137;
        const bool zero = stream && (trial & 1);
        for (unsigned h = 0; h < kv; ++h) {
            std::memcpy(query + h * 256, capture_query, 1024);
            for (unsigned t = 0; t < capacity; ++t)
                for (unsigned d = 0; d < 128; ++d) {
                    unsigned pos = (t * kv + h) * 128 + d;
                    key[pos] = t < 137 ? capture_key[t * 128 + d] : 0;
                    value[pos] = t >= 137 || zero ? 0 : capture_value[t * 128 + d] ^ ((h & 1) ? 0x8000u : 0);
                }
        }
        for (unsigned t = 0; t < capacity; ++t) mask_data[t] = t < tokens ? capture_mask[t] : 0xfc00;
        const void *input[] = {query, key, value, mask_data};
        size_t bytes[] = {kv * 1024u, capacity * kv * 256u, capacity * kv * 256u, capacity * 2u};
        uint64_t before[4];
        for (unsigned i = 0; i < 4; ++i) before[i] = hash(input[i], bytes[i]);
        std::memset(&out, 0xa5, sizeof(out));
        calls = completed = registrations = groups = 0; copied = 0;
        asm volatile("csrw fcsr,zero\ncsrw vcsr,zero\ncsrw vstart,zero" ::: "memory");
        uint64_t begin = now();
        bool accepted = ggml_riscv_akv_flash_attn(&params, &dst);
        asm volatile("csrr zero,vl\nfence rw,rw" ::: "memory");
        unsigned long fcsr, vcsr, vstart;
        asm volatile("csrr %0,fcsr\ncsrr %1,vcsr\ncsrr %2,vstart" : "=r"(fcsr), "=r"(vcsr), "=r"(vstart) :: "memory");
        uint64_t ns = now() - begin;
        unsigned errors = !accepted || !ns || vcsr || vstart, expected_flags = 0;
        for (unsigned h = 0; h < kv; ++h) {
            const uint32_t *gold;
            unsigned flags;
#define CHOOSE(kind) do { gold = tokens == 65 ? golden_##kind##65 : tokens == 128 ? golden_##kind##128 : golden_##kind##137; \
                         flags = tokens == 65 ? flags_##kind##65 : tokens == 128 ? flags_##kind##128 : flags_##kind##137; } while (0)
            if (zero) CHOOSE(zero_);
            else if (h & 1) CHOOSE(negative_);
            else CHOOSE();
#undef CHOOSE
            expected_flags |= flags;
            for (unsigned i = 0; i < 256; ++i) {
                uint32_t bits;
                std::memcpy(&bits, out.data + h * 256 + i, 4);
                errors += bits != gold[i];
            }
        }
        errors += fcsr != expected_flags;
        errors += calls != (native ? 0u : views ? 1u : kv) || completed != calls || groups != (native ? 0u : kv);
        errors += registrations != (views && !trial ? 1u : 0u);
        if (profile && !native) errors += copied != (views ? kv * 512u + tokens * 2u : kv * (512u + tokens * 514u));
        for (unsigned i = 0; i < 64; ++i) errors += out.before[i] != 0xa5 || out.after[i] != 0xa5;
        for (unsigned i = kv * 256; i < 1024; ++i) { uint32_t bits; std::memcpy(&bits, out.data + i, 4); errors += bits != 0xa5a5a5a5; }
        for (unsigned i = 0; i < 4; ++i) errors += before[i] != hash(input[i], bytes[i]);
        std::printf("VIEW_PAIR {\"mode\":\"%s\",\"stream\":%s,\"tokens\":%u,\"kv_heads\":%u,\"trial\":%u,\"warmup\":%s,\"ns\":%llu,\"calls\":%u,\"completed\":%u,\"groups\":%u,\"registrations\":%u,\"fflags\":%lu,\"diagnostic\":%s,\"errors\":%u}\n",
            argv[1], stream ? "true" : "false", tokens, kv, trial, trial ? "false" : "true",
            (unsigned long long)ns, calls, completed, groups, registrations, fcsr & 31, profile ? "true" : "false", errors);
        std::fflush(stdout);
        if (errors) return 1;
    }
    ggml_free(ctx);
    std::puts("RESIDENT_VIEW_PAIR_PASS");
    return 0;
}
