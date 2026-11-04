#include "qbs/qbs.h"
#include <stdio.h>

static unsigned visits;
void __cyg_profile_func_enter(void *function, void *caller) {
  (void)caller;
  if (function == (void *)qbs_plan_next) ++visits;
}
void __cyg_profile_func_exit(void *function, void *caller) {
  (void)function;
  (void)caller;
}
int main(void) {
  qbs_device_t device;
  if (qbs_device_init_reference(1024, &device) != QBS_STATUS_OK) return 1;
  const unsigned ns[] = {64, 1024, 6144, 151936};
  const unsigned ms[] = {1, 4, 5, 8, 9, 17};
  for (unsigned i=0; i<sizeof(ns)/sizeof(ns[0]); ++i) {
    for (unsigned j=0; j<sizeof(ms)/sizeof(ms[0]); ++j) {
      const unsigned storage = ms[j] == 1 ? QBS_ACTIVATION_STORAGE_ROW_MAJOR :
          (ms[j] < 8 ? QBS_ACTIVATION_STORAGE_M4_GROUPED : QBS_ACTIVATION_STORAGE_M8_GROUPED);
      const qbs_problem_t p = {QBS_WEIGHT_PROFILE_Q4_0, QBS_ACTIVATION_PROFILE_Q8_0,
          QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, storage, ms[j], ns[i], 256};
      qbs_plan_t plan;
      visits = 0;
      if (qbs_plan_create(&device, &p, &plan) != QBS_STATUS_OK) return 2;
      const unsigned tiles = (ms[j]+(storage == QBS_ACTIVATION_STORAGE_M8_GROUPED ? 7u : 3u)) /
          (storage == QBS_ACTIVATION_STORAGE_M8_GROUPED ? 8u : 4u);
      if (visits == 0 || visits > 2u*tiles+1u) {
        fprintf(stderr, "Unbounded context scan m=%u n=%u visits=%u\n", ms[j], ns[i], visits);
        return 3;
      }
    }
  }
  puts("QBS_CONTEXT_COST_PASS: at most two commands per input tile plus end marker");
  return 0;
}
