#include "akv/akv.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #x); exit(1); } } while (0)
static unsigned info_reads, env_reads, cases;
static const char *environment;
static uint64_t words[4];
static akv_attention_plan_t plan;
static akv_device_t device;

uint64_t akv_native_info(void *context, unsigned index) {
  CHECK(context == NULL && index < 4);
  ++info_reads;
  return words[index];
}

extern char *panel4_test_getenv(const char *) __attribute__((weak));
#ifndef PANEL4_NO_ENV
char *panel4_test_getenv(const char *name) {
  CHECK(strcmp(name, "AKV_QK_PANEL4") == 0);
  ++env_reads;
  return (char *)environment;
}
#endif

#define getenv panel4_test_getenv
#include "panel4_selection.inc"
#undef getenv

static void setup(void) {
  memset(&plan, 0, sizeof(plan));
  plan.descriptor.element_format = AKV_ELEMENT_FORMAT_F16;
  plan.descriptor.head_dim = 128;
  plan.descriptor.q_rows = 6;
  plan.descriptor.kv_length = 128;
  for (unsigned i = 0; i < 4; ++i)
    words[i] = i < 2 ? akv_capability_word(i, 1) : akv_v2_capability_word(i, 1);
  CHECK(akv_device_query(akv_native_info, NULL, &device) == AKV_STATUS_OK);
  environment = NULL;
  info_reads = env_reads = 0;
}

static void expect(const akv_attention_plan_t *p, const akv_device_t *d,
                   unsigned automatic, int selected, unsigned env, unsigned info) {
  CHECK(qk_panel4_enabled_for_plan(p, d, automatic) == selected);
  CHECK(env_reads == env && info_reads == info);
  ++cases;
  env_reads = info_reads = 0;
}

int main(void) {
#ifdef PANEL4_NO_ENV
  const unsigned env = 0;
#else
  const unsigned env = 1;
#endif
  setup();
  expect(&plan, &device, 1, 1, env, 0);
  expect(&plan, NULL, 0, 0, env, 0);
  expect(&plan, NULL, 1, 0, env, 0);
  expect(NULL, &device, 1, 0, 0, 0);
  expect(&plan, &device, 2, 0, 0, 0);
  const unsigned lengths[] = {1, 17, 65, 127, 128, 129, 255, 4096};
  for (size_t i = 0; i < sizeof(lengths) / sizeof(lengths[0]); ++i) {
    setup(); plan.descriptor.kv_length = lengths[i];
    expect(&plan, &device, 1, lengths[i] >= 128, env, 0);
#ifndef PANEL4_NO_ENV
    environment = "1";
    expect(&plan, NULL, 0, 1, 1, 4);
    expect(&plan, &device, 1, 1, 1, 0);
#endif
  }

#ifndef PANEL4_NO_ENV
  const char *values[] = {NULL, "", "0", "1", "2", "01", "true", "1x", "1 ", " 1"};
  for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
    setup(); environment = values[i];
    const int on = values[i] != NULL && strcmp(values[i], "1") == 0;
    expect(&plan, &device, 1, values[i] == NULL || on, 1, 0);
    expect(&plan, NULL, 0, on, 1, on ? 4 : 0);
    expect(&plan, NULL, 1, 0, 1, 0);
  }
  // Generic explicit opt-in still queries native hardware, not the passed cache.
  setup(); environment = "1"; device.capabilities.valid = 0;
  expect(&plan, &device, 0, 1, 1, 4);
  expect(&plan, &device, 1, 0, 1, 0);
  setup(); environment = "1"; words[0] ^= UINT64_C(1) << 63;
  expect(&plan, NULL, 0, 0, 1, 4);
  expect(&plan, &device, 1, 1, 1, 0);
  // No global caching of overrides or capability selection.
  setup(); environment = "0"; expect(&plan, &device, 1, 0, 1, 0);
  environment = NULL; expect(&plan, &device, 1, 1, 1, 0);
  environment = "1"; expect(&plan, NULL, 0, 1, 1, 4);
  environment = NULL; expect(&plan, NULL, 0, 0, 1, 0);
#endif

  for (unsigned h = 0; h <= 9; ++h) if (h != 6) {
    setup(); plan.descriptor.q_rows = (uint8_t)h;
    expect(&plan, &device, 1, 0, 0, 0);
    expect(&plan, NULL, 0, 0, 0, 0);
  }
  const unsigned dims[] = {0, 64, 96, 127, 129, 256};
  for (size_t i = 0; i < sizeof(dims) / sizeof(dims[0]); ++i) {
    setup(); plan.descriptor.head_dim = (uint16_t)dims[i];
    expect(&plan, &device, 1, 0, 0, 0);
  }
  const unsigned formats[] = {AKV_ELEMENT_FORMAT_INVALID, 2u, 255u};
  for (size_t i = 0; i < sizeof(formats) / sizeof(formats[0]); ++i) {
    setup(); plan.descriptor.element_format = (uint8_t)formats[i];
    expect(&plan, &device, 1, 0, 0, 0);
  }
  for (unsigned missing = 0; missing < 7; ++missing) {
    setup();
    switch (missing) {
      case 0: device.capabilities.valid = 0; break;
      case 1: device.capabilities.f16_payload = 0; break;
      case 2: device.capabilities.head_dim_128 = 0; break;
      case 3: device.capabilities.max_q_rows = 5; break;
      case 4: device.capabilities.token_axis_valid = 0; break;
      case 5: device.capabilities.token_axis_tail = 0; break;
      case 6: device.capabilities.token_axis_column_panel4 = 0; break;
    }
    expect(&plan, &device, 1, 0, env, 0);
#ifndef PANEL4_NO_ENV
    environment = "1"; expect(&plan, &device, 1, 0, 1, 0);
#endif
  }
#ifndef PANEL4_NO_ENV
  for (unsigned missing = 0; missing < 8; ++missing) {
    setup(); environment = "1";
    switch (missing) {
      case 0: words[2] &= ~(UINT64_C(1) << AKV_V2_COLUMN_PANEL_CAPABILITY_BIT); break;
      case 1: words[2] &= ~(UINT64_C(1) << 32); break;
      case 2: words[0] &= ~(UINT64_C(1) << 49); break;
      case 3: words[0] &= ~(UINT64_C(1) << 51); break;
      default: words[missing-4] ^= UINT64_C(1) << 63; break;
    }
    expect(&plan, NULL, 0, 0, 1, 4);
  }
#endif
  printf("PANEL4_SELECTOR_PASS cases=%u no_env=%u\n", cases, env == 0);
  return 0;
}
