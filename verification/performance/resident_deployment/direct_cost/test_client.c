/* Setup/teardown only. All system calls are intercepted by the test hook. */
#include "direct_client.h"
#include <asm/unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef ARA_AKV_DIRECT_CLIENT_TEST
#error "This test must never make real admission syscalls"
#endif
#ifndef __NR_riscv_hwprobe
#define __NR_riscv_hwprobe 258
#endif

#define CHECK(x) do { ++checks; if (!(x)) { \
  fprintf(stderr, "%s:%d: %s (case %s)\n", __FILE__, __LINE__, #x, label); \
  abort(); } } while (0)
#define LENGTH(x) (sizeof(x) / sizeof((x)[0]))
_Static_assert(sizeof(long) == 8, "RV64-compatible host required");
_Static_assert(sizeof(struct ara_akv_direct_info) == 64, "info ABI size");
_Static_assert(sizeof(struct ara_akv_direct_lease) == 64, "lease ABI size");
_Static_assert(_Alignof(struct ara_akv_direct_info) == 8, "info ABI alignment");
_Static_assert(_Alignof(struct ara_akv_direct_lease) == 8, "lease ABI alignment");
#define OFFSET(t, f, n) _Static_assert(offsetof(struct t, f) == n, #t "." #f)
OFFSET(ara_akv_direct_info, abi, 0);
OFFSET(ara_akv_direct_info, bytes, 4);
OFFSET(ara_akv_direct_info, features, 8);
OFFSET(ara_akv_direct_info, online_cpus, 12);
OFFSET(ara_akv_direct_info, gate_signature, 16);
OFFSET(ara_akv_direct_info, generation, 24);
OFFSET(ara_akv_direct_info, reserved, 32);
OFFSET(ara_akv_direct_lease, abi, 0);
OFFSET(ara_akv_direct_lease, bytes, 4);
OFFSET(ara_akv_direct_lease, flags, 8);
OFFSET(ara_akv_direct_lease, reserved0, 12);
OFFSET(ara_akv_direct_lease, generation, 16);
OFFSET(ara_akv_direct_lease, owner_tid, 24);
OFFSET(ara_akv_direct_lease, hart, 28);
OFFSET(ara_akv_direct_lease, reserved, 32);
_Static_assert(ARA_AKV_DIRECT_ABI == 1, "version");
_Static_assert(ARA_AKV_GATE_CSR == 0x5c0, "gate number, never accessed here");
_Static_assert(ARA_AKV_GATE_SIGNATURE == UINT64_C(0x414b5601), "signature");
_Static_assert(ARA_AKV_GATE_STRICT == 1 && ARA_AKV_GATE_USER == 2 &&
               ARA_AKV_GATE_SUPERVISOR == 4, "gate flags");
_Static_assert(ARA_AKV_DIRECT_THREAD_EXCLUSIVE == 1 && ARA_AKV_DIRECT_NO_HOT_IOCTL == 2 &&
               ARA_AKV_DIRECT_FAIL_CLOSED == 4 && ARA_AKV_DIRECT_REQUIRED_FEATURES == 7,
               "feature flags");
_Static_assert(ARA_AKV_DIRECT_GET_INFO == 0x80404bb0UL, "GET_INFO encoding");
_Static_assert(ARA_AKV_DIRECT_ACQUIRE == 0xc0404bb1UL, "ACQUIRE encoding");
_Static_assert(ARA_AKV_DIRECT_RELEASE == 0x4bb2UL, "RELEASE encoding");

enum operation { POLICY, PROBE, OPEN, INFO, ACQUIRE, TID, RELEASE, CLOSE };
struct step { enum operation operation; long result; };
struct guarded_info { unsigned char before[16]; struct ara_akv_direct_info value; unsigned char after[16]; };
struct guarded_lease { unsigned char before[16]; struct ara_akv_direct_lease value; unsigned char after[16]; };
static struct step script[32];
static size_t used, next;
static unsigned cases, checks, calls, info_calls, acquire_calls, release_calls;
static const char *label;
static struct guarded_info info_guard;
static struct guarded_lease lease_guard;
static struct ara_akv_direct_info info_reply;
static struct ara_akv_direct_lease lease_reply;
static int64_t probe_key;
static uint64_t probe_value;
static long descriptor, thread_id;
static const uint64_t required_isa = UINT64_C(5) | (UINT64_C(1) << 27) | (UINT64_C(1) << 30);

static void begin(const char *name)
{
    label = name;
    ++cases;
    used = next = 0;
    descriptor = 17;
    thread_id = 4242;
    probe_key = 4;
    probe_value = required_isa;
    info_reply = (struct ara_akv_direct_info){ .abi = 1, .bytes = 64, .features = 7,
        .online_cpus = 1, .gate_signature = UINT64_C(0x414b5601), .generation = 11 };
    lease_reply = (struct ara_akv_direct_lease){ .abi = 1, .bytes = 64, .generation = 12,
        .owner_tid = 4242, .hart = 0 };
    memset(&info_guard, 0xa5, sizeof(info_guard));
    memset(&lease_guard, 0xa5, sizeof(lease_guard));
    errno = EDOM;
}

static void expect(enum operation op, long result)
{
    CHECK(used < LENGTH(script));
    script[used++] = (struct step){op, result};
}

static void bytes_equal(const void *object, unsigned char byte, size_t size)
{
    const unsigned char *p = object;
    for (size_t i = 0; i < size; ++i) CHECK(p[i] == byte);
}

static void finish(void)
{
    CHECK(next == used);
    CHECK(errno == EDOM);
    bytes_equal(info_guard.before, 0xa5, sizeof(info_guard.before));
    bytes_equal(info_guard.after, 0xa5, sizeof(info_guard.after));
    bytes_equal(lease_guard.before, 0xa5, sizeof(lease_guard.before));
    bytes_equal(lease_guard.after, 0xa5, sizeof(lease_guard.after));
}

long ara_akv_direct_test_syscall(long nr, long x0, long x1, long x2);
long ara_akv_direct_test_syscall(long nr, long x0, long x1, long x2)
{
    CHECK(next < used);
    struct step step = script[next++];
    ++calls;
    switch (step.operation) {
    case POLICY:
        CHECK(nr == __NR_prctl && x0 == 70 && x1 == 0 && x2 == 0);
        bytes_equal(&info_guard.value, 0, sizeof(info_guard.value));
        break;
    case PROBE: {
        struct probe { int64_t key; uint64_t value; };
        CHECK(nr == __NR_riscv_hwprobe && x0 != 0 && x1 == 1 && x2 == 0);
        /* The production pair is an anonymous struct; memcpy avoids type punning. */
        struct probe pair;
        memcpy(&pair, (void *)(uintptr_t)x0, sizeof(pair));
        CHECK(pair.key == 4 && pair.value == 0);
        pair.key = probe_key; pair.value = probe_value;
        memcpy((void *)(uintptr_t)x0, &pair, sizeof(pair));
        break;
    }
    case OPEN:
        CHECK(nr == __NR_openat && x0 == AT_FDCWD && x1 != 0);
        CHECK(strcmp((const char *)(uintptr_t)x1, "/dev/ara-akv-direct") == 0);
        CHECK(x2 == (O_RDWR | O_CLOEXEC));
        break;
    case INFO:
        CHECK(nr == __NR_ioctl && x0 == descriptor && (unsigned long)x1 == 0x80404bb0UL);
        CHECK((void *)(uintptr_t)x2 == &info_guard.value);
        bytes_equal(&info_guard.value, 0, sizeof(info_guard.value));
        memcpy((void *)(uintptr_t)x2, &info_reply, sizeof(info_reply));
        ++info_calls;
        break;
    case ACQUIRE: {
        CHECK(nr == __NR_ioctl && x0 == descriptor && (unsigned long)x1 == 0xc0404bb1UL);
        CHECK((void *)(uintptr_t)x2 == &lease_guard.value);
        const struct ara_akv_direct_lease input = {.abi = 1, .bytes = 64};
        CHECK(memcmp(&lease_guard.value, &input, sizeof(input)) == 0);
        memcpy((void *)(uintptr_t)x2, &lease_reply, sizeof(lease_reply));
        ++acquire_calls;
        break;
    }
    case TID:
        CHECK(nr == __NR_gettid && x0 == 0 && x1 == 0 && x2 == 0);
        break;
    case RELEASE:
        CHECK(nr == __NR_ioctl && x0 == descriptor && (unsigned long)x1 == 0x4bb2UL && x2 == 0);
        ++release_calls;
        break;
    case CLOSE:
        CHECK(nr == __NR_close && x0 == descriptor && x1 == 0 && x2 == 0);
        break;
    default:
        CHECK(0);
    }
    return step.result;
}

static void open_prefix(void)
{
    expect(POLICY, 2); expect(PROBE, 0); expect(OPEN, descriptor);
}

static void malformed_info(void)
{
    open_prefix(); expect(INFO, 0); expect(CLOSE, 0);
    CHECK(ara_akv_direct_open(&info_guard.value) == -EPROTO);
    CHECK(memcmp(&info_guard.value, &info_reply, sizeof(info_reply)) == 0);
    finish();
}

static void malformed_lease(long cleanup)
{
    expect(ACQUIRE, 0); expect(TID, thread_id); expect(RELEASE, cleanup);
    CHECK(ara_akv_direct_acquire((int)descriptor, &lease_guard.value) == -EPROTO);
    CHECK(memcmp(&lease_guard.value, &lease_reply, sizeof(lease_reply)) == 0);
    finish();
}

static void test_null_and_negative_fd(void)
{
    begin("null-info");
    CHECK(ara_akv_direct_open(NULL) == -EINVAL);
    bytes_equal(&info_guard.value, 0xa5, sizeof(info_guard.value)); finish();
    const int bad[] = {-1, -EBADF, INT_MIN};
    for (size_t i = 0; i < LENGTH(bad); ++i) {
        begin("negative-fd");
        CHECK(ara_akv_direct_acquire(bad[i], &lease_guard.value) == -EINVAL);
        CHECK(ara_akv_direct_release(bad[i]) == -EINVAL);
        ara_akv_direct_close(bad[i]);
        bytes_equal(&lease_guard.value, 0xa5, sizeof(lease_guard.value)); finish();
    }
    begin("null-lease");
    CHECK(ara_akv_direct_acquire(17, NULL) == -EINVAL); finish();
}

static void test_admission_prefix(void)
{
    const long policies[] = {-ENOSYS, -EINTR, -EPERM, -EIO, -2, LONG_MIN, 0, 1, 3};
    for (size_t i = 0; i < LENGTH(policies); ++i) {
        begin("policy-denied"); expect(POLICY, policies[i]);
        CHECK(ara_akv_direct_open(&info_guard.value) == -EOPNOTSUPP); finish();
    }
    const long policies_on[] = {2, 2 | 4 | 8 | 16, (LONG_MAX & ~3L) | 2};
    for (size_t i = 0; i < LENGTH(policies_on); ++i) {
        begin("policy-current-on"); expect(POLICY, policies_on[i]);
        expect(PROBE, 0); expect(OPEN, descriptor); expect(INFO, 0);
        CHECK(ara_akv_direct_open(&info_guard.value) == descriptor);
        expect(CLOSE, 0); ara_akv_direct_close((int)descriptor); finish();
    }
    const long errors[] = {-ENOSYS, -EINVAL, -EFAULT, -EINTR, 1, LONG_MAX};
    for (size_t i = 0; i < LENGTH(errors); ++i) {
        begin("hwprobe-error"); expect(POLICY, 2); expect(PROBE, errors[i]);
        CHECK(ara_akv_direct_open(&info_guard.value) == -EOPNOTSUPP); finish();
    }
    const int64_t keys[] = {-1, 0, 3, 5, INT64_MIN, INT64_MAX};
    for (size_t i = 0; i < LENGTH(keys); ++i) {
        begin("old-hwprobe-key"); probe_key = keys[i]; expect(POLICY, 2); expect(PROBE, 0);
        CHECK(ara_akv_direct_open(&info_guard.value) == -EOPNOTSUPP); finish();
    }
    for (unsigned bit = 0; bit < 64; ++bit) {
        begin("hwprobe-feature-bit"); probe_value ^= UINT64_C(1) << bit;
        expect(POLICY, 2); expect(PROBE, 0);
        if (required_isa & (UINT64_C(1) << bit)) {
            CHECK(ara_akv_direct_open(&info_guard.value) == -EOPNOTSUPP);
        } else {
            expect(OPEN, descriptor); expect(INFO, 0);
            CHECK(ara_akv_direct_open(&info_guard.value) == descriptor);
            expect(CLOSE, 0); ara_akv_direct_close((int)descriptor);
        }
        finish();
    }
    begin("hwprobe-all-zero"); probe_value = 0; expect(POLICY, 2); expect(PROBE, 0);
    CHECK(ara_akv_direct_open(&info_guard.value) == -EOPNOTSUPP); finish();
    begin("hwprobe-superset"); probe_value = UINT64_MAX; open_prefix(); expect(INFO, 0);
    CHECK(ara_akv_direct_open(&info_guard.value) == descriptor);
    expect(CLOSE, 0); ara_akv_direct_close((int)descriptor); finish();
}

static void test_open_errors_and_info(void)
{
    const int errors[] = {-ENOENT, -ENODEV, -EPERM, -EMFILE, -EINTR, -ENOMEM, -EIO, -ENOTTY, -EFAULT};
    for (size_t i = 0; i < LENGTH(errors); ++i) {
        begin("openat-error"); expect(POLICY, 2); expect(PROBE, 0); expect(OPEN, errors[i]);
        CHECK(ara_akv_direct_open(&info_guard.value) == errors[i]); finish();
        begin("info-error-close-once"); open_prefix(); expect(INFO, errors[i]); expect(CLOSE, -EBADF);
        CHECK(ara_akv_direct_open(&info_guard.value) == errors[i]); finish();
    }
    const int fds[] = {0, 1, 17, INT_MAX};
    for (size_t i = 0; i < LENGTH(fds); ++i) {
        begin("valid-fd-boundary"); descriptor = fds[i]; open_prefix(); expect(INFO, 0);
        CHECK(ara_akv_direct_open(&info_guard.value) == fds[i]);
        CHECK(memcmp(&info_guard.value, &info_reply, sizeof(info_reply)) == 0);
        expect(CLOSE, -EINTR); ara_akv_direct_close(fds[i]); finish();
    }
    begin("old-info-zero"); memset(&info_reply, 0, sizeof(info_reply)); malformed_info();
    const uint32_t versions[] = {0, 2, UINT32_MAX};
    const uint32_t sizes[] = {0, 32, 63, 65, UINT32_MAX};
    for (size_t i = 0; i < LENGTH(versions); ++i) {
        begin("info-abi"); info_reply.abi = versions[i]; malformed_info();
    }
    for (size_t i = 0; i < LENGTH(sizes); ++i) {
        begin("info-size"); info_reply.bytes = sizes[i]; malformed_info();
    }
    for (unsigned bit = 0; bit < 32; ++bit) {
        begin("info-feature-exact"); info_reply.features ^= UINT32_C(1) << bit; malformed_info();
    }
    const uint32_t cpus[] = {0, 2, UINT32_MAX};
    for (size_t i = 0; i < LENGTH(cpus); ++i) {
        begin("info-online-cpus"); info_reply.online_cpus = cpus[i]; malformed_info();
    }
    for (unsigned bit = 0; bit < 64; ++bit) {
        begin("info-signature"); info_reply.gate_signature ^= UINT64_C(1) << bit; malformed_info();
    }
    for (unsigned slot = 0; slot < 4; ++slot)
        for (unsigned bit = 0; bit < 64; ++bit) {
            begin("info-reserved"); info_reply.reserved[slot] = UINT64_C(1) << bit; malformed_info();
        }
    const uint64_t generations[] = {0, 1, UINT64_MAX};
    for (size_t i = 0; i < LENGTH(generations); ++i) {
        begin("info-generation-is-not-a-lease"); info_reply.generation = generations[i];
        open_prefix(); expect(INFO, 0);
        CHECK(ara_akv_direct_open(&info_guard.value) == descriptor);
        expect(CLOSE, 0); ara_akv_direct_close((int)descriptor); finish();
    }
    begin("malformed-info-cleanup-error"); info_reply.features = 0;
    open_prefix(); expect(INFO, 0); expect(CLOSE, -EIO);
    CHECK(ara_akv_direct_open(&info_guard.value) == -EPROTO); finish();
}

static void test_lease_errors_and_owner(void)
{
    const long errors[] = {-EBADF, -EINTR, -EFAULT, -EBUSY, -EPERM, -ENOTTY, -ENODEV, -EOPNOTSUPP};
    for (size_t i = 0; i < LENGTH(errors); ++i) {
        begin("acquire-error-no-extra-cleanup"); expect(ACQUIRE, errors[i]);
        CHECK(ara_akv_direct_acquire((int)descriptor, &lease_guard.value) == errors[i]); finish();
        begin("release-error"); expect(RELEASE, errors[i]);
        CHECK(ara_akv_direct_release((int)descriptor) == errors[i]); finish();
    }
    begin("old-lease-zero"); memset(&lease_reply, 0, sizeof(lease_reply)); malformed_lease(0);
    const uint32_t values[] = {0, 2, 63, 65, UINT32_MAX};
    for (size_t i = 0; i < LENGTH(values); ++i) {
        begin("lease-abi"); lease_reply.abi = values[i]; malformed_lease(0);
        begin("lease-size"); lease_reply.bytes = values[i]; malformed_lease(0);
    }
    for (unsigned bit = 0; bit < 32; ++bit) {
        begin("lease-flags"); lease_reply.flags = UINT32_C(1) << bit; malformed_lease(0);
        begin("lease-reserved0"); lease_reply.reserved0 = UINT32_C(1) << bit; malformed_lease(0);
        begin("lease-hart"); lease_reply.hart = UINT32_C(1) << bit; malformed_lease(0);
    }
    begin("lease-generation-zero"); lease_reply.generation = 0; malformed_lease(0);
    const uint32_t owners[] = {0, 1, 4241, 4243, UINT32_MAX};
    for (size_t i = 0; i < LENGTH(owners); ++i) {
        begin("lease-owner"); lease_reply.owner_tid = owners[i]; malformed_lease(0);
    }
    for (unsigned slot = 0; slot < 4; ++slot)
        for (unsigned bit = 0; bit < 64; ++bit) {
            begin("lease-reserved"); lease_reply.reserved[slot] = UINT64_C(1) << bit; malformed_lease(0);
        }
    const long bad_tids[] = {-ENOSYS, -EINTR, -1, 0, LONG_MIN, (long)UINT32_MAX + 1};
    for (size_t i = 0; i < LENGTH(bad_tids); ++i) {
        begin("gettid-fails-closed"); thread_id = bad_tids[i]; malformed_lease(0);
    }
    for (size_t i = 0; i < LENGTH(errors); ++i) {
        begin("lease-cleanup-preserves-primary-error"); lease_reply.flags = 1; malformed_lease(errors[i]);
    }
    const long good_tids[] = {1, 4242, INT_MAX};
    for (size_t i = 0; i < LENGTH(good_tids); ++i) {
        begin("valid-owner-and-generation-boundary"); thread_id = good_tids[i];
        lease_reply.owner_tid = (uint32_t)thread_id; lease_reply.generation = UINT64_MAX;
        expect(ACQUIRE, 0); expect(TID, thread_id);
        CHECK(ara_akv_direct_acquire((int)descriptor, &lease_guard.value) == 0);
        expect(RELEASE, 0); CHECK(ara_akv_direct_release((int)descriptor) == 0); finish();
    }
}

static void test_full_setup_and_reuse(void)
{
    begin("complete-setup-teardown-fd-zero"); descriptor = 0;
    open_prefix(); expect(INFO, 0); expect(ACQUIRE, 0); expect(TID, thread_id);
    expect(RELEASE, 0); expect(CLOSE, 0);
    const int fd = ara_akv_direct_open(&info_guard.value);
    CHECK(fd == 0);
    CHECK(ara_akv_direct_acquire(fd, &lease_guard.value) == 0);
    CHECK(ara_akv_direct_release(fd) == 0); ara_akv_direct_close(fd); finish();
    begin("reuse-buffers-no-stale-input");
    open_prefix(); expect(INFO, 0); expect(CLOSE, 0);
    CHECK(ara_akv_direct_open(&info_guard.value) == descriptor);
    ara_akv_direct_close((int)descriptor);
    expect(POLICY, 0);
    CHECK(ara_akv_direct_open(&info_guard.value) == -EOPNOTSUPP);
    bytes_equal(&info_guard.value, 0, sizeof(info_guard.value));
    expect(ACQUIRE, 0); expect(TID, thread_id);
    CHECK(ara_akv_direct_acquire((int)descriptor, &lease_guard.value) == 0);
    lease_reply.owner_tid = 0;
    expect(ACQUIRE, 0); expect(TID, thread_id); expect(RELEASE, 0);
    CHECK(ara_akv_direct_acquire((int)descriptor, &lease_guard.value) == -EPROTO); finish();
}

int main(void)
{
    test_null_and_negative_fd();
    test_admission_prefix();
    test_open_errors_and_info();
    test_lease_errors_and_owner();
    test_full_setup_and_reuse();
    printf("DIRECT_CLIENT_PASS cases=%u checks=%u mock_calls=%u info=%u acquire=%u release=%u\n",
           cases, checks, calls, info_calls, acquire_calls, release_calls);
    return 0;
}
