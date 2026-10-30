#include <stddef.h>
#include <stdint.h>

#include "../qbs_ref.h"

#define QBS_UART_MMIO UINT64_C(0x10000000)
#define QBS_FINISHER  UINT64_C(0x00100000)
#define QBS_RAM_END   UINT64_C(0x88000000)
#define QBS_MCAUSE_ILLEGAL UINT64_C(2)
#define QBS_MCAUSE_LOAD_ACCESS UINT64_C(5)
#define QBS_FFLAG_DZ UINT32_C(0x08)
#define QBS_FFLAG_NV UINT32_C(0x10)
#define QBS_DEST_POISON UINT32_C(0x4c7c7c7c)

volatile uint64_t qbs_trap_cause;
volatile uint64_t qbs_trap_tval;

static qbs_block_q8_0_t weights[2] __attribute__((aligned(16)));
static qbs_block_q8_0_t activations[2] __attribute__((aligned(16)));
static qbs_block_q8_0_t matrix_weights[32] __attribute__((aligned(16)));
static qbs_block_q8_0_t matrix_activations[8] __attribute__((aligned(16)));
static uint8_t matrix_activations_m8[8 * sizeof(qbs_block_q8_0_t)]
    __attribute__((aligned(16)));
static qbs_block_q4_k_t context_weights[2] __attribute__((aligned(16)));
static qbs_block_q8_k_t context_activations[2]
    __attribute__((aligned(16)));
static qbs_descriptor_t descriptor __attribute__((aligned(16)));
static uint32_t output[8][32] __attribute__((aligned(16)));
static uint8_t page_crossing_storage[3 * 4096] __attribute__((aligned(4096)));
static qbs_block_q8_0_t tile_weights_q8[32 * 32]
    __attribute__((aligned(16)));
static qbs_block_q4_k_t tile_weights_q4[7 * 4]
    __attribute__((aligned(16)));
static uint8_t tile_activation[4672] __attribute__((aligned(16)));

static void finish(unsigned code) {
  const uint32_t value = code == 0 ? UINT32_C(0x5555)
                                   : (code << 16) | UINT32_C(0x3333);
  *(volatile uint32_t *)(uintptr_t)QBS_FINISHER = value;
  for (;;) __asm__ volatile("wfi");
}

static void clear_bytes(void *data, size_t bytes) {
  uint8_t *cursor = data;
  while (bytes-- != 0) *cursor++ = 0;
}

static void copy_bytes(void *destination, const void *source, size_t bytes) {
  uint8_t *output_bytes = destination;
  const uint8_t *input_bytes = source;
  while (bytes-- != 0) *output_bytes++ = *input_bytes++;
}

static void clear_trap(void) {
  qbs_trap_cause = UINT64_MAX;
  qbs_trap_tval = UINT64_MAX;
}

static void run_qbexec(const void *descriptor_address,
                       const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(
      "li t0, 32\n"
      "vsetvli zero, t0, e32, m1, ta, ma\n"
      ".word 0x00b5005b"
      : : "r"(rs1), "r"(rs2) : "t0", "memory");
}

static void run_qbexec_no_vset(const void *descriptor_address,
                               const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(".word 0x00b5005b"
                   : : "r"(rs1), "r"(rs2) : "memory");
}

static void run_qbexec_m2(const void *descriptor_address,
                          const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(
      "li t0, 64\n"
      "vsetvli zero, t0, e32, m2, ta, ma\n"
      ".word 0x02b5005b"
      : : "r"(rs1), "r"(rs2) : "t0", "memory");
}

static void run_qbexec_m3(const void *descriptor_address,
                          const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(
      "li t0, 128\n"
      "vsetvli zero, t0, e32, m4, ta, ma\n"
      ".word 0x04b5005b"
      : : "r"(rs1), "r"(rs2) : "t0", "memory");
}

static void run_qbexec_m4(const void *descriptor_address,
                          const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(
      "li t0, 128\n"
      "vsetvli zero, t0, e32, m4, ta, ma\n"
      ".word 0x06b5005b"
      : : "r"(rs1), "r"(rs2) : "t0", "memory");
}

static void run_qbexec_m5(const void *descriptor_address,
                          const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(
      "li t0, 256\n"
      "vsetvli zero, t0, e32, m8, ta, ma\n"
      ".word 0x08b5005b"
      : : "r"(rs1), "r"(rs2) : "t0", "memory");
}

static void run_qbexec_m8(const void *descriptor_address,
                          const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  __asm__ volatile(
      "li t0, 256\n"
      "vsetvli zero, t0, e32, m8, ta, ma\n"
      ".word 0x0eb5005b"
      : : "r"(rs1), "r"(rs2) : "t0", "memory");
}

static void run_qbexec_m8_bad_vd(const void *descriptor_address,
                                 const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  /* M8 reserves eight registers, so v1 is not a legal group base. */
  __asm__ volatile(".word 0x0eb500db"
                   : : "r"(rs1), "r"(rs2) : "memory");
}

static void run_qbexec_m2_bad_vd(const void *descriptor_address,
                                 const void *activation_address) {
  register uintptr_t rs1 __asm__("a0") = (uintptr_t)descriptor_address;
  register uintptr_t rs2 __asm__("a1") = (uintptr_t)activation_address;
  /* M2 reserves two registers, so an odd destination register is illegal. */
  __asm__ volatile(".word 0x02b500db"
                   : : "r"(rs1), "r"(rs2) : "memory");
}

static uint64_t run_qbinfo(uint64_t index) {
  register uint64_t value __asm__("a0") = index;
  __asm__ volatile(".word 0x0005155b" : "+r"(value));
  return value;
}

static uint32_t read_v0_word0(void) {
  __asm__ volatile(
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vse32.v v0, (%0)\n"
      : : "r"(output[0]) : "memory");
  return output[0][0];
}

static void write_v0_word0(uint32_t value) {
  output[0][0] = value;
  __asm__ volatile(
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vle32.v v0, (%0)\n"
      : : "r"(output[0]) : "memory");
}

static void write_destination(uint32_t value) {
  for (unsigned reg = 0; reg < 8; ++reg)
    for (unsigned element = 0; element < 32; ++element)
      output[reg][element] = value;
  __asm__ volatile(
      "li t0, 32\n"
      "vsetvli zero, t0, e32, m1, ta, ma\n"
      "vle32.v v0, (%0)\n"
      "vle32.v v1, (%1)\n"
      "vle32.v v2, (%2)\n"
      "vle32.v v3, (%3)\n"
      "vle32.v v4, (%4)\n"
      "vle32.v v5, (%5)\n"
      "vle32.v v6, (%6)\n"
      "vle32.v v7, (%7)\n"
      : : "r"(output[0]), "r"(output[1]), "r"(output[2]),
          "r"(output[3]), "r"(output[4]), "r"(output[5]),
          "r"(output[6]), "r"(output[7]) : "t0", "memory");
}

static void read_destination(void) {
  __asm__ volatile(
      "li t0, 32\n"
      "vsetvli zero, t0, e32, m1, ta, ma\n"
      "vse32.v v0, (%0)\n"
      "vse32.v v1, (%1)\n"
      "vse32.v v2, (%2)\n"
      "vse32.v v3, (%3)\n"
      "vse32.v v4, (%4)\n"
      "vse32.v v5, (%5)\n"
      "vse32.v v6, (%6)\n"
      "vse32.v v7, (%7)\n"
      : : "r"(output[0]), "r"(output[1]), "r"(output[2]),
          "r"(output[3]), "r"(output[4]), "r"(output[5]),
          "r"(output[6]), "r"(output[7]) : "t0", "memory");
}

static uint32_t float_bits(float value) {
  union {
    float value;
    uint32_t bits;
  } conversion = { .value = value };
  return conversion.bits;
}

static void install_matrix_descriptor(unsigned m, unsigned n) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = m >= QBS_WIDE_M_MIN
          ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
          : QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = (uint8_t)n,
      .k_blocks = 1,
  };
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = (uintptr_t)matrix_weights;
}

static int check_matrix_result(unsigned m, unsigned n) {
  const unsigned registers = m == 1 ? 1 : (m == 2 ? 2 : (m <= 4 ? 4 : 8));
  read_destination();
  for (unsigned context = 0; context < registers; ++context) {
    for (unsigned row = 0; row < 32; ++row) {
      uint32_t expected = 0;
      if (context < m && row < n)
        expected = float_bits((float)((context + 1u) * (row + 1u)));
      else if (context >= m || m >= QBS_WIDE_M_MIN)
        expected = QBS_DEST_POISON;
      if (output[context][row] != expected) return 0;
    }
  }
  return 1;
}

static int run_matrix_case(unsigned m, unsigned n) {
  install_matrix_descriptor(m, n);
  write_destination(QBS_DEST_POISON);
  clear_trap();
  if (m == 1) run_qbexec(&descriptor, matrix_activations);
  else if (m == 2) run_qbexec_m2(&descriptor, matrix_activations);
  else if (m == 3) run_qbexec_m3(&descriptor, matrix_activations);
  else if (m == 4) run_qbexec_m4(&descriptor, matrix_activations);
  else if (m == 5) run_qbexec_m5(&descriptor, matrix_activations_m8);
  else run_qbexec_m8(&descriptor, matrix_activations_m8);
  return qbs_trap_cause == UINT64_MAX && check_matrix_result(m, n);
}

static void pack_matrix_activations_m8(void) {
  clear_bytes(matrix_activations_m8, sizeof(matrix_activations_m8));
  for (unsigned context = 0; context < 8; ++context) {
    copy_bytes(matrix_activations_m8 + context * sizeof(uint16_t),
               &matrix_activations[context].d, sizeof(uint16_t));
    for (unsigned byte = 0; byte < 32; ++byte) {
      matrix_activations_m8[8 * sizeof(uint16_t) + byte * 8 + context] =
          (uint8_t)matrix_activations[context].qs[byte];
    }
  }
}

static void install_descriptor(uint64_t weight_base) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = 1,
      .k_blocks = 2,
  };
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = weight_base;
}

static void install_context_descriptor(unsigned access, unsigned generation,
                                       unsigned k_blocks) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = 1,
      .k_blocks = (uint16_t)k_blocks,
      .activation_access = (uint8_t)access,
      .context_id = 0,
      .context_generation = (uint8_t)generation,
  };
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = (uintptr_t)context_weights;
}

static int expect_load_access(uint64_t expected_tval) {
  return qbs_trap_cause == QBS_MCAUSE_LOAD_ACCESS &&
         qbs_trap_tval == expected_tval;
}

static int expect_illegal(uint32_t expected_instruction) {
  return qbs_trap_cause == QBS_MCAUSE_ILLEGAL &&
         (qbs_trap_tval == 0 || qbs_trap_tval == expected_instruction);
}

typedef struct {
  unsigned m, n, blocks, q8_k;
} tile_context_case_t;

static void run_tile_instruction(unsigned m, const void *activation) {
  if (m == 1) run_qbexec(&descriptor, activation);
  else if (m == 2) run_qbexec_m2(&descriptor, activation);
  else if (m == 3) run_qbexec_m3(&descriptor, activation);
  else if (m == 4) run_qbexec_m4(&descriptor, activation);
  else if (m == 5) run_qbexec_m5(&descriptor, activation);
  else run_qbexec_m8(&descriptor, activation);
}

static qbs_descriptor_fields_t tile_fields(const tile_context_case_t *test,
                                           unsigned access) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = test->q8_k ? QBS_WEIGHT_PROFILE_Q4_K
                                  : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      .activation_profile = test->q8_k ? QBS_ACTIVATION_PROFILE_Q8_K
                                      : QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = test->m == 4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
                                       : QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED,
      .n = (uint8_t)test->n,
      .k_blocks = (uint16_t)test->blocks,
      .activation_access = (uint8_t)access,
      .context_id = 0,
      .context_generation = access == QBS_ACTIVATION_ACCESS_DIRECT ? 0 : 41,
  };
  return fields;
}

static void install_tile(const tile_context_case_t *test, unsigned access) {
  const qbs_descriptor_fields_t fields = tile_fields(test, access);
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = test->q8_k ? (uintptr_t)tile_weights_q4
                                     : (uintptr_t)tile_weights_q8;
}

static void prepare_tile_weights(const tile_context_case_t *test) {
  clear_bytes(tile_weights_q8, sizeof(tile_weights_q8));
  clear_bytes(tile_weights_q4, sizeof(tile_weights_q4));
  for (unsigned row = 0; row < test->n; ++row) {
    for (unsigned block = 0; block < test->blocks; ++block) {
      if (test->q8_k) {
        qbs_block_q4_k_t *w = &tile_weights_q4[row * test->blocks + block];
        w->d = UINT16_C(0x3c00);
        w->dmin = UINT16_C(0x3800);
        /* All eight scales/mins are one, so every weight is row + 1/2. */
        for (unsigned j = 0; j < 8; ++j) w->scales[j] = 1;
        for (unsigned j = 8; j < 12; ++j) w->scales[j] = 0x11;
        for (unsigned j = 0; j < 128; ++j)
          w->qs[j] = (uint8_t)((row + 1u) * 0x11u);
      } else {
        qbs_block_q8_0_t *w = &tile_weights_q8[row * test->blocks + block];
        w->d = block % 2 ? UINT16_C(0x3800) : UINT16_C(0x3c00);
        for (unsigned j = 0; j < 32; ++j)
          w->qs[j] = (int8_t)(row + 1u + j % 2u);
      }
    }
  }
}

static void prepare_tile_activation(const tile_context_case_t *test,
                                     unsigned multiplier) {
  const unsigned stored_m = test->m == 4 ? 4 : 8;
  const unsigned elements = test->q8_k ? 256 : 32;
  const unsigned scale_bytes = test->q8_k ? 4 : 2;
  const unsigned block_bytes = test->q8_k ? 292 : 34;
  clear_bytes(tile_activation, sizeof(tile_activation));
  for (unsigned block = 0; block < test->blocks; ++block) {
    uint8_t *slab = tile_activation + block * stored_m * block_bytes;
    /* Nonzero padded M5 rows expose accidental writes to inactive registers. */
    for (unsigned input = 0; input < stored_m; ++input) {
      const uint32_t scale = test->q8_k
          ? (input % 2 ? UINT32_C(0x40000000) : UINT32_C(0x3f800000))
          : (input % 2 ? UINT32_C(0x4000) : UINT32_C(0x3c00));
      for (unsigned byte = 0; byte < scale_bytes; ++byte)
        slab[input * scale_bytes + byte] = (uint8_t)(scale >> (8u * byte));
      for (unsigned j = 0; j < elements; ++j)
        slab[stored_m * scale_bytes + j * stored_m + input] =
            (uint8_t)(multiplier * (input + 1u + block + j % 4u));
      if (test->q8_k) {
        const unsigned sum16 = multiplier * (16u * (input + 1u + block) + 24u);
        for (unsigned group = 0; group < 16; ++group) {
          const unsigned offset = stored_m * 260u + 2u * (group * stored_m + input);
          slab[offset] = (uint8_t)sum16;
          slab[offset + 1u] = (uint8_t)(sum16 >> 8);
        }
      }
    }
  }
}

static void tile_before_instruction(void) {
  write_destination(QBS_DEST_POISON);
  __asm__ volatile("csrw fflags, %0" : : "r"(QBS_FFLAG_DZ));
  clear_trap();
}

static int tile_flags_unchanged(void) {
  uint64_t flags;
  __asm__ volatile("csrr %0, fflags" : "=r"(flags));
  return flags == QBS_FFLAG_DZ;
}

static int tile_destination_unchanged(void) {
  read_destination();
  for (unsigned reg = 0; reg < 8; ++reg)
    for (unsigned word = 0; word < 32; ++word)
      if (output[reg][word] != QBS_DEST_POISON) return 0;
  return tile_flags_unchanged();
}

static int tile_result(const tile_context_case_t *test, unsigned multiplier) {
  if (qbs_trap_cause != UINT64_MAX || !tile_flags_unchanged()) return 0;
  read_destination();
  for (unsigned input = 0; input < 8; ++input) {
    for (unsigned row = 0; row < 32; ++row) {
      uint32_t expected = QBS_DEST_POISON;
      if (input < test->m && row < test->n) {
        /* Closed-form integer oracle, independent of packed byte addressing.
         * Every conversion, scale product, FMA and final sum is exact FP32. */
        unsigned sum = 0;
        for (unsigned b = 0; b < test->blocks; ++b) {
          const unsigned base = input + 1u + b;
          if (test->q8_k)
            sum += (256u * base + 384u) * (2u * row + 1u) / 2u;
          else
            sum += ((32u * base + 48u) * (row + 1u) + 16u * base + 32u) /
                   (b % 2 ? 2u : 1u);
        }
        expected = float_bits((float)(sum * multiplier * (input % 2 ? 2u : 1u)));
      } else if (test->m == 4 && input < 4) {
        expected = 0;
      }
      if (output[input][row] != expected) return 0;
    }
  }
  return 1;
}

static int tile_success(const tile_context_case_t *test, unsigned access,
                         unsigned expected_multiplier) {
  install_tile(test, access);
  tile_before_instruction();
  run_tile_instruction(test->m, access == QBS_ACTIVATION_ACCESS_DIRECT ||
      access == QBS_ACTIVATION_ACCESS_FILL ? tile_activation
      : (const void *)(uintptr_t)QBS_UART_MMIO);
  return tile_result(test, expected_multiplier);
}

static int tile_reject(unsigned m) {
  /* Both payload pointers are invalid: validation must win over memory faults. */
  descriptor.weight_base = QBS_UART_MMIO;
  tile_before_instruction();
  run_tile_instruction(m, (const void *)(uintptr_t)QBS_UART_MMIO);
  return expect_illegal(UINT32_C(0x00b5005b) | ((m - 1u) << 25)) &&
         tile_destination_unchanged();
}

/* Failure codes are 40 + 24*case_index + stage, with stages below.
 * Keep every failure below 256 so the host exit status cannot wrap to zero. */
static unsigned run_tile_context_case(const tile_context_case_t *test) {
  prepare_tile_weights(test);
  prepare_tile_activation(test, 1);
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_DIRECT, 1)) return 1;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_FILL, 1)) return 2;
  prepare_tile_activation(test, 2);
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_DIRECT, 2)) return 3;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 4;

  qbs_descriptor_fields_t fields = tile_fields(test, QBS_ACTIVATION_ACCESS_REUSE);
  ++fields.context_generation;
  descriptor.header = qbs_pack_descriptor_header(&fields);
  if (!tile_reject(test->m)) return 5;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 6;

  fields = tile_fields(test, QBS_ACTIVATION_ACCESS_REUSE);
  fields.k_blocks = test->blocks == 1 ? 2 : test->blocks - 1;
  descriptor.header = qbs_pack_descriptor_header(&fields);
  if (!tile_reject(test->m)) return 7;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 8;

  fields = tile_fields(test, QBS_ACTIVATION_ACCESS_REUSE);
  unsigned other_m = test->m == 5 ? 8 : (test->m == 8 ? 5 : 1);
  if (other_m == 1) fields.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  descriptor.header = qbs_pack_descriptor_header(&fields);
  if (!tile_reject(other_m)) return 9;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 10;

  fields = tile_fields(test, QBS_ACTIVATION_ACCESS_FILL);
  /* M4 Q8_0: 33 blocks fits bytes but exceeds maxK. M5/M8 Q8_0:
   * 18*8*34=4896; M4 Q8_K: 5*4*292=5840. Both exceed bytes below maxK. */
  fields.k_blocks = test->q8_k ? 5 : (test->m == 4 ? 33 : 18);
  descriptor.header = qbs_pack_descriptor_header(&fields);
  if (!tile_reject(test->m)) return 11;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 12;

  /* Switch both profiles so the descriptor is otherwise legal and fits;
   * rejection must come from resident metadata, not profile compatibility. */
  if (test->q8_k || test->blocks == 1) {
    fields = tile_fields(test, QBS_ACTIVATION_ACCESS_REUSE);
    fields.weight_profile = test->q8_k ? QBS_WEIGHT_PROFILE_Q8_0_WEIGHT
                                      : QBS_WEIGHT_PROFILE_Q4_K;
    fields.activation_profile = test->q8_k ? QBS_ACTIVATION_PROFILE_Q8_0
                                          : QBS_ACTIVATION_PROFILE_Q8_K;
    descriptor.header = qbs_pack_descriptor_header(&fields);
    if (!tile_reject(test->m)) return 20;
    if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 21;
  }

  for (unsigned access = QBS_ACTIVATION_ACCESS_REUSE;
       access <= QBS_ACTIVATION_ACCESS_RELEASE; ++access) {
    install_tile(test, access);
    descriptor.weight_base = QBS_UART_MMIO;
    tile_before_instruction();
    run_tile_instruction(test->m, (const void *)(uintptr_t)QBS_UART_MMIO);
    if (!expect_load_access(QBS_UART_MMIO) || !tile_destination_unchanged()) return 13;
    if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 1)) return 14;
  }
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_RELEASE, 1)) return 15;
  install_tile(test, QBS_ACTIVATION_ACCESS_REUSE);
  if (!tile_reject(test->m)) return 16;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_FILL, 2)) return 17;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_REUSE, 2)) return 18;
  if (!tile_success(test, QBS_ACTIVATION_ACCESS_RELEASE, 2)) return 19;
  return 0;
}

static void run_tile_context_tests(void) {
  static const tile_context_case_t cases[] = {
      {4, 3, 1, 0}, {4, 32, 28, 0}, {4, 31, 32, 0},
      {5, 15, 1, 0}, {5, 15, 17, 0}, {8, 16, 17, 0},
      {4, 7, 4, 1},
  };
  for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    unsigned stage = run_tile_context_case(&cases[i]);
    if (stage != 0) finish(40u + 24u * i + stage);
  }

  /* An otherwise valid M2/M3 row-major command is not a resident slab. */
  for (unsigned m = 2; m <= 3; ++m) {
    install_matrix_descriptor(m, 1);
    qbs_descriptor_fields_t fields = qbs_unpack_descriptor_header(descriptor.header);
    fields.activation_access = QBS_ACTIVATION_ACCESS_FILL;
    fields.context_generation = 41;
    descriptor.header = qbs_pack_descriptor_header(&fields);
    if (!tile_reject(m)) finish(230u + m);
  }
}

void qbs_contract_main(void) {
  clear_bytes(weights, sizeof(weights));
  clear_bytes(activations, sizeof(activations));
  clear_bytes(output, sizeof(output));

  if (run_qbinfo(0) != qbs_capability_word(0, 1024) ||
      run_qbinfo(1) != qbs_capability_word(1, 1024) ||
      run_qbinfo(2) != qbs_capability_word(2, 1024))
    finish(1);

  /* Literal contract expectations, not just the shared generated helper.
   * Word3 has exactly 4672 bytes, version 1, and zero reserved high bits. */
  clear_trap();
  const uint64_t context_caps = UINT64_C(1) | (UINT64_C(7) << 4) |
      (UINT64_C(31) << 7) | (UINT64_C(6) << 12) |
      (UINT64_C(15) << 28) | (UINT64_C(8) << 32) | (UINT64_C(14) << 40);
  if (run_qbinfo(2) != context_caps ||
      run_qbinfo(3) != UINT64_C(0x0000000100001240) ||
      qbs_trap_cause != UINT64_MAX)
    finish(32);

  /* 1.0 + 2^-24 is an FP32 tie. RNE keeps 1.0; RUP increments one ULP. */
  weights[0].d = UINT16_C(0x3c00);
  weights[0].qs[0] = 1;
  weights[1].d = UINT16_C(0x0001);
  weights[1].qs[0] = 1;
  activations[0].d = UINT16_C(0x3c00);
  activations[0].qs[0] = 1;
  activations[1].d = UINT16_C(0x3c00);
  activations[1].qs[0] = 1;
  install_descriptor((uintptr_t)weights);

  clear_trap();
  __asm__ volatile("csrw frm, %0" : : "r"(UINT64_C(3)));  /* RUP */
  run_qbexec(&descriptor, activations);
  if (qbs_trap_cause != UINT64_MAX ||
      read_v0_word0() != UINT32_C(0x3f800000))
    finish(2);

  clear_trap();
  run_qbexec((const void *)(uintptr_t)QBS_UART_MMIO, activations);
  if (!expect_load_access(QBS_UART_MMIO)) finish(3);

  install_descriptor((uintptr_t)weights);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_load_access(QBS_UART_MMIO)) finish(4);

  install_descriptor(QBS_UART_MMIO);
  clear_trap();
  run_qbexec(&descriptor, activations);
  if (!expect_load_access(QBS_UART_MMIO)) finish(5);

  /* A legal RAM range may cross a 4-KiB translation boundary. */
  qbs_block_q8_0_t *cross_activations =
      (qbs_block_q8_0_t *)(void *)(page_crossing_storage + 4096 - 32);
  qbs_block_q8_0_t *cross_weights =
      (qbs_block_q8_0_t *)(void *)(page_crossing_storage + 8192 - 32);
  copy_bytes(cross_activations, activations, sizeof(activations));
  copy_bytes(cross_weights, weights, sizeof(weights));
  install_descriptor((uintptr_t)cross_weights);
  clear_trap();
  run_qbexec(&descriptor, cross_activations);
  if (qbs_trap_cause != UINT64_MAX ||
      read_v0_word0() != UINT32_C(0x3f800000))
    finish(6);

  /* A range whose first bytes are RAM but whose tail is unmapped must fault
   * before the helper modifies architectural destination state. */
  install_descriptor((uintptr_t)weights);
  write_v0_word0(UINT32_C(0x4a5a5a5a));
  clear_trap();
  run_qbexec(&descriptor,
             (const void *)(uintptr_t)(QBS_RAM_END - UINT64_C(32)));
  if (!expect_load_access(QBS_RAM_END) ||
      read_v0_word0() != UINT32_C(0x4a5a5a5a))
    finish(7);

  install_descriptor(QBS_RAM_END - UINT64_C(32));
  write_v0_word0(UINT32_C(0x4b6b6b6b));
  clear_trap();
  run_qbexec(&descriptor, activations);
  if (!expect_load_access(QBS_RAM_END) ||
      read_v0_word0() != UINT32_C(0x4b6b6b6b))
    finish(8);

  clear_bytes(matrix_weights, sizeof(matrix_weights));
  clear_bytes(matrix_activations, sizeof(matrix_activations));
  for (unsigned row = 0; row < 32; ++row) {
    matrix_weights[row].d = UINT16_C(0x3c00);
    matrix_weights[row].qs[0] = (int8_t)(row + 1u);
  }
  for (unsigned context = 0; context < 8; ++context) {
    matrix_activations[context].d = UINT16_C(0x3c00);
    matrix_activations[context].qs[0] = (int8_t)(context + 1u);
  }
  pack_matrix_activations_m8();
  if (!run_matrix_case(1, 1)) finish(9);
  if (!run_matrix_case(2, 31)) finish(10);
  if (!run_matrix_case(3, 32)) finish(11);
  if (!run_matrix_case(4, 31)) finish(12);

  /* Wide commands use a fixed eight-row activation payload and preserve the
   * inactive destination tail. M5 exercises row padding; M8 exercises all
   * contexts. */
  if (!run_matrix_case(5, 15)) finish(29);
  if (!run_matrix_case(8, 16)) finish(30);

  install_matrix_descriptor(8, 16);
  write_destination(QBS_DEST_POISON);
  clear_trap();
  run_qbexec_m8_bad_vd(&descriptor, matrix_activations_m8);
  if (!expect_illegal(UINT32_C(0x0eb500db)) ||
      read_v0_word0() != QBS_DEST_POISON)
    finish(31);

  install_matrix_descriptor(1, 1);
  descriptor.header |= UINT64_C(1) << 63;
  write_v0_word0(UINT32_C(0x4d8d8d8d));
  clear_trap();
  run_qbexec(&descriptor, matrix_activations);
  if (!expect_illegal(UINT32_C(0x00b5005b)) ||
      read_v0_word0() != UINT32_C(0x4d8d8d8d))
    finish(13);

  install_matrix_descriptor(2, 1);
  write_v0_word0(UINT32_C(0x4e9e9e9e));
  clear_trap();
  run_qbexec_m2_bad_vd(&descriptor, matrix_activations);
  if (!expect_illegal(UINT32_C(0x02b500db)) ||
      read_v0_word0() != UINT32_C(0x4e9e9e9e))
    finish(14);

  write_v0_word0(UINT32_C(0x4fafafaf));
  __asm__ volatile("csrw vstart, %0" : : "r"(UINT64_C(1)));
  clear_trap();
  run_qbexec_no_vset(&descriptor, matrix_activations);
  __asm__ volatile("csrw vstart, zero");
  if (!expect_illegal(UINT32_C(0x00b5005b)) ||
      read_v0_word0() != UINT32_C(0x4fafafaf))
    finish(15);

  __asm__ volatile("csrw fflags, %0" : : "r"(QBS_FFLAG_DZ));
  clear_trap();
  run_qbexec(&descriptor, matrix_activations);
  uint64_t fflags;
  __asm__ volatile("csrr %0, fflags" : "=r"(fflags));
  if (qbs_trap_cause != UINT64_MAX ||
      (fflags & UINT32_C(0x1f)) != QBS_FFLAG_DZ)
    finish(16);

  matrix_weights[0].d = UINT16_C(0x7c00);
  matrix_weights[0].qs[0] = 0;
  __asm__ volatile("csrw fflags, %0" : : "r"(QBS_FFLAG_DZ));
  clear_trap();
  run_qbexec(&descriptor, matrix_activations);
  __asm__ volatile("csrr %0, fflags" : "=r"(fflags));
  if (qbs_trap_cause != UINT64_MAX ||
      (fflags & (QBS_FFLAG_DZ | QBS_FFLAG_NV)) !=
          (QBS_FFLAG_DZ | QBS_FFLAG_NV))
    finish(17);

  clear_bytes(context_weights, sizeof(context_weights));
  clear_bytes(context_activations, sizeof(context_activations));
  context_weights[0].d = UINT16_C(0x3c00);
  context_weights[0].scales[0] = 1;
  context_weights[0].qs[0] = 1;
  context_activations[0].d = 1.0f;
  context_activations[0].qs[0] = 1;
  context_activations[0].bsums[0] = 1;

  install_context_descriptor(QBS_ACTIVATION_ACCESS_FILL, 7, 1);
  clear_trap();
  run_qbexec(&descriptor, context_activations);
  const uint32_t fill_result = read_v0_word0();
  if (qbs_trap_cause != UINT64_MAX || fill_result == 0) finish(18);

  /* REUSE ignores rs2 completely and consumes the per-hart context. */
  context_activations[0].qs[0] = 17;
  install_context_descriptor(QBS_ACTIVATION_ACCESS_REUSE, 7, 1);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (qbs_trap_cause != UINT64_MAX || read_v0_word0() != fill_result)
    finish(19);

  write_v0_word0(QBS_DEST_POISON);
  install_context_descriptor(QBS_ACTIVATION_ACCESS_REUSE, 8, 1);
  descriptor.weight_base = QBS_UART_MMIO;
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_illegal(UINT32_C(0x00b5005b)) ||
      read_v0_word0() != QBS_DEST_POISON)
    finish(20);

  install_context_descriptor(QBS_ACTIVATION_ACCESS_REUSE, 7, 2);
  descriptor.weight_base = QBS_UART_MMIO;
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_illegal(UINT32_C(0x00b5005b)) ||
      read_v0_word0() != QBS_DEST_POISON)
    finish(21);

  /* Descriptor rejection precedes FILL acceptance and preserves the old
   * context. A valid FILL that faults later deliberately invalidates it. */
  install_context_descriptor(QBS_ACTIVATION_ACCESS_FILL, 9,
                             QBS_ACTIVATION_CONTEXT_MAX_K_BLOCKS + 1u);
  descriptor.weight_base = QBS_UART_MMIO;
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_illegal(UINT32_C(0x00b5005b))) finish(22);

  install_context_descriptor(QBS_ACTIVATION_ACCESS_REUSE, 7, 1);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (qbs_trap_cause != UINT64_MAX || read_v0_word0() != fill_result)
    finish(23);

  install_context_descriptor(QBS_ACTIVATION_ACCESS_RELEASE, 7, 1);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (qbs_trap_cause != UINT64_MAX || read_v0_word0() != fill_result)
    finish(24);
  write_v0_word0(QBS_DEST_POISON);
  install_context_descriptor(QBS_ACTIVATION_ACCESS_REUSE, 7, 1);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_illegal(UINT32_C(0x00b5005b)) ||
      read_v0_word0() != QBS_DEST_POISON)
    finish(25);

  context_activations[0].qs[0] = 1;
  install_context_descriptor(QBS_ACTIVATION_ACCESS_FILL, 10, 1);
  clear_trap();
  run_qbexec(&descriptor, context_activations);
  if (qbs_trap_cause != UINT64_MAX) finish(26);
  install_context_descriptor(QBS_ACTIVATION_ACCESS_FILL, 11, 1);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_load_access(QBS_UART_MMIO)) finish(27);
  write_v0_word0(QBS_DEST_POISON);
  install_context_descriptor(QBS_ACTIVATION_ACCESS_REUSE, 10, 1);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_illegal(UINT32_C(0x00b5005b)) ||
      read_v0_word0() != QBS_DEST_POISON)
    finish(28);

  run_tile_context_tests();
  finish(0);
}
