#include "micro_kernels.h"

#ifdef SPIKE
#define REPORT(...) do { } while (0)
#else
#include "printf.h"
#define REPORT(...) printf(__VA_ARGS__)
#endif
#include <stdint.h>
#include <string.h>

#define DECLARE_DATA(name)         \
  extern const uint8_t name##_start[]; \
  extern const uint8_t name##_end[]

DECLARE_DATA(quant1536_input);
DECLARE_DATA(quant1536_golden);
DECLARE_DATA(quant8960_input);
DECLARE_DATA(quant8960_golden);
DECLARE_DATA(q4_1536_weight);
DECLARE_DATA(q4_1536_activation);
DECLARE_DATA(q4_1536_golden);
DECLARE_DATA(q4_8960_weight);
DECLARE_DATA(q4_8960_activation);
DECLARE_DATA(q4_8960_golden);
DECLARE_DATA(q6_1536_weight);
DECLARE_DATA(q6_1536_activation);
DECLARE_DATA(q6_1536_golden);
DECLARE_DATA(q6_8960_weight);
DECLARE_DATA(q6_8960_activation);
DECLARE_DATA(q6_8960_golden);

static block_q8_K quantized[8960 / QK_K];

static inline uint64_t read_completed_cycle(void) {
#ifdef SPIKE
  return 0;
#else
  uint64_t cycle;
  asm volatile("fence rw, rw; csrr %0, cycle" : "=r"(cycle) : : "memory");
  return cycle;
#endif
}

static int bytes_equal(const uint8_t *left, const uint8_t *right, size_t size) {
  for (size_t index = 0; index < size; ++index) {
    if (left[index] != right[index]) return 0;
  }
  return 1;
}

static uint32_t float_bits(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return bits;
}

static int run_quantize(const char *name, int k, const uint8_t *input,
                        const uint8_t *golden, const uint8_t *golden_end) {
  const size_t bytes = (size_t)(golden_end - golden);
  const uint64_t start = read_completed_cycle();
  q4km_quantize_row_q8_K((const float *)input, quantized, k);
  const uint64_t cycles = read_completed_cycle() - start;
  const int pass = bytes == (size_t)(k / QK_K) * sizeof(block_q8_K) &&
                   bytes_equal((const uint8_t *)quantized, golden, bytes);
  REPORT("MICRO %s %s cycles=%lu bytes=%d\n", name,
         pass ? "PASS" : "FAIL", (unsigned long)cycles, (int)bytes);
  return pass ? 0 : 1;
}

static int run_dot(const char *name, int n, int q6, const uint8_t *weight,
                   const uint8_t *activation, const uint8_t *golden_data) {
  const uint64_t start = read_completed_cycle();
  float actual = q6 ? q4km_vec_dot_q6_K_q8_K(
                          (const block_q6_K *)weight,
                          (const block_q8_K *)activation, n)
                    : q4km_vec_dot_q4_K_q8_K(
                          (const block_q4_K *)weight,
                          (const block_q8_K *)activation, n);
  const uint64_t cycles = read_completed_cycle() - start;
  float golden;
  memcpy(&golden, golden_data, sizeof(golden));
  float error = actual - golden;
  if (error < 0.0f) error = -error;
  float magnitude = golden < 0.0f ? -golden : golden;
  const int pass = error <= 1.0e-5f + 1.0e-5f * magnitude;
  REPORT("MICRO %s %s cycles=%lu actual=0x%x golden=0x%x\n", name,
         pass ? "PASS" : "FAIL", (unsigned long)cycles,
         float_bits(actual), float_bits(golden));
  return pass ? 0 : 1;
}

int main(void) {
  int failures = 0;
  failures += run_quantize("quantize_f32_to_q8_k_k1536", 1536,
                           quant1536_input_start, quant1536_golden_start,
                           quant1536_golden_end);
  failures += run_quantize("quantize_f32_to_q8_k_k8960", 8960,
                           quant8960_input_start, quant8960_golden_start,
                           quant8960_golden_end);
  failures += run_dot("q4_k_x_q8_k_dot_n1536_nrc1", 1536, 0,
                      q4_1536_weight_start, q4_1536_activation_start,
                      q4_1536_golden_start);
  failures += run_dot("q4_k_x_q8_k_dot_n8960_nrc1", 8960, 0,
                      q4_8960_weight_start, q4_8960_activation_start,
                      q4_8960_golden_start);
  failures += run_dot("q6_k_x_q8_k_dot_n1536_nrc1", 1536, 1,
                      q6_1536_weight_start, q6_1536_activation_start,
                      q6_1536_golden_start);
  failures += run_dot("q6_k_x_q8_k_dot_n8960_nrc1", 8960, 1,
                      q6_8960_weight_start, q6_8960_activation_start,
                      q6_8960_golden_start);
  REPORT("Q4_K_M micro verification: %s (%d/6 failed)\n",
         failures == 0 ? "PASS" : "FAIL", failures);
  return failures;
}
