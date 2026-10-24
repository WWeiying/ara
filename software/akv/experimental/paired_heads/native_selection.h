#ifndef AKV_PAIR_NATIVE_SELECTION_H
#define AKV_PAIR_NATIVE_SELECTION_H

#include "admission.h"
#include "dispatch.h"

extern char *getenv(const char *) __attribute__((weak));

/* The candidate caller invokes this once before its first FULL, never from a
 * leaf or after partial execution. No selection state survives the call. */
static int akv_pair_candidate_enabled_for_plan(const akv_attention_plan_t *plan) {
  const unsigned heads = plan->descriptor.q_rows;
  const unsigned dim = plan->descriptor.head_dim;
  if (getenv == NULL || heads < 2 || heads > AKV_MAX_Q_ROWS ||
      (dim != 64 && dim != 96 && dim != 128) || (heads == 6 && dim == 128))
    return 0;
  const char *value = getenv("AKV_PAIR_HEADS");
  if (value == NULL || value[0] != '1' || value[1] != '\0')
    return 0;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0, vlenb" : "=r"(vlenb));
  if (vlenb != 128)
    return 0;
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device) != AKV_STATUS_OK)
    return 0;
  return akv_pair_f16_admitted(1, &plan->descriptor, &device.capabilities);
}

#endif
