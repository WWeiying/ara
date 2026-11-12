/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARA_RESIDENT_JOB_LAYOUT_H
#define ARA_RESIDENT_JOB_LAYOUT_H

#include "ara_resident_uapi.h"

struct ara_resident_sizes {
    unsigned query, key, value, mask, output;
};

/* Scalar metadata only. Bounds keep all products below 2^32. */
static inline int ara_resident_job_sizes(const struct ara_resident_job *j,
                                          struct ara_resident_sizes *out)
{
    unsigned dim;
    if (!j || !out || j->abi != ARA_RESIDENT_ABI || j->bytes != sizeof(*j) ||
        !j->heads || j->heads > ARA_RESIDENT_MAX_HEADS ||
        !j->tokens || j->tokens > ARA_RESIDENT_MAX_TOKENS || j->flags || j->fflags)
        return 0;
    dim = j->dimension;
    if (dim != 64 && dim != 96 && dim != 128)
        return 0;
    if ((j->scale_bits >> 31) || !(j->scale_bits & 0x7fffffffU) ||
        (j->scale_bits & 0x7f800000U) == 0x7f800000U)
        return 0;
    for (unsigned i = 0; i < 4; ++i)
        if (j->reserved[i]) return 0;
    if (!j->query || !j->key || !j->value || !j->mask || !j->output ||
        (j->query | j->key | j->value | j->mask) & 1 || j->output & 3)
        return 0;
    out->query = j->heads * dim * 2;
    out->key = out->value = j->tokens * dim * 2;
    out->mask = j->tokens * 2;
    out->output = j->heads * dim * 4;
    if (j->query > ~(__u64)0 - out->query || j->key > ~(__u64)0 - out->key ||
        j->value > ~(__u64)0 - out->value || j->mask > ~(__u64)0 - out->mask ||
        j->output > ~(__u64)0 - out->output)
        return 0;
    return 1;
}

#endif
