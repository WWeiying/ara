#include <stdint.h>
#include <string.h>

#include "printf.h"
#include "../llama_q4km_micro/micro_kernels.h"

#include <riscv_vector.h>

/* Use the same quantization implementation as the Qwen FPGA benchmark. */
#include "../llama_q4km_micro/micro_kernels.c"

static float input[QK_K] __attribute__((aligned(128)));
static block_q8_K output __attribute__((aligned(128)));
static uint32_t integer_input[QK_K] __attribute__((aligned(128)));
static uint32_t vector_output[QK_K] __attribute__((aligned(128)));

static uint64_t read_mstatus(void) {
  uint64_t value;
  asm volatile("csrr %0, mstatus" : "=r"(value));
  return value;
}

static uint64_t read_mcause(void) {
  uint64_t value;
  asm volatile("csrr %0, mcause" : "=r"(value));
  return value;
}

static uint64_t read_mepc(void) {
  uint64_t value;
  asm volatile("csrr %0, mepc" : "=r"(value));
  return value;
}

static uint64_t read_vlenb(void) {
  uint64_t value;
  asm volatile("csrr %0, vlenb" : "=r"(value));
  return value;
}

int main(void) {
  printf("FPGA_PROBE 0 main\n");
  printf("FPGA_PROBE csr mstatus=0x%lx mcause=0x%lx mepc=0x%lx vlenb=%lu\n",
         (unsigned long)read_mstatus(), (unsigned long)read_mcause(),
         (unsigned long)read_mepc(), (unsigned long)read_vlenb());

  for (unsigned i = 0; i < QK_K; ++i) {
    input[i] = (float)(i % 31u) - 15.0f;
    integer_input[i] = i * 17u + 3u;
  }

  size_t vl_m1 = __riscv_vsetvl_e32m1(QK_K);
  printf("FPGA_PROBE 1 vsetvl_e32m1=%lu\n", (unsigned long)vl_m1);
  if (vl_m1 == 0) return 1;

  vuint32m1_t values_m1 = __riscv_vle32_v_u32m1(integer_input, vl_m1);
  values_m1 = __riscv_vadd_vx_u32m1(values_m1, 1u, vl_m1);
  __riscv_vse32_v_u32m1(vector_output, values_m1, vl_m1);
  printf("FPGA_PROBE 2 rvv_m1_done=%lu\n", (unsigned long)vector_output[0]);

  size_t vl_m8 = __riscv_vsetvlmax_e32m8();
  printf("FPGA_PROBE 3 vsetvlmax_e32m8=%lu\n", (unsigned long)vl_m8);
  if (vl_m8 == 0) return 2;

  printf("FPGA_PROBE 4 quantize_begin\n");
  q4km_quantize_row_q8_K((const float *)input, &output, QK_K);
  uint32_t d_bits;
  memcpy(&d_bits, &output.d, sizeof(d_bits));
  printf("FPGA_PROBE 5 quantize_done d_bits=0x%x sum0=%d\n",
         d_bits, output.bsums[0]);
  return 0;
}
