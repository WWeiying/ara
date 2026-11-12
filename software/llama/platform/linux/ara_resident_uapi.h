/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef ARA_RESIDENT_LINUX_UAPI_H
#define ARA_RESIDENT_LINUX_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define ARA_RESIDENT_ABI 1u
#define ARA_RESIDENT_MAX_HEADS 8u
#define ARA_RESIDENT_MAX_TOKENS 256u
#define ARA_RESIDENT_DIM64 1u
#define ARA_RESIDENT_DIM96 2u
#define ARA_RESIDENT_DIM128 4u
#define ARA_RESIDENT_FEATURE_ATOMIC_GROUP 1u
#define ARA_RESIDENT_FEATURE_COPY_IO 2u

struct ara_resident_info {
    __u32 abi, bytes;
    __u32 features, dimensions;
    __u32 max_heads, max_tokens, nr_lanes, vlen_bits;
    __aligned_u64 reserved[4];
};

/* Packed F16 Q[heads][D], K/V[tokens][D], mask[tokens]; F32 out[heads][D].
 * There is no userspace descriptor, command list, ownership flag or kernel pointer.
 */
struct ara_resident_job {
    __u32 abi, bytes;
    __u32 heads, dimension, tokens, scale_bits;
    __u32 flags, fflags;
    __aligned_u64 query, key, value, mask, output;
    __aligned_u64 reserved[4];
};

#define ARA_RESIDENT_GET_INFO _IOR('R', 0xa0, struct ara_resident_info)
#define ARA_RESIDENT_EXECUTE _IOWR('R', 0xa1, struct ara_resident_job)

#endif
