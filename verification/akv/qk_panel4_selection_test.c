#include "akv/akv.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #x); exit(1); } } while (0)
static unsigned info_reads, env_reads, cases;
static const char *environment;
static uint64_t words[4];

uint64_t akv_native_info(void *context, unsigned index) {
  CHECK(context == NULL && index < 4);
  ++info_reads;
  return words[index];
}

#ifndef QK_TEST_NO_ENV
char *qk_panel4_test_getenv(const char *name) {
  CHECK(strcmp(name, "AKV_QK_PANEL4") == 0);
  ++env_reads;
  return (char *)environment;
}
#endif

#define getenv qk_panel4_test_getenv
#include "qk_panel4_selection.inc"
#undef getenv

static akv_attention_plan_t plan;
static void setup(void) {
  memset(&plan, 0, sizeof(plan));
  plan.descriptor.element_format = AKV_ELEMENT_FORMAT_F16;
  plan.descriptor.head_dim = 128;
  plan.descriptor.q_rows = 6;
  environment = "1";
  env_reads = info_reads = 0;
  for (unsigned i = 0; i < 4; ++i)
    words[i] = i < 2 ? akv_capability_word(i, 1) : akv_v2_capability_word(i, 1);
}

static void expect(int selected, unsigned env, unsigned info) {
  CHECK(qk_panel4_enabled_for_plan(&plan) == selected);
  CHECK(env_reads == env && info_reads == info);
  ++cases;
}

int main(void) {
  setup();
#ifdef QK_TEST_NO_ENV
  expect(0, 0, 0);
#else
  expect(1, 1, 4);
  const char *off[] = {NULL, "", "0", "2", "01", "true", "1x", "1 ", " 1"};
  for (size_t i = 0; i < sizeof(off) / sizeof(off[0]); ++i) {
    setup(); environment = off[i]; expect(0, 1, 0);
  }
  for (unsigned h = 0; h <= 9; ++h) if (h != 6) {
    setup(); plan.descriptor.q_rows = (uint8_t)h; expect(0, 0, 0);
  }
  const unsigned dims[] = {0, 64, 96, 127, 129, 256};
  for (size_t i = 0; i < sizeof(dims) / sizeof(dims[0]); ++i) {
    setup(); plan.descriptor.head_dim = (uint16_t)dims[i]; expect(0, 0, 0);
  }
  setup(); plan.descriptor.element_format = AKV_ELEMENT_FORMAT_INVALID; expect(0, 0, 0);
  setup(); words[2] &= ~(UINT64_C(1) << AKV_V2_COLUMN_PANEL_CAPABILITY_BIT); expect(0, 1, 4);
  setup(); words[2] &= ~(UINT64_C(1) << 32); expect(0, 1, 4);
  setup(); words[0] &= ~(UINT64_C(1) << 49); expect(0, 1, 4);
  setup(); words[0] &= ~(UINT64_C(1) << 51); expect(0, 1, 4);
  setup(); words[0] = (words[0] & ~(UINT64_C(255) << 24)) | (UINT64_C(5) << 24); expect(0, 1, 4);
  for (unsigned i = 0; i < 4; ++i) {
    setup(); words[i] ^= UINT64_C(1) << 63; expect(0, 1, 4);
  }
  setup(); words[2] = words[3] = 0; expect(0, 1, 4);
  setup(); words[2] &= ~((UINT64_C(1) << AKV_V2_D_AXIS_TAIL_CAPABILITY_BIT) |
                         (UINT64_C(1) << AKV_V2_D256_SEGMENTED_CAPABILITY_BIT));
  expect(1, 1, 4);
  // No process-global cache: changing the environment affects the next call.
  setup(); environment = "0"; expect(0, 1, 0);
  env_reads = info_reads = 0; environment = "1"; expect(1, 1, 4);
#endif
  printf("AKV_QK_PANEL4_SELECTION_PASS cases=%u\n", cases);
  return 0;
}
