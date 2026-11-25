#ifndef ARA_RESIDENT_KERNEL_COMPUTE_H
#define ARA_RESIDENT_KERNEL_COMPUTE_H

#if defined(__KERNEL__) && !defined(ARA_COMPUTE_FREESTANDING)
#include <linux/types.h>
#else
#include <stddef.h>
#endif

#define ARA_RESIDENT_COMPUTE_VALIDATED_AVAILABLE 1u
#define ARA_RESIDENT_COMPUTE_PLATFORM_ADMITTED 2u
#define ARA_RESIDENT_COMPUTE_WHOLE_CALL_OWNED 4u
#define ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS 7u

/* Kernel-owned, stable, prefaulted buffers only: never pass a user pointer.
 * Q is F16[heads][dimension], K/V are F16[tokens][dimension] shared by heads,
 * mask is F16[tokens] (required; zero means unmasked), output is a separate
 * kernel scratch F32[heads][dimension]. Each row is contiguous; K/V token
 * strides may include other KV heads. Zero strides select packed rows. Q/K/V and
 * scratch must be aligned to 64 bytes; mask to 2 and output to 4 bytes.
 * Q/K/V must be finite F16; mask finite F16 or -Inf, with at least one finite
 * entry. Scale bits encode finite 0 < scale <= 1. Unsupported numerical domains
 * return -EOPNOTSUPP before started; no user-mode SDK algorithm is changed.
 * Scratch must not overlap this descriptor or any tensor. Output must not
 * overlap inputs or this descriptor. The caller checks allocation extents.
 *
 * On entry set flags only from the real validated/platform/whole-call scope.
 * On success flags is replaced by the actual accrued RISC-V fflags (bits 0..4).
 * Caller owns preempt_disable + kernel_fpu_begin + kernel_vector_begin +
 * IRQ-save for this entire call, and restores them in reverse order. Admission
 * must establish trap-safe AKV query/CSR access and eligible kernel memory.
 * This entry installs fcsr=0 (RNE), vcsr=0 and vstart=0 in the owned scope;
 * the surrounding kernel APIs remain responsible for restoring user state.
 * No allocation, syscall, sleeping, printing, or userspace access occurs here.
 *
 * started/resident_used are call-local results; initialize both to zero.
 * Nonzero started on entry is terminal -EIO, never reset or retried. Once
 * started becomes 1, every error is terminal; frontend fallback is forbidden.
 * 0 = success, -EOPNOTSUPP = unavailable before execution, -EINVAL = invalid
 * buffers/shape/flags, -EIO = terminal execution state. No board acceptance.
 */
struct ara_resident_compute_buffers {
    void *query, *key, *value, *mask, *output, *scratch;
    size_t scratch_bytes;
    unsigned heads, dimension, tokens, scale_bits;
    unsigned flags, started, resident_used;
    unsigned key_token_stride, value_token_stride;
};

size_t ara_resident_compute_scratch_bytes(void);
int ara_resident_compute(struct ara_resident_compute_buffers *buffers);

#endif
