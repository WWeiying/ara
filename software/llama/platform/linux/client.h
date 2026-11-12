/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARA_RESIDENT_LINUX_CLIENT_H
#define ARA_RESIDENT_LINUX_CLIENT_H

#include "ara_resident_uapi.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Returns a close-on-exec FD, or a negative errno; no accelerator instruction. */
int ara_resident_linux_open(struct ara_resident_info *);
void ara_resident_linux_close(int);

/* Zero is completion. -EOPNOTSUPP/-ENODEV/-EBUSY decline before publication.
 * Other errors are terminal for this attempt. In particular, never retry EFAULT.
 * RV64 entry requires user F/V access; rejects nonzero VSTART without a syscall.
 * Preserves exact entry VCSR/VSTART and FCSR, ORing returned FFLAGS on success.
 * Vector registers follow the ordinary function/syscall ABI, not callee-save.
 */
long ara_resident_linux_execute(int, struct ara_resident_job *);

#ifdef __cplusplus
}
#endif
#endif
