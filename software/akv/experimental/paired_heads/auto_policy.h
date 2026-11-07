#ifndef AKV_PAIR_AUTO_POLICY_H
#define AKV_PAIR_AUTO_POLICY_H

#include "admission.h"

/* Pure selection on a validated call and a platform-admitted native device.
 * Capabilities may be cached, but shape, precision and VLEN are per call.
 */
static inline int akv_pair_f16_auto_admitted(
    const akv_descriptor_t *descriptor, const akv_device_t *device,
    uintptr_t vlenb, unsigned plain_scores) {
  return device != NULL && vlenb == 128u && plain_scores == 1u &&
         akv_pair_f16_admitted(1u, descriptor, &device->capabilities);
}

#endif
