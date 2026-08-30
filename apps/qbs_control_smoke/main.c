#include <stddef.h>
#include <stdint.h>

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

static volatile uint64_t trap_count;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_tval;
static volatile uint64_t recovery_store;

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

enum {
  QBINFO_A0_A0 = 0x0005155b,
  QBINFO_RESERVED_A0_A0 = 0x0205155b,
  QBEXEC_M1_V8_A0_A1 = 0x00b5045b,
  QBEXEC_M3_V8_A0_A1 = 0x04b5045b,
};

static uint64_t issue_qbinfo(uint64_t index) {
  register uint64_t a0 asm("a0") = index;
  asm volatile(".word 0x0005155b" : "+r"(a0) : : "memory");
  return a0;
}

static void issue_reserved_qbinfo(uint64_t index) {
  register uint64_t a0 asm("a0") = index;
  asm volatile(".word 0x0205155b" : "+r"(a0) : : "memory");
}

static void issue_qbexec_m1(const qbs_descriptor_t *descriptor,
                            const void *activation,
                            const uint32_t source[32],
                            uint32_t observed[32]) {
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)source;
  register uintptr_t a3 asm("a3") = (uintptr_t)observed;

  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vle32.v v8, (a2)\n"
               ".word 0x00b5045b\n"
               "vse32.v v8, (a3)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
               :
               : "t0", "memory");
}

static void issue_qbexec_m3(const qbs_descriptor_t *descriptor,
                            const void *activation,
                            const uint32_t source[128],
                            uint32_t observed[128]) {
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)source;
  register uintptr_t a3 asm("a3") = (uintptr_t)observed;

  asm volatile("li t0, 128\n"
               "vsetvli zero, t0, e32, m4, ta, ma\n"
               "vle32.v v8, (a2)\n"
               ".word 0x04b5045b\n"
               "vse32.v v8, (a3)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
               :
               : "t0", "memory");
}

static uint32_t fp32_bits(float value) {
  union {
    float f;
    uint32_t u;
  } conversion = {.f = value};
  return conversion.u;
}

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

static qbs_descriptor_t make_descriptor(const void *weights, unsigned n) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = (uint8_t)n,
      .k_blocks = 1,
  };
  const qbs_descriptor_t descriptor = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base = (uintptr_t)weights,
  };
  return descriptor;
}

static int check_encoding_contract(void) {
  int failures = 0;
  if (qbs_encode_qbinfo(10, 10) != QBINFO_A0_A0) {
    printf("qbinfo encoding mismatch: got=0x%x expected=0x%x\n",
           qbs_encode_qbinfo(10, 10), QBINFO_A0_A0);
    ++failures;
  }
  if ((qbs_encode_qbinfo(10, 10) | (1u << 25)) !=
      QBINFO_RESERVED_A0_A0) {
    printf("reserved qbinfo encoding mismatch\n");
    ++failures;
  }
  if (qbs_encode_qbexec(8, 10, 11, 1) != QBEXEC_M1_V8_A0_A1 ||
      qbs_encode_qbexec(8, 10, 11, 3) != QBEXEC_M3_V8_A0_A1) {
    printf("qbexec encoding mismatch\n");
    ++failures;
  }
  return failures;
}

static int check_capabilities(void) {
  static const uint64_t indices[] = {
      0x00, 0x01, 0x11, 0x12, 0x21, 0x22, 0x31, 0x7f,
  };
  int failures = 0;

  for (size_t i = 0; i < sizeof(indices) / sizeof(indices[0]); ++i) {
    const uint64_t before = trap_count;
    const uint64_t observed = issue_qbinfo(indices[i]);
    const uint64_t expected = qbs_capability_word(indices[i], VLEN);
    if (trap_count != before || observed != expected) {
      printf("qbinfo[%lx] failed: traps=%ld got=%lx expected=%lx\n",
             indices[i], trap_count - before, observed, expected);
      ++failures;
    }
  }
  return failures;
}

static int check_m1_execution(void) {
  static const qbs_block_q4_k_t weights[5] __attribute__((aligned(16))) = {
      Q4_BLOCK(1), Q4_BLOCK(2), Q4_BLOCK(3), Q4_BLOCK(4), Q4_BLOCK(5),
  };
  static const qbs_block_q8_k_t activation __attribute__((aligned(16))) =
      Q8_BLOCK(1);
  static const uint32_t source[32] __attribute__((aligned(16))) = {
      [0 ... 31] = 0x7fc00000u,
  };
  static uint32_t observed[32] __attribute__((aligned(16)));
  static qbs_descriptor_t descriptor __attribute__((aligned(16)));
  int failures = 0;

  descriptor = make_descriptor(weights, 5);

  const uint64_t before = trap_count;
  issue_qbexec_m1(&descriptor, &activation, source, observed);
  if (trap_count != before) {
    printf("M1 qbexec trapped: cause=%lx tval=%lx\n", trap_cause, trap_tval);
    return 1;
  }
  for (unsigned index = 0; index < 5; ++index) {
    const uint32_t expected =
        fp32_bits(256.0f * (float)(index + 1));
    if (observed[index] != expected) {
      printf("M1 result[%d] mismatch: got=%x expected=%x\n", (int)index,
             observed[index], expected);
      ++failures;
    }
  }
  if (observed[5] != 0 || observed[31] != 0) {
    printf("M1 tail mismatch: result[5]=%x result[31]=%x\n", observed[5],
           observed[31]);
    ++failures;
  }
  return failures;
}

static int check_m3_execution(void) {
  static const qbs_block_q4_k_t weights[3] __attribute__((aligned(16))) = {
      Q4_BLOCK(1), Q4_BLOCK(2), Q4_BLOCK(3),
  };
  static const qbs_block_q8_k_t activation[3]
      __attribute__((aligned(16))) = {
          Q8_BLOCK(1), Q8_BLOCK(2), Q8_BLOCK(3),
      };
  static const uint32_t source[128] __attribute__((aligned(16))) = {
      [0 ... 127] = 0x3f000000u,
  };
  static uint32_t observed[128] __attribute__((aligned(16)));
  static qbs_descriptor_t descriptor __attribute__((aligned(16)));
  int failures = 0;

  descriptor = make_descriptor(weights, 3);

  const uint64_t before = trap_count;
  issue_qbexec_m3(&descriptor, activation, source, observed);
  if (trap_count != before) {
    printf("M3 qbexec trapped: cause=%lx tval=%lx\n", trap_cause, trap_tval);
    return 1;
  }
  for (unsigned context = 0; context < 3; ++context) {
    for (unsigned output = 0; output < 3; ++output) {
      const unsigned index = context * 32 + output;
      const uint32_t expected = fp32_bits(256.0f * (float)(context + 1) *
                                          (float)(output + 1));
      if (observed[index] != expected) {
        printf("M3 result[%d,%d] mismatch: got=%x expected=%x\n",
               (int)context, (int)output, observed[index], expected);
        ++failures;
      }
    }
    if (observed[context * 32 + 3] != 0 ||
        observed[context * 32 + 31] != 0) {
      printf("M3 tail[%d] mismatch: result[3]=%x result[31]=%x\n",
             (int)context, observed[context * 32 + 3],
             observed[context * 32 + 31]);
      ++failures;
    }
  }
  if (observed[96] != source[96] || observed[127] != source[127]) {
    printf("M3 reserved register changed: result[0]=%x result[31]=%x\n",
           observed[96], observed[127]);
    ++failures;
  }
  return failures;
}

static int check_validation_fault_is_atomic(void) {
  static const qbs_block_q4_k_t weight __attribute__((aligned(16))) =
      Q4_BLOCK(1);
  static const qbs_block_q8_k_t activation __attribute__((aligned(16))) =
      Q8_BLOCK(1);
  static const uint32_t source[32] __attribute__((aligned(16))) = {
      [0 ... 31] = 0x41000000u,
  };
  static uint32_t observed[32] __attribute__((aligned(16)));
  static qbs_descriptor_t descriptor __attribute__((aligned(16)));
  int failures = 0;

  descriptor = make_descriptor(&weight, 1);
  descriptor.header =
      (descriptor.header & ~UINT64_C(0xf)) |
      ((QBS_DESCRIPTOR_VERSION ^ UINT64_C(0xf)) & UINT64_C(0xf));

  const uint64_t before = trap_count;
  issue_qbexec_m1(&descriptor, &activation, source, observed);
  if (trap_count != before + 1 || trap_cause != 2) {
    printf("validation fault mismatch: traps=%ld cause=%lx tval=%lx\n",
           trap_count - before, trap_cause, trap_tval);
    ++failures;
  }
  if (observed[0] != source[0] || observed[31] != source[31]) {
    printf("validation fault changed v8: result[0]=%x result[31]=%x\n",
           observed[0], observed[31]);
    ++failures;
  }
  return failures;
}

int main(void) {
  int failures = check_encoding_contract();

  trap_count = 0;
  trap_cause = 0;
  trap_tval = 0;
  recovery_store = 0;

  const uint64_t before_probe = trap_count;
  const uint64_t capability0 = issue_qbinfo(0);
  const int qbs_enabled = trap_count == before_probe;

  if (!qbs_enabled) {
    if (trap_count != before_probe + 1 || trap_cause != 2 ||
        (uint32_t)trap_tval != QBINFO_A0_A0) {
      printf("disabled decode failed: traps=%ld cause=%lx tval=%lx\n",
             trap_count - before_probe, trap_cause, trap_tval);
      ++failures;
    }
    recovery_store = 0x1122334455667788UL;
    if (recovery_store != 0x1122334455667788UL) ++failures;
    printf("QBS control smoke (disabled): %s\n",
           failures == 0 ? "PASS" : "FAIL");
    return failures;
  }

  if (capability0 != qbs_capability_word(0, VLEN)) {
    printf("capability[0] failed: got=%lx expected=%lx\n", capability0,
           qbs_capability_word(0, VLEN));
    ++failures;
  }
  failures += check_capabilities();

  const uint64_t before_reserved = trap_count;
  issue_reserved_qbinfo(0);
  if (trap_count != before_reserved + 1 || trap_cause != 2 ||
      (uint32_t)trap_tval != QBINFO_RESERVED_A0_A0) {
    printf("reserved qbinfo failed: traps=%ld cause=%lx tval=%lx\n",
           trap_count - before_reserved, trap_cause, trap_tval);
    ++failures;
  }

  failures += check_m1_execution();
  failures += check_m3_execution();
  failures += check_validation_fault_is_atomic();

  // This is deliberately the first scalar store/load sequence after qbexec.
  // It detects a leaked CVA6 pending-load entry as a forward-progress failure.
  recovery_store = 0x5a5aa5a55a5aa5a5UL;
  if (recovery_store != 0x5a5aa5a55a5aa5a5UL) ++failures;

  printf("QBS control smoke (enabled): %s\n",
         failures == 0 ? "PASS" : "FAIL");
  return failures;
}
