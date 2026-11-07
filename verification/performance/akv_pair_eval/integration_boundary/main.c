#include "akv/akv.h"
#include "printf.h"
#include <stdint.h>
#include <string.h>

static akv_device_t cached_device;
static unsigned queries, calls, autos, fallbacks, route_errors;
static akv_status_t capture_device(akv_info_reader_t, void *, akv_device_t *)
    __attribute__((noinline, noclone));
static akv_status_t boundary_route(const akv_attention_plan_t *, akv_attention_v2_workspace_t *)
    __attribute__((noinline, noclone));
int boundary_body(void) __attribute__((noinline, noclone));

#define getenv boundary_harness_getenv
#define akv_device_query capture_device
#define akv_attention_execute_v2_native boundary_route
#define main boundary_body
#include "native_runtime_main.c"
#undef main
#undef akv_attention_execute_v2_native
#undef akv_device_query
#undef getenv
#include "expected.h"

char *getenv(const char *name) {
  (void)name;
  return NULL;
}

static akv_status_t capture_device(akv_info_reader_t reader, void *context, akv_device_t *device) {
  const akv_status_t status = akv_device_query(reader, context, device);
  ++queries;
  if (status == AKV_STATUS_OK) memcpy(&cached_device, device, sizeof(cached_device));
  return status;
}

static akv_status_t boundary_route(const akv_attention_plan_t *p, akv_attention_v2_workspace_t *ws) {
  const unsigned c = calls / 3, trial = calls % 3;
  const unsigned automatic = requested == 1;
  const unsigned missing = automatic && c == 3;
  ++calls;
  if (queries != 1 || c >= 4 || automatic != (trial == 1)) {
    ++route_errors;
    return AKV_STATUS_BAD_ARGUMENT;
  }
  akv_device_t local;
  memcpy(&local, &cached_device, sizeof(local));
  if (missing) local.capabilities.token_axis_column_panel4 = 0;
  printf("AKV_AUTO_BOUNDARY_ROUTE case=%u trial=%u auto=%u missing_panel=%u panel=%u\n",
         c, trial, automatic, missing, local.capabilities.token_axis_column_panel4);
  if (!automatic) return akv_attention_execute_v2_native(p, ws);
  ++autos;
  fallbacks += missing;
  return akv_attention_execute_v2_native_auto(missing ? &local : &cached_device, p, ws);
}

static uint64_t payload_hash(const void *data, size_t bytes) {
  const volatile unsigned char *p = data;
  uint64_t value = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < bytes; ++i) value = (value ^ p[i]) * UINT64_C(1099511628211);
  return value;
}

static unsigned payload(const char *name, const void *data, size_t bytes, uint64_t expected) {
  const uint64_t actual = payload_hash(data, bytes);
  const unsigned errors = actual != expected;
  printf("AKV_BOUNDARY_PAYLOAD name=%s bytes=%lu fnv=%016lx expected=%016lx errors=%u\n",
         name, (unsigned long)bytes, (unsigned long)actual, (unsigned long)expected, errors);
  return errors;
}

int main(void) {
  printf("AKV_AUTO_BOUNDARY_CAP sdk=b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1 order=OFF/AUTO/OFF fallback_case=3\n");
  const int body = boundary_body();
  unsigned errors = body != 0 || queries != 1 || calls != 12 || autos != 4 || fallbacks != 1 || route_errors;
  errors += cached_device.capabilities.token_axis_column_panel4 != 1;
  errors += payload("q", candidate_query_f32, 6144, BOUNDARY_EXPECT_Q);
  errors += payload("k", candidate_key, 131072, BOUNDARY_EXPECT_K);
  errors += payload("v", candidate_value, 131072, BOUNDARY_EXPECT_V);
  printf("AKV_BOUNDARY_DONE body=%d checks=3 errors=%u\n", body, errors);
  printf("AKV_AUTO_BOUNDARY_DONE calls=%u queries=%u autos=%u fallbacks=%u errors=%u\n",
         calls, queries, autos, fallbacks, errors);
  return errors != 0;
}
