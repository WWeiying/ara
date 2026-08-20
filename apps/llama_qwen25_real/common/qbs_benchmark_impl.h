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

#define BENCH_BLOCKS (BENCH_K / QK_K)
#define BENCH_TILES ((BENCH_ROWS + QBS_MAX_N - 1) / QBS_MAX_N)
#define BENCH_Q8_BLOCKS (BENCH_INPUTS * BENCH_BLOCKS)
#define BENCH_OUTPUT_STRIDE (BENCH_INPUTS * QBS_MAX_N)
#define BENCH_OUTPUT_STORAGE (BENCH_TILES * BENCH_OUTPUT_STRIDE)
#define BENCH_OUTPUTS (BENCH_INPUTS * BENCH_ROWS)

#if BENCH_WEIGHT_Q4
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q4_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q4_K_BLOCK_BYTES
#else
#define BENCH_WEIGHT_PROFILE QBS_WEIGHT_PROFILE_Q6_K
#define BENCH_WEIGHT_BLOCK_BYTES QBS_Q6_K_BLOCK_BYTES
#endif

_Static_assert(BENCH_K > 0 && BENCH_K % QK_K == 0,
               "QBS K must be a positive multiple of 256");
_Static_assert(BENCH_BLOCKS <= QBS_MAX_K_BLOCKS,
               "QBS K block count exceeds the ABI limit");
_Static_assert(BENCH_ROWS > 0, "QBS requires at least one output row");
_Static_assert(BENCH_INPUTS >= 1 && BENCH_INPUTS <= QBS_MAX_M,
               "QBS M must be in [1,4]");
_Static_assert(VLEN >= QBS_MAX_N * 32,
               "this benchmark requires 32 FP32 results per context");

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

static block_q8_K quantized_activation[BENCH_Q8_BLOCKS]
    __attribute__((aligned(64), section(".bss")));
static qbs_descriptor_v1_t benchmark_descriptors[BENCH_TILES]
    __attribute__((aligned(64), section(".bss")));
static float benchmark_output[BENCH_OUTPUT_STORAGE]
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

static void benchmark_setup_descriptors(void) {
  for (unsigned tile = 0; tile < BENCH_TILES; ++tile) {
    const unsigned first_row = tile * QBS_MAX_N;
    const unsigned remaining = BENCH_ROWS - first_row;
    const unsigned tile_n = remaining < QBS_MAX_N ? remaining : QBS_MAX_N;
    const qbs_descriptor_fields_t fields = {
        .descriptor_version = QBS_DESCRIPTOR_VERSION,
        .weight_profile = BENCH_WEIGHT_PROFILE,
        .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
        .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
        .n = (uint8_t)tile_n,
        .k_blocks = BENCH_BLOCKS,
    };
    benchmark_descriptors[tile].header = qbs_pack_descriptor_header(&fields);
    benchmark_descriptors[tile].weight_base =
        (uintptr_t)benchmark_weight_start +
        (uintptr_t)first_row * BENCH_BLOCKS * BENCH_WEIGHT_BLOCK_BYTES;
  }
  asm volatile("fence rw, rw" ::: "memory");
}

static __attribute__((noinline)) void benchmark_quantize(void) {
  const float *activation = (const float *)benchmark_activation_start;
  for (int input = 0; input < BENCH_INPUTS; ++input) {
    q4km_quantize_row_q8_K(
        activation + input * BENCH_K,
        quantized_activation + input * BENCH_BLOCKS, BENCH_K);
  }
}

static inline void benchmark_set_qbs_vl(void) {
#if BENCH_INPUTS == 1
  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               : : : "t0", "memory");
#elif BENCH_INPUTS == 2
  asm volatile("li t0, 64\n"
               "vsetvli zero, t0, e32, m2, ta, ma\n"
               : : : "t0", "memory");
#elif BENCH_INPUTS == 3
  asm volatile("li t0, 96\n"
               "vsetvli zero, t0, e32, m4, ta, ma\n"
               : : : "t0", "memory");
#else
  asm volatile("li t0, 128\n"
               "vsetvli zero, t0, e32, m4, ta, ma\n"
               : : : "t0", "memory");
#endif
}

static inline void benchmark_issue_qbs(const qbs_descriptor_v1_t *descriptor,
                                       const block_q8_K *activation,
                                       float *output) {
  register uintptr_t a0 asm("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)output;
#if BENCH_INPUTS == 1
  asm volatile(".word 0x00b5045b\n"
               "vse32.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2) : : "memory");
#elif BENCH_INPUTS == 2
  asm volatile(".word 0x02b5045b\n"
               "vse32.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2) : : "memory");
#elif BENCH_INPUTS == 3
  asm volatile(".word 0x04b5045b\n"
               "vse32.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2) : : "memory");
#else
  asm volatile(".word 0x06b5045b\n"
               "vse32.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2) : : "memory");
#endif
}

static __attribute__((noinline)) uint64_t benchmark_qbs(void) {
  benchmark_set_qbs_vl();
  for (unsigned tile = 0; tile < BENCH_TILES; ++tile) {
    benchmark_issue_qbs(&benchmark_descriptors[tile], quantized_activation,
                        benchmark_output + tile * BENCH_OUTPUT_STRIDE);
  }

  const uint64_t quantization_input_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float);
  const uint64_t descriptor_bytes =
      (uint64_t)BENCH_TILES * sizeof(qbs_descriptor_v1_t);
  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
  const uint64_t activation_bytes =
      (uint64_t)BENCH_TILES * BENCH_Q8_BLOCKS * sizeof(block_q8_K);
  return quantization_input_bytes + descriptor_bytes + weight_bytes +
         activation_bytes;
}

static float benchmark_actual(int input, int row) {
  const int tile = row / QBS_MAX_N;
  const int lane = row % QBS_MAX_N;
  return benchmark_output[tile * BENCH_OUTPUT_STRIDE +
                          input * QBS_MAX_N + lane];
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
  benchmark_setup_descriptors();
  HW_CNT_READY
  HW_CNT_PHASE(BENCH_PHASE_QUANTIZE);
  benchmark_perf_boundary();
  const uint64_t start = benchmark_cycle();
  benchmark_quantize();
  const uint64_t quantize_end = benchmark_cycle();
  HW_CNT_PHASE(BENCH_PHASE_MATMUL);
  const uint64_t matmul_start = benchmark_cycle();
  const uint64_t logical_read_bytes = benchmark_qbs();
  const uint64_t matmul_end = benchmark_cycle();
  const uint64_t quantize_cycles = quantize_end - start;
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
      "tiles=%d compute_cycles=%lu cycles_per_output_x1000=%lu "
      "quantize_cycles=%lu pack_cycles=0 matmul_cycles=%lu "
      "logical_read_bytes=%lu checksum=0x%lx mismatches=%d "
      "max_abs_bits=0x%x max_rel_bits=0x%x\n",
      BENCH_CASE_ID, mismatches == 0 ? "PASS" : "FAIL", BENCH_K,
      BENCH_ROWS, BENCH_INPUTS, BENCH_OUTPUTS, BENCH_TILES,
      (unsigned long)compute_cycles,
      (unsigned long)(compute_cycles * 1000 / BENCH_OUTPUTS),
      (unsigned long)quantize_cycles, (unsigned long)matmul_cycles,
      (unsigned long)logical_read_bytes, (unsigned long)checksum, mismatches,
      benchmark_float_bits(max_abs), benchmark_float_bits(max_rel));
#ifdef SPIKE
  printstr(BENCH_CASE_ID);
  printstr(mismatches == 0 ? ": PASS\n" : ": FAIL\n");
#endif
  return mismatches != 0;
}

#endif
