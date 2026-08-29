#include "qbs/qbs.h"

#include <string.h>

int main(void) {
  qbs_device_t device;
  if (qbs_device_init_reference(1024, &device) != QBS_STATUS_OK)
    return 1;
  if (!qbs_device_supports_profile(
          &device, QBS_WEIGHT_PROFILE_Q4_K,
          QBS_ACTIVATION_PROFILE_Q8_K))
    return 1;
  return strcmp(qbs_weight_profile_name(QBS_WEIGHT_PROFILE_Q4_K),
                "Q4_K") != 0;
}
