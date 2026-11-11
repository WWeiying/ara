#include "entry.h"
#include "execution_contract.h"
#include <asm/hwprobe.h>
#include <asm/unistd.h>
#include <linux/prctl.h>
#include <linux/auxvec.h>
#include <stdint.h>

/* Only the reviewed, single-vCPU, static /test Linux deployment is supported.
 * No libc, vector instruction or CSR write is permitted in these callbacks. */
#ifdef STAGE5_PROVIDER_HOST_TEST
extern long stage5_host_syscall(long, long, long, long, long, long, long);
#define call stage5_host_syscall
#else
static long call(long nr, long x0, long x1, long x2, long x3, long x4, long x5) {
    register long a0 asm("a0") = x0, a1 asm("a1") = x1, a2 asm("a2") = x2;
    register long a3 asm("a3") = x3, a4 asm("a4") = x4, a5 asm("a5") = x5;
    register long a7 asm("a7") = nr;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a7) : "memory");
    return a0;
}
#endif

static long pid(void) { return call(__NR_getpid, 0, 0, 0, 0, 0, 0); }
static long tid(void) { return call(__NR_gettid, 0, 0, 0, 0, 0, 0); }
static long open_read(const char *path, unsigned flags) {
    return call(__NR_openat, -100, (long)path, flags, 0, 0, 0);
}
static long read_bytes(long fd, void *p, size_t n) {
    long rc;
    do { rc = call(__NR_read, fd, (long)p, n, 0, 0, 0); } while (rc == -4);
    return rc;
}
static int close_fd(long fd) { return call(__NR_close, fd, 0, 0, 0, 0, 0) == 0; }
static int same(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

static int os_ready(void) {
    const long p = pid();
    if (!STAGE5_PROVIDER_ENABLED || p <= 1 || tid() != p) return 0;
    const long policy = call(__NR_prctl, PR_RISCV_V_GET_CONTROL, 0, 0, 0, 0, 0);
    if (policy < 0 || (policy & PR_RISCV_V_VSTATE_CTRL_CUR_MASK) != PR_RISCV_V_VSTATE_CTRL_ON) return 0;
    struct riscv_hwprobe probe;
    probe.key = RISCV_HWPROBE_KEY_IMA_EXT_0; probe.value = 0;
    const uint64_t required = RISCV_HWPROBE_IMA_FD | RISCV_HWPROBE_IMA_V |
                              RISCV_HWPROBE_EXT_ZFH | RISCV_HWPROBE_EXT_ZVFH;
    if (call(__NR_riscv_hwprobe, (long)&probe, 1, 0, 0, 0, 0) != 0 ||
        probe.key != RISCV_HWPROBE_KEY_IMA_EXT_0 || (probe.value & required) != required) return 0;
    long fd = open_read("/proc/self/auxv", 0);
    if (fd < 0) return 0;
    unsigned found = 0, ended = 0;
    for (unsigned i = 0; i < 128; ++i) {
        uintptr_t pair[2]; size_t done = 0;
        while (done < sizeof(pair)) {
            long n = read_bytes(fd, (char *)pair + done, sizeof(pair) - done);
            if (n <= 0) break;
            done += (size_t)n;
        }
        if (done != sizeof(pair)) break;
        if (pair[0] == AT_HWCAP) {
            const uintptr_t mask = (1UL << ('F'-'A')) | (1UL << ('D'-'A')) | (1UL << ('V'-'A'));
            found = (pair[1] & mask) == mask;
        }
        if (pair[0] == AT_NULL) { ended = 1; break; }
    }
    return close_fd(fd) && found && ended;
}

static int one_thread(void) {
    /* Linux getdents64 record layout, consumed bytewise to avoid alignment UB. */
    long fd = open_read("/proc/self/task", 00200000);
    if (fd < 0) return 0;
    unsigned count = 0; int ok = 1;
    char data[1024];
    for (;;) {
        long n = call(__NR_getdents64, fd, (long)data, sizeof(data), 0, 0, 0);
        if (n == -4) continue;
        if (n < 0) { ok = 0; break; }
        if (!n) break;
        size_t at = 0;
        while (at < (size_t)n) {
            if ((size_t)n-at < 20) { ok = 0; break; }
            const unsigned size = (unsigned char)data[at+16] | ((unsigned char)data[at+17] << 8);
            if (size < 20 || size > (size_t)n-at) { ok = 0; break; }
            size_t end = at+19;
            while (end < at+size && data[end]) ++end;
            if (end == at+size) { ok = 0; break; }
            if (!same(data+at+19, ".") && !same(data+at+19, "..")) {
                for (size_t i = at+19; i < end; ++i)
                    if (data[i] < '0' || data[i] > '9') ok = 0;
                if (++count > 1) ok = 0;
            }
            at += size;
        }
        if (!ok) break;
    }
    unsigned long cpus = 0;
    long bytes = call(__NR_sched_getaffinity, 0, sizeof(cpus), (long)&cpus, 0, 0, 0);
    return close_fd(fd) && ok && count == 1 && bytes > 0 && bytes <= (long)sizeof(cpus) && cpus == 1;
}

static int hex_number(const char **text, uintptr_t *out) {
    uintptr_t value = 0; unsigned count = 0;
    for (;;) {
        unsigned c = (unsigned char)**text;
        unsigned digit = c >= '0' && c <= '9' ? c-'0' : c >= 'a' && c <= 'f' ? c-'a'+10 : 16;
        if (digit == 16) break;
        if (value > (UINTPTR_MAX-digit)/16) return 0;
        value = value*16+digit; ++*text; ++count;
    }
    *out = value; return count != 0;
}

static int map_line(const char *line, const akv_platform_request_v1 *r,
                    uintptr_t *progress, uintptr_t *previous) {
    uintptr_t first, last;
    if (!hex_number(&line, &first) || *line++ != '-' || !hex_number(&line, &last) ||
        *line++ != ' ' || first >= last || first < *previous) return 0;
    *previous = last;
    const char *permissions = line;
    unsigned length = 0;
    while (line[length] && line[length] != ' ') ++length;
    if (length != 4) return 0;
    line += 4;
    /* Skip offset, device and inode. Kernel owns this procfs grammar. */
    for (unsigned field = 0; field < 3; ++field) {
        while (*line == ' ') ++line;
        if (!*line) return 0;
        while (*line && *line != ' ') ++line;
    }
    while (*line == ' ') ++line;
    const int ram = !*line || same(line, "[heap]") || same(line, "[stack]") ||
                    same(line, "/test") || same(line, STAGE5_MODEL_PATH);
    /* vDSO/vvar and unknown/device-backed mappings never authorize a span. */
    if (!ram) return same(line, "[vdso]") || same(line, "[vvar]") || same(line, "[vvar_vclock]");
    if (permissions[3] != 'p' || (permissions[0] != 'r' && permissions[0] != '-')) return 0;
    for (size_t i = 0; i < r->span_count; ++i) {
        const akv_platform_span_v1 *s = r->spans+i;
        uintptr_t end = (uintptr_t)s->base+s->bytes;
        if (progress[i] >= first && progress[i] < last && progress[i] < end) {
            if (permissions[0] != 'r' || (s->writable && permissions[1] != 'w')) return 0;
            progress[i] = end < last ? end : last;
        }
    }
    return 1;
}

static int ram_spans(const akv_platform_request_v1 *r) {
    if (!r || r->abi_version != 1 || r->struct_bytes != sizeof(*r) || r->requested != 1 ||
        r->workers != 1 || !r->query_tokens || !r->groups || r->refill_overlap ||
        !r->spans || !r->span_count || r->span_count > 32) return 0;
    uintptr_t progress[32], previous = 0;
    for (size_t i = 0; i < r->span_count; ++i) {
        const akv_platform_span_v1 *s = r->spans+i;
        progress[i] = (uintptr_t)s->base;
        if (!progress[i] || !s->bytes || s->bytes > UINTPTR_MAX-progress[i] || s->writable > 1) return 0;
    }
    long fd = open_read("/proc/self/maps", 0);
    if (fd < 0) return 0;
    char data[4096], line[1024]; size_t used = 0; int ok = 1; unsigned lines = 0;
    for (;;) {
        long n = read_bytes(fd, data, sizeof(data));
        if (n < 0) { ok = 0; break; }
        if (!n) break;
        for (long i = 0; i < n; ++i) {
            if (data[i] == '\n') {
                line[used] = 0;
                if (++lines > 2048 || !map_line(line, r, progress, &previous)) { ok = 0; break; }
                used = 0;
            } else if (used+1 < sizeof(line)) line[used++] = data[i];
            else { ok = 0; break; }
        }
        if (!ok) break;
    }
    if (!close_fd(fd) || used || !lines) ok = 0;
    for (size_t i = 0; i < r->span_count; ++i)
        if (progress[i] != (uintptr_t)r->spans[i].base+r->spans[i].bytes) ok = 0;
    return ok;
}

static uintptr_t lease, generation;
static long lease_pid;
static akv_platform_result_t state(void *context, akv_platform_thread_state_v1 *out) {
    (void)context;
    if (!os_ready()) return AKV_PLATFORM_KEEP_NATIVE;
    return akv_resident_platform_read_state_v1(NULL, out);
}
static uintptr_t acquire(void *context, const akv_platform_request_v1 *r) {
    (void)context;
    if (lease || !os_ready() || !one_thread() || !ram_spans(r) || generation == UINTPTR_MAX) return 0;
    lease_pid = pid(); lease = ++generation; return lease;
}
static void release(void *context, uintptr_t cookie) {
    (void)context;
    if (!cookie || cookie != lease || pid() != lease_pid || tid() != lease_pid) {
        call(__NR_exit_group, 94, 0, 0, 0, 0, 0);
        __builtin_trap();
    }
    lease = 0; lease_pid = 0;
}

static const akv_resident_platform_provider_v1 provider = {
    .abi_version=1, .struct_bytes=sizeof(provider), .kind=AKV_PLATFORM_VALIDATED_TEST_MODEL,
    .assurances=AKV_PLATFORM_REQUIRED_ASSURANCES, .contract_sha256=STAGE5_CONTRACT_BYTES,
    .operation_mask=AKV_PLATFORM_QK_PV_V1, .qk_profile=1, .pv_profile=1, .nr_lanes=4, .vlen_bits=1024,
    .context=NULL, .read_state=state, .acquire=acquire, .release=release
};
static const ggml_akv_legacy_contract_v1 legacy = {
    .abi_version=1, .struct_bytes=sizeof(legacy), .provider=&provider,
    .contract_sha256=STAGE5_CONTRACT_BYTES,
    .operation_mask=GGML_AKV_LEGACY_BASE|GGML_AKV_LEGACY_PREFILL|GGML_AKV_LEGACY_QUANT_KV,
    .whole_process_ram=1
};
const akv_resident_platform_provider_v1 *akv_resident_platform_current_v1(void) {
    return STAGE5_PROVIDER_ENABLED ? &provider : NULL;
}
const ggml_akv_legacy_contract_v1 *ggml_akv_legacy_current_v1(void) {
    return STAGE5_PROVIDER_ENABLED ? &legacy : NULL;
}
