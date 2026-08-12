// Regression for VID followed by a full dependent VALU queue.

#include "vector_macros.h"

#define ELEMENTS 256

static uint16_t result[ELEMENTS] __attribute__((aligned(128)));
static uint16_t direct_result[ELEMENTS] __attribute__((aligned(128)));
static uint16_t individual_result[ELEMENTS] __attribute__((aligned(128)));
static uint64_t old_registers[4][16] __attribute__((aligned(128)));
static uint8_t all_ones_mask[ELEMENTS / 8] __attribute__((aligned(128)));

static uint16_t expected_value(unsigned index) {
  uint16_t value = (uint16_t)(3u + index);
  uint16_t mixed = value;
  mixed ^= value >> 1;
  mixed ^= value >> 3;
  mixed ^= value >> 12;
  return mixed;
}

static void test_vid_after_eew_transition(void) {
  for (unsigned reg = 0; reg < 4; ++reg)
    for (unsigned index = 0; index < 16; ++index)
      old_registers[reg][index] = 0x1111000000000000ull * reg + index;

  unsigned long vl;
  asm volatile(
      "vsetivli zero, 16, e64, m1, ta, ma\n"
      "vle64.v v12, 0(%[old0])\n"
      "vle64.v v13, 0(%[old1])\n"
      "vle64.v v14, 0(%[old2])\n"
      "vle64.v v15, 0(%[old3])\n"
      "vsetvli %[vl], zero, e16, m4, tu, mu\n"
      "vid.v v12\n"
      "vse16.v v12, (%[result])\n"
      "vsetvli zero, %[reg_vl], e16, m1, tu, mu\n"
      "vse16.v v12, (%[individual0])\n"
      "vse16.v v13, (%[individual1])\n"
      "vse16.v v14, (%[individual2])\n"
      "vse16.v v15, (%[individual3])\n"
      : [vl] "=r"(vl)
      : [reg_vl] "r"(64), [old0] "r"(old_registers[0]),
        [old1] "r"(old_registers[1]),
        [old2] "r"(old_registers[2]), [old3] "r"(old_registers[3]),
        [result] "r"(direct_result), [individual0] "r"(&individual_result[0]),
        [individual1] "r"(&individual_result[64]),
        [individual2] "r"(&individual_result[128]),
        [individual3] "r"(&individual_result[192])
      : "memory");

  asm volatile("fence rw, rw" ::: "memory");
  if (vl != ELEMENTS) {
    printf("VID EEW transition set wrong VL: got=%lu expected=%u\n", vl,
           ELEMENTS);
    ++num_failed;
    return;
  }
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    if (individual_result[index] != index) {
      printf("VID individual-register export failed at %d: got=%x expected=%x\n",
             index, individual_result[index], index);
      ++num_failed;
      break;
    }
  }
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    if (direct_result[index] != index) {
      printf("VID EEW transition failed at %d: got=%x expected=%x\n",
             index, direct_result[index], index);
      ++num_failed;
      break;
    }
  }
}

static void test_viota_after_eew_transition(void) {
  for (unsigned index = 0; index < ELEMENTS / 8; ++index)
    all_ones_mask[index] = 0xff;

  unsigned long vl;
  asm volatile(
      "vsetvli zero, %[mask_vl], e8, m1, ta, ma\n"
      "vle8.v v0, (%[mask])\n"
      "vsetivli zero, 16, e64, m1, ta, ma\n"
      "vle64.v v12, 0(%[old0])\n"
      "vle64.v v13, 0(%[old1])\n"
      "vle64.v v14, 0(%[old2])\n"
      "vle64.v v15, 0(%[old3])\n"
      "vsetvli %[vl], zero, e16, m4, tu, mu\n"
      "viota.m v12, v0\n"
      "vse16.v v12, (%[result])\n"
      : [vl] "=r"(vl)
      : [mask_vl] "r"(ELEMENTS / 8), [mask] "r"(all_ones_mask),
        [old0] "r"(old_registers[0]),
        [old1] "r"(old_registers[1]),
        [old2] "r"(old_registers[2]), [old3] "r"(old_registers[3]),
        [result] "r"(direct_result)
      : "memory");

  asm volatile("fence rw, rw" ::: "memory");
  if (vl != ELEMENTS) {
    printf("VIOTA EEW transition set wrong VL: got=%lu expected=%u\n", vl,
           ELEMENTS);
    ++num_failed;
    return;
  }
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    if (direct_result[index] != index) {
      printf("VIOTA EEW transition failed at %d: got=%x expected=%x\n",
             index, direct_result[index], index);
      ++num_failed;
      break;
    }
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  test_vid_after_eew_transition();
  test_viota_after_eew_transition();

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vmv.v.i v0, 3\n"
      "vid.v v12\n"
      "vadd.vv v0, v0, v12\n"
      "vmv.v.v v20, v0\n"
      "vsrl.vi v12, v0, 1\n"
      "vxor.vv v20, v12, v20\n"
      "vsrl.vi v12, v0, 3\n"
      "vxor.vv v20, v12, v20\n"
      "vsrl.vi v12, v0, 12\n"
      "vxor.vv v20, v12, v20\n"
      "vse16.v v20, (%[result])\n"
      :
      : [vl] "r"(ELEMENTS), [result] "r"(result)
      : "memory");

  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");

  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint16_t expected = expected_value(index);
    if (result[index] != expected) {
      printf("VID queue regression failed at %d: got=%x expected=%x\n",
             index, result[index], expected);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
