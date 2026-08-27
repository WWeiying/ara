#include <stddef.h>
#include <stdint.h>

#include "../qbs_ref.h"

#define QBS_UART_MMIO UINT64_C(0x10000000)
#define QBS_FINISHER  UINT64_C(0x00100000)
#define QBS_RAM_END   UINT64_C(0x88000000)
#define QBS_MCAUSE_LOAD_ACCESS UINT64_C(5)

volatile uint64_t qbs_trap_cause;
volatile uint64_t qbs_trap_tval;

static qbs_block_q8_0_t weights[2] __attribute__((aligned(16)));
static qbs_block_q8_0_t activations[2] __attribute__((aligned(16)));
static qbs_descriptor_v1_t descriptor __attribute__((aligned(16)));
static uint32_t output[32] __attribute__((aligned(16)));
static uint8_t page_crossing_storage[3 * 4096] __attribute__((aligned(4096)));

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
  __asm__ volatile(".word 0x00b5005b" : : "r"(rs1), "r"(rs2) : "memory");
}

static uint32_t read_v0_word0(void) {
  __asm__ volatile(
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vse32.v v0, (%0)\n"
      : : "r"(output) : "memory");
  return output[0];
}

static void write_v0_word0(uint32_t value) {
  output[0] = value;
  __asm__ volatile(
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vle32.v v0, (%0)\n"
      : : "r"(output) : "memory");
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

static int expect_load_access(uint64_t expected_tval) {
  return qbs_trap_cause == QBS_MCAUSE_LOAD_ACCESS &&
         qbs_trap_tval == expected_tval;
}

void qbs_contract_main(void) {
  clear_bytes(weights, sizeof(weights));
  clear_bytes(activations, sizeof(activations));
  clear_bytes(output, sizeof(output));

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
    finish(1);

  clear_trap();
  run_qbexec((const void *)(uintptr_t)QBS_UART_MMIO, activations);
  if (!expect_load_access(QBS_UART_MMIO)) finish(2);

  install_descriptor((uintptr_t)weights);
  clear_trap();
  run_qbexec(&descriptor, (const void *)(uintptr_t)QBS_UART_MMIO);
  if (!expect_load_access(QBS_UART_MMIO)) finish(3);

  install_descriptor(QBS_UART_MMIO);
  clear_trap();
  run_qbexec(&descriptor, activations);
  if (!expect_load_access(QBS_UART_MMIO)) finish(4);

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
    finish(5);

  /* A range whose first bytes are RAM but whose tail is unmapped must fault
   * before the helper modifies architectural destination state. */
  install_descriptor((uintptr_t)weights);
  write_v0_word0(UINT32_C(0x4a5a5a5a));
  clear_trap();
  run_qbexec(&descriptor,
             (const void *)(uintptr_t)(QBS_RAM_END - UINT64_C(32)));
  if (!expect_load_access(QBS_RAM_END) ||
      read_v0_word0() != UINT32_C(0x4a5a5a5a))
    finish(6);

  install_descriptor(QBS_RAM_END - UINT64_C(32));
  write_v0_word0(UINT32_C(0x4b6b6b6b));
  clear_trap();
  run_qbexec(&descriptor, activations);
  if (!expect_load_access(QBS_RAM_END) ||
      read_v0_word0() != UINT32_C(0x4b6b6b6b))
    finish(7);

  finish(0);
}
