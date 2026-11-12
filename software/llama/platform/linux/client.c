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
    register long a7 asm("a7") = nr;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
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
