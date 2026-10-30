#ifndef LLAMA_QWEN25_REAL_QBS_BENCHMARK_IMPL_H_
#define LLAMA_QWEN25_REAL_QBS_BENCHMARK_IMPL_H_

#include "../../common/qbs_abi.h"
#include "../../common/runtime.h"
#include "../../llama_q4k_repack_bench/repack_kernels.h"
#include "../../../software/qbs/include/qbs/qbs.h"

#include <stdint.h>
#include <string.h>

#ifdef SPIKE
extern void printstr(const char *string);
#define BENCH_REPORT(...) do { } while (0)
#else
#include "printf.h"
#define BENCH_REPORT(...) printf(__VA_ARGS__)
#endif

void q4km_quantize_row_q8_K(const float *x, block_q8_K *y, int64_t k)
    __attribute__((noinline));
#include "../../llama_q4k_repack_bench/repack_kernels.c"

#ifndef BENCH_WEIGHT_Q3
#define BENCH_WEIGHT_Q3 0
#endif
#ifndef BENCH_WEIGHT_Q4
#define BENCH_WEIGHT_Q4 0
#endif
#ifndef BENCH_WEIGHT_Q5
#define BENCH_WEIGHT_Q5 0
#endif
#ifndef BENCH_WEIGHT_Q6
#define BENCH_WEIGHT_Q6 0
#endif
#ifndef BENCH_WEIGHT_Q8_0
#define BENCH_WEIGHT_Q8_0 0
#endif
#ifndef BENCH_WEIGHT_Q4_0
#define BENCH_WEIGHT_Q4_0 0
#endif
#ifndef BENCH_WEIGHT_Q5_0
#define BENCH_WEIGHT_Q5_0 0
#endif
#ifndef BENCH_WEIGHT_IQ4_NL
#define BENCH_WEIGHT_IQ4_NL 0
#endif
#ifndef BENCH_WEIGHT_Q2
#define BENCH_WEIGHT_Q2 0
#endif

// The primary measurement follows the production GGML command path: construct
// one stack descriptor for each QBS command, issue a fence and vsetvli, execute
// the command, restore the result VL, and store each output row separately.
// The prebuilt mode is retained only to isolate descriptor construction cost.
#ifndef QBS_BENCH_PREBUILT_DESCRIPTOR
#define QBS_BENCH_PREBUILT_DESCRIPTOR 0
#endif
#ifndef QBS_BENCH_ACTIVATION_CONTEXT
#define QBS_BENCH_ACTIVATION_CONTEXT 0
#endif
#ifndef QBS_BENCH_CONTEXT_KEEP_VALID
#define QBS_BENCH_CONTEXT_KEEP_VALID 0
#endif
#ifndef QBS_BENCH_CONTEXT_GENERATION
#define QBS_BENCH_CONTEXT_GENERATION 1
#endif
#ifndef QBS_BENCH_OPERATIONS
#define QBS_BENCH_OPERATIONS 1
#endif
#ifndef QBS_BENCH_CROSS_OP_REUSE
#define QBS_BENCH_CROSS_OP_REUSE 0
#endif
#ifndef QBS_BENCH_COMPACT_M4
#define QBS_BENCH_COMPACT_M4 0
#endif
#ifndef QBS_BENCH_PREFLIGHT
#define QBS_BENCH_PREFLIGHT 0
#endif
#ifndef QBS_BENCH_INDEPENDENT_ORACLE
#define QBS_BENCH_INDEPENDENT_ORACLE 0
#endif
#if QBS_BENCH_COMPACT_M4 != 0 && QBS_BENCH_COMPACT_M4 != 1
#error "QBS_BENCH_COMPACT_M4 must be 0 or 1"
#endif
#if QBS_BENCH_INDEPENDENT_ORACLE && defined(__FAST_MATH__)
#error "independent numerical validation requires -fno-fast-math"
#endif

#if QBS_BENCH_PREBUILT_DESCRIPTOR != 0 && \
    QBS_BENCH_PREBUILT_DESCRIPTOR != 1
#error "QBS_BENCH_PREBUILT_DESCRIPTOR must be 0 or 1"
#endif
#if QBS_BENCH_ACTIVATION_CONTEXT != 0 && \
    QBS_BENCH_ACTIVATION_CONTEXT != 1
#error "QBS_BENCH_ACTIVATION_CONTEXT must be 0 or 1"
#endif
#if QBS_BENCH_CONTEXT_KEEP_VALID != 0 && \
    QBS_BENCH_CONTEXT_KEEP_VALID != 1
#error "QBS_BENCH_CONTEXT_KEEP_VALID must be 0 or 1"
#endif
#if QBS_BENCH_OPERATIONS < 1
#error "QBS_BENCH_OPERATIONS must be positive"
#endif
#if QBS_BENCH_CROSS_OP_REUSE != 0 && QBS_BENCH_CROSS_OP_REUSE != 1
#error "QBS_BENCH_CROSS_OP_REUSE must be 0 or 1"
#endif
#if QBS_BENCH_CROSS_OP_REUSE && !QBS_BENCH_ACTIVATION_CONTEXT
#error "cross-operator reuse requires the activation context"
#endif
#if QBS_BENCH_CROSS_OP_REUSE && QBS_BENCH_OPERATIONS < 2
#error "cross-operator reuse requires at least two operations"
#endif

#if QBS_BENCH_PREBUILT_DESCRIPTOR
#define QBS_BENCH_TIMING_SCOPE "prebuilt_descriptor"
#else
#define QBS_BENCH_TIMING_SCOPE "production_command"
#endif

// Existing Q6_K apps predate explicit one-hot format macros and only set
// BENCH_WEIGHT_Q4=0. Preserve that source contract.
#if !(BENCH_WEIGHT_Q3 || BENCH_WEIGHT_Q4 || BENCH_WEIGHT_Q5 || \
      BENCH_WEIGHT_Q6 || BENCH_WEIGHT_Q8_0 || BENCH_WEIGHT_Q4_0 || \
      BENCH_WEIGHT_Q5_0 || BENCH_WEIGHT_IQ4_NL || BENCH_WEIGHT_Q2)
#undef BENCH_WEIGHT_Q6
#define BENCH_WEIGHT_Q6 1
#endif

#if (BENCH_WEIGHT_Q3 + BENCH_WEIGHT_Q4 + BENCH_WEIGHT_Q5 + \
     BENCH_WEIGHT_Q6 + BENCH_WEIGHT_Q8_0 + BENCH_WEIGHT_Q4_0 + \
     BENCH_WEIGHT_Q5_0 + BENCH_WEIGHT_IQ4_NL + BENCH_WEIGHT_Q2) != 1
#error "select exactly one QBS weight format"
#endif

#if BENCH_WEIGHT_Q2
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q2_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q2_K_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q2_K_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_Q3
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q3_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q3_K_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q3_K_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_Q4
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q4_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q4_K_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q4_K_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_Q5
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q5_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q5_K_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q5_K_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_Q6
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q6_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q6_K_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q6_K_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_Q4_0
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q4_0
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q4_0_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q4_0_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_Q5_0
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q5_0
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q5_0_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q5_0_BLOCK_ELEMENTS
#elif BENCH_WEIGHT_IQ4_NL
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_IQ4_NL
#define BENCH_WEIGHT_BLOCK_BYTES QBS_IQ4_NL_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_IQ4_NL_BLOCK_ELEMENTS
#else
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q8_0_WEIGHT
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q8_0_WEIGHT_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q8_0_WEIGHT_BLOCK_ELEMENTS
#endif

#if BENCH_WEIGHT_Q8_0 || BENCH_WEIGHT_Q4_0 || BENCH_WEIGHT_Q5_0 || \
    BENCH_WEIGHT_IQ4_NL
typedef block_q8_0 benchmark_activation_block_t;
#define BENCH_ACTIVATION_PROFILE QBS_ACTIVATION_PROFILE_Q8_0
#else
typedef block_q8_K benchmark_activation_block_t;
#define BENCH_ACTIVATION_PROFILE QBS_ACTIVATION_PROFILE_Q8_K
#endif

#define BENCH_BLOCKS (BENCH_K / BENCH_BLOCK_ELEMENTS)
#define BENCH_Q8_BLOCKS (BENCH_INPUTS * BENCH_BLOCKS)
#define BENCH_OUTPUTS (BENCH_INPUTS * BENCH_ROWS)
#define BENCH_TOTAL_OUTPUTS (QBS_BENCH_OPERATIONS * BENCH_OUTPUTS)

#if BENCH_INPUTS >= QBS_WIDE_M_MIN
#define BENCH_TILE_N QBS_WIDE_M_MAX_N
#define BENCH_USE_M8_INTERLEAVED 1
#define BENCH_USE_M4_INTERLEAVED 0
#define BENCH_ACTIVATION_LAYOUT QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
#define BENCH_PACKED_ACTIVATION_ROWS QBS_MAX_M
#elif BENCH_INPUTS == 4 && (QBS_BENCH_COMPACT_M4 || \
      (!BENCH_WEIGHT_Q8_0 && !BENCH_WEIGHT_Q4_0 && \
       !BENCH_WEIGHT_Q5_0 && !BENCH_WEIGHT_IQ4_NL))
#define BENCH_TILE_N QBS_MAX_N
#define BENCH_USE_M8_INTERLEAVED 0
#define BENCH_USE_M4_INTERLEAVED 1
#define BENCH_ACTIVATION_LAYOUT QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
#define BENCH_PACKED_ACTIVATION_ROWS 4u
#else
#define BENCH_TILE_N QBS_MAX_N
#define BENCH_USE_M8_INTERLEAVED 0
#define BENCH_USE_M4_INTERLEAVED 0
#define BENCH_ACTIVATION_LAYOUT QBS_ACTIVATION_LAYOUT_ROW_MAJOR
#endif
#define BENCH_TILES ((BENCH_ROWS + BENCH_TILE_N - 1) / BENCH_TILE_N)
#if BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED
#define BENCH_ACTIVATION_BYTES (BENCH_PACKED_ACTIVATION_ROWS * BENCH_BLOCKS * \
                              sizeof(benchmark_activation_block_t))
#else
#define BENCH_ACTIVATION_BYTES (BENCH_Q8_BLOCKS * sizeof(benchmark_activation_block_t))
#endif

_Static_assert(BENCH_K > 0 && BENCH_K % BENCH_BLOCK_ELEMENTS == 0,
               "QBS K must align to the selected weight block");
_Static_assert(BENCH_BLOCKS <= QBS_MAX_K_BLOCKS,
               "QBS K block count exceeds the ABI limit");
_Static_assert(BENCH_ROWS > 0, "QBS requires at least one output row");
_Static_assert(BENCH_INPUTS >= 1 && BENCH_INPUTS <= QBS_MAX_M,
               "QBS M must be in [1,QBS_MAX_M]");
_Static_assert(VLEN >= QBS_MAX_N * 32,
               "this benchmark requires 32 FP32 results per context");
#if QBS_BENCH_ACTIVATION_CONTEXT
_Static_assert(BENCH_INPUTS == 1 || BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED,
               "context requires M1 row-major, M4 interleaved or M5--8 interleaved");
_Static_assert(BENCH_BLOCKS <= QBS_ACTIVATION_CONTEXT_MAX_K_BLOCKS,
               "activation context K exceeds the tag limit");
_Static_assert(BENCH_ACTIVATION_BYTES <= QBS_ACTIVATION_CONTEXT_CAPACITY_BYTES,
               "activation context exceeds the packed byte budget");
_Static_assert(BENCH_TILES >= 2,
               "activation context requires at least two output tiles");
#endif
#if QBS_BENCH_INDEPENDENT_ORACLE
_Static_assert(BENCH_WEIGHT_Q8_0 && BENCH_INPUTS == 4 && BENCH_USE_M4_INTERLEAVED,
               "independent oracle currently covers compact Q8_0 M4");
_Static_assert(QBS_BENCH_OPERATIONS == 1 && !QBS_BENCH_PREBUILT_DESCRIPTOR,
               "full-projection oracle apps measure one production-command operation");
#endif

enum benchmark_phase {
  BENCH_PHASE_QUANTIZE = 1,
  BENCH_PHASE_PACK = 2,
  BENCH_PHASE_MATMUL = 3,
};

extern const uint8_t benchmark_weight_start[];
extern const uint8_t benchmark_weight_end[];
extern const uint8_t benchmark_activation_start[];
extern const uint8_t benchmark_activation_end[];
extern const uint8_t benchmark_golden_start[];
extern const uint8_t benchmark_golden_end[];
#if QBS_BENCH_INDEPENDENT_ORACLE
extern const uint8_t benchmark_oracle_start[], benchmark_oracle_end[];
extern const uint8_t benchmark_expected_q8_start[], benchmark_expected_q8_end[];
#endif

static benchmark_activation_block_t quantized_activation[BENCH_Q8_BLOCKS]
    __attribute__((aligned(64), section(".bss")));
#if BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED
static uint8_t packed_activation[BENCH_PACKED_ACTIVATION_ROWS * BENCH_BLOCKS *
                                 sizeof(benchmark_activation_block_t)]
    __attribute__((aligned(64), section(".bss")));
#endif
#if QBS_BENCH_PREBUILT_DESCRIPTOR
static qbs_descriptor_t
    benchmark_descriptors[QBS_BENCH_OPERATIONS][BENCH_TILES]
    __attribute__((aligned(64), section(".bss")));
#endif
static float benchmark_output[BENCH_TOTAL_OUTPUTS]
    __attribute__((aligned(64), section(".bss")));
static qbs_status_t benchmark_execution_status = QBS_STATUS_OK;
static uint64_t benchmark_last_compute_cycles;

static inline uint64_t benchmark_cycle(void) {
#ifdef SPIKE
  return 0;
#else
  uint64_t cycle;
  asm volatile("fence rw, rw; csrr %0, cycle" : "=r"(cycle) : : "memory");
  return cycle;
#endif
}

static inline void benchmark_perf_boundary(void) {
#ifndef SPIKE
  asm volatile("fence rw, rw; rdcycle zero" ::: "memory");
#endif
}

static uint32_t benchmark_float_bits(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return bits;
}

static inline qbs_descriptor_t benchmark_make_descriptor(unsigned operation,
                                                         unsigned tile) {
  const unsigned first_row = tile * BENCH_TILE_N;
  const unsigned remaining = BENCH_ROWS - first_row;
  const unsigned tile_n = remaining < BENCH_TILE_N ? remaining : BENCH_TILE_N;
  unsigned activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
#if QBS_BENCH_ACTIVATION_CONTEXT
#if QBS_BENCH_CROSS_OP_REUSE
  if (operation == 0 && tile == 0) {
    activation_access = QBS_ACTIVATION_ACCESS_FILL;
  } else if (operation + 1 == QBS_BENCH_OPERATIONS &&
             tile + 1 == BENCH_TILES) {
    activation_access = QBS_ACTIVATION_ACCESS_RELEASE;
  } else {
    activation_access = QBS_ACTIVATION_ACCESS_REUSE;
  }
#else
  if (tile == 0) {
    activation_access = QBS_ACTIVATION_ACCESS_FILL;
  } else if (!QBS_BENCH_CONTEXT_KEEP_VALID && tile + 1 == BENCH_TILES) {
    activation_access = QBS_ACTIVATION_ACCESS_RELEASE;
  } else {
    activation_access = QBS_ACTIVATION_ACCESS_REUSE;
  }
#endif
#endif
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = BENCH_WEIGHT_PROFILE,
      .activation_profile = BENCH_ACTIVATION_PROFILE,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_layout = BENCH_ACTIVATION_LAYOUT,
      .n = (uint8_t)tile_n,
      .k_blocks = BENCH_BLOCKS,
      .activation_access = (uint8_t)activation_access,
      .context_id = 0,
      .context_generation = QBS_BENCH_ACTIVATION_CONTEXT
          ? (uint8_t)(QBS_BENCH_CONTEXT_GENERATION +
                      (QBS_BENCH_CROSS_OP_REUSE ? 0 : operation))
          : 0,
  };
  const qbs_descriptor_t descriptor = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base =
          (uintptr_t)benchmark_weight_start +
          (uintptr_t)first_row * BENCH_BLOCKS * BENCH_WEIGHT_BLOCK_BYTES,
  };
  return descriptor;
}

#if QBS_BENCH_PREFLIGHT
static qbs_status_t benchmark_preflight(void) {
  qbs_device_t device;
  qbs_status_t status = qbs_device_query(qbs_native_info, NULL, &device);
  if (status != QBS_STATUS_OK) return status;
  const qbs_capabilities_t *caps = &device.capabilities;
  if (caps->max_m < BENCH_INPUTS || caps->max_n < BENCH_TILE_N ||
      caps->max_k_blocks < BENCH_BLOCKS ||
      caps->max_results < BENCH_INPUTS * BENCH_TILE_N ||
      !(caps->activation_layouts & (UINT16_C(1) << BENCH_ACTIVATION_LAYOUT)))
    return QBS_STATUS_CAPABILITY;
  const qbs_problem_t problem = {
      .weight_profile = BENCH_WEIGHT_PROFILE,
      .activation_profile = BENCH_ACTIVATION_PROFILE,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = BENCH_USE_M8_INTERLEAVED ? QBS_ACTIVATION_STORAGE_M8_GROUPED :
          (BENCH_USE_M4_INTERLEAVED ? QBS_ACTIVATION_STORAGE_M4_GROUPED :
                                    QBS_ACTIVATION_STORAGE_ROW_MAJOR),
      .m = BENCH_INPUTS, .n = BENCH_ROWS, .k_elements = BENCH_K,
  };
  qbs_plan_t plan;
  status = qbs_plan_create(&device, &problem, &plan);
  if (status != QBS_STATUS_OK) return status;
  if (plan.split_k || plan.needs_activation_gather) return QBS_STATUS_SHAPE;
#if QBS_BENCH_ACTIVATION_CONTEXT
  if (!qbs_plan_supports_activation_context(&plan) ||
      BENCH_ACTIVATION_BYTES > caps->activation_context_capacity_bytes)
    return QBS_STATUS_CONTEXT_UNSUPPORTED;
#endif
  qbs_plan_cursor_t cursor;
  unsigned access_counts[4] = {0};
  for (unsigned operation = 0; operation < QBS_BENCH_OPERATIONS; ++operation) {
    qbs_plan_cursor_reset(&cursor);
    for (unsigned tile = 0; tile < BENCH_TILES; ++tile) {
    qbs_command_t command;
    int has_command;
    status = qbs_plan_next(&plan, &cursor, &command, &has_command);
    if (status != QBS_STATUS_OK) return status;
    const qbs_descriptor_t descriptor = benchmark_make_descriptor(operation, tile);
    const qbs_descriptor_fields_t fields = qbs_unpack_descriptor_header(descriptor.header);
    // The runtime cursor supplies geometry, not access modes. Independently
    // check this app's explicit emitter contract before any QBS command.
    const unsigned ordinal = operation * BENCH_TILES + tile;
    const unsigned first = QBS_BENCH_CROSS_OP_REUSE ? ordinal == 0 : tile == 0;
    const unsigned last = QBS_BENCH_CROSS_OP_REUSE
        ? ordinal + 1 == QBS_BENCH_OPERATIONS * BENCH_TILES
        : tile + 1 == BENCH_TILES && !QBS_BENCH_CONTEXT_KEEP_VALID;
    const unsigned access = !QBS_BENCH_ACTIVATION_CONTEXT ? QBS_ACTIVATION_ACCESS_DIRECT :
        (first ? QBS_ACTIVATION_ACCESS_FILL :
         last ? QBS_ACTIVATION_ACCESS_RELEASE : QBS_ACTIVATION_ACCESS_REUSE);
    const unsigned generation = QBS_BENCH_ACTIVATION_CONTEXT
        ? QBS_BENCH_CONTEXT_GENERATION + (QBS_BENCH_CROSS_OP_REUSE ? 0 : operation) : 0;
    if (generation > UINT8_MAX || fields.activation_access != access ||
        fields.context_id != 0 || fields.context_generation != generation ||
        fields.descriptor_version != QBS_DESCRIPTOR_VERSION ||
        fields.weight_profile != BENCH_WEIGHT_PROFILE ||
        fields.activation_profile != BENCH_ACTIVATION_PROFILE ||
        fields.weight_layout != QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR)
      return QBS_STATUS_CONTEXT_TOKEN;
    ++access_counts[access];
    if (!has_command || command.input_start != 0 || command.m != BENCH_INPUTS ||
        command.output_start != tile * BENCH_TILE_N || command.n != fields.n ||
        command.k_blocks != fields.k_blocks || command.k_block_start != 0 ||
        command.gather_activation || command.accumulate || command.activation_offset_bytes != 0 ||
        command.activation_layout != fields.activation_layout ||
        descriptor.weight_base != (uintptr_t)benchmark_weight_start + command.weight_offset_bytes)
      return QBS_STATUS_SHAPE;
    }
    qbs_command_t command;
    int has_command;
    status = qbs_plan_next(&plan, &cursor, &command, &has_command);
    if (status != QBS_STATUS_OK || has_command) return QBS_STATUS_SHAPE;
  }
  BENCH_REPORT("QBS_REAL_PREFLIGHT case=%s PASS layout=%u packed_bytes=%lu context_capacity=%u tiles=%u planned_direct=%u planned_fill=%u planned_reuse=%u planned_release=%u\n",
      BENCH_CASE_ID, BENCH_ACTIVATION_LAYOUT, (unsigned long)BENCH_ACTIVATION_BYTES,
      caps->activation_context_capacity_bytes, BENCH_TILES,
      access_counts[QBS_ACTIVATION_ACCESS_DIRECT], access_counts[QBS_ACTIVATION_ACCESS_FILL],
      access_counts[QBS_ACTIVATION_ACCESS_REUSE], access_counts[QBS_ACTIVATION_ACCESS_RELEASE]);
  return QBS_STATUS_OK;
}
#endif

#if QBS_BENCH_PREBUILT_DESCRIPTOR
static void benchmark_setup_descriptors(void) {
  for (unsigned operation = 0; operation < QBS_BENCH_OPERATIONS; ++operation)
    for (unsigned tile = 0; tile < BENCH_TILES; ++tile)
      benchmark_descriptors[operation][tile] =
          benchmark_make_descriptor(operation, tile);
  asm volatile("fence rw, rw" ::: "memory");
}
#endif

static __attribute__((noinline)) void benchmark_quantize(void) {
  const float *activation = (const float *)benchmark_activation_start;
  for (int input = 0; input < BENCH_INPUTS; ++input) {
#if BENCH_WEIGHT_Q8_0 || BENCH_WEIGHT_Q4_0 || BENCH_WEIGHT_Q5_0 || \
    BENCH_WEIGHT_IQ4_NL
    q4km_quantize_row_q8_0(
        activation + input * BENCH_K,
        quantized_activation + input * BENCH_BLOCKS, BENCH_K);
#else
    q4km_quantize_row_q8_K(
        activation + input * BENCH_K,
        quantized_activation + input * BENCH_BLOCKS, BENCH_K);
#endif
  }
}

#if BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED
static __attribute__((noinline)) qbs_status_t benchmark_pack_activation(void) {
#if BENCH_USE_M8_INTERLEAVED
  return qbs_pack_activation_m8_grouped(
      BENCH_ACTIVATION_PROFILE, quantized_activation,
      sizeof(quantized_activation), BENCH_INPUTS, BENCH_BLOCKS,
      packed_activation, sizeof(packed_activation));
#else
  return qbs_pack_activation_m4(
      BENCH_ACTIVATION_PROFILE, quantized_activation,
      sizeof(quantized_activation), BENCH_BLOCKS, packed_activation,
      sizeof(packed_activation));
#endif
}
#endif

static inline qbs_status_t benchmark_issue_qbs(
    const qbs_descriptor_t *descriptor, const void *activation, float *output,
    unsigned output_stride, unsigned n) {
#if BENCH_INPUTS == 1
  (void)output_stride;
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
  asm volatile("fence rw, rw\n"
               "li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               ".word 0x00b5045b\n"
               "mv t0, %[n]\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vse32.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2)
               : [n] "r"(n)
               : "t0", "v8", "memory");
  return QBS_STATUS_OK;
#elif BENCH_INPUTS == 2
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
  register uintptr_t a3 asm("a3") =
      (uintptr_t)(output + output_stride);
  asm volatile("fence rw, rw\n"
               "li t0, 64\n"
               "vsetvli zero, t0, e32, m2, ta, ma\n"
               ".word 0x02b5045b\n"
               "mv t0, %[n]\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vse32.v v8, (a2)\n"
               "vse32.v v9, (a3)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
               : [n] "r"(n)
               : "t0", "v8", "v9", "memory");
  return QBS_STATUS_OK;
#elif BENCH_INPUTS == 3
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
  register uintptr_t a3 asm("a3") =
      (uintptr_t)(output + output_stride);
  register uintptr_t a4 asm("a4") =
      (uintptr_t)(output + 2u * output_stride);
  asm volatile("fence rw, rw\n"
               "li t0, 128\n"
               "vsetvli zero, t0, e32, m4, ta, ma\n"
               ".word 0x04b5045b\n"
               "mv t0, %[n]\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vse32.v v8, (a2)\n"
               "vse32.v v9, (a3)\n"
               "vse32.v v10, (a4)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a4)
               : [n] "r"(n)
               : "t0", "v8", "v9", "v10", "v11", "memory");
  return QBS_STATUS_OK;
#elif BENCH_INPUTS == 4
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
  register uintptr_t a3 asm("a3") =
      (uintptr_t)(output + output_stride);
  register uintptr_t a4 asm("a4") =
      (uintptr_t)(output + 2u * output_stride);
  register uintptr_t a5 asm("a5") =
      (uintptr_t)(output + 3u * output_stride);
  asm volatile("fence rw, rw\n"
               "li t0, 128\n"
               "vsetvli zero, t0, e32, m4, ta, ma\n"
               ".word 0x06b5045b\n"
               "mv t0, %[n]\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vse32.v v8, (a2)\n"
               "vse32.v v9, (a3)\n"
               "vse32.v v10, (a4)\n"
               "vse32.v v11, (a5)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a4),
                 "+r"(a5)
               : [n] "r"(n)
               : "t0", "v8", "v9", "v10", "v11", "memory");
  return QBS_STATUS_OK;
#elif BENCH_INPUTS == 8
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
  register uintptr_t a3 asm("a3") =
      output_stride * sizeof(*output);
  asm volatile("fence rw, rw\n"
               "li t0, 256\n"
               "vsetvli zero, t0, e32, m8, ta, ma\n"
               ".word 0x0eb5045b\n"
               "mv t0, %[n]\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "mv t1, a2\n"
               "vse32.v v8, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v9, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v10, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v11, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v12, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v13, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v14, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v15, (t1)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
               : [n] "r"(n)
               : "t0", "t1", "v8", "v9", "v10", "v11", "v12",
                 "v13", "v14", "v15", "memory");
  return QBS_STATUS_OK;
#else
  return qbs_native_execute_command(NULL, descriptor, BENCH_INPUTS, activation,
                                    output, output_stride, n, 0);
#endif
}

static __attribute__((noinline)) uint64_t benchmark_qbs(unsigned operation) {
  for (unsigned tile = 0; tile < BENCH_TILES; ++tile) {
    const unsigned first_row = tile * BENCH_TILE_N;
    const unsigned remaining = BENCH_ROWS - first_row;
    const unsigned tile_n = remaining < BENCH_TILE_N ? remaining : BENCH_TILE_N;
#if QBS_BENCH_PREBUILT_DESCRIPTOR
    const qbs_descriptor_t *descriptor =
        &benchmark_descriptors[operation][tile];
#else
    const qbs_descriptor_t descriptor_value __attribute__((aligned(16))) =
        benchmark_make_descriptor(operation, tile);
    const qbs_descriptor_t *descriptor = &descriptor_value;
#endif
#if BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED
    const void *activation = packed_activation;
#else
    const void *activation = quantized_activation;
#endif
    benchmark_execution_status = benchmark_issue_qbs(
        descriptor, activation,
        benchmark_output + operation * BENCH_OUTPUTS + first_row, BENCH_ROWS,
        tile_n);
    if (benchmark_execution_status != QBS_STATUS_OK) break;
  }

  const uint64_t quantization_input_bytes =
      (!QBS_BENCH_CROSS_OP_REUSE || operation == 0)
          ? (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float)
          : 0;
  const uint64_t descriptor_bytes =
      (uint64_t)BENCH_TILES * sizeof(qbs_descriptor_t);
  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
#if BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED
  const uint64_t activation_bytes =
      (uint64_t)(QBS_BENCH_ACTIVATION_CONTEXT
                     ? (!QBS_BENCH_CROSS_OP_REUSE || operation == 0)
                     : BENCH_TILES) * BENCH_PACKED_ACTIVATION_ROWS * BENCH_BLOCKS *
      sizeof(benchmark_activation_block_t);
#else
  const uint64_t activation_bytes =
      (uint64_t)(QBS_BENCH_ACTIVATION_CONTEXT
                     ? (!QBS_BENCH_CROSS_OP_REUSE || operation == 0)
                     : BENCH_TILES) *
      BENCH_Q8_BLOCKS *
      sizeof(benchmark_activation_block_t);
#endif
  return quantization_input_bytes + descriptor_bytes + weight_bytes +
         activation_bytes;
}

static float benchmark_actual(unsigned operation, int input, int row) {
  return benchmark_output[operation * BENCH_OUTPUTS + input * BENCH_ROWS + row];
}

static __attribute__((noinline)) int benchmark_validate(
    float *max_abs_out, float *max_rel_out, uint64_t *checksum_out) {
  const float *golden = (const float *)benchmark_golden_start;
  int mismatches = 0;
  float max_abs = 0.0f;
  float max_rel = 0.0f;
  uint64_t checksum = 1469598103934665603ull;
  for (unsigned operation = 0; operation < QBS_BENCH_OPERATIONS;
       ++operation) {
    for (int input = 0; input < BENCH_INPUTS; ++input) {
      for (int row = 0; row < BENCH_ROWS; ++row) {
        const int index = input * BENCH_ROWS + row;
        const float actual = benchmark_actual(operation, input, row);
        const float reference = golden[index];
        const uint32_t bits = benchmark_float_bits(actual);
        const uint32_t reference_bits = benchmark_float_bits(reference);
        // NaN comparisons are false; reject nonfinite values before tolerance arithmetic.
        if ((bits & 0x7f800000u) == 0x7f800000u ||
            (reference_bits & 0x7f800000u) == 0x7f800000u) {
          const uint32_t infinity_bits = 0x7f800000u;
          ++mismatches;
          memcpy(&max_abs, &infinity_bits, sizeof(max_abs));
          memcpy(&max_rel, &infinity_bits, sizeof(max_rel));
        } else {
          float absolute = actual - reference;
          if (absolute < 0.0f) absolute = -absolute;
          const float magnitude = reference < 0.0f ? -reference : reference;
          const float relative =
              absolute / (magnitude > 1.0e-12f ? magnitude : 1.0e-12f);
          if (absolute > max_abs) max_abs = absolute;
          if (relative > max_rel) max_rel = relative;
          if (absolute > BENCH_ATOL + BENCH_RTOL * magnitude) ++mismatches;
        }
        for (int byte = 0; byte < 4; ++byte) {
          checksum ^= (bits >> (8 * byte)) & 0xffu;
          checksum *= 1099511628211ull;
        }
      }
    }
  }
  *max_abs_out = max_abs;
  *max_rel_out = max_rel;
  *checksum_out = checksum;
  return mismatches;
}

#if QBS_BENCH_INDEPENDENT_ORACLE
static int benchmark_validate_independent(void) {
  const float *oracle = (const float *)benchmark_oracle_start;
  unsigned quant_byte_mismatches = 0, output_mismatches = 0;
  float max_abs = 0;
  for (unsigned byte = 0; byte < sizeof(quantized_activation); ++byte)
    quant_byte_mismatches += ((const uint8_t *)quantized_activation)[byte] !=
        benchmark_expected_q8_start[byte];
  for (unsigned i = 0; i < BENCH_OUTPUTS; ++i) {
    const float actual = benchmark_output[i], expected = oracle[i];
    if ((benchmark_float_bits(actual) & 0x7f800000u) == 0x7f800000u ||
        (benchmark_float_bits(expected) & 0x7f800000u) == 0x7f800000u) {
      ++output_mismatches;
      continue;
    }
    const float delta = actual - expected;
    const float error = delta < 0 ? -delta : delta;
    const float magnitude = expected < 0 ? -expected : expected;
    if (error > max_abs) max_abs = error;
    if (error > 2.0e-4f + 2.0e-5f * magnitude) ++output_mismatches;
  }
  BENCH_REPORT("QBS_REAL_ORACLE case=%s outputs=%u quant_byte_mismatches=%u mismatches=%u max_abs_bits=0x%x kind=scalar_fp64_offline\n",
      BENCH_CASE_ID, BENCH_OUTPUTS, quant_byte_mismatches, output_mismatches,
      benchmark_float_bits(max_abs));
  return quant_byte_mismatches != 0 || output_mismatches != 0;
}
#endif

int main(void) {
  const uint64_t expected_weight_bytes =
      (uint64_t)((BENCH_ROWS + 3) & ~3) * BENCH_BLOCKS *
      BENCH_WEIGHT_BLOCK_BYTES;
  if ((uint64_t)(benchmark_weight_end - benchmark_weight_start) !=
          expected_weight_bytes ||
      (int)(benchmark_activation_end - benchmark_activation_start) !=
          BENCH_INPUTS * BENCH_K * 4 ||
      (int)(benchmark_golden_end - benchmark_golden_start) !=
          BENCH_OUTPUTS * 4) {
#ifdef SPIKE
    printstr(BENCH_CASE_ID ": invalid embedded data\n");
#else
    BENCH_REPORT("QBS_REAL_BENCH %s FAIL reason=data_size\n", BENCH_CASE_ID);
#endif
    return 1;
  }

#if QBS_BENCH_INDEPENDENT_ORACLE
  if (benchmark_oracle_end - benchmark_oracle_start != BENCH_OUTPUTS * 4 ||
      benchmark_expected_q8_end - benchmark_expected_q8_start != sizeof(quantized_activation))
    return 1;
  for (unsigned i = 0; i < BENCH_TOTAL_OUTPUTS; ++i) {
    const uint32_t poison = 0x7fc00001u;
    memcpy(&benchmark_output[i], &poison, sizeof(poison));
  }
#else
  memset(benchmark_output, 0, sizeof(benchmark_output));
#endif
#if QBS_BENCH_PREFLIGHT
  benchmark_execution_status = benchmark_preflight();
  if (benchmark_execution_status != QBS_STATUS_OK) {
    BENCH_REPORT("QBS_REAL_BENCH %s FAIL reason=capability qbs_status=%u\n",
                 BENCH_CASE_ID, (unsigned)benchmark_execution_status);
    return 1;
  }
#endif

#if QBS_BENCH_PREBUILT_DESCRIPTOR
  benchmark_setup_descriptors();
#endif
  HW_CNT_READY
  HW_CNT_PHASE(BENCH_PHASE_QUANTIZE);
  benchmark_perf_boundary();
  const uint64_t start = benchmark_cycle();
  benchmark_quantize();
  const uint64_t quantize_end = benchmark_cycle();
#if BENCH_USE_M4_INTERLEAVED || BENCH_USE_M8_INTERLEAVED
  HW_CNT_PHASE(BENCH_PHASE_PACK);
  benchmark_execution_status = benchmark_pack_activation();
  const uint64_t pack_end = benchmark_cycle();
#else
  const uint64_t pack_end = quantize_end;
#endif
  HW_CNT_PHASE(BENCH_PHASE_MATMUL);
  const uint64_t matmul_start = pack_end;
  uint64_t logical_read_bytes = benchmark_execution_status == QBS_STATUS_OK
      ? benchmark_qbs(0)
      : 0;
  const uint64_t matmul_end = benchmark_cycle();
  uint64_t quantize_cycles = quantize_end - start;
  const uint64_t pack_cycles = pack_end - quantize_end;
  uint64_t matmul_cycles = matmul_end - matmul_start;
  uint64_t compute_cycles = matmul_end - start;
#if QBS_BENCH_OPERATIONS > 1
  uint64_t chain_end = matmul_end;
  for (unsigned operation = 1; operation < QBS_BENCH_OPERATIONS;
       ++operation) {
    if (benchmark_execution_status != QBS_STATUS_OK) break;
#if !QBS_BENCH_CROSS_OP_REUSE
    HW_CNT_PHASE(BENCH_PHASE_QUANTIZE);
    const uint64_t operation_quantize_start = benchmark_cycle();
    benchmark_quantize();
    const uint64_t operation_quantize_end = benchmark_cycle();
    quantize_cycles += operation_quantize_end - operation_quantize_start;
#endif
    HW_CNT_PHASE(BENCH_PHASE_MATMUL);
    logical_read_bytes += benchmark_qbs(operation);
    chain_end = benchmark_cycle();
  }
  matmul_cycles = chain_end - start - quantize_cycles - pack_cycles;
  compute_cycles = chain_end - start;
#endif
  benchmark_perf_boundary();
  HW_CNT_NOT_READY

  float max_abs;
  float max_rel;
  uint64_t checksum;
  const int mismatches = benchmark_validate(&max_abs, &max_rel, &checksum);
  int passed =
      mismatches == 0 && benchmark_execution_status == QBS_STATUS_OK;
#if QBS_BENCH_INDEPENDENT_ORACLE
  if (benchmark_validate_independent()) passed = 0;
#endif
  benchmark_last_compute_cycles = compute_cycles;
  BENCH_REPORT(
      "QBS_REAL_BENCH case=%s result=%s k=%d rows=%d inputs=%d outputs=%d "
      "tiles=%d operations=%d outputs_per_operation=%d result_count=%d "
      "quantizations=%d cross_op_reuse=%d "
      "timing_scope=%s setup_included=%d timed_cycles=%lu "
      "activation_context=%d context_generation=%d "
      "timed_cycles_per_output_x1000=%lu descriptor_setup_cycles=0 "
      "descriptor_setup_cycles_valid=0 compute_cycles=%lu "
      "cycles_per_output_x1000=%lu quantize_cycles=%lu pack_cycles=%lu "
      "matmul_cycles=%lu "
      "logical_read_bytes=%lu checksum=0x%lx mismatches=%d "
      "max_abs_bits=0x%x max_rel_bits=0x%x qbs_status=%u\n",
      BENCH_CASE_ID, passed ? "PASS" : "FAIL", BENCH_K,
      BENCH_ROWS, BENCH_INPUTS, BENCH_OUTPUTS, BENCH_TILES,
      QBS_BENCH_OPERATIONS, BENCH_OUTPUTS, BENCH_TOTAL_OUTPUTS,
      QBS_BENCH_CROSS_OP_REUSE ? 1 : QBS_BENCH_OPERATIONS,
      QBS_BENCH_CROSS_OP_REUSE,
      QBS_BENCH_TIMING_SCOPE, !QBS_BENCH_PREBUILT_DESCRIPTOR,
      (unsigned long)compute_cycles,
      QBS_BENCH_ACTIVATION_CONTEXT,
      QBS_BENCH_ACTIVATION_CONTEXT ? QBS_BENCH_CONTEXT_GENERATION : 0,
      (unsigned long)(compute_cycles * 1000 / BENCH_TOTAL_OUTPUTS),
      (unsigned long)compute_cycles,
      (unsigned long)(compute_cycles * 1000 / BENCH_TOTAL_OUTPUTS),
      (unsigned long)quantize_cycles, (unsigned long)pack_cycles,
      (unsigned long)matmul_cycles,
      (unsigned long)logical_read_bytes, (unsigned long)checksum, mismatches,
      benchmark_float_bits(max_abs), benchmark_float_bits(max_rel),
      (unsigned)benchmark_execution_status);
#ifdef SPIKE
  printstr(BENCH_CASE_ID);
  printstr(passed ? ": PASS\n" : ": FAIL\n");
#endif
  return !passed;
}

#endif
