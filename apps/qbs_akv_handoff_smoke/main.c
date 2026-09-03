#include <stddef.h>
#include <stdint.h>

#include "akv_abi.h"
#include "printf.h"
#include "qbs_abi.h"

typedef struct {
  uint16_t d;
  uint16_t dmin;
  uint8_t scales[12];
  uint8_t qs[128];
} qbs_block_q4_k_t;

typedef struct {
  float d;
  int8_t qs[256];
  int16_t bsums[16];
} qbs_block_q8_k_t;

_Static_assert(sizeof(qbs_block_q4_k_t) == QBS_Q4_K_BLOCK_BYTES,
               "invalid Q4_K block size");
_Static_assert(sizeof(qbs_block_q8_k_t) == QBS_Q8_K_BLOCK_BYTES,
               "invalid Q8_K block size");

#define SEQ16(base_)                                                        \
  (base_) + 0, (base_) + 1, (base_) + 2, (base_) + 3, (base_) + 4,         \
      (base_) + 5, (base_) + 6, (base_) + 7, (base_) + 8, (base_) + 9,     \
      (base_) + 10, (base_) + 11, (base_) + 12, (base_) + 13,              \
      (base_) + 14, (base_) + 15

#define ROW64(base_)                                                        \
  SEQ16((base_) + 0), SEQ16((base_) + 16), SEQ16((base_) + 32),            \
      SEQ16((base_) + 48)

#define Q4_BLOCK(value_)                                                    \
  {                                                                         \
      .d = 0x3c00u, .dmin = 0,                                              \
      .scales = {[0 ... 3] = 1, [8 ... 11] = 1},                            \
      .qs = {[0 ... 127] = (uint8_t)(((value_) << 4) | (value_))},           \
  }

#define Q8_BLOCK(value_)                                                    \
  {                                                                         \
      .d = 1.0f, .qs = {[0 ... 255] = (int8_t)(value_)},                    \
      .bsums = {[0 ... 15] = (int16_t)(16 * (value_))},                     \
  }

static const qbs_block_q4_k_t qbs_weights[3]
    __attribute__((aligned(64))) = {
        Q4_BLOCK(1), Q4_BLOCK(2), Q4_BLOCK(3)};
static const qbs_block_q8_k_t qbs_activation
    __attribute__((aligned(64))) = Q8_BLOCK(1);
static qbs_descriptor_t qbs_descriptor __attribute__((aligned(64)));
static uint32_t qbs_observed[32] __attribute__((aligned(64)));

static const uint16_t akv_query[2][64] __attribute__((aligned(64))) = {
    {ROW64(0x1000)}, {ROW64(0x1200)}};
static const uint16_t akv_key[3][64] __attribute__((aligned(64))) = {
    {ROW64(0x2000)}, {ROW64(0x2200)}, {ROW64(0x2400)}};
static const uint16_t akv_value[3][64] __attribute__((aligned(64))) = {
    {ROW64(0x3000)}, {ROW64(0x3200)}, {ROW64(0x3400)}};
static akv_descriptor_t akv_descriptor __attribute__((aligned(64)));
static uint16_t akv_observed[64] __attribute__((aligned(64)));

static uint32_t rvv_source[32] __attribute__((aligned(64)));
static uint32_t rvv_observed[32] __attribute__((aligned(64)));

static volatile uint64_t trap_count;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_tval;

void __attribute__((naked, used)) mtvec_handler(void) {
  asm volatile("csrr t0, mcause\n"
               "la t1, trap_cause\n"
               "sd t0, 0(t1)\n"
               "csrr t0, mtval\n"
               "la t1, trap_tval\n"
               "sd t0, 0(t1)\n"
               "la t1, trap_count\n"
               "ld t0, 0(t1)\n"
               "addi t0, t0, 1\n"
               "sd t0, 0(t1)\n"
               "csrr t0, mepc\n"
               "addi t0, t0, 4\n"
               "csrw mepc, t0\n"
               "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(mtvec_handler) : "memory");
}

static uint64_t issue_qbinfo(uint64_t index) {
  register uint64_t a0 asm("a0") = index;
  asm volatile(".word 0x0005155b" : "+r"(a0) : : "memory");
  return a0;
}

static uint64_t issue_akvinfo(uint64_t index) {
  register uint64_t a0 asm("a0") = index;
  asm volatile(".word 0x0005455b" : "+r"(a0) : : "memory");
  return a0;
}

static void issue_qbs_m1(int store_result) {
  register uintptr_t a0 asm("a0") = (uintptr_t)&qbs_descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)&qbs_activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)qbs_observed;

  if (store_result) {
    asm volatile("li t0, 32\n"
                 "vsetvli zero, t0, e32, m1, ta, ma\n"
                 ".word 0x00b5045b\n"
                 "vse32.v v8, (a2)\n"
                 : "+r"(a0), "+r"(a1), "+r"(a2)
                 :
                 : "t0", "v8", "memory");
  } else {
    asm volatile("li t0, 32\n"
                 "vsetvli zero, t0, e32, m1, ta, ma\n"
                 ".word 0x00b5045b\n"
                 : "+r"(a0), "+r"(a1)
                 :
                 : "t0", "v8", "memory");
  }
}

static void issue_akv_v2_full(void) {
  register uintptr_t a0 asm("a0") = (uintptr_t)&akv_descriptor;
  register uint64_t a1 asm("a1") = 0;
  asm volatile("fence rw, rw\n.word 0x00b5605b"
               : "+r"(a0), "+r"(a1)
               :
               : "memory");
}

static void issue_akv_load_d64(uint32_t selector) {
  register uint64_t a0 asm("a0") = selector;
  register uintptr_t a1 asm("a1") = (uintptr_t)akv_observed;
  asm volatile("li t0, 64\n"
               "vsetvli zero, t0, e16, m1, ta, ma\n"
               ".word 0x0005345b\n"
               "vse16.v v8, (a1)\n"
               : "+r"(a0), "+r"(a1)
               :
               : "t0", "v8", "memory");
}

static void issue_akv_release(void) {
  asm volatile(".word 0x0000505b" : : : "memory");
}

static int check_no_trap(const char *stage, uint64_t before) {
  if (trap_count == before) return 0;
  printf("%s trapped: count=%ld cause=%lx tval=%lx\n", stage,
         trap_count - before, trap_cause, trap_tval);
  return 1;
}

static int check_u16(const char *stage, const uint16_t *expected) {
  for (size_t index = 0; index < 64; ++index) {
    if (akv_observed[index] != expected[index]) {
      printf("%s mismatch[%d]: got=%x expected=%x\n", stage, (int)index,
             akv_observed[index], expected[index]);
      return 1;
    }
  }
  return 0;
}

static int check_qbs(void) {
  static const uint32_t expected_results[3] = {
      0x43800000u, 0x44000000u, 0x44400000u};
  const uint64_t before = trap_count;
  issue_qbs_m1(1);
  if (check_no_trap("QBS", before)) return 1;

  int failures = 0;
  for (size_t index = 0; index < 3; ++index) {
    const uint32_t expected = expected_results[index];
    if (qbs_observed[index] != expected) {
      printf("QBS mismatch[%d]: got=%x expected=%x\n", (int)index,
             qbs_observed[index], expected);
      ++failures;
    }
  }
  for (size_t index = 3; index < 32; ++index) {
    if (qbs_observed[index] != 0) {
      printf("QBS tail mismatch[%d]: got=%x\n", (int)index,
             qbs_observed[index]);
      ++failures;
      break;
    }
  }
  return failures;
}

static int check_rvv(uint32_t seed) {
  for (size_t index = 0; index < 32; ++index) {
    rvv_source[index] = seed + (uint32_t)index * 3u;
    rvv_observed[index] = 0;
  }

  register uintptr_t a0 asm("a0") = (uintptr_t)rvv_source;
  register uintptr_t a1 asm("a1") = (uintptr_t)rvv_observed;
  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vle32.v v16, (a0)\n"
               "vadd.vi v16, v16, 1\n"
               "vse32.v v16, (a1)\n"
               : "+r"(a0), "+r"(a1)
               :
               : "t0", "v16", "memory");

  for (size_t index = 0; index < 32; ++index) {
    const uint32_t expected = rvv_source[index] + 1u;
    if (rvv_observed[index] != expected) {
      printf("RVV mismatch[%d]: got=%x expected=%x\n", (int)index,
             rvv_observed[index], expected);
      return 1;
    }
  }
  return 0;
}

static int check_akv_v2(void) {
  int failures = 0;
  const uint64_t before = trap_count;
  issue_akv_v2_full();
  if (check_no_trap("AKV-v2 FULL", before)) return 1;

  issue_akv_load_d64(akv_v2_selector(AKV_STREAM_Q, 1));
  failures += check_no_trap("AKV-v2 Q load", before);
  failures += check_u16("AKV-v2 Q1", akv_query[1]);

  issue_akv_load_d64(akv_v2_selector(AKV_STREAM_K, 2));
  failures += check_no_trap("AKV-v2 K load", before);
  failures += check_u16("AKV-v2 K2", akv_key[2]);

  issue_akv_load_d64(akv_v2_selector(AKV_STREAM_V, 0));
  failures += check_no_trap("AKV-v2 V load", before);
  failures += check_u16("AKV-v2 V0", akv_value[0]);

  issue_akv_release();
  failures += check_no_trap("AKV-v2 RELEASE", before);
  return failures;
}

static void initialize_descriptors(void) {
  const qbs_descriptor_fields_t qbs_fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = 3,
      .k_blocks = 1,
  };
  qbs_descriptor = (qbs_descriptor_t){
      .header = qbs_pack_descriptor_header(&qbs_fields),
      .weight_base = (uintptr_t)qbs_weights,
  };

  akv_descriptor = (akv_descriptor_t){
      .version = AKV_DESCRIPTOR_VERSION,
      .element_format = AKV_ELEMENT_FORMAT_F16,
      .q_rows = 2,
      .flags = 0,
      .head_dim = 64,
      .kv_length = 3,
      .q_row_stride_bytes = sizeof(akv_query[0]),
      .k_token_stride_bytes = sizeof(akv_key[0]),
      .v_token_stride_bytes = sizeof(akv_value[0]),
      .reserved0 = 0,
      .q_base = (uintptr_t)akv_query,
      .k_base = (uintptr_t)akv_key,
      .v_base = (uintptr_t)akv_value,
      .reserved1 = 0,
      .reserved2 = 0,
  };
}

int main(void) {
  int failures = 0;
  initialize_descriptors();

  const uint64_t before_qbs_probe = trap_count;
  const uint64_t qbs_capability = issue_qbinfo(0);
  if (trap_count != before_qbs_probe) {
    printf("QBS/AKV handoff smoke: SKIP (QBS disabled)\n");
    return 0;
  }
  if (qbs_capability != qbs_capability_word(0, VLEN)) ++failures;

  const uint64_t before_akv_probe = trap_count;
  const uint64_t akv_capability = issue_akvinfo(2);
  if (trap_count != before_akv_probe) {
    printf("QBS/AKV handoff smoke: SKIP (AKV-v2 disabled)\n");
    return 0;
  }
  if (akv_capability != akv_v2_capability_word(2, 1)) ++failures;

  failures += check_rvv(0x1000u);
  failures += check_qbs();

  // These two commands are adjacent at the architectural stream. They test
  // direct QBS-to-AKV ownership transfer without an intervening normal VLSU
  // request; the first QBS result is intentionally discarded.
  uint64_t before = trap_count;
  issue_qbs_m1(0);
  issue_akv_v2_full();
  failures += check_no_trap("QBS-to-AKV", before);
  issue_akv_load_d64(akv_v2_selector(AKV_STREAM_K, 1));
  failures += check_u16("QBS-to-AKV K1", akv_key[1]);
  issue_akv_release();

  failures += check_rvv(0x2000u);
  failures += check_akv_v2();

  // RELEASE followed immediately by qbexec exercises the reverse ownership
  // direction. A final normal vector request checks that neither client left
  // MMU, AXI, or result routing state behind.
  before = trap_count;
  issue_akv_v2_full();
  issue_akv_release();
  issue_qbs_m1(0);
  failures += check_no_trap("AKV-to-QBS", before);

  failures += check_qbs();
  failures += check_rvv(0x3000u);

  printf("QBS/AKV handoff smoke: %s traps=%ld\n",
         failures == 0 ? "PASS" : "FAIL", trap_count);
  return failures != 0;
}
