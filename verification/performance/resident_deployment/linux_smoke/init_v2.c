/* SPDX-License-Identifier: Apache-2.0 */
#include <asm/unistd.h>
#include <stdint.h>
#include "client.h"
#include "device_numbers.h"

#define AT_FDCWD (-100)
#define O_RDWR 2
#define O_NONBLOCK 2048
#define EOPNOTSUPP 95

static unsigned checks, errors;
static char text[65536];
static uint16_t query[128] __attribute__((aligned(64)));
static uint16_t key[192] __attribute__((aligned(64)));
static uint16_t value[192] __attribute__((aligned(64)));
static uint16_t mask[3] __attribute__((aligned(64)));
static unsigned char output[512] __attribute__((aligned(64)));

extern void smoke_checked_execute(int, struct ara_resident_job *, unsigned long, unsigned long *);

static long call(long nr, long x0, long x1, long x2, long x3, long x4, long x5)
{
    register long a0 asm("a0") = x0;
    register long a1 asm("a1") = x1;
    register long a2 asm("a2") = x2;
    register long a3 asm("a3") = x3;
    register long a4 asm("a4") = x4;
    register long a5 asm("a5") = x5;
    register long a7 asm("a7") = nr;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a7) : "memory");
    return a0;
}

static unsigned length(const char *s)
{
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

static void put(const char *s)
{
    unsigned n = length(s);
    while (n) {
        long count = call(__NR_write, 1, (long)s, n, 0, 0, 0);
        if (count <= 0) return;
        s += count;
        n -= count;
    }
}

static void number(long value)
{
    char digits[32];
    unsigned n = 0;
    unsigned long v = value < 0 ? -(unsigned long)value : (unsigned long)value;
    if (value < 0) put("-");
    do { digits[n++] = '0' + v % 10; v /= 10; } while (v);
    while (n) { char s[2] = {digits[--n], 0}; put(s); }
}

static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

static int contains(const char *s, const char *needle)
{
    for (; *s; ++s) {
        unsigned n = 0;
        while (needle[n] && s[n] == needle[n]) ++n;
        if (!needle[n]) return 1;
    }
    return 0;
}

static void check(const char *name, long actual, long expected)
{
    ++checks;
    if (actual != expected) ++errors;
    put("CHECK name="); put(name); put(" rc="); number(actual);
    put(" expected="); number(expected);
    put(actual == expected ? " PASS\n" : " FAIL\n");
}

static long read_file(const char *path)
{
    long fd = call(__NR_openat, AT_FDCWD, (long)path, 0, 0, 0, 0);
    long n;
    if (fd < 0) return fd;
    n = call(__NR_read, fd, (long)text, sizeof(text) - 1, 0, 0, 0);
    call(__NR_close, fd, 0, 0, 0, 0, 0);
    if (n >= 0) text[n] = 0;
    return n;
}

static long make_device(void)
{
    unsigned maj, min;
    dev_t dev;
    long rc = read_file("/sys/class/misc/ara-resident/dev");
    if (rc <= 0) return rc ? rc : -1;
    put("MISC_DEV "); put(text);
    if (!smoke_parse_device(text, &maj, &min, &dev) || maj != 10) return -22;
    put("MKNOD_DEV encoded="); number((long)dev); put("\n");
    call(__NR_unlinkat, AT_FDCWD, (long)"/dev/ara-resident", 0, 0, 0, 0);
    return call(__NR_mknodat, AT_FDCWD, (long)"/dev/ara-resident", 0020600,
                (long)dev, 0, 0);
}

static long ioctl(int fd, unsigned command, void *arg)
{
    return call(__NR_ioctl, fd, command, (long)arg, 0, 0, 0);
}

static void unchanged(void)
{
    unsigned changed = 0;
    for (unsigned i = 0; i < sizeof(output); ++i) changed |= output[i] ^ 0xa5;
    check("output_unchanged", changed, 0);
}

static void snapshot(int fd, struct ara_resident_job *job, unsigned start, long expected)
{
    unsigned long state[4];
    smoke_checked_execute(fd, job, start, state);
    check(start ? "wrapper_bad_vstart" : "wrapper_cap_decline", (long)state[0], expected);
    check("wrapper_fcsr", state[1], 0x15);
    check("wrapper_vcsr", state[2], 5);
    check("wrapper_vstart", state[3], start);
    unchanged();
}

void smoke_main(void)
{
    char uts[6][65];
    struct ara_resident_info info = {0};
    struct ara_resident_job job = {
        .abi = ARA_RESIDENT_ABI, .bytes = sizeof(job),
        .heads = 2, .dimension = 64, .tokens = 3, .scale_bits = 0x3f000000,
        .query = (uintptr_t)query, .key = (uintptr_t)key, .value = (uintptr_t)value,
        .mask = (uintptr_t)mask, .output = (uintptr_t)output,
    };
    long module_fd = -1, fd = -1, rc;
    unsigned cpus = 1;
    put("RESIDENT_LINUX_SMOKE_BEGIN\n");
    check("mount_proc", call(__NR_mount, (long)"proc", (long)"/proc", (long)"proc", 0, 0, 0), 0);
    check("mount_sys", call(__NR_mount, (long)"sysfs", (long)"/sys", (long)"sysfs", 0, 0, 0), 0);
    rc = call(__NR_uname, (long)uts, 0, 0, 0, 0, 0);
    check("uname", rc, 0);
    if (rc) goto finish;
    put("KERNEL_RELEASE "); put(uts[2]); put("\n");
    check("kernel_release_exact", equal(uts[2], "6.19.6"), 1);
    if (read_file("/proc/cmdline") > 0 && contains(text, "resident_smoke_cpus=2")) cpus = 2;
    if (read_file("/sys/devices/system/cpu/online") <= 0) { check("cpu_online_read", -1, 0); goto finish; }
    put("ONLINE_CPUS "); put(text);
    check("online_exact", equal(text, cpus == 1 ? "0\n" : "0-1\n"), 1);
    module_fd = call(__NR_openat, AT_FDCWD, (long)"/ara_resident.ko", 0, 0, 0, 0);
    check("module_open", module_fd >= 0, 1);
    if (module_fd < 0) goto finish;
    rc = call(__NR_finit_module, module_fd, (long)"", 0, 0, 0, 0);
    check("finit_module", rc, 0);
    if (rc) goto finish;
    if (read_file("/proc/modules") > 0) { put("MODULES_BEGIN\n"); put(text); put("MODULES_END\n"); }
    rc = make_device(); check("mknod", rc, 0);
    if (rc) goto finish;
    fd = call(__NR_openat, AT_FDCWD, (long)"/dev/ara-resident", O_RDWR, 0, 0, 0);
    check("device_open", fd >= 0, 1);
    if (fd < 0) goto finish;
    check("get_info", ioctl(fd, ARA_RESIDENT_GET_INFO, &info), 0);
    check("info_abi", info.abi, 1);
    check("info_bytes", info.bytes, sizeof(info));
    check("info_geometry", info.nr_lanes == 4 && info.vlen_bits == 1024 &&
          info.max_heads == 8 && info.max_tokens == 256 && info.dimensions == 7 && info.features == 3, 1);
    check("info_bad_user", ioctl(fd, ARA_RESIDENT_GET_INFO, (void *)1), -14);
    check("unknown_ioctl", ioctl(fd, 0xdead, &job), -25);
    check("job_bad_user", ioctl(fd, ARA_RESIDENT_EXECUTE, (void *)1), -14);
    for (unsigned i = 0; i < sizeof(output); ++i) output[i] = 0xa5;
    job.heads = 9;
    check("invalid_shape", ioctl(fd, ARA_RESIDENT_EXECUTE, &job), -22);
    job.heads = 2;
    job.key = 0x1000;
    check("input_bad_user", ioctl(fd, ARA_RESIDENT_EXECUTE, &job), -14);
    job.key = (uintptr_t)key;
    unchanged();
    check("legal_old_cap_first", ioctl(fd, ARA_RESIDENT_EXECUTE, &job), -EOPNOTSUPP);
    unchanged();
    check("legal_old_cap_repeat", ioctl(fd, ARA_RESIDENT_EXECUTE, &job), -EOPNOTSUPP);
    unchanged();
    check("job_fflags_unpublished", job.fflags, 0);
    rc = ara_resident_linux_open(&info);
    put("CLIENT_V2_OPEN rc="); number(rc); put("\n");
    if (rc >= 0) {
        snapshot(rc, &job, 0, -EOPNOTSUPP);
        snapshot(rc, &job, 7, -34);
        ara_resident_linux_close(rc);
        put("CLIENT_V2_CSR_TESTS PASS\n");
    } else {
        check("client_safe_decline", rc, -EOPNOTSUPP);
        put("CLIENT_V2_CSR_TESTS SKIP_SAFE_DISCOVERY_DECLINE\n");
    }
    check("unload_open_fd", call(__NR_delete_module, (long)"ara_resident", O_NONBLOCK, 0, 0, 0, 0), -11);
    check("device_close", call(__NR_close, fd, 0, 0, 0, 0, 0), 0);
    fd = -1;
    rc = call(__NR_delete_module, (long)"ara_resident", O_NONBLOCK, 0, 0, 0, 0);
    check("delete_module", rc, 0);
    if (rc) goto finish;
    check("removed_minor", read_file("/sys/class/misc/ara-resident/dev"), -2);
    rc = call(__NR_finit_module, module_fd, (long)"", 0, 0, 0, 0);
    check("reload_module", rc, 0);
    if (rc) goto finish;
    rc = make_device(); check("reload_mknod", rc, 0);
    if (rc) goto finish;
    fd = call(__NR_openat, AT_FDCWD, (long)"/dev/ara-resident", O_RDWR, 0, 0, 0);
    check("reload_device_open", fd >= 0, 1);
    if (fd >= 0) check("reload_get_info", ioctl(fd, ARA_RESIDENT_GET_INFO, &info), 0);

finish:
    if (fd >= 0) call(__NR_close, fd, 0, 0, 0, 0, 0);
    if (module_fd >= 0) call(__NR_close, module_fd, 0, 0, 0, 0, 0);
    rc = call(__NR_syslog, 3, (long)text, sizeof(text) - 1, 0, 0, 0);
    if (rc >= 0) { text[rc] = 0; put("DMESG_BEGIN\n"); put(text); put("DMESG_END\n"); }
    else check("dmesg", rc, 0);
    put(errors ? "RESIDENT_LINUX_SMOKE_FAIL cpus=" : "RESIDENT_LINUX_SMOKE_PASS cpus=");
    number(cpus); put(" checks="); number(checks); put(" errors="); number(errors); put("\n");
    call(__NR_reboot, 0xfee1dead, 0x28121969, 0x4321fedc, 0, 0, 0);
    for (;;) asm volatile("" ::: "memory");
}
