#include "qbs/qbs.h"
#include "printf.h"

#ifndef EXPECT_COOPERATIVE
#error EXPECT_COOPERATIVE must match the selected image
#endif

static uint64_t legacy_info(void *context, unsigned index) {
  return index == QBS_COOPERATIVE_CAPABILITY_INDEX ? 0 : qbs_native_info(context, index);
}

int main(void) {
  qbs_device_t device, legacy;
  const uint64_t feature = qbs_native_info(NULL, QBS_COOPERATIVE_CAPABILITY_INDEX);
  unsigned errors = feature != EXPECT_COOPERATIVE;
  errors += qbs_native_info(NULL, 0) != qbs_capability_word(0, 1024);
  errors += qbs_native_info(NULL, 1) != qbs_capability_word(1, 1024);
  errors += qbs_native_info(NULL, 0xffff) != 0;
  errors += qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK;
  errors += device.capabilities.q4_k_cooperative != EXPECT_COOPERATIVE;
  errors += qbs_device_query(legacy_info, NULL, &legacy) != QBS_STATUS_OK;
  errors += legacy.capabilities.q4_k_cooperative != 0;
  printf("EXT_NATIVE_CAPABILITY_DONE expected=%u actual=%lu decoded=%u legacy=%u errors=%u\n",
         EXPECT_COOPERATIVE, (unsigned long)feature, device.capabilities.q4_k_cooperative,
         legacy.capabilities.q4_k_cooperative, errors);
  return errors != 0;
}
