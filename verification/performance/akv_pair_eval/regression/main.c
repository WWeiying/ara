#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "expected.h"

enum { DIM = 64, HEADS = 3, TOKENS = 5, CAPACITY = 256, GUARD = 64, TRIALS = 4 };
_Static_assert(AKV_V2_TILE_TOKENS == 64 && AKV_MAX_Q_ROWS == 8, "Workspace geometry");
_Static_assert(sizeof(akv_attention_v2_workspace_t) == 6272, "Workspace padding");
extern const float decode_query[HEADS*DIM], decode_golden[HEADS*DIM], native_golden[HEADS*DIM];
extern const uint16_t decode_query_f16[HEADS*DIM], decode_key[CAPACITY*DIM];
extern const uint16_t decode_value[CAPACITY*DIM], decode_mask[CAPACITY];
extern const unsigned char data_begin[], data_end[], data_guard_before[], data_guard_after[];
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD];
  akv_attention_v2_workspace_t value;
  unsigned char after[GUARD];
} workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD];
  uint16_t value[HEADS*DIM];
  unsigned char after[GUARD];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD];
  float value[HEADS*DIM];
  unsigned char after[GUARD];
} output;
static struct {
  uint64_t begin, returned, end, fcsr, vcsr, vstart, groups, errors;
  uint64_t initial_fcsr, initial_vcsr, initial_vstart, query_hash, guard_hash;
  uint32_t bits[HEADS*DIM];
} results[TRIALS];
static volatile unsigned selected_arm;

char *getenv(const char *name) {
  if (name != NULL && strcmp(name, "AKV_PAIR_HEADS") == 0)
    return selected_arm ? "1" : "0";
  return NULL;
}

#ifdef AKV_SMOL_HOST_TEST
/* These hooks test the firmware/checker only, not the native ISA or cycles. */
extern uint64_t smol_host_cycles(void), smol_host_initialize(void);
extern void smol_host_drain(void), smol_host_reset(void);
extern void smol_host_csr(uint64_t *, uint64_t *, uint64_t *);
static uint64_t cycles(void) { return smol_host_cycles(); }
static uint64_t initialize(void) { return smol_host_initialize(); }
static void drain(void) { smol_host_drain(); }
static void reset_csr(void) { smol_host_reset(); }
static void read_csr(uint64_t *f, uint64_t *v, uint64_t *s) { smol_host_csr(f, v, s); }
#else
static inline uint64_t cycles(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
  return value;
}
static inline uint64_t initialize(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, vlenb\nvsetivli zero, 1, e32, m1, ta, ma\nvmv.v.i v0, 0"
                   : "=r"(value) : : "v0", "memory");
  return value;
}
static inline void drain(void) {
  uintptr_t value;
  __asm__ volatile("vmv.x.s %0, v0\nfence rw, rw" : "=r"(value) : : "memory");
}
static inline void reset_csr(void) {
  __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0" : : : "memory");
}
static inline void read_csr(uint64_t *f, uint64_t *v, uint64_t *s) {
  __asm__ volatile("frcsr %0\ncsrr %1, vcsr\ncsrr %2, vstart"
                   : "=r"(*f), "=r"(*v), "=r"(*s) : : "memory");
}
#endif

static uint64_t hash_bytes(uint64_t hash, const volatile void *ptr, size_t count) {
  const volatile unsigned char *p = ptr;
  for (size_t i = 0; i < count; ++i) hash = (hash ^ p[i])*UINT64_C(1099511628211);
  return hash;
}
static uint64_t fingerprint(const volatile void *ptr, size_t count) {
  return hash_bytes(UINT64_C(14695981039346656037), ptr, count);
}

static uint64_t guards(void) {
  uint64_t hash = UINT64_C(14695981039346656037);
#define HASH(ptr, count) hash = hash_bytes(hash, ptr, count)
  HASH(workspace.before, GUARD); HASH(workspace.after, GUARD);
  HASH(query.before, GUARD); HASH(query.after, GUARD);
  HASH(output.before, GUARD); HASH(output.after, GUARD);
  HASH(data_guard_before, GUARD); HASH(data_guard_after, GUARD);
  for (unsigned h = 0; h < AKV_MAX_Q_ROWS; ++h) {
    const unsigned dimension = h < HEADS ? DIM : 0;
    const unsigned tokens = h < HEADS ? TOKENS : 0;
    HASH(workspace.value.accumulator[h]+dimension, (AKV_HEAD_DIM_256-dimension)*2);
    HASH(workspace.value.score[h]+tokens, (AKV_V2_TILE_TOKENS-tokens)*4);
    if (h >= HEADS) {
      HASH(&workspace.value.maximum[h], sizeof(float));
      HASH(&workspace.value.sum[h], sizeof(float));
      HASH(&workspace.value.old_scale[h], sizeof(float));
    }
  }
  const size_t tail = offsetof(akv_attention_v2_workspace_t, old_scale)+sizeof(workspace.value.old_scale);
  HASH((const unsigned char *)&workspace.value+tail, sizeof(workspace.value)-tail);
#undef HASH
  return hash;
}

static akv_status_t execute_group(void *context, const akv_attention_plan_t *plan,
                                  uint32_t batch, uint32_t first_head) {
  (void)context;
  if (batch || first_head) return AKV_STATUS_SHAPE;
  return akv_attention_execute_v2_native(plan, &workspace.value);
}

static __attribute__((noinline)) akv_status_t full_call(uint64_t *groups) {
  for (unsigned i = 0; i < HEADS*DIM; ++i) {
#ifdef AKV_SMOL_HOST_TEST
    _Float16 value = (_Float16)decode_query[i];
    memcpy(&query.value[i], &value, sizeof(value));
#else
    uintptr_t bits;
    __asm__ volatile("fcvt.h.s ft0, %1\nfmv.x.h %0, ft0"
                     : "=r"(bits) : "f"(decode_query[i]) : "ft0");
    query.value[i] = (uint16_t)bits;
#endif
  }
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device) != AKV_STATUS_OK ||
      device.capabilities.token_axis_tile_tokens != 64)
    return AKV_STATUS_CAPABILITY;
  const akv_decode_problem_t problem = {
      .query=query.value, .key=decode_key, .value=decode_value,
      .mask=decode_mask, .output=output.value,
      .query_bytes=sizeof(query.value), .key_bytes=sizeof(decode_key),
      .value_bytes=sizeof(decode_value), .mask_bytes=sizeof(decode_mask),
      .output_bytes=sizeof(output.value),
      .q_head_stride=DIM*2, .q_batch_stride=HEADS*DIM*2,
      .k_token_stride=DIM*2, .k_head_stride=CAPACITY*DIM*2, .k_batch_stride=CAPACITY*DIM*2,
      .v_token_stride=DIM*2, .v_head_stride=CAPACITY*DIM*2, .v_batch_stride=CAPACITY*DIM*2,
      .mask_batch_stride=0, .output_head_stride=DIM*4, .output_batch_stride=HEADS*DIM*4,
      .batches=1, .query_heads=HEADS, .kv_heads=1, .kv_length=TOKENS,
      .head_dim=DIM, .scale=0.125f,
  };
  return akv_decode_execute(&device, &problem, execute_group, NULL, groups);
}

static int near(float actual, float expected, float atol, float rtol) {
  float difference = actual-expected;
  if (difference < 0) difference = -difference;
  if (expected < 0) expected = -expected;
  return difference <= atol+rtol*expected;
}

int main(void) {
  static const unsigned order[TRIALS] = {0, 1, 1, 0};
  const uint64_t vlenb = initialize();
  drain();
  if (vlenb != 128) { printf("AKV_SMOL_FAIL vlenb=%lu\n", vlenb); return 1; }
  uint64_t errors = 0;
  for (unsigned t = 0; t < TRIALS; ++t) {
    selected_arm = order[t];
    memset(&workspace, 0xa5, sizeof(workspace));
    memset(&query, 0xa5, sizeof(query));
    memset(&output, 0xa5, sizeof(output));
    drain();
    reset_csr();
    read_csr(&results[t].initial_fcsr, &results[t].initial_vcsr, &results[t].initial_vstart);
    results[t].begin = cycles();
    const akv_status_t status = full_call(&results[t].groups);
    results[t].returned = cycles();
    drain();
    results[t].end = cycles();
    read_csr(&results[t].fcsr, &results[t].vcsr, &results[t].vstart);
    results[t].query_hash = fingerprint(query.value, sizeof(query.value));
    results[t].guard_hash = guards();
    uint64_t bad = status != AKV_STATUS_OK || results[t].groups != 1 ||
        results[t].initial_fcsr || results[t].initial_vcsr || results[t].initial_vstart ||
        (results[t].fcsr & ~UINT64_C(3)) || results[t].vcsr || results[t].vstart ||
        results[t].query_hash != SMOL_EXPECT_QUERY_HASH ||
        results[t].guard_hash != SMOL_EXPECT_GUARD_HASH ||
        memcmp(query.value, decode_query_f16, sizeof(query.value)) != 0;
    for (unsigned i = 0; i < HEADS*DIM; ++i) {
      memcpy(&results[t].bits[i], &output.value[i], sizeof(uint32_t));
      bad += !near(output.value[i], decode_golden[i], 0.003f, 0.02f);
      bad += !near(output.value[i], native_golden[i], 0.0002f, 0.003f);
    }
    if (t) bad += memcmp(results[t].bits, results[0].bits, sizeof(results[t].bits)) != 0 ||
                  results[t].fcsr != results[0].fcsr || results[t].vcsr != results[0].vcsr ||
                  results[t].vstart != results[0].vstart;
    results[t].errors = bad;
    errors += bad;
  }
  /* Read the full capacity256 selected payloads only after all four ROIs. */
  const uint64_t data_bytes = (uintptr_t)data_end-(uintptr_t)data_begin;
  const uint64_t data_hash = fingerprint(data_begin, data_bytes);
  const uint64_t q_hash = fingerprint(decode_query, sizeof(decode_query));
  const uint64_t k_hash = fingerprint(decode_key, sizeof(decode_key));
  const uint64_t v_hash = fingerprint(decode_value, sizeof(decode_value));
  const uint64_t m_hash = fingerprint(decode_mask, sizeof(decode_mask));
  const uint64_t data_errors = data_bytes != SMOL_EXPECT_DATA_BYTES || data_hash != SMOL_EXPECT_DATA_HASH ||
      q_hash != SMOL_EXPECT_QUERY_F32_HASH || k_hash != SMOL_EXPECT_KEY_HASH ||
      v_hash != SMOL_EXPECT_VALUE_HASH || m_hash != SMOL_EXPECT_MASK_HASH;
  errors += data_errors;
  printf("AKV_SMOL_SHAPE d=64 qheads=3 kvheads=1 tokens=5 capacity=256 tile=64 vlenb=%lu\n", vlenb);
  for (unsigned t = 0; t < TRIALS; ++t) {
    printf("AKV_SMOL_TRIAL trial=%u arm=%u begin=%lu returned=%lu end=%lu fcsr=%lu vcsr=%lu vstart=%lu initial_fcsr=%lu initial_vcsr=%lu initial_vstart=%lu groups=%lu errors=%lu\n",
        t, order[t], results[t].begin, results[t].returned, results[t].end, results[t].fcsr,
        results[t].vcsr, results[t].vstart, results[t].initial_fcsr, results[t].initial_vcsr,
        results[t].initial_vstart, results[t].groups, results[t].errors);
    printf("AKV_SMOL_MEMORY trial=%u query_hash=%016lx guard_hash=%016lx guard_bytes=%lu\n",
        t, results[t].query_hash, results[t].guard_hash, (unsigned long)SMOL_EXPECT_GUARD_BYTES);
    for (unsigned i = 0; i < HEADS*DIM; ++i)
      printf("AKV_SMOL_OUT trial=%u index=%u bits=%08x\n", t, i, results[t].bits[i]);
  }
  printf("AKV_SMOL_DATA data_hash=%016lx data_bytes=%lu query_f32_hash=%016lx key_hash=%016lx value_hash=%016lx mask_hash=%016lx checks=1 errors=%lu\n",
      data_hash, data_bytes, q_hash, k_hash, v_hash, m_hash, data_errors);
  printf("AKV_SMOL_DONE trials=4 errors=%lu\n", errors);
  return errors != 0;
}
