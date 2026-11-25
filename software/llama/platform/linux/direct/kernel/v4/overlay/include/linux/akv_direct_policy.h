/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_AKV_DIRECT_POLICY_H
#define _LINUX_AKV_DIRECT_POLICY_H

#include <linux/ara_akv_direct.h>

static inline int akv_direct_valid_lease(const struct ara_akv_direct_lease *v)
{
	unsigned int i;

	if (v->abi != ARA_AKV_DIRECT_ABI || v->bytes != sizeof(*v) ||
	    v->flags || v->reserved0 || v->generation || v->owner_tid || v->hart)
		return 0;
	for (i = 0; i < 4; i++)
		if (v->reserved[i])
			return 0;
	return 1;
}

static inline int akv_direct_valid_gate(__u64 value)
{
	return (value >> 32) == ARA_AKV_GATE_SIGNATURE &&
	       !(value & 0xfffffff8ULL);
}
#endif
