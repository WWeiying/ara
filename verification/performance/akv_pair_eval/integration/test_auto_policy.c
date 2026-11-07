#include "akv/akv.h"
#include "akv/akv_features.h"
#include "auto_policy.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint16_t query[3*64] __attribute__((aligned(64)));
static uint16_t key[5*64] __attribute__((aligned(64)));
static uint16_t value[5*64] __attribute__((aligned(64)));
static uint16_t mask[5] __attribute__((aligned(64)));
static float output[3*64] __attribute__((aligned(64)));
static akv_attention_v2_workspace_t workspace;

int main(void) {
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  const uintptr_t lengths[] = {0, 16, 32, 64, 128, 256};
  unsigned decisions = 0;
  for (unsigned dim = 0; dim <= 257; ++dim)
    for (unsigned heads = 0; heads <= 9; ++heads)
      for (unsigned format = 0; format < 4; ++format)
        for (unsigned l = 0; l < sizeof(lengths)/sizeof(lengths[0]); ++l)
          for (unsigned plain = 0; plain < 3; ++plain) {
            const akv_descriptor_t desc = {.head_dim=dim, .q_rows=heads, .element_format=format};
            const int expected = plain == 1 && lengths[l] == 128 &&
                heads >= 2 && heads <= AKV_MAX_Q_ROWS &&
                (dim == 64 || dim == 96 || dim == 128) && !(heads == 6 && dim == 128) &&
                format == AKV_ELEMENT_FORMAT_F16;
            assert(akv_pair_f16_auto_admitted(&desc, &device, lengths[l], plain) == expected);
            ++decisions;
          }
  const akv_descriptor_t desc = {.head_dim=128, .q_rows=2, .element_format=AKV_ELEMENT_FORMAT_F16};
  assert(!akv_pair_f16_auto_admitted(NULL, &device, 128, 1));
  assert(!akv_pair_f16_auto_admitted(&desc, NULL, 128, 1));
#define REJECT_WITHOUT(field) do { \
    akv_device_t missing = device; missing.capabilities.field = 0; \
    assert(!akv_pair_f16_auto_admitted(&desc, &missing, 128, 1)); \
  } while (0)
  REJECT_WITHOUT(valid); REJECT_WITHOUT(enabled); REJECT_WITHOUT(f16_payload);
  REJECT_WITHOUT(max_q_rows); REJECT_WITHOUT(context_count); REJECT_WITHOUT(head_dim_128);
  REJECT_WITHOUT(token_axis_valid); REJECT_WITHOUT(token_axis_enabled);
  REJECT_WITHOUT(token_axis_tail); REJECT_WITHOUT(token_axis_row_view);
  REJECT_WITHOUT(token_axis_column_panel4); REJECT_WITHOUT(token_axis_tile_tokens);
#undef REJECT_WITHOUT
  akv_device_t limited = device;
  limited.capabilities.token_axis_tile_tokens = 32;
  assert(!akv_pair_f16_auto_admitted(&desc, &limited, 128, 1));
  limited = device;
  limited.capabilities.max_q_rows = 1;
  assert(!akv_pair_f16_auto_admitted(&desc, &limited, 128, 1));

  const akv_attention_problem_t problem = {
      .query=query, .key=key, .value=value, .mask=mask, .output=output,
      .q_row_stride_bytes=128, .k_token_stride_bytes=128, .v_token_stride_bytes=128,
      .output_row_stride_bytes=256, .q_rows=3, .head_dim=64, .kv_length=5, .scale=.125f};
  akv_attention_plan_t plan;
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) == AKV_STATUS_OK);
  memset(&workspace, 0xa5, sizeof(workspace));
  memset(output, 0xa5, sizeof(output));
  assert(akv_attention_execute_v2_native_auto(NULL, &plan, &workspace) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_attention_execute_v2_native_auto(&device, NULL, &workspace) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_attention_execute_v2_native_auto(&device, &plan, NULL) == AKV_STATUS_BAD_ARGUMENT);
  /* Host execution must report unavailable, never pretend to run native ISA. */
  assert(akv_attention_execute_v2_native_auto(&device, &plan, &workspace) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(akv_attention_execute_v2_native(&plan, &workspace) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  akv_attention_features_t features = {0};
  assert(akv_attention_execute_v2_with_features_native_auto(&device, &plan, &workspace, &features)
         == AKV_STATUS_RUNTIME_UNAVAILABLE);
  features.softcap = 20.0f;
  assert(akv_attention_execute_v2_with_features_native_auto(&device, &plan, &workspace, &features)
         == AKV_STATUS_RUNTIME_UNAVAILABLE);
  features.softcap = NAN;
  assert(akv_attention_execute_v2_with_features_native_auto(&device, &plan, &workspace, &features)
         == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_attention_execute_v2_with_features_native_auto(NULL, &plan, &workspace, NULL)
         == AKV_STATUS_BAD_ARGUMENT);
  const unsigned char *bytes = (const unsigned char *)&workspace;
  for (size_t i = 0; i < sizeof(workspace); ++i) assert(bytes[i] == 0xa5);
  bytes = (const unsigned char *)output;
  for (size_t i = 0; i < sizeof(output); ++i) assert(bytes[i] == 0xa5);
  printf("AUTO_POLICY_HOST_PASS decisions=%u native_execution=0\n", decisions);
  return 0;
}
