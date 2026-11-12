/* SPDX-License-Identifier: Apache-2.0 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "client.h"
#include "job_layout.h"
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

struct ara_linux_hwprobe { int64_t key; uint64_t value; };

#ifdef ARA_RESIDENT_CLIENT_TEST
extern long ara_resident_test_syscall(long, long, long, long);
#define scalar_syscall ara_resident_test_syscall
#else
#if !defined(__riscv) || __riscv_xlen != 64
#error "The Resident Linux client requires RV64"
#endif
static long scalar_syscall(long nr, long x0, long x1, long x2)
{
    register long a0 asm("a0") = x0;
    register long a1 asm("a1") = x1;
    register long a2 asm("a2") = x2;
    register long a3 asm("a3") = 0;
    register long a4 asm("a4") = 0;
    register long a5 asm("a5") = 0;
    register long a7 asm("a7") = nr;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a7) : "memory");
    return a0;
}
#endif

void ara_resident_linux_close(int fd)
{
    if (fd >= 0) (void)scalar_syscall(__NR_close, fd, 0, 0);
}

int ara_resident_linux_open(struct ara_resident_info *info)
{
    if (!info) return -EINVAL;
    const long policy = scalar_syscall(__NR_prctl, PR_RISCV_V_GET_CONTROL, 0, 0);
    if (policy < 0 || (policy & PR_RISCV_V_VSTATE_CTRL_CUR_MASK) != PR_RISCV_V_VSTATE_CTRL_ON)
        return -EOPNOTSUPP;
    struct ara_linux_hwprobe probe = {4, 0};
    const uint64_t required = UINT64_C(5) | (UINT64_C(1) << 27) | (UINT64_C(1) << 30);
    if (scalar_syscall(__NR_riscv_hwprobe, (long)&probe, 1, 0) != 0 || probe.key != 4 ||
        (probe.value & required) != required) return -EOPNOTSUPP;
    long fd = scalar_syscall(__NR_openat, AT_FDCWD, (long)"/dev/ara-resident", O_RDWR | O_CLOEXEC);
    if (fd < 0) return (int)fd;
    /* A scalar loop avoids depending on libc's vector CSR behavior. */
    volatile unsigned char *bytes = (volatile unsigned char *)info;
    for (unsigned i = 0; i < sizeof(*info); ++i) bytes[i] = 0;
    long rc = scalar_syscall(__NR_ioctl, fd, ARA_RESIDENT_GET_INFO, (long)info);
    if (rc == 0) {
        if (info->abi != ARA_RESIDENT_ABI || info->bytes != sizeof(*info) ||
            info->features != (ARA_RESIDENT_FEATURE_ATOMIC_GROUP | ARA_RESIDENT_FEATURE_COPY_IO) ||
            info->nr_lanes != 4 || info->vlen_bits != 1024 ||
            info->max_heads != ARA_RESIDENT_MAX_HEADS || info->max_tokens != ARA_RESIDENT_MAX_TOKENS ||
            info->dimensions != (ARA_RESIDENT_DIM64 | ARA_RESIDENT_DIM96 | ARA_RESIDENT_DIM128)) rc = -EPROTO;
        for (unsigned i = 0; i < 4; ++i) if (info->reserved[i]) rc = -EPROTO;
    }
    if (rc) { ara_resident_linux_close((int)fd); return (int)rc; }
    return (int)fd;
}

/* The assembly entry guards state before this function inspects metadata. */
long ara_resident_linux_execute_scalar(int fd, struct ara_resident_job *job)
{
    struct ara_resident_sizes sizes;
    if (fd < 0 || !ara_resident_job_sizes(job, &sizes)) return -EINVAL;
    const long rc = scalar_syscall(__NR_ioctl, fd, ARA_RESIDENT_EXECUTE, (long)job);
    if (rc) return rc;
    if (job->fflags & ~31U) return -EPROTO;
    return 0;
}
