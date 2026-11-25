/* SPDX-License-Identifier: Apache-2.0 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "direct_client.h"
#include <asm/unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <linux/prctl.h>

#ifndef PR_RISCV_V_GET_CONTROL
#define PR_RISCV_V_GET_CONTROL 70
#define PR_RISCV_V_VSTATE_CTRL_ON 2
#define PR_RISCV_V_VSTATE_CTRL_CUR_MASK 3
#endif
#ifndef __NR_riscv_hwprobe
#define __NR_riscv_hwprobe 258
#endif

_Static_assert(sizeof(struct ara_akv_direct_info) == 64, "info ABI");
_Static_assert(sizeof(struct ara_akv_direct_lease) == 64, "lease ABI");

#ifdef ARA_AKV_DIRECT_CLIENT_TEST
extern long ara_akv_direct_test_syscall(long, long, long, long);
#define call_scalar ara_akv_direct_test_syscall
#else
#if !defined(__riscv) || __riscv_xlen != 64
#error "Direct AKV Linux client requires RV64"
#endif
static long call_scalar(long nr, long x0, long x1, long x2)
{
    register long a0 asm("a0") = x0;
    register long a1 asm("a1") = x1;
    register long a2 asm("a2") = x2;
    register long a3 asm("a3") = 0;
    register long a4 asm("a4") = 0;
    register long a5 asm("a5") = 0;
    register long a7 asm("a7") = nr;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3),
                 "r"(a4), "r"(a5), "r"(a7) : "memory");
    return a0;
}
#endif

static void zero_scalar(void *object, unsigned size)
{
    volatile unsigned char *bytes = object;
    for (unsigned i = 0; i < size; ++i) bytes[i] = 0;
}

void ara_akv_direct_close(int fd)
{
    if (fd >= 0) (void)call_scalar(__NR_close, fd, 0, 0);
}

int ara_akv_direct_open(struct ara_akv_direct_info *info)
{
    struct { int64_t key; uint64_t value; } probe = {4, 0};
    const uint64_t required = UINT64_C(5) | (UINT64_C(1) << 27) | (UINT64_C(1) << 30);
    if (!info) return -EINVAL;
    zero_scalar(info, sizeof(*info));
    const long policy = call_scalar(__NR_prctl, PR_RISCV_V_GET_CONTROL, 0, 0);
    if (policy < 0 || (policy & PR_RISCV_V_VSTATE_CTRL_CUR_MASK) != PR_RISCV_V_VSTATE_CTRL_ON)
        return -EOPNOTSUPP;
    if (call_scalar(__NR_riscv_hwprobe, (long)&probe, 1, 0) != 0 || probe.key != 4 ||
        (probe.value & required) != required) return -EOPNOTSUPP;
    const long fd = call_scalar(__NR_openat, AT_FDCWD, (long)"/dev/ara-akv-direct", O_RDWR | O_CLOEXEC);
    if (fd < 0) return (int)fd;
    long rc = call_scalar(__NR_ioctl, fd, ARA_AKV_DIRECT_GET_INFO, (long)info);
    if (!rc) {
        if (info->abi != ARA_AKV_DIRECT_ABI || info->bytes != sizeof(*info) ||
            info->features != ARA_AKV_DIRECT_REQUIRED_FEATURES || info->online_cpus != 1 ||
            info->gate_signature != ARA_AKV_GATE_SIGNATURE) rc = -EPROTO;
        for (unsigned i = 0; i < 4; ++i) if (info->reserved[i]) rc = -EPROTO;
    }
    if (rc) { ara_akv_direct_close((int)fd); return (int)rc; }
    return (int)fd;
}

long ara_akv_direct_acquire(int fd, struct ara_akv_direct_lease *lease)
{
    if (fd < 0 || !lease) return -EINVAL;
    zero_scalar(lease, sizeof(*lease));
    lease->abi = ARA_AKV_DIRECT_ABI;
    lease->bytes = sizeof(*lease);
    long rc = call_scalar(__NR_ioctl, fd, ARA_AKV_DIRECT_ACQUIRE, (long)lease);
    if (rc) return rc;
    const long tid = call_scalar(__NR_gettid, 0, 0, 0);
    if (tid <= 0 || lease->abi != ARA_AKV_DIRECT_ABI || lease->bytes != sizeof(*lease) ||
        lease->flags || lease->reserved0 || !lease->generation || lease->owner_tid != (uint64_t)tid ||
        lease->hart != 0) rc = -EPROTO;
    for (unsigned i = 0; i < 4; ++i) if (lease->reserved[i]) rc = -EPROTO;
    if (rc) (void)call_scalar(__NR_ioctl, fd, ARA_AKV_DIRECT_RELEASE, 0);
    return rc;
}

long ara_akv_direct_release(int fd)
{
    return fd < 0 ? -EINVAL : call_scalar(__NR_ioctl, fd, ARA_AKV_DIRECT_RELEASE, 0);
}
