/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef ARA_AKV_DIRECT_UAPI_H
#define ARA_AKV_DIRECT_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define ARA_AKV_DIRECT_ABI 1u
#define ARA_AKV_GATE_CSR 0x5c0
#define ARA_AKV_GATE_SIGNATURE 0x414b5601ULL
#define ARA_AKV_GATE_STRICT 1u
#define ARA_AKV_GATE_USER 2u
#define ARA_AKV_GATE_SUPERVISOR 4u

#define ARA_AKV_DIRECT_THREAD_EXCLUSIVE 1u
#define ARA_AKV_DIRECT_NO_HOT_IOCTL 2u
#define ARA_AKV_DIRECT_FAIL_CLOSED 4u
#define ARA_AKV_DIRECT_REQUIRED_FEATURES 7u

struct ara_akv_direct_info {
    __u32 abi, bytes, features, online_cpus;
    __u64 gate_signature, generation;
    __u64 reserved[4];
};

/* Only abi and bytes are nonzero on input. Ownership is never user supplied. */
struct ara_akv_direct_lease {
    __u32 abi, bytes, flags, reserved0;
    __u64 generation;
    __u32 owner_tid, hart;
    __u64 reserved[4];
};

#define ARA_AKV_DIRECT_GET_INFO _IOR('K', 0xb0, struct ara_akv_direct_info)
#define ARA_AKV_DIRECT_ACQUIRE _IOWR('K', 0xb1, struct ara_akv_direct_lease)
#define ARA_AKV_DIRECT_RELEASE _IO('K', 0xb2)

#endif
