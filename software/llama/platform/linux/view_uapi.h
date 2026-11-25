/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef ARA_RESIDENT_VIEW_UAPI_H
#define ARA_RESIDENT_VIEW_UAPI_H
#include "ara_resident_uapi.h"

#define ARA_RESIDENT_VIEW_ABI 1u
#define ARA_RESIDENT_MAX_VIEWS 32u
#define ARA_RESIDENT_MAX_KV_HEADS 32u
#define ARA_RESIDENT_MAX_BATCH 16u
#define ARA_RESIDENT_MAX_VIEW_BYTES (1024u * 1024u)
#define ARA_RESIDENT_PIN_LIMIT_BYTES (64u * 1024u * 1024u)

struct ara_resident_view_caps {
    __u32 abi, bytes, max_views, max_groups;
    __u32 max_kv_heads, max_view_bytes, pin_limit_bytes, flags;
    __aligned_u64 reserved[4];
};

/* A view describes live F16 K/V storage, not an immutable data snapshot.
 * All writers must be synchronized with EXECUTE_BATCH. Unmap/COW invalidates
 * the handle. Handles are FD- and address-space-local, never kernel pointers.
 */
struct ara_resident_kv_view {
    __u32 abi, bytes, dimension, kv_heads, capacity, flags;
    __u32 key_token_stride, key_head_stride, value_token_stride, value_head_stride;
    __aligned_u64 key, value, handle;
    __aligned_u64 reserved[4];
};

struct ara_resident_view_release {
    __u32 abi, bytes;
    __aligned_u64 handle;
    __aligned_u64 reserved[2];
};

struct ara_resident_batch_group {
    __u32 kv_head, heads;
    __aligned_u64 reserved;
};

/* Q and output rows are packed in group order. One mask is shared by groups.
 * No result is copied until all groups finish; copy faults are terminal.
 * fflags deliberately has the same offset as the original execute wrapper.
 */
struct ara_resident_batch {
    __u32 abi, bytes, count, dimension, tokens, scale_bits, flags, fflags;
    __aligned_u64 handle, groups, query, mask, output;
    __u32 completed, reserved0;
    __aligned_u64 reserved[3];
};

#define ARA_RESIDENT_VIEW_CAPS _IOR('R', 0xa3, struct ara_resident_view_caps)
#define ARA_RESIDENT_REGISTER_KV _IOWR('R', 0xa4, struct ara_resident_kv_view)
#define ARA_RESIDENT_RELEASE_KV _IOW('R', 0xa5, struct ara_resident_view_release)
#define ARA_RESIDENT_EXECUTE_BATCH _IOWR('R', 0xa6, struct ara_resident_batch)
#endif
