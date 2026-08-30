#include <stddef.h>
#include <stdint.h>

#include "akv_abi.h"
#include "printf.h"

#define SEQ16(base_)                                                        \
  (base_) + 0, (base_) + 1, (base_) + 2, (base_) + 3, (base_) + 4,         \
      (base_) + 5, (base_) + 6, (base_) + 7, (base_) + 8, (base_) + 9,     \
      (base_) + 10, (base_) + 11, (base_) + 12, (base_) + 13,              \
      (base_) + 14, (base_) + 15

#define ROW128(base_)                                                       \
  SEQ16((base_) + 0), SEQ16((base_) + 16), SEQ16((base_) + 32),            \
      SEQ16((base_) + 48), SEQ16((base_) + 64), SEQ16((base_) + 80),       \
      SEQ16((base_) + 96), SEQ16((base_) + 112)

static const uint16_t q_rows[3][128] __attribute__((aligned(64))) = {
    {ROW128(0x1000)}, {ROW128(0x1200)}, {ROW128(0x1400)}};

static const uint16_t k_rows[12][128] __attribute__((aligned(64))) = {
    {ROW128(0x2000)}, {ROW128(0x2200)}, {ROW128(0x2400)},
    {ROW128(0x2600)}, {ROW128(0x2800)}, {ROW128(0x2a00)},
    {ROW128(0x2c00)}, {ROW128(0x2e00)}, {ROW128(0x3000)},
    {ROW128(0x3200)}, {ROW128(0x3400)}, {ROW128(0x3600)}};

static const uint16_t v_rows[12][128] __attribute__((aligned(64))) = {
    {ROW128(0x4000)}, {ROW128(0x4200)}, {ROW128(0x4400)},
    {ROW128(0x4600)}, {ROW128(0x4800)}, {ROW128(0x4a00)},
    {ROW128(0x4c00)}, {ROW128(0x4e00)}, {ROW128(0x5000)},
    {ROW128(0x5200)}, {ROW128(0x5400)}, {ROW128(0x5600)}};

static akv_descriptor_t descriptor __attribute__((aligned(64)));
static uint16_t observed[128] __attribute__((aligned(64)));
static uint16_t sentinel[128] __attribute__((aligned(64)));

static volatile uint64_t trap_count;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_tval;
static volatile uint64_t recovery_store;

enum {
  AKVINFO_A0_A0 = 0x0005455b,
  AKVFILL_FULL_A0_A1 = 0x00b5205b,
  AKVFILL_REFILL_X0_A0 = 0x02a0205b,
  AKVLOAD_D64_V8_A0 = 0x0005345b,
  AKVLOAD_D128_V8_A0 = 0x0205345b,
  AKVLOAD_D128_V9_A0 = 0x020534db,
  AKVRELEASE = 0x0000505b,
};

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

static uint64_t issue_info(uint64_t index) {
  register uint64_t a0 asm("a0") = index;
  asm volatile(".word 0x0005455b" : "+r"(a0) : : "memory");
  return a0;
}

static void issue_full(const akv_descriptor_t *desc, uint64_t tile_start) {
  register uintptr_t a0 asm("a0") = (uintptr_t)desc;
  register uint64_t a1 asm("a1") = tile_start;
  asm volatile(".word 0x00b5205b" : "+r"(a0), "+r"(a1) : : "memory");
}

static void issue_refill(uint64_t tile_start) {
  register uint64_t a0 asm("a0") = tile_start;
  asm volatile(".word 0x02a0205b" : "+r"(a0) : : "memory");
}

static void issue_load_d128(uint32_t selector, uint16_t destination[128]) {
  register uint64_t a0 asm("a0") = selector;
  register uintptr_t a1 asm("a1") = (uintptr_t)destination;
  asm volatile("li t0, 128\n"
               "vsetvli zero, t0, e16, m2, ta, ma\n"
               ".word 0x0205345b\n"
               "vse16.v v8, (a1)\n"
               : "+r"(a0), "+r"(a1)
               :
               : "t0", "memory");
}

static void issue_load_d64(uint32_t selector, uint16_t destination[64]) {
  register uint64_t a0 asm("a0") = selector;
  register uintptr_t a1 asm("a1") = (uintptr_t)destination;
  asm volatile("li t0, 64\n"
               "vsetvli zero, t0, e16, m1, ta, ma\n"
               ".word 0x0005345b\n"
               "vse16.v v8, (a1)\n"
               : "+r"(a0), "+r"(a1)
               :
               : "t0", "memory");
}

static void issue_trapping_load_d128(uint32_t selector,
                                     const uint16_t initial[128],
                                     uint16_t destination[128]) {
  register uint64_t a0 asm("a0") = selector;
  register uintptr_t a1 asm("a1") = (uintptr_t)initial;
  register uintptr_t a2 asm("a2") = (uintptr_t)destination;
  asm volatile("li t0, 128\n"
               "vsetvli zero, t0, e16, m2, ta, ma\n"
               "vle16.v v8, (a1)\n"
               ".word 0x0205345b\n"
               "vse16.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2)
               :
               : "t0", "memory");
}

static void issue_trapping_odd_load_d128(uint32_t selector,
                                         const uint16_t initial[128],
                                         uint16_t destination[128]) {
  register uint64_t a0 asm("a0") = selector;
  register uintptr_t a1 asm("a1") = (uintptr_t)initial;
  register uintptr_t a2 asm("a2") = (uintptr_t)destination;
  asm volatile("li t0, 128\n"
               "vsetvli zero, t0, e16, m2, ta, ma\n"
               "vle16.v v8, (a1)\n"
               ".word 0x020534db\n"
               "vse16.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2)
               :
               : "t0", "memory");
}

static void issue_release(void) {
  asm volatile(".word 0x0000505b" : : : "memory");
}

static int compare_u16(const char *name, const uint16_t *got,
                       const uint16_t *expected, size_t count) {
  for (size_t index = 0; index < count; ++index) {
    if (got[index] != expected[index]) {
      printf("%s mismatch at %d: got=%x expected=%x\n", name, (int)index,
             got[index], expected[index]);
      return 1;
    }
  }
  return 0;
}

static int is_expected_illegal_tval(uint64_t value, uint32_t instruction) {
  return value == 0 || (uint32_t)value == instruction;
}

static int load_and_compare(const char *name, akv_stream_t stream,
                            uint32_t index, const uint16_t *expected) {
  issue_load_d128(akv_selector(stream, index), observed);
  return compare_u16(name, observed, expected, 128);
}

static void initialize_descriptor(uint16_t head_dim) {
  descriptor = (akv_descriptor_t){
      .version = AKV_DESCRIPTOR_VERSION,
      .element_format = AKV_ELEMENT_FORMAT_F16,
      .q_rows = 3,
      .flags = 0,
      .head_dim = head_dim,
      .kv_length = 12,
      .q_row_stride_bytes = sizeof(q_rows[0]),
      .k_token_stride_bytes = sizeof(k_rows[0]),
      .v_token_stride_bytes = sizeof(v_rows[0]),
      .reserved0 = 0,
      .q_base = (uint64_t)(uintptr_t)q_rows,
      .k_base = (uint64_t)(uintptr_t)k_rows,
      .v_base = (uint64_t)(uintptr_t)v_rows,
      .reserved1 = 0,
      .reserved2 = 0,
  };
  asm volatile("fence rw, rw" : : : "memory");
}

int main(void) {
  int failures = 0;

  if (akv_encode_info(10, 10) != AKVINFO_A0_A0 ||
      akv_encode_fill(10, 11, AKV_FILL_FULL) != AKVFILL_FULL_A0_A1 ||
      akv_encode_fill(0, 10, AKV_FILL_REFILL) !=
          AKVFILL_REFILL_X0_A0 ||
      akv_encode_load(8, 10, 64) != AKVLOAD_D64_V8_A0 ||
      akv_encode_load(8, 10, 128) != AKVLOAD_D128_V8_A0 ||
      akv_encode_release() != AKVRELEASE) {
    printf("AKV instruction encoding mismatch\n");
    return 1;
  }

  const uint64_t probe_traps = trap_count;
  const uint64_t capability = issue_info(0);
  if (trap_count != probe_traps) {
    printf("AKV context smoke: SKIP (extension disabled)\n");
    return 0;
  }
  if (capability != akv_capability_word(0, 1)) {
    printf("AKV capability mismatch: got=%lx expected=%lx\n", capability,
           akv_capability_word(0, 1));
    ++failures;
  }

  initialize_descriptor(128);
  issue_full(&descriptor, 0);
  if (trap_count != probe_traps) {
    printf("AKV full trapped: cause=%lx tval=%lx\n", trap_cause, trap_tval);
    return 1;
  }

  failures += load_and_compare("Q2/full", AKV_STREAM_Q, 2, q_rows[2]);
  failures += load_and_compare("K0/full", AKV_STREAM_K, 0, k_rows[0]);
  failures += load_and_compare("K7/full", AKV_STREAM_K, 7, k_rows[7]);
  failures += load_and_compare("V3/full", AKV_STREAM_V, 3, v_rows[3]);

  issue_refill(8);
  if (trap_count != probe_traps) {
    printf("AKV refill trapped: cause=%lx tval=%lx\n", trap_cause, trap_tval);
    return 1;
  }
  failures += load_and_compare("Q0/refill", AKV_STREAM_Q, 0, q_rows[0]);
  failures += load_and_compare("K0/refill", AKV_STREAM_K, 0, k_rows[8]);
  failures += load_and_compare("K3/refill", AKV_STREAM_K, 3, k_rows[11]);
  failures += load_and_compare("V2/refill", AKV_STREAM_V, 2, v_rows[10]);

  for (size_t index = 0; index < 128; ++index)
    sentinel[index] = (uint16_t)(0x7000u + index);
  const uint64_t before_bad_selector = trap_count;
  issue_trapping_load_d128(akv_selector(AKV_STREAM_K, 7), sentinel,
                           observed);
  if (trap_count != before_bad_selector + 1 || trap_cause != 2 ||
      !is_expected_illegal_tval(trap_tval, AKVLOAD_D128_V8_A0)) {
    printf("AKV invalid selector trap failed: traps=%ld cause=%lx tval=%lx\n",
           trap_count - before_bad_selector, trap_cause, trap_tval);
    ++failures;
  }
  failures += compare_u16("invalid-selector/no-write", observed, sentinel,
                          128);
  failures += load_and_compare("Q1/after-invalid", AKV_STREAM_Q, 1,
                               q_rows[1]);

  const uint64_t before_odd_destination = trap_count;
  issue_trapping_odd_load_d128(akv_selector(AKV_STREAM_Q, 0), sentinel,
                               observed);
  if (trap_count != before_odd_destination + 1 || trap_cause != 2 ||
      !is_expected_illegal_tval(trap_tval, AKVLOAD_D128_V9_A0)) {
    printf("AKV odd D128 destination trap failed: traps=%ld cause=%lx "
           "tval=%lx\n",
           trap_count - before_odd_destination, trap_cause, trap_tval);
    ++failures;
  }
  failures += compare_u16("odd-destination/no-write", observed, sentinel,
                          128);

  // Refill the same context with a smaller architectural D and verify that
  // the one-register replay path uses exactly the first 64 F16 elements.
  issue_release();
  initialize_descriptor(64);
  issue_full(&descriptor, 0);
  issue_load_d64(akv_selector(AKV_STREAM_V, 7), observed);
  failures += compare_u16("V7/D64", observed, v_rows[7], 64);

  issue_release();
  const uint64_t before_empty_load = trap_count;
  issue_trapping_load_d128(akv_selector(AKV_STREAM_Q, 0), sentinel,
                           observed);
  if (trap_count != before_empty_load + 1 || trap_cause != 2 ||
      !is_expected_illegal_tval(trap_tval, AKVLOAD_D128_V8_A0)) {
    printf("AKV released-context trap failed: traps=%ld cause=%lx tval=%lx\n",
           trap_count - before_empty_load, trap_cause, trap_tval);
    ++failures;
  }
  failures += compare_u16("released-context/no-write", observed, sentinel,
                          128);

  recovery_store = UINT64_C(0x5a5aa5a55a5aa5a5);
  if (recovery_store != UINT64_C(0x5a5aa5a55a5aa5a5)) ++failures;

  printf("AKV context smoke: %s\n", failures == 0 ? "PASS" : "FAIL");
  return failures;
}
