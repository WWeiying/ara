/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARA_AKV_DIRECT_CLIENT_H
#define ARA_AKV_DIRECT_CLIENT_H

#include "direct_uapi.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Setup/teardown only. No function here belongs inside an Attention call. */
int ara_akv_direct_open(struct ara_akv_direct_info *info);
long ara_akv_direct_acquire(int fd, struct ara_akv_direct_lease *lease);
long ara_akv_direct_release(int fd);
void ara_akv_direct_close(int fd);

#ifdef __cplusplus
}
#endif
#endif
