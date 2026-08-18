#include "repack_kernels.h"

#ifdef SPIKE
extern void printstr(const char *string);
#define REPORT(...) do { } while (0)
#else
#include "printf.h"
#define REPORT(...) printf(__VA_ARGS__)
#endif

#include <stdint.h>
#include <string.h>

extern const uint8_t weight_original_start[];
extern const uint8_t activation_original_start[];
extern const uint8_t weight_vl1024_start[];
extern const uint8_t activation_vl1024_start[];
extern const uint8_t weight_gemv_start[];
extern const uint8_t activation_gemv_start[];
extern const uint8_t weight_gemm_start[];
extern const uint8_t activation_gemm_start[];
extern const uint8_t golden_f32_start[];

static float output[Q4K_BENCH_INPUTS * Q4K_BENCH_ROWS]
    __attribute__((aligned(64)));

static inline uint64_t read_cycle(void) {
#ifdef SPIKE
  return 0;
#else
  uint64_t cycle;
  asm volatile("fence rw, rw; csrr %0, cycle" : "=r"(cycle) : : "memory");
  return cycle;
#endif
}

static inline void perf_boundary(void) {
#ifndef SPIKE
  asm volatile("fence rw, rw; rdcycle zero" ::: "memory");
#endif
}

static int validate(const char *name) {
  const float *golden = (const float *)golden_f32_start;
  int failures = 0;
  float max_error = 0.0f;
  for (int input = 0; input < Q4K_BENCH_INPUTS; ++input) {
    for (int row = 0; row < Q4K_BENCH_ROWS; ++row) {
      const int index = input * Q4K_BENCH_ROWS + row;
      float error = output[index] - golden[row];
      if (error < 0.0f) error = -error;
      if (error > max_error) max_error = error;
      float magnitude = golden[row] < 0.0f ? -golden[row] : golden[row];
      if (error > 2.0e-4f + 2.0e-4f * magnitude) ++failures;
    }
  }
  uint32_t max_error_bits;
  memcpy(&max_error_bits, &max_error, sizeof(max_error_bits));
  REPORT("BENCH_CHECK %s %s mismatches=%d max_error_bits=0x%x\n",
         name, failures == 0 ? "PASS" : "FAIL", failures, max_error_bits);
#ifdef SPIKE
  printstr(name);
  printstr(failures == 0 ? ": PASS\n" : ": FAIL\n");
#endif
  return failures;
}

static uint64_t run_original(void) {
  const block_q4_K *weight = (const block_q4_K *)weight_original_start;
  const block_q8_K *activation = (const block_q8_K *)activation_original_start;
  for (int input = 0; input < Q4K_BENCH_INPUTS; ++input) {
    for (int row = 0; row < Q4K_BENCH_ROWS; ++row) {
      output[input * Q4K_BENCH_ROWS + row] = q4k_dot_original(
          weight + row * Q4K_BENCH_BLOCKS,
          activation + input * Q4K_BENCH_BLOCKS, Q4K_BENCH_K);
    }
  }
  return (uint64_t)Q4K_BENCH_INPUTS * Q4K_BENCH_ROWS *
         Q4K_BENCH_BLOCKS * (sizeof(block_q4_K) + sizeof(block_q8_K));
}

static uint64_t run_vl1024(void) {
  const block_q4_K *weight = (const block_q4_K *)weight_vl1024_start;
  const block_q8_K *activation = (const block_q8_K *)activation_vl1024_start;
  for (int input = 0; input < Q4K_BENCH_INPUTS; ++input) {
    for (int row = 0; row < Q4K_BENCH_ROWS; ++row) {
      output[input * Q4K_BENCH_ROWS + row] = q4k_dot_vl1024(
          weight + row * Q4K_BENCH_BLOCKS,
          activation + input * Q4K_BENCH_BLOCKS, Q4K_BENCH_K);
    }
  }
  return (uint64_t)Q4K_BENCH_INPUTS * Q4K_BENCH_ROWS *
         Q4K_BENCH_BLOCKS * (sizeof(block_q4_K) + sizeof(block_q8_K));
}

static uint64_t run_gemv(void) {
  const block_q4_Kx32_ara *weight =
      (const block_q4_Kx32_ara *)weight_gemv_start;
  const block_q8_K *activation = (const block_q8_K *)activation_gemv_start;
  for (int input = 0; input < Q4K_BENCH_INPUTS; ++input) {
    q4k_gemv_32(weight, activation + input * Q4K_BENCH_BLOCKS,
                 output + input * Q4K_BENCH_ROWS, Q4K_BENCH_K);
  }
  return (uint64_t)Q4K_BENCH_INPUTS *
         (Q4K_BENCH_ROWS * Q4K_BENCH_BLOCKS * sizeof(block_q4_K) +
          Q4K_BENCH_BLOCKS * sizeof(block_q8_K));
}

static uint64_t run_gemm(void) {
  q4k_gemm_32x4((const block_q4_Kx32_ara *)weight_gemm_start,
                 (const block_q8_Kx4 *)activation_gemm_start,
                 output, Q4K_BENCH_K);
  return (uint64_t)Q4K_BENCH_ROWS * Q4K_BENCH_BLOCKS * sizeof(block_q4_K) +
         Q4K_BENCH_INPUTS * Q4K_BENCH_BLOCKS * sizeof(block_q8_K);
}

typedef uint64_t (*bench_fn)(void);

static int run_benchmark(const char *name, bench_fn function) {
  for (int i = 0; i < Q4K_BENCH_INPUTS * Q4K_BENCH_ROWS; ++i) output[i] = 0.0f;
  REPORT("BENCH_BEGIN %s outputs=%d\n", name,
         Q4K_BENCH_INPUTS * Q4K_BENCH_ROWS);
  perf_boundary();
  const uint64_t start = read_cycle();
  const uint64_t logical_read_bytes = function();
  const uint64_t cycles = read_cycle() - start;
  perf_boundary();
  REPORT("BENCH_END %s cycles=%lu logical_read_bytes=%lu\n", name,
         (unsigned long)cycles, (unsigned long)logical_read_bytes);
  return validate(name);
}

int main(void) {
  int failures = 0;
  failures += run_benchmark("single_original", run_original);
  failures += run_benchmark("single_vl1024", run_vl1024);
  failures += run_benchmark("gemv_32", run_gemv);
  failures += run_benchmark("gemm_32x4", run_gemm);
  REPORT("Q4_K repack comparison: %s failures=%d\n",
         failures == 0 ? "PASS" : "FAIL", failures);
  return failures != 0;
}
