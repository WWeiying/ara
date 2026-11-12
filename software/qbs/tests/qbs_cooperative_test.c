#include "qbs/qbs.h"
#include <assert.h>
#include <stdio.h>

typedef struct {
  unsigned vlen;
  uint64_t extra;
  unsigned no_m8_layout;
  unsigned no_q4;
  unsigned extra_reads;
} fixture_t;

static uint64_t info(void *context, unsigned index) {
  fixture_t *f = context;
  if (index == QBS_COOPERATIVE_CAPABILITY_INDEX) {
    ++f->extra_reads;
    return f->extra;
  }
  uint64_t value = qbs_capability_word(index, f->vlen);
  if (index == 1 && f->no_m8_layout)
    value &= ~(UINT64_C(1) << (16u + QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED));
  if (index == 0x20u + QBS_WEIGHT_PROFILE_Q4_K && f->no_q4) return 0;
  return value;
}

int main(void) {
  unsigned checked = 0;
  for (unsigned width = 512; width <= 1024; width += 512) {
    for (unsigned feature = 0; feature < 4; ++feature) {
      for (unsigned layout = 0; layout < 2; ++layout) {
        for (unsigned profile = 0; profile < 2; ++profile) {
          fixture_t f = {width, (feature & 1u) | ((uint64_t)(feature >> 1u) << 63), layout, profile, 0};
          qbs_device_t device;
          assert(qbs_device_query(info, &f, &device) == QBS_STATUS_OK);
          assert(device.capabilities.q4_k_cooperative ==
                 (width == 1024 && (feature & 1u) && !layout && !profile));
          assert(f.extra_reads == 1);
          ++checked;
        }
      }
    }
  }
  qbs_device_t reference;
  assert(qbs_device_init_reference(1024, &reference) == QBS_STATUS_OK);
  assert(!reference.capabilities.q4_k_cooperative);
  assert(qbs_capability_word(QBS_COOPERATIVE_CAPABILITY_INDEX, 1024) == 0);
  qbs_capabilities_t decoded;
  assert(qbs_capabilities_decode(qbs_capability_word(0, 1024) | (UINT64_C(1) << 49),
                                 qbs_capability_word(1, 1024), &decoded) == QBS_STATUS_OK);
  assert(!decoded.q4_k_cooperative);
  printf("QBS_COOPERATIVE_CAPABILITY_PASS combinations=%u legacy=off info0_unchanged=1\n", checked);
  return 0;
}
