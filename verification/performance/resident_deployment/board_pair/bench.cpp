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
#include <time.h>
#ifdef RESIDENT_COST_STATS
#include <sys/ioctl.h>
static ara_resident_stats last_stats;
static bool collect_stats;
static int stats_rc;
#endif

static unsigned portal_calls, portal_completed;
extern "C" long __real_ara_resident_linux_execute(int, ara_resident_job *);
extern "C" long __wrap_ara_resident_linux_execute(int fd, ara_resident_job *job) {
    ++portal_calls;
    const long rc = __real_ara_resident_linux_execute(fd, job);
    portal_completed += rc == 0;
#ifdef RESIDENT_COST_STATS
    if (collect_stats) stats_rc = ioctl(fd, ARA_RESIDENT_GET_STATS, &last_stats);
#endif
    return rc;
}

static uint64_t now() {
    timespec t{};
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &t)) std::abort();
    return uint64_t(t.tv_sec) * UINT64_C(1000000000) + uint64_t(t.tv_nsec);
}

static uint64_t hash(const void *ptr, size_t size) {
    auto p = static_cast<const unsigned char *>(ptr);
    uint64_t h = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * UINT64_C(1099511628211);
    return h;
}

static void tensor(ggml_tensor &t, ggml_type type, void *data,
                   int64_t d, int64_t n, int64_t h, size_t element) {
    t.type = type;
    t.data = data;
    t.ne[0] = d; t.ne[1] = n; t.ne[2] = h; t.ne[3] = 1;
    t.nb[0] = element; t.nb[1] = size_t(d) * element;
    t.nb[2] = size_t(n) * t.nb[1]; t.nb[3] = size_t(h) * t.nb[2];
}

int main(int argc, char **argv) {
    if (argc == 2 && !std::strcmp(argv[1], "--probe")) {
        ara_resident_info info{};
        const int fd = ara_resident_linux_open(&info);
        if (fd < 0) {
            std::fprintf(stderr, "Resident device/ABI unavailable: %d\n", fd);
            return 1;
        }
        ara_resident_linux_close(fd);
        std::printf("RESIDENT_INFO abi=%u lanes=%u vlen=%u max_tokens=%u\n",
                    info.abi, info.nr_lanes, info.vlen_bits, info.max_tokens);
        return 0;
    }
    if (argc != 3 || (std::strcmp(argv[1], "native") && std::strcmp(argv[1], "resident"))) {
        std::fprintf(stderr, "usage: resident-ggml-pair native|resident 65|128|137\n");
        return 2;
    }
    char *end = nullptr;
    const long tokens = std::strtol(argv[2], &end, 10);
    if (!end || *end || (tokens != 65 && tokens != 128 && tokens != 137)) return 2;
    const bool resident = !std::strcmp(argv[1], "resident");
#ifdef RESIDENT_COST_STATS
    collect_stats = std::getenv("RESIDENT_PHASE_STATS") && !std::strcmp(std::getenv("RESIDENT_PHASE_STATS"), "1");
#endif
    setenv("GGML_RISCV_AKV", "1", 1);
    setenv("GGML_RISCV_AKV_EMULATE", "0", 1);
    setenv("GGML_RISCV_AKV_RESIDENT", "0", 1);
    setenv("GGML_RISCV_AKV_LINUX_PORTAL", resident ? "1" : "0", 1);
    setenv("GGML_RISCV_ACCEL_AUTO", "1", 1);
    setenv("GGML_RISCV_AKV_TRACE", "0", 1);
    setenv("GGML_RISCV_AKV_PORTABLE", "0", 1);
    unsetenv("GGML_RISCV_AKV_KERNEL");
    unsetenv("AKV_PAIR_HEADS");
    const auto *expected = tokens == 65 ? golden_65 : tokens == 128 ? golden_128 : golden_137;
    const unsigned expected_flags = tokens == 65 ? flags_65 : tokens == 128 ? flags_128 : flags_137;
    ggml_context *context = ggml_init({4096, nullptr, true});
    if (!context) return 2;
    ggml_cpu_init();
    ggml_tensor q{}, k{}, v{}, mask{}, dst{};
    struct alignas(64) { unsigned char before[64]; float data[256]; unsigned char after[64]; } out;
    tensor(q, GGML_TYPE_F32, const_cast<float *>(capture_query), 128, 1, 2, 4);
    tensor(k, GGML_TYPE_F16, const_cast<uint16_t *>(capture_key), 128, tokens, 1, 2);
    tensor(v, GGML_TYPE_F16, const_cast<uint16_t *>(capture_value), 128, tokens, 1, 2);
    tensor(mask, GGML_TYPE_F16, const_cast<uint16_t *>(capture_mask), tokens, 1, 1, 2);
    tensor(dst, GGML_TYPE_F32, out.data, 128, 2, 1, 4);
    dst.op = GGML_OP_FLASH_ATTN_EXT;
    dst.src[0] = &q; dst.src[1] = &k; dst.src[2] = &v; dst.src[3] = &mask;
    dst.op_params[0] = 0x3db504f3;
    ggml_compute_params params{};
    params.nth = 1;
    const void *inputs[] = {capture_query, capture_key, capture_value, capture_mask};
    const size_t sizes[] = {256 * 4, size_t(tokens) * 256, size_t(tokens) * 256, size_t(tokens) * 2};
    uint64_t hashes[4];
    for (unsigned i = 0; i < 4; ++i) hashes[i] = hash(inputs[i], sizes[i]);
    for (unsigned trial = 0; trial < 4; ++trial) {
        std::memset(&out, 0xa5, sizeof(out));
        portal_calls = portal_completed = 0;
        asm volatile("csrw fcsr,zero\ncsrw vcsr,zero\ncsrw vstart,zero" ::: "memory");
        const uint64_t begin = now();
        const bool accepted = ggml_riscv_akv_flash_attn(&params, &dst);
        asm volatile("csrr zero,vl\nfence rw,rw" ::: "memory");
        unsigned long fcsr, vcsr, vstart;
        asm volatile("csrr %0,fcsr\ncsrr %1,vcsr\ncsrr %2,vstart"
                     : "=r"(fcsr), "=r"(vcsr), "=r"(vstart) :: "memory");
        const uint64_t elapsed = now() - begin;
#ifdef RESIDENT_COST_STATS
        if (resident && collect_stats) {
            if (stats_rc || last_stats.abi != ARA_RESIDENT_ABI || last_stats.bytes != sizeof(last_stats) ||
                last_stats.status || last_stats.copied_input_bytes != 512 + uint64_t(tokens) * 514 ||
                (trial && last_stats.allocated_buffers)) std::abort();
            std::printf("PHASE {\"trial\":%u,\"profile_enabled\":%u,\"sequence\":%llu,\"allocations\":%llu,"
                        "\"input_bytes\":%llu,\"buffer_ns\":%llu,\"input_copy_ns\":%llu,\"address_check_ns\":%llu,"
                        "\"execute_ns\":%llu,\"output_copy_ns\":%llu,\"total_ns\":%llu}\n", trial, last_stats.profile_enabled,
                        (unsigned long long)last_stats.sequence, (unsigned long long)last_stats.allocated_buffers,
                        (unsigned long long)last_stats.copied_input_bytes, (unsigned long long)last_stats.buffer_ns,
                        (unsigned long long)last_stats.input_copy_ns, (unsigned long long)last_stats.address_check_ns,
                        (unsigned long long)last_stats.execute_ns, (unsigned long long)last_stats.output_copy_ns,
                        (unsigned long long)last_stats.total_ns);
        }
#endif
        unsigned errors = !accepted || !elapsed || fcsr != expected_flags || vcsr || vstart;
        errors += portal_calls != unsigned(resident) || portal_completed != unsigned(resident);
        for (unsigned i = 0; i < 256; ++i) {
            uint32_t bits;
            std::memcpy(&bits, out.data + i, 4);
            if (bits != expected[i] && errors < 4)
                std::fprintf(stderr, "output[%u]: expected=%08x actual=%08x\n", i, expected[i], bits);
            errors += bits != expected[i];
        }
        for (unsigned i = 0; i < 64; ++i) errors += out.before[i] != 0xa5 || out.after[i] != 0xa5;
        for (unsigned i = 0; i < 4; ++i) errors += hash(inputs[i], sizes[i]) != hashes[i];
        std::printf("PAIR {\"mode\":\"%s\",\"tokens\":%ld,\"trial\":%u,\"warmup\":%s,"
                    "\"ns\":%llu,\"accepted\":%s,\"portal_calls\":%u,\"portal_completed\":%u,"
                    "\"fflags\":%lu,\"errors\":%u}\n", argv[1], tokens, trial,
                    trial ? "false" : "true", static_cast<unsigned long long>(elapsed),
                    accepted ? "true" : "false", portal_calls, portal_completed, fcsr & 31, errors);
        std::fflush(stdout);
        if (errors) { ggml_free(context); return 1; }
    }
    ggml_free(context);
    std::puts("RESIDENT_GGML_PAIR_PASS");
    return 0;
}
