#include "qbs/qbs.h"
#include "printf.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

extern void quantize_row_q8_0(const float *, void *, int64_t);
extern const float quant_query0_f32[], quant_query1_f32[];
extern const unsigned char quant_key0[], quant_key1[];

static struct __attribute__((aligned(64))) {
  unsigned char before[64], data[12][136], after[64];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[64]; float data[4][32]; unsigned char after[64];
} scores;
static qbs_descriptor_t descriptor __attribute__((aligned(64)));

static uint32_t bits(float value) {
  uint32_t result;
  memcpy(&result, &value, 4);
  return result;
}

static void snapshot(uintptr_t *fc, uintptr_t *vc) {
  uintptr_t drain;
  __asm__ volatile("vmv.x.s %0,v12\nfence rw,rw\nfrcsr %1\ncsrr %2,vcsr"
      : "=&r"(drain), "=&r"(*fc), "=&r"(*vc) : : "memory");
  (void)drain;
}

static unsigned guard_errors(void) {
  unsigned errors = 0;
  for (unsigned i = 0; i < 64; ++i)
    errors += query.before[i] != 0xa5 || query.after[i] != 0xa5 ||
              scores.before[i] != 0xa5 || scores.after[i] != 0xa5;
  return errors;
}

static unsigned execute(unsigned kind, unsigned kv_head, unsigned first_q,
                        unsigned m, unsigned first_token, unsigned n,
                        const unsigned char *keys, unsigned *sequence,
                        unsigned *outputs) {
  const unsigned row_bytes = kind ? 72 : 136;
  const unsigned char *weight = keys + (kv_head * 256 + first_token) * row_bytes;
  qbs_descriptor_fields_t fields = {0};
  fields.descriptor_version = QBS_DESCRIPTOR_VERSION;
  fields.weight_profile = kind ? QBS_WEIGHT_PROFILE_Q4_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
  fields.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
  fields.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
  fields.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  fields.n = n;
  fields.k_blocks = 4;
  fields.activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = (uintptr_t)weight;
  memset(&scores, 0xa5, sizeof(scores));
  __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
  const qbs_status_t status = qbs_native_execute_command(NULL, &descriptor, m,
      query.data[first_q], &scores.data[0][0], 32, n, 0);
  uintptr_t fc, vc;
  snapshot(&fc, &vc);
  unsigned errors = status != QBS_STATUS_OK || fc > 31 || vc != 5 || guard_errors();
  for (unsigned row = 0; row < 4; ++row)
    for (unsigned column = 0; column < 32; ++column) {
      const uint32_t value = bits(scores.data[row][column]);
      if (row < m && column < n)
        errors += (value & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000);
      else
        errors += value != UINT32_C(0xa5a5a5a5);
    }
  printf("QUANT_QK_BATCH_SCORE seq=%u kind=%u kv_head=%u first_q=%u m=%u first_token=%u n=%u fcsr=%lu vcsr=5 errors=%u hex=",
      ++*sequence, kind, kv_head, first_q, m, first_token, n, (unsigned long)fc, errors);
  for (unsigned row = 0; row < m; ++row)
    for (unsigned column = 0; column < n; ++column)
      printf("%08x", bits(scores.data[row][column]));
  printf("\n");
  *outputs += m * n;
  return errors;
}

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128 || qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK ||
      !(device.weight_profiles & (1u << QBS_WEIGHT_PROFILE_Q8_0_WEIGHT)) ||
      !(device.weight_profiles & (1u << QBS_WEIGHT_PROFILE_Q4_0))) return 1;
  const float *const inputs[] = {quant_query0_f32, quant_query1_f32};
  const unsigned char *const keys[] = {quant_key0, quant_key1};
  unsigned sequence = 0, outputs = 0;
  printf("QUANT_QK_BATCH_CAP profiles=2 d=128 query_heads=12 kv_heads=2 visible=128 capacity=256 commands=40 outputs=3336\n");
  for (unsigned kind = 0; kind < 2; ++kind) {
    memset(&query, 0xa5, sizeof(query));
    for (unsigned head = 0; head < 12; ++head) {
      __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
      quantize_row_q8_0(inputs[kind] + head * 128, query.data[head], 128);
      uintptr_t fc, vc;
      snapshot(&fc, &vc);
      if (fc > 31 || vc != 5) return 1;
      printf("QUANT_QK_BATCH_QUERY kind=%u head=%u bytes=136 fcsr=%lu vcsr=5 hex=",
          kind, head, (unsigned long)fc);
      for (unsigned byte = 0; byte < 136; ++byte) printf("%02x", query.data[head][byte]);
      printf("\n");
    }
    for (unsigned kv_head = 0; kv_head < 2; ++kv_head) {
      for (unsigned start = 0; start < 6; start += 4) {
        const unsigned m = start ? 2 : 4;
        for (unsigned token = 0; token < 128; token += 32)
          if (execute(kind, kv_head, kv_head * 6 + start, m, token, 32,
                      keys[kind], &sequence, &outputs)) return 1;
      }
      /* N31 stops at token62; N1 starts at token64. Neither reads a hidden row. */
      if (execute(kind, kv_head, kv_head * 6 + 4, 2, 32, 31,
                  keys[kind], &sequence, &outputs) ||
          execute(kind, kv_head, kv_head * 6, 4, 64, 1,
                  keys[kind], &sequence, &outputs)) return 1;
    }
  }
  if (sequence != 40 || outputs != 3336) return 1;
  printf("QUANT_QK_BATCH_SUITE_PASS commands=40 outputs=3336 guards=1 inactive_memory=1 deployment_accepted=0\n");
  return 0;
}
