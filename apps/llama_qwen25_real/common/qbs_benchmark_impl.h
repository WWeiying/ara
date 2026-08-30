#ifndef LLAMA_QWEN25_REAL_QBS_BENCHMARK_IMPL_H_
#define LLAMA_QWEN25_REAL_QBS_BENCHMARK_IMPL_H_

#include "../../common/qbs_abi.h"
#include "../../common/runtime.h"
#include "../../llama_q4k_repack_bench/repack_kernels.h"

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

#if QBS_BENCH_PREBUILT_DESCRIPTOR
#define QBS_BENCH_TIMING_SCOPE "prebuilt_descriptor"
#else
#define QBS_BENCH_TIMING_SCOPE "production_command"
#endif

// Existing Q6_K apps predate explicit one-hot format macros and only set
// BENCH_WEIGHT_Q4=0. Preserve that source contract.
#if !(BENCH_WEIGHT_Q3 || BENCH_WEIGHT_Q4 || BENCH_WEIGHT_Q5 || \
      BENCH_WEIGHT_Q6 || BENCH_WEIGHT_Q8_0)
#undef BENCH_WEIGHT_Q6
#define BENCH_WEIGHT_Q6 1
#endif

#if (BENCH_WEIGHT_Q3 + BENCH_WEIGHT_Q4 + BENCH_WEIGHT_Q5 + \
     BENCH_WEIGHT_Q6 + BENCH_WEIGHT_Q8_0) != 1
#error "select exactly one QBS weight format"
#endif

#if BENCH_WEIGHT_Q3
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
#else
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q8_0_WEIGHT
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q8_0_WEIGHT_BLOCK_BYTES
#define BENCH_BLOCK_ELEMENTS QBS_Q8_0_WEIGHT_BLOCK_ELEMENTS
#endif

#if BENCH_WEIGHT_Q8_0
typedef block_q8_0 benchmark_activation_block_t;
#define BENCH_ACTIVATION_PROFILE QBS_ACTIVATION_PROFILE_Q8_0
#else
typedef block_q8_K benchmark_activation_block_t;
#define BENCH_ACTIVATION_PROFILE QBS_ACTIVATION_PROFILE_Q8_K
#endif

#define BENCH_BLOCKS (BENCH_K / BENCH_BLOCK_ELEMENTS)
#define BENCH_TILES ((BENCH_ROWS + QBS_MAX_N - 1) / QBS_MAX_N)
#define BENCH_Q8_BLOCKS (BENCH_INPUTS * BENCH_BLOCKS)
#define BENCH_OUTPUTS (BENCH_INPUTS * BENCH_ROWS)

#if BENCH_INPUTS == 4 && !BENCH_WEIGHT_Q8_0
#define BENCH_USE_M4_INTERLEAVED 1
#define BENCH_ACTIVATION_LAYOUT QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
#else
#define BENCH_USE_M4_INTERLEAVED 0
#define BENCH_ACTIVATION_LAYOUT QBS_ACTIVATION_LAYOUT_ROW_MAJOR
#endif

_Static_assert(BENCH_K > 0 && BENCH_K % BENCH_BLOCK_ELEMENTS == 0,
               "QBS K must align to the selected weight block");
_Static_assert(BENCH_BLOCKS <= QBS_MAX_K_BLOCKS,
               "QBS K block count exceeds the ABI limit");
_Static_assert(BENCH_ROWS > 0, "QBS requires at least one output row");
_Static_assert(BENCH_INPUTS >= 1 && BENCH_INPUTS <= QBS_MAX_M,
               "QBS M must be in [1,4]");
_Static_assert(VLEN >= QBS_MAX_N * 32,
               "this benchmark requires 32 FP32 results per context");
#if QBS_BENCH_ACTIVATION_CONTEXT
_Static_assert(BENCH_INPUTS == 1,
               "activation context supports only M=1");
_Static_assert(BENCH_ACTIVATION_PROFILE == QBS_ACTIVATION_PROFILE_Q8_K,
               "activation context supports only Q8_K");
_Static_assert(BENCH_BLOCKS <= QBS_ACTIVATION_CONTEXT_MAX_K_BLOCKS,
               "activation context K exceeds context capacity");
_Static_assert(BENCH_TILES >= 2,
               "activation context requires at least two output tiles");
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

static benchmark_activation_block_t quantized_activation[BENCH_Q8_BLOCKS]
    __attribute__((aligned(64), section(".bss")));
#if BENCH_USE_M4_INTERLEAVED
static block_q8_Kx4 packed_activation[BENCH_BLOCKS]
    __attribute__((aligned(64), section(".bss")));
#endif
#if QBS_BENCH_PREBUILT_DESCRIPTOR
static qbs_descriptor_t benchmark_descriptors[BENCH_TILES]
    __attribute__((aligned(64), section(".bss")));
#endif
static float benchmark_output[BENCH_OUTPUTS]
    __attribute__((aligned(64), section(".bss")));

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

static inline qbs_descriptor_t benchmark_make_descriptor(unsigned tile) {
  const unsigned first_row = tile * QBS_MAX_N;
  const unsigned remaining = BENCH_ROWS - first_row;
  const unsigned tile_n = remaining < QBS_MAX_N ? remaining : QBS_MAX_N;
  unsigned activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
#if QBS_BENCH_ACTIVATION_CONTEXT
  if (tile == 0) {
    activation_access = QBS_ACTIVATION_ACCESS_FILL;
  } else if (!QBS_BENCH_CONTEXT_KEEP_VALID && tile + 1 == BENCH_TILES) {
    activation_access = QBS_ACTIVATION_ACCESS_RELEASE;
  } else {
    activation_access = QBS_ACTIVATION_ACCESS_REUSE;
  }
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
          ? QBS_BENCH_CONTEXT_GENERATION : 0,
  };
  const qbs_descriptor_t descriptor = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base =
          (uintptr_t)benchmark_weight_start +
          (uintptr_t)first_row * BENCH_BLOCKS * BENCH_WEIGHT_BLOCK_BYTES,
  };
  return descriptor;
}

#if QBS_BENCH_PREBUILT_DESCRIPTOR
static void benchmark_setup_descriptors(void) {
  for (unsigned tile = 0; tile < BENCH_TILES; ++tile)
    benchmark_descriptors[tile] = benchmark_make_descriptor(tile);
  asm volatile("fence rw, rw" ::: "memory");
}
#endif

static __attribute__((noinline)) void benchmark_quantize(void) {
  const float *activation = (const float *)benchmark_activation_start;
  for (int input = 0; input < BENCH_INPUTS; ++input) {
#if BENCH_WEIGHT_Q8_0
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

#if BENCH_USE_M4_INTERLEAVED
static __attribute__((noinline)) void benchmark_pack_activation(void) {
  for (unsigned block = 0; block < BENCH_BLOCKS; ++block) {
    for (unsigned input = 0; input < 4; ++input)
      packed_activation[block].d[input] =
          quantized_activation[input * BENCH_BLOCKS + block].d;
    for (unsigned element = 0; element < QK_K; ++element) {
      for (unsigned input = 0; input < 4; ++input) {
        packed_activation[block].qs[element * 4 + input] =
            quantized_activation[input * BENCH_BLOCKS + block].qs[element];
      }
    }
    for (unsigned sub_block = 0; sub_block < QK_K / 16; ++sub_block) {
      const unsigned group = sub_block / 2;
      const unsigned half = sub_block & 1;
      for (unsigned input = 0; input < 4; ++input) {
        packed_activation[block].bsums[group * 8 + half * 4 + input] =
            quantized_activation[input * BENCH_BLOCKS + block]
                .bsums[sub_block];
      }
    }
  }
}
#endif

static inline void benchmark_issue_qbs(const qbs_descriptor_t *descriptor,
                                       const void *activation, float *output,
                                       unsigned output_stride, unsigned n) {
#if BENCH_INPUTS == 1
  (void)output_stride;
#endif
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
#if BENCH_INPUTS == 1
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
#elif BENCH_INPUTS == 2
  register uintptr_t a3 asm("a3") = (uintptr_t)(output + output_stride);
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
#elif BENCH_INPUTS == 3
  register uintptr_t a3 asm("a3") = (uintptr_t)(output + output_stride);
  register uintptr_t a4 asm("a4") = (uintptr_t)(output + 2 * output_stride);
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
#else
  register uintptr_t a3 asm("a3") = (uintptr_t)(output + output_stride);
  register uintptr_t a4 asm("a4") = (uintptr_t)(output + 2 * output_stride);
  register uintptr_t a5 asm("a5") = (uintptr_t)(output + 3 * output_stride);
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
#endif
}

static __attribute__((noinline)) uint64_t benchmark_qbs(void) {
  for (unsigned tile = 0; tile < BENCH_TILES; ++tile) {
    const unsigned first_row = tile * QBS_MAX_N;
    const unsigned remaining = BENCH_ROWS - first_row;
    const unsigned tile_n = remaining < QBS_MAX_N ? remaining : QBS_MAX_N;
#if QBS_BENCH_PREBUILT_DESCRIPTOR
    const qbs_descriptor_t *descriptor = &benchmark_descriptors[tile];
#else
    const qbs_descriptor_t descriptor_value __attribute__((aligned(16))) =
        benchmark_make_descriptor(tile);
    const qbs_descriptor_t *descriptor = &descriptor_value;
#endif
#if BENCH_USE_M4_INTERLEAVED
    const void *activation = packed_activation;
#else
    const void *activation = quantized_activation;
#endif
    benchmark_issue_qbs(descriptor, activation,
                        benchmark_output + first_row, BENCH_ROWS, tile_n);
  }

  const uint64_t quantization_input_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float);
  const uint64_t descriptor_bytes =
      (uint64_t)BENCH_TILES * sizeof(qbs_descriptor_t);
  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
#if BENCH_USE_M4_INTERLEAVED
  const uint64_t activation_bytes =
      (uint64_t)BENCH_TILES * BENCH_BLOCKS * sizeof(block_q8_Kx4);
#else
  const uint64_t activation_bytes =
      (uint64_t)(QBS_BENCH_ACTIVATION_CONTEXT ? 1 : BENCH_TILES) *
      BENCH_Q8_BLOCKS *
      sizeof(benchmark_activation_block_t);
#endif
  return quantization_input_bytes + descriptor_bytes + weight_bytes +
         activation_bytes;
}

static float benchmark_actual(int input, int row) {
  return benchmark_output[input * BENCH_ROWS + row];
}

static __attribute__((noinline)) int benchmark_validate(
    float *max_abs_out, float *max_rel_out, uint64_t *checksum_out) {
  const float *golden = (const float *)benchmark_golden_start;
  int mismatches = 0;
  float max_abs = 0.0f;
  float max_rel = 0.0f;
  uint64_t checksum = 1469598103934665603ull;
  for (int input = 0; input < BENCH_INPUTS; ++input) {
    for (int row = 0; row < BENCH_ROWS; ++row) {
      const int index = input * BENCH_ROWS + row;
      const float actual = benchmark_actual(input, row);
      const float reference = golden[index];
      float absolute = actual - reference;
      if (absolute < 0.0f) absolute = -absolute;
      const float magnitude = reference < 0.0f ? -reference : reference;
      const float relative =
          absolute / (magnitude > 1.0e-12f ? magnitude : 1.0e-12f);
      if (absolute > max_abs) max_abs = absolute;
      if (relative > max_rel) max_rel = relative;
      if (absolute > BENCH_ATOL + BENCH_RTOL * magnitude) ++mismatches;
      const uint32_t bits = benchmark_float_bits(actual);
      for (int byte = 0; byte < 4; ++byte) {
        checksum ^= (bits >> (8 * byte)) & 0xffu;
        checksum *= 1099511628211ull;
      }
    }
  }
  *max_abs_out = max_abs;
  *max_rel_out = max_rel;
  *checksum_out = checksum;
  return mismatches;
}

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

  memset(benchmark_output, 0, sizeof(benchmark_output));
#if QBS_BENCH_PREBUILT_DESCRIPTOR
  benchmark_setup_descriptors();
#endif
  HW_CNT_READY
  HW_CNT_PHASE(BENCH_PHASE_QUANTIZE);
  benchmark_perf_boundary();
  const uint64_t start = benchmark_cycle();
  benchmark_quantize();
  const uint64_t quantize_end = benchmark_cycle();
#if BENCH_USE_M4_INTERLEAVED
  HW_CNT_PHASE(BENCH_PHASE_PACK);
  benchmark_pack_activation();
  const uint64_t pack_end = benchmark_cycle();
#else
  const uint64_t pack_end = quantize_end;
#endif
  HW_CNT_PHASE(BENCH_PHASE_MATMUL);
  const uint64_t matmul_start = pack_end;
  const uint64_t logical_read_bytes = benchmark_qbs();
  const uint64_t matmul_end = benchmark_cycle();
  const uint64_t quantize_cycles = quantize_end - start;
  const uint64_t pack_cycles = pack_end - quantize_end;
  const uint64_t matmul_cycles = matmul_end - matmul_start;
  const uint64_t compute_cycles = matmul_end - start;
  benchmark_perf_boundary();
  HW_CNT_NOT_READY

  float max_abs;
  float max_rel;
  uint64_t checksum;
  const int mismatches = benchmark_validate(&max_abs, &max_rel, &checksum);
  BENCH_REPORT(
      "QBS_REAL_BENCH case=%s result=%s k=%d rows=%d inputs=%d outputs=%d "
      "tiles=%d timing_scope=%s setup_included=%d timed_cycles=%lu "
      "activation_context=%d context_generation=%d "
      "timed_cycles_per_output_x1000=%lu descriptor_setup_cycles=0 "
      "descriptor_setup_cycles_valid=0 compute_cycles=%lu "
      "cycles_per_output_x1000=%lu quantize_cycles=%lu pack_cycles=%lu "
      "matmul_cycles=%lu "
      "logical_read_bytes=%lu checksum=0x%lx mismatches=%d "
      "max_abs_bits=0x%x max_rel_bits=0x%x\n",
      BENCH_CASE_ID, mismatches == 0 ? "PASS" : "FAIL", BENCH_K,
      BENCH_ROWS, BENCH_INPUTS, BENCH_OUTPUTS, BENCH_TILES,
      QBS_BENCH_TIMING_SCOPE, !QBS_BENCH_PREBUILT_DESCRIPTOR,
      (unsigned long)compute_cycles,
      QBS_BENCH_ACTIVATION_CONTEXT,
      QBS_BENCH_ACTIVATION_CONTEXT ? QBS_BENCH_CONTEXT_GENERATION : 0,
      (unsigned long)(compute_cycles * 1000 / BENCH_OUTPUTS),
      (unsigned long)compute_cycles,
      (unsigned long)(compute_cycles * 1000 / BENCH_OUTPUTS),
      (unsigned long)quantize_cycles, (unsigned long)pack_cycles,
      (unsigned long)matmul_cycles,
      (unsigned long)logical_read_bytes, (unsigned long)checksum, mismatches,
      benchmark_float_bits(max_abs), benchmark_float_bits(max_rel));
#ifdef SPIKE
  printstr(BENCH_CASE_ID);
  printstr(mismatches == 0 ? ": PASS\n" : ": FAIL\n");
#endif
  return mismatches != 0;
}

#endif
