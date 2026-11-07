#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "probe.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

enum { DIM = 128, HEADS = 2, TOKENS = 137, CAPACITY = 256, GUARD = 64 };
_Static_assert(AKV_V2_TILE_TOKENS == 64, "This capture requires tile64");
_Static_assert(AKV_MAX_Q_ROWS == 8, "Guard footprint requires eight SDK workspace rows");
extern const float decode_query[HEADS * DIM];
extern const uint16_t decode_query_f16[HEADS * DIM];
extern const uint16_t decode_key[CAPACITY * DIM], decode_value[CAPACITY * DIM];
extern const uint16_t decode_mask[CAPACITY];
extern const float decode_golden[HEADS * DIM], native_golden[HEADS * DIM];
extern const unsigned char data_begin[], data_end[];
extern akv_status_t f16_profile_execute(const akv_attention_plan_t *,
                                      akv_attention_v2_workspace_t *);
volatile f16_probe_buffer_t f16_probe_buffer;

static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD];
  akv_attention_v2_workspace_t value;
  unsigned char after[GUARD];
} workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD];
  uint16_t value[HEADS * DIM];
  unsigned char after[GUARD];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD];
  float value[HEADS * DIM];
  unsigned char after[GUARD];
} output;
static struct {
  uint64_t begin, returned, end, fcsr, vcsr, vstart, groups, errors;
  uint64_t data_hash, query_hash, guard_hash;
  uint32_t bits[HEADS * DIM];
  f16_span_t spans[F16_SPANS];
} results[F16_TRIALS];
static const size_t guard_bytes = 8 * GUARD +
    (AKV_MAX_Q_ROWS * AKV_HEAD_DIM_256 - HEADS * DIM) * sizeof(uint16_t) +
    (AKV_MAX_Q_ROWS - HEADS) * (AKV_V2_TILE_TOKENS + 3) * sizeof(float);

/* Keep all optional experimental dispatch off in both copies. */
char *getenv(const char *name) { (void)name; return NULL; }

static inline uint64_t cycles(void) {
  uint64_t x;
  __asm__ volatile("rdcycle %0" : "=r"(x) : : "memory");
  return x;
}

static inline void drain(void) {
  uintptr_t x;
  /* Ara's scalar-result vector operation waits for older vector work.
   * The fence also completes the final output stores before the end stamp. */
  __asm__ volatile("vmv.x.s %0, v0\nfence rw, rw" : "=r"(x) : : "memory");
}

static uint64_t hash_data(void) {
  uint64_t x = UINT64_C(14695981039346656037);
  for (const unsigned char *p = data_begin; p < data_end; ++p)
    x = (x ^ *p) * UINT64_C(1099511628211);
  return x;
}

static uint64_t hash_bytes(uint64_t hash, const volatile void *ptr, size_t size) {
  const volatile unsigned char *p = ptr;
  for (size_t i = 0; i < size; ++i) hash = (hash ^ p[i]) * UINT64_C(1099511628211);
  return hash;
}

static uint64_t hash_guards(void) {
  uint64_t x = UINT64_C(14695981039346656037);
#define HASH(ptr, size) x = hash_bytes(x, ptr, size)
  HASH(workspace.before, GUARD); HASH(workspace.after, GUARD);
  HASH(query.before, GUARD); HASH(query.after, GUARD);
  HASH(output.before, GUARD); HASH(output.after, GUARD);
  HASH(f16_probe_buffer.before, GUARD); HASH(f16_probe_buffer.after, GUARD);
  for (unsigned h = 0; h < AKV_MAX_Q_ROWS; ++h) {
    const unsigned start = h < HEADS ? DIM : 0;
    HASH(workspace.value.accumulator[h] + start,
         (AKV_HEAD_DIM_256 - start) * sizeof(uint16_t));
    if (h >= HEADS) {
      HASH(workspace.value.score[h], sizeof(workspace.value.score[h]));
      HASH(&workspace.value.maximum[h], sizeof(float));
      HASH(&workspace.value.sum[h], sizeof(float));
      HASH(&workspace.value.old_scale[h], sizeof(float));
    }
  }
#undef HASH
  return x;
}

static int filled(const void *p, size_t n) {
  const unsigned char *b = p;
  for (size_t i = 0; i < n; ++i) if (b[i] != 0xa5) return 0;
  return 1;
}

static int guards(void) {
  int ok = filled(workspace.before, GUARD) && filled(workspace.after, GUARD) &&
      filled(query.before, GUARD) && filled(query.after, GUARD) &&
      filled(output.before, GUARD) && filled(output.after, GUARD);
  for (unsigned i = 0; i < GUARD; ++i)
    ok &= f16_probe_buffer.before[i] == 0xa5 && f16_probe_buffer.after[i] == 0xa5;
  for (unsigned h = 0; h < AKV_MAX_Q_ROWS; ++h) {
    const unsigned start = h < HEADS ? DIM : 0;
    ok &= filled(workspace.value.accumulator[h] + start,
                 (AKV_HEAD_DIM_256 - start) * sizeof(uint16_t));
    if (h >= HEADS) {
      ok &= filled(workspace.value.score[h], sizeof(workspace.value.score[h]));
      ok &= filled(&workspace.value.maximum[h], sizeof(float));
      ok &= filled(&workspace.value.sum[h], sizeof(float));
      ok &= filled(&workspace.value.old_scale[h], sizeof(float));
    }
  }
  return ok;
}

static akv_status_t execute_group(void *context, const akv_attention_plan_t *plan,
                                  uint32_t batch, uint32_t first_head) {
  if (batch || first_head) return AKV_STATUS_SHAPE;
  return *(const int *)context ? f16_profile_execute(plan, &workspace.value) :
      akv_attention_execute_v2_native(plan, &workspace.value);
}

static __attribute__((noinline)) akv_status_t full_call(int profile, uint64_t *groups) {
  /* Conversion is inside the total ROI, in captured head/dimension order. */
  for (unsigned i = 0; i < HEADS * DIM; ++i) {
    uint32_t bits;
    __asm__ volatile("fcvt.h.s ft0, %1\nfmv.x.h %0, ft0"
                     : "=r"(bits) : "f"(decode_query[i]) : "ft0");
    query.value[i] = (uint16_t)bits;
  }
  akv_device_t device;
  akv_status_t status = akv_device_query(akv_native_info, NULL, &device);
  if (status != AKV_STATUS_OK || device.capabilities.token_axis_tile_tokens != 64)
    return AKV_STATUS_CAPABILITY;
  const akv_decode_problem_t problem = {
      .query = query.value, .key = decode_key, .value = decode_value,
      .mask = decode_mask, .output = output.value,
      .query_bytes = sizeof(query.value), .key_bytes = sizeof(decode_key),
      .value_bytes = sizeof(decode_value), .mask_bytes = sizeof(decode_mask),
      .output_bytes = sizeof(output.value),
      .q_head_stride = DIM * 2, .q_batch_stride = HEADS * DIM * 2,
      .k_token_stride = DIM * 2, .k_head_stride = CAPACITY * DIM * 2,
      .k_batch_stride = CAPACITY * DIM * 2,
      .v_token_stride = DIM * 2, .v_head_stride = CAPACITY * DIM * 2,
      .v_batch_stride = CAPACITY * DIM * 2, .mask_batch_stride = 0,
      .output_head_stride = DIM * 4, .output_batch_stride = HEADS * DIM * 4,
      .batches = 1, .query_heads = HEADS, .kv_heads = 1,
      .kv_length = TOKENS, .head_dim = DIM, .scale = 0x1.6a09e6p-4f,
  };
  return akv_decode_execute(&device, &problem, execute_group, &profile, groups);
}

static int near(float actual, float expected, float atol, float rtol) {
  float diff = actual - expected;
  if (diff < 0) diff = -diff;
  if (expected < 0) expected = -expected;
  return diff <= atol + rtol * expected;
}

int main(void) {
  const int order[F16_TRIALS] = {0, 1, 1, 0};
  uint64_t vlenb;
  __asm__ volatile("csrr %0, vlenb\nvsetivli zero, 1, e32, m1, ta, ma\nvmv.v.i v0, 0"
                   : "=r"(vlenb) : : "v0", "memory");
  drain();
  if (vlenb != 128) { printf("CHAIN_F16_FAIL vlenb=%lu\n", vlenb); return 1; }
  const uint64_t original_hash = hash_data();
  uint64_t errors = 0;
  for (unsigned trial = 0; trial < F16_TRIALS; ++trial) {
    memset(&workspace, 0xa5, sizeof(workspace));
    memset(&query, 0xa5, sizeof(query));
    memset(&output, 0xa5, sizeof(output));
    for (unsigned i = 0; i < GUARD; ++i)
      f16_probe_buffer.before[i] = f16_probe_buffer.after[i] = 0xa5;
    for (unsigned i = 0; i < F16_SPANS; ++i) f16_spans[i] = (f16_span_t){0, 0};
    drain();
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0" : : : "memory");
    results[trial].begin = cycles();
    const akv_status_t status = full_call(order[trial], &results[trial].groups);
    results[trial].returned = cycles();
    drain();
    results[trial].end = cycles();
    __asm__ volatile("frcsr %0\ncsrr %1, vcsr\ncsrr %2, vstart"
        : "=r"(results[trial].fcsr), "=r"(results[trial].vcsr),
          "=r"(results[trial].vstart) : : "memory");
    uint64_t bad = status != AKV_STATUS_OK || results[trial].groups != 1 ||
        !guards() || hash_data() != original_hash ||
        memcmp(query.value, decode_query_f16, sizeof(query.value)) != 0;
    bad += (results[trial].fcsr & ~UINT64_C(3)) != 0 ||
           results[trial].vcsr != 0 || results[trial].vstart != 0;
    for (unsigned i = 0; i < HEADS * DIM; ++i) {
      memcpy(&results[trial].bits[i], &output.value[i], sizeof(uint32_t));
      bad += !near(output.value[i], decode_golden[i], 0.003f, 0.02f);
      bad += !near(output.value[i], native_golden[i], 0.0002f, 0.003f);
    }
    if (trial) bad += memcmp(results[trial].bits, results[0].bits,
                            sizeof(results[trial].bits)) != 0 ||
                     results[trial].fcsr != results[0].fcsr;
    for (unsigned i = 0; i < F16_SPANS; ++i) results[trial].spans[i] = f16_spans[i];
    results[trial].data_hash = hash_data();
    results[trial].query_hash = hash_bytes(UINT64_C(14695981039346656037), query.value, sizeof(query.value));
    results[trial].guard_hash = hash_guards();
    results[trial].errors = bad;
    errors += bad;
  }

  /* Calibrate the identical stamps/stores, separately from real work. */
  uint64_t calibration[8], stamp_cost[8][F16_SPANS];
  for (unsigned sample = 0; sample < 8; ++sample) {
    drain();
    const uint64_t begin = cycles();
    for (unsigned i = 0; i < F16_SPANS; ++i) { F16_BEGIN(i); F16_END(i); }
    __asm__ volatile("fence rw, rw" : : : "memory");
    calibration[sample] = cycles() - begin;
    for (unsigned i = 0; i < F16_SPANS; ++i)
      stamp_cost[sample][i] = f16_spans[i].after - f16_spans[i].before;
  }
  errors += !guards() || hash_data() != original_hash;
  printf("CHAIN_F16_SHAPE d=128 qheads=2 kvheads=1 tokens=137 capacity=256 tile=64 vlenb=%lu\n", vlenb);
  for (unsigned trial = 0; trial < F16_TRIALS; ++trial) {
    printf("CHAIN_F16_TRIAL trial=%u profile=%d begin=%lu returned=%lu end=%lu fcsr=%lu vcsr=%lu vstart=%lu groups=%lu errors=%lu\n",
        trial, order[trial], results[trial].begin, results[trial].returned,
        results[trial].end, results[trial].fcsr, results[trial].vcsr,
        results[trial].vstart, results[trial].groups, results[trial].errors);
    printf("CHAIN_F16_MEMORY trial=%u data_hash=%016lx query_hash=%016lx guard_hash=%016lx guard_bytes=%lu\n",
        trial, results[trial].data_hash, results[trial].query_hash, results[trial].guard_hash,
        (unsigned long)guard_bytes);
    for (unsigned i = 0; i < F16_SPANS; ++i)
      printf("CHAIN_F16_SPAN trial=%u slot=%u before=%lu after=%lu\n", trial, i,
             results[trial].spans[i].before, results[trial].spans[i].after);
    for (unsigned i = 0; i < HEADS * DIM; ++i)
      printf("CHAIN_F16_OUT trial=%u index=%u bits=%08x\n", trial, i, results[trial].bits[i]);
  }
  for (unsigned s = 0; s < 8; ++s) {
    printf("CHAIN_F16_CAL sample=%u total=%lu\n", s, calibration[s]);
    for (unsigned i = 0; i < F16_SPANS; ++i)
      printf("CHAIN_F16_EMPTY sample=%u slot=%u cycles=%lu\n", s, i, stamp_cost[s][i]);
  }
  printf("CHAIN_F16_DONE trials=4 errors=%lu\n", errors);
  return errors != 0;
}
