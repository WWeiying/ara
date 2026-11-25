/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARA_RESIDENT_LINUX_CLIENT_H
#define ARA_RESIDENT_LINUX_CLIENT_H

#include "ara_resident_uapi.h"
#include "view_uapi.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Returns a close-on-exec FD, or a negative errno; no accelerator instruction. */
int ara_resident_linux_open(struct ara_resident_info *);
void ara_resident_linux_close(int);

/* Recheck the calling thread's F/V policy and ISA without opening a device.
 * A retained FD does not grant hardware ownership; EXECUTE still checks the
 * device epoch, online CPUs and protected execution context on every call.
 */
int ara_resident_linux_admit(void);

/* Zero is completion. -EOPNOTSUPP/-ENODEV/-EBUSY decline before publication.
 * Other errors are terminal for this attempt. In particular, never retry EFAULT.
 * RV64 entry requires user F/V access; rejects nonzero VSTART without a syscall.
 * Preserves exact entry VCSR/VSTART and FCSR, ORing returned FFLAGS on success.
 * Vector registers follow the ordinary function/syscall ABI, not callee-save.
 */
long ara_resident_linux_execute(int, struct ara_resident_job *);

/* Optional live-KV extension. Registration pins mappings, not tensor contents.
 * Callers own storage lifetime and exclude all concurrent writers during a batch.
 * Close releases every handle. Invalidation is terminal for a handle; do not
 * replay a failed batch. Keep output private until successful completion.
 */
long ara_resident_linux_view_caps(int, struct ara_resident_view_caps *);
long ara_resident_linux_register_kv(int, struct ara_resident_kv_view *);
long ara_resident_linux_release_kv(int, __u64);
long ara_resident_linux_execute_batch(int, struct ara_resident_batch *);

#ifdef __cplusplus
}
#endif
#endif
