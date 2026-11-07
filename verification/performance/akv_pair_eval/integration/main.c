#include "akv/akv.h"
#include "akv/akv_decode.h"
#include <stddef.h>

#if !defined(AKV_NATIVE_AUTO_PAIR_POLICY) || AKV_NATIVE_AUTO_PAIR_POLICY != 1
#error "The archived SDK must provide the call-local native auto API"
#endif

static akv_status_t policy_decode_execute(
    const akv_device_t *, const akv_decode_problem_t *,
    akv_decode_group_executor_t, void *, uint64_t *);

/* Include headers first: remap the sealed caller, never an SDK declaration. */
#define akv_decode_execute policy_decode_execute
#define getenv sealed_trial_getenv_unused
#include "../main.c"
#undef getenv
#undef akv_decode_execute

char *getenv(const char *name) {
  (void)name;
  return NULL;
}

static akv_status_t policy_group(void *context, const akv_attention_plan_t *plan,
                                  uint32_t batch, uint32_t first_head) {
  if (!selected_arm) return execute_group(NULL, plan, batch, first_head);
  if (batch || first_head || context == NULL) return AKV_STATUS_SHAPE;
  return akv_attention_execute_v2_native_auto(
      (const akv_device_t *)context, plan, &workspace.value);
}

static akv_status_t policy_decode_execute(
    const akv_device_t *device, const akv_decode_problem_t *problem,
    akv_decode_group_executor_t executor, void *context, uint64_t *groups) {
  if (executor != execute_group || context != NULL) return AKV_STATUS_BAD_ARGUMENT;
  return akv_decode_execute(device, problem, policy_group, (void *)device, groups);
}
