// SPDX-License-Identifier: Apache-2.0
// Directed checks for versioned reduction seeds and reduction writeback
// forwarding.

#include <stdint.h>

#include "printf.h"
#include "runtime.h"

static const uint32_t __attribute__((aligned(128))) fp32_ones[32] = {
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
    0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
};

static const uint32_t __attribute__((aligned(128))) fp32_twos[32] = {
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
    0x40000000, 0x40000000, 0x40000000, 0x40000000,
};

static const uint32_t __attribute__((aligned(128))) int32_ones[32] = {
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
};

static const uint16_t __attribute__((aligned(64))) fp16_ones[32] = {
    0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00,
    0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00,
    0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00,
    0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00, 0x3c00,
};

static uint32_t __attribute__((aligned(128))) reduction_store[32];
static uint32_t __attribute__((aligned(128))) integer_store[32];

static uint32_t test_in_place_chain(void) {
  uint64_t result;
  const uint64_t seed = 0x3f000000;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.s.x v2, %[seed]\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfmv.f.s ft0, v2\n"
      "fmv.x.w %[dst], ft0\n"
      : [dst] "=&r"(result)
      : [src] "r"(fp32_ones), [seed] "r"(seed)
      : "t0", "ft0", "memory");
  return (uint32_t)result;
}

static uint32_t test_renamed_chain(void) {
  uint64_t result;
  const uint64_t seed = 0x3f000000;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.s.x v3, %[seed]\n"
      "vfredusum.vs v4, v1, v3\n"
      "vfredusum.vs v5, v1, v4\n"
      "vfredusum.vs v6, v1, v5\n"
      "vfmv.f.s ft0, v6\n"
      "fmv.x.w %[dst], ft0\n"
      : [dst] "=&r"(result)
      : [src] "r"(fp32_ones), [seed] "r"(seed)
      : "t0", "ft0", "memory");
  return (uint32_t)result;
}

static uint32_t test_version_invalidation(void) {
  uint64_t result;
  const uint64_t seed = 0x3f000000;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[ones])\n"
      "vmv.s.x v18, %[seed]\n"
      "vfredusum.vs v19, v1, v18\n"
      "vle32.v v19, (%[twos])\n"
      "vfredusum.vs v20, v1, v19\n"
      "vfmv.f.s ft0, v20\n"
      "fmv.x.w %[dst], ft0\n"
      : [dst] "=&r"(result)
      : [ones] "r"(fp32_ones), [twos] "r"(fp32_twos), [seed] "r"(seed)
      : "t0", "ft0", "memory");
  return (uint32_t)result;
}

static void test_interleaved_reduction_table(uint32_t *first_result,
                                             uint32_t *second_result) {
  uint64_t first;
  uint64_t second;
  const uint64_t half_seed = 0x3f000000;
  const uint64_t zero_seed = 0;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.s.x v21, %[half]\n"
      "vmv.s.x v22, %[zero]\n"
      "vfredusum.vs v23, v1, v21\n"
      // Keep two independent rounded seeds live, then consume both in the
      // opposite half of the stream.  This requires distinct producer-table
      // entries; a single global seed slot can accelerate only one branch.
      "vfredusum.vs v24, v1, v22\n"
      "vfredusum.vs v25, v1, v23\n"
      "vfredusum.vs v26, v1, v24\n"
      "vfmv.f.s ft0, v25\n"
      "vfmv.f.s ft1, v26\n"
      "fmv.x.w %[first], ft0\n"
      "fmv.x.w %[second], ft1\n"
      : [first] "=&r"(first), [second] "=&r"(second)
      : [src] "r"(fp32_ones), [half] "r"(half_seed),
        [zero] "r"(zero_seed)
      : "t0", "ft0", "ft1", "memory");
  *first_result = (uint32_t)first;
  *second_result = (uint32_t)second;
}

static void test_reduction_seed_fanout(uint32_t *first_result,
                                       uint32_t *second_result) {
  uint64_t first;
  uint64_t second;
  const uint64_t half_seed = 0x3f000000;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.s.x v15, %[half]\n"
      "vfredusum.vs v16, v1, v15\n"
      // Both renamed consumers use the same producer version.  Binding the
      // first must not consume or invalidate the producer-table entry.
      "vfredusum.vs v17, v1, v16\n"
      "vfredusum.vs v18, v1, v16\n"
      "vfmv.f.s ft0, v17\n"
      "vfmv.f.s ft1, v18\n"
      "fmv.x.w %[first], ft0\n"
      "fmv.x.w %[second], ft1\n"
      : [first] "=&r"(first), [second] "=&r"(second)
      : [src] "r"(fp32_ones), [half] "r"(half_seed)
      : "t0", "ft0", "ft1", "memory");
  *first_result = (uint32_t)first;
  *second_result = (uint32_t)second;
}

static uint32_t test_mul_reduction_forward(void) {
  uint64_t result;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v8, (%[ones])\n"
      "vle32.v v9, (%[twos])\n"
      "vfmul.vv v10, v8, v9\n"
      "vmv.v.i v11, 0\n"
      "vfredusum.vs v12, v10, v11\n"
      "vfmv.f.s ft0, v12\n"
      "fmv.x.w %[dst], ft0\n"
      : [dst] "=&r"(result)
      : [ones] "r"(fp32_ones), [twos] "r"(fp32_twos)
      : "t0", "ft0", "memory");
  return (uint32_t)result;
}

static uint32_t test_reduction_store_forward(void) {
  const uint64_t seed = 0;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.s.x v13, %[seed]\n"
      "vfredusum.vs v14, v1, v13\n"
      // Request only the defined scalar reduction element.  A full-vector
      // store also needs untouched tail bytes and cannot safely be satisfied
      // by the one-word reduction-result entry alone.
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vse32.v v14, (%[dst])\n"
      :
      : [src] "r"(fp32_ones), [dst] "r"(reduction_store), [seed] "r"(seed)
      : "t0", "memory");
  return reduction_store[0];
}

static uint16_t test_fp16_chain(void) {
  uint64_t result;
  const uint64_t seed = 0x3800;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e16, m1, ta, ma\n"
      "vle16.v v1, (%[src])\n"
      "vmv.s.x v2, %[seed]\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfredusum.vs v2, v1, v2\n"
      "vfredusum.vs v2, v1, v2\n"
      "vmv.x.s %[dst], v2\n"
      : [dst] "=&r"(result)
      : [src] "r"(fp16_ones), [seed] "r"(seed)
      : "t0", "memory");
  return (uint16_t)result;
}

static uint32_t test_integer_reduction_scalar(void) {
  uint64_t result;
  const uint64_t seed = 0;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v26, (%[src])\n"
      "vmv.s.x v27, %[seed]\n"
      "vredsum.vs v28, v26, v27\n"
      "vmv.x.s %[dst], v28\n"
      : [dst] "=&r"(result)
      : [src] "r"(int32_ones), [seed] "r"(seed)
      : "t0", "memory");
  return (uint32_t)result;
}

static uint32_t test_integer_reduction_store(void) {
  const uint64_t seed = 0;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v26, (%[src])\n"
      "vmv.s.x v27, %[seed]\n"
      "vredsum.vs v29, v26, v27\n"
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vse32.v v29, (%[dst])\n"
      :
      : [src] "r"(int32_ones), [dst] "r"(integer_store), [seed] "r"(seed)
      : "t0", "memory");
  return integer_store[0];
}

static void test_dual_reduction_result_cache(uint32_t *first_result,
                                             uint32_t *second_result) {
  uint64_t first;
  uint64_t second;
  const uint64_t seed = 0;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v26, (%[src])\n"
      "vmv.s.x v27, %[seed]\n"
      // Both completed scalar results must remain forwardable.  A one-entry
      // victim cache evicts v28 when v29 reaches writeback.
      "vredsum.vs v28, v26, v27\n"
      "vredsum.vs v29, v26, v27\n"
      "vmv.x.s %[first], v28\n"
      "vmv.x.s %[second], v29\n"
      : [first] "=&r"(first), [second] "=&r"(second)
      : [src] "r"(int32_ones), [seed] "r"(seed)
      : "t0", "memory");
  *first_result = (uint32_t)first;
  *second_result = (uint32_t)second;
}

int main(void) {
  uint64_t mismatch = 0;

  HW_CNT_READY;
  perf_time();
  const uint32_t in_place = test_in_place_chain();
  const uint32_t renamed = test_renamed_chain();
  const uint32_t invalidated = test_version_invalidation();
  uint32_t interleaved_first;
  uint32_t interleaved_second;
  test_interleaved_reduction_table(&interleaved_first, &interleaved_second);
  uint32_t fanout_first;
  uint32_t fanout_second;
  test_reduction_seed_fanout(&fanout_first, &fanout_second);
  const uint32_t mul_reduction = test_mul_reduction_forward();
  const uint32_t stored = test_reduction_store_forward();
  const uint16_t fp16 = test_fp16_chain();
  const uint32_t integer_scalar = test_integer_reduction_scalar();
  const uint32_t integer_stored = test_integer_reduction_store();
  uint32_t dual_cache_first;
  uint32_t dual_cache_second;
  test_dual_reduction_result_cache(&dual_cache_first, &dual_cache_second);
  perf_time();
  HW_CNT_NOT_READY;

  mismatch |= in_place != 0x43008000;
  mismatch |= renamed != 0x42c10000;
  mismatch |= invalidated != 0x42080000;
  mismatch |= interleaved_first != 0x42810000;
  mismatch |= interleaved_second != 0x42800000;
  mismatch |= fanout_first != 0x42810000;
  mismatch |= fanout_second != 0x42810000;
  mismatch |= mul_reduction != 0x42800000;
  mismatch |= stored != 0x42000000;
  mismatch |= fp16 != 0x5804;
  mismatch |= integer_scalar != 0x20;
  mismatch |= integer_stored != 0x20;
  mismatch |= dual_cache_first != 0x20;
  mismatch |= dual_cache_second != 0x20;

  printf("reduction chain in-place: %x/%x\n", in_place, 0x43008000);
  printf("reduction chain renamed: %x/%x\n", renamed, 0x42c10000);
  printf("reduction version invalidation: %x/%x\n", invalidated, 0x42080000);
  printf("interleaved reduction table A: %x/%x\n",
         interleaved_first, 0x42810000);
  printf("interleaved reduction table B: %x/%x\n",
         interleaved_second, 0x42800000);
  printf("reduction seed fanout A: %x/%x\n", fanout_first, 0x42810000);
  printf("reduction seed fanout B: %x/%x\n", fanout_second, 0x42810000);
  printf("vfmul to reduction: %x/%x\n", mul_reduction, 0x42800000);
  printf("reduction to store: %x/%x\n", stored, 0x42000000);
  printf("fp16 reduction chain: %x/%x\n", fp16, 0x5804);
  printf("integer reduction to scalar: %x/%x\n", integer_scalar, 0x20);
  printf("integer reduction to store: %x/%x\n", integer_stored, 0x20);
  printf("dual reduction result cache A: %x/%x\n",
         dual_cache_first, 0x20);
  printf("dual reduction result cache B: %x/%x\n",
         dual_cache_second, 0x20);
  printf("reduction chain bypass probe: %s\n",
         mismatch ? "FAILED" : "PASSED");

  return mismatch != 0;
}
