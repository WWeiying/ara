#ifndef LLAMA_QWEN25_REAL_BENCHMARK_IMPL_H_
#define LLAMA_QWEN25_REAL_BENCHMARK_IMPL_H_

#include "../../common/runtime.h"
#include "../../llama_q4k_repack_bench/repack_kernels.h"

#ifdef SPIKE
extern void printstr(const char *string);
#define BENCH_REPORT(...) do { } while (0)
#else
#include "printf.h"
#define BENCH_REPORT(...) printf(__VA_ARGS__)
#endif

#include <stdint.h>
#include <string.h>

// Pull the same RVV kernels used by the existing standalone comparison into
// each independently linked real-model case.
void q4km_quantize_row_q8_K(const float *x, block_q8_K *y, int64_t k)
    __attribute__((noinline));
void q4km_quantize_row_q8_0(const float *x, block_q8_0 *y, int64_t k)
    __attribute__((noinline));
float q4km_vec_dot_q3_K_q8_K(const block_q3_K *x, const block_q8_K *y, int n)
    __attribute__((noinline));
float q4km_vec_dot_q4_K_q8_K(const block_q4_K *x, const block_q8_K *y, int n)
    __attribute__((noinline));
float q4km_vec_dot_q5_K_q8_K(const block_q5_K *x, const block_q8_K *y, int n)
    __attribute__((noinline));
float q4km_vec_dot_q6_K_q8_K(const block_q6_K *x, const block_q8_K *y, int n)
    __attribute__((noinline));
float q4km_vec_dot_q8_0_q8_0(const block_q8_0 *x, const block_q8_0 *y, int n)
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

#if !(BENCH_WEIGHT_Q3 || BENCH_WEIGHT_Q4 || BENCH_WEIGHT_Q5 || \
      BENCH_WEIGHT_Q6 || BENCH_WEIGHT_Q8_0)
#undef BENCH_WEIGHT_Q6
#define BENCH_WEIGHT_Q6 1
#endif

#if (BENCH_WEIGHT_Q3 + BENCH_WEIGHT_Q4 + BENCH_WEIGHT_Q5 + \
     BENCH_WEIGHT_Q6 + BENCH_WEIGHT_Q8_0) != 1
#error "select exactly one RVV weight format"
#endif

#if BENCH_WEIGHT_Q8_0
#define BENCH_BLOCK_ELEMENTS QK8_0
typedef block_q8_0 benchmark_activation_block_t;
#else
#define BENCH_BLOCK_ELEMENTS QK_K
typedef block_q8_K benchmark_activation_block_t;
#endif

#define BENCH_BLOCKS (BENCH_K / BENCH_BLOCK_ELEMENTS)
#define BENCH_ROW_GROUPS (BENCH_ROWS / Q4K_BENCH_ROWS)
#define BENCH_Q8_BLOCKS (BENCH_INPUTS * BENCH_BLOCKS)
#define BENCH_OUTPUTS (BENCH_INPUTS * BENCH_ROWS)
#define BENCH_GEMM_GROUPS (BENCH_INPUTS / Q4K_BENCH_INPUTS)

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
static float benchmark_output[BENCH_OUTPUTS]
    __attribute__((aligned(64), section(".bss")));

#if BENCH_WEIGHT_Q4 && BENCH_GEMM_GROUPS > 0
static block_q8_Kx4 packed_activation[BENCH_GEMM_GROUPS * BENCH_BLOCKS]
    __attribute__((aligned(64), section(".bss")));
#endif

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

#if BENCH_WEIGHT_Q4 && BENCH_GEMM_GROUPS > 0
static void benchmark_pack_q8_x4(const block_q8_K *source,
                                 block_q8_Kx4 *destination) {
  for (int block = 0; block < BENCH_BLOCKS; ++block) {
    for (int input = 0; input < 4; ++input) {
      destination[block].d[input] = source[input * BENCH_BLOCKS + block].d;
    }
    for (int element = 0; element < QK_K; ++element) {
      for (int input = 0; input < 4; ++input) {
        destination[block].qs[element * 4 + input] =
            source[input * BENCH_BLOCKS + block].qs[element];
      }
    }
    for (int sub_block = 0; sub_block < QK_K / 16; ++sub_block) {
      const int group = sub_block / 2;
      const int half = sub_block & 1;
      for (int input = 0; input < 4; ++input) {
        destination[block].bsums[group * 8 + half * 4 + input] =
            source[input * BENCH_BLOCKS + block].bsums[sub_block];
      }
    }
  }
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

#if BENCH_WEIGHT_Q4 && BENCH_GEMM_GROUPS > 0
static __attribute__((noinline)) void benchmark_pack(void) {
  for (int group = 0; group < BENCH_GEMM_GROUPS; ++group) {
    benchmark_pack_q8_x4(
        quantized_activation + group * 4 * BENCH_BLOCKS,
        packed_activation + group * BENCH_BLOCKS);
  }
}
#endif

#if BENCH_WEIGHT_Q4
static __attribute__((noinline)) uint64_t benchmark_q4(void) {
  const block_q4_Kx32_ara *weight =
      (const block_q4_Kx32_ara *)benchmark_weight_start;
  for (int row_group = 0; row_group < BENCH_ROW_GROUPS; ++row_group) {
    const block_q4_Kx32_ara *group_weight =
        weight + row_group * BENCH_BLOCKS;
    int input = 0;
#if BENCH_GEMM_GROUPS > 0
    for (int group = 0; group < BENCH_GEMM_GROUPS; ++group, input += 4) {
      q4k_gemm_32x4(group_weight,
                    packed_activation + group * BENCH_BLOCKS,
                    benchmark_output + (row_group * BENCH_INPUTS + input) * 32,
                    BENCH_K);
    }
#endif
    for (; input < BENCH_INPUTS; ++input) {
      q4k_gemv_32(group_weight,
                  quantized_activation + input * BENCH_BLOCKS,
                  benchmark_output + (row_group * BENCH_INPUTS + input) * 32,
                  BENCH_K);
    }
  }

  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
  const uint64_t activation_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_BLOCKS * sizeof(block_q8_K);
  const uint64_t weight_passes = BENCH_GEMM_GROUPS + (BENCH_INPUTS % 4);
  const uint64_t quantization_input_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float);
  const uint64_t activation_pack_input_bytes =
      (uint64_t)BENCH_GEMM_GROUPS * 4 * BENCH_BLOCKS * sizeof(block_q8_K);
  return quantization_input_bytes + activation_pack_input_bytes +
         weight_passes * weight_bytes + BENCH_ROW_GROUPS * activation_bytes;
}
#elif BENCH_WEIGHT_Q6
static __attribute__((noinline)) uint64_t benchmark_q6(void) {
#if BENCH_GEMM_GROUPS > 0
  const block_q6_Kx32_ara *weight =
      (const block_q6_Kx32_ara *)benchmark_weight_start;
  for (int row_group = 0; row_group < BENCH_ROW_GROUPS; ++row_group) {
    const block_q6_Kx32_ara *group_weight =
        weight + row_group * BENCH_BLOCKS;
    int input = 0;
#if BENCH_GEMM_GROUPS > 0
    for (; input + 4 <= BENCH_INPUTS; input += 4) {
      q6k_gemm_32x4(
          group_weight, quantized_activation + input * BENCH_BLOCKS,
          BENCH_BLOCKS, benchmark_output + input * BENCH_ROWS + row_group * 32,
          BENCH_ROWS, BENCH_K);
    }
#endif
    for (; input < BENCH_INPUTS; ++input) {
      q6k_gemv_32(group_weight,
                  quantized_activation + input * BENCH_BLOCKS,
                  benchmark_output + input * BENCH_ROWS + row_group * 32,
                  BENCH_K);
    }
  }
  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
  const uint64_t activation_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_BLOCKS * sizeof(block_q8_K);
  const uint64_t weight_passes = BENCH_GEMM_GROUPS + (BENCH_INPUTS % 4);
  const uint64_t quantization_input_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float);
  return quantization_input_bytes + weight_passes * weight_bytes +
         BENCH_ROW_GROUPS * activation_bytes;
#else
  const block_q6_K *weight = (const block_q6_K *)benchmark_weight_start;
  for (int input = 0; input < BENCH_INPUTS; ++input) {
    for (int row = 0; row < BENCH_ROWS; ++row) {
      benchmark_output[input * BENCH_ROWS + row] = q4km_vec_dot_q6_K_q8_K(
          weight + row * BENCH_BLOCKS,
          quantized_activation + input * BENCH_BLOCKS, BENCH_K);
    }
  }
  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
  const uint64_t activation_bytes =
      (uint64_t)BENCH_BLOCKS * sizeof(block_q8_K);
  const uint64_t quantization_input_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float);
  return quantization_input_bytes + BENCH_INPUTS * weight_bytes +
         (uint64_t)BENCH_INPUTS * BENCH_ROWS * activation_bytes;
#endif
}
#else
static __attribute__((noinline)) uint64_t benchmark_row_major(void) {
#if BENCH_WEIGHT_Q3
  const block_q3_K *weight = (const block_q3_K *)benchmark_weight_start;
#elif BENCH_WEIGHT_Q5
  const block_q5_K *weight = (const block_q5_K *)benchmark_weight_start;
#else
  const block_q8_0 *weight = (const block_q8_0 *)benchmark_weight_start;
#endif

  for (int input = 0; input < BENCH_INPUTS; ++input) {
    for (int row = 0; row < BENCH_ROWS; ++row) {
#if BENCH_WEIGHT_Q3
      benchmark_output[input * BENCH_ROWS + row] = q4km_vec_dot_q3_K_q8_K(
          weight + row * BENCH_BLOCKS,
          quantized_activation + input * BENCH_BLOCKS, BENCH_K);
#elif BENCH_WEIGHT_Q5
      benchmark_output[input * BENCH_ROWS + row] = q4km_vec_dot_q5_K_q8_K(
          weight + row * BENCH_BLOCKS,
          quantized_activation + input * BENCH_BLOCKS, BENCH_K);
#else
      benchmark_output[input * BENCH_ROWS + row] = q4km_vec_dot_q8_0_q8_0(
          weight + row * BENCH_BLOCKS,
          quantized_activation + input * BENCH_BLOCKS, BENCH_K);
#endif
    }
  }

  const uint64_t weight_bytes =
      (uint64_t)(benchmark_weight_end - benchmark_weight_start);
  const uint64_t activation_bytes =
      (uint64_t)BENCH_BLOCKS * sizeof(benchmark_activation_block_t);
  const uint64_t quantization_input_bytes =
      (uint64_t)BENCH_INPUTS * BENCH_K * sizeof(float);
  return quantization_input_bytes + BENCH_INPUTS * weight_bytes +
         (uint64_t)BENCH_INPUTS * BENCH_ROWS * activation_bytes;
}
#endif

static float benchmark_actual(int input, int row) {
#if BENCH_WEIGHT_Q4
  const int row_group = row / 32;
  const int lane = row % 32;
  return benchmark_output[(row_group * BENCH_INPUTS + input) * 32 + lane];
#else
  return benchmark_output[input * BENCH_ROWS + row];
#endif
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
      float magnitude = reference < 0.0f ? -reference : reference;
      float relative = absolute / (magnitude > 1.0e-12f ? magnitude : 1.0e-12f);
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
  if ((int)(benchmark_activation_end - benchmark_activation_start) !=
          BENCH_INPUTS * BENCH_K * 4 ||
      (int)(benchmark_golden_end - benchmark_golden_start) !=
          BENCH_OUTPUTS * 4) {
#ifdef SPIKE
    printstr(BENCH_CASE_ID ": invalid embedded data\n");
#else
    BENCH_REPORT("REAL_BENCH %s FAIL reason=data_size\n", BENCH_CASE_ID);
#endif
    return 1;
  }

  memset(benchmark_output, 0, sizeof(benchmark_output));
  HW_CNT_READY
  HW_CNT_PHASE(BENCH_PHASE_QUANTIZE);
  benchmark_perf_boundary();
  const uint64_t start = benchmark_cycle();
  benchmark_quantize();
  const uint64_t quantize_end = benchmark_cycle();
#if BENCH_WEIGHT_Q4 && BENCH_GEMM_GROUPS > 0
  HW_CNT_PHASE(BENCH_PHASE_PACK);
  const uint64_t pack_start = benchmark_cycle();
  benchmark_pack();
  const uint64_t pack_end = benchmark_cycle();
#else
  const uint64_t pack_start = quantize_end;
  const uint64_t pack_end = quantize_end;
#endif
  HW_CNT_PHASE(BENCH_PHASE_MATMUL);
  const uint64_t matmul_start = benchmark_cycle();
#if BENCH_WEIGHT_Q4
  const uint64_t logical_read_bytes = benchmark_q4();
#elif BENCH_WEIGHT_Q6
  const uint64_t logical_read_bytes = benchmark_q6();
#else
  const uint64_t logical_read_bytes = benchmark_row_major();
#endif
  const uint64_t matmul_end = benchmark_cycle();
  const uint64_t quantize_cycles = quantize_end - start;
  const uint64_t pack_cycles = pack_end - pack_start;
  const uint64_t matmul_cycles = matmul_end - matmul_start;
  const uint64_t compute_cycles = matmul_end - start;
  benchmark_perf_boundary();
  HW_CNT_NOT_READY

  float max_abs;
  float max_rel;
  uint64_t checksum;
  const int mismatches = benchmark_validate(&max_abs, &max_rel, &checksum);
  BENCH_REPORT(
      "REAL_BENCH case=%s result=%s k=%d rows=%d inputs=%d outputs=%d "
      "setup_cycles=0 compute_cycles=%lu cycles_per_output_x1000=%lu "
      "quantize_cycles=%lu pack_cycles=%lu matmul_cycles=%lu "
      "logical_read_bytes=%lu checksum=0x%lx mismatches=%d "
      "max_abs_bits=0x%x max_rel_bits=0x%x\n",
      BENCH_CASE_ID, mismatches == 0 ? "PASS" : "FAIL", BENCH_K,
      BENCH_ROWS, BENCH_INPUTS, BENCH_OUTPUTS,
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
