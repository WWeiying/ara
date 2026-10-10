// SPDX-License-Identifier: SHL-0.51
#include "vector_macros.h"

enum { CAP = 8192 };
static uint8_t src[CAP] __attribute__((aligned(128)));
static uint8_t mask[CAP / 8] __attribute__((aligned(128)));
static uint16_t initial[CAP] __attribute__((aligned(128)));
static uint16_t result[CAP] __attribute__((aligned(128)));
static unsigned cases;

static uint16_t half_from_byte(uint8_t value, unsigned uns) {
  int x = uns ? (int)value : (value < 128 ? (int)value : (int)value - 256);
  unsigned sign = x < 0;
  unsigned mag = sign ? -x : x;
  if (!mag) return 0;
  unsigned p = 0;
  while ((mag >> (p + 1)) != 0) ++p;
  return (sign << 15) | ((p + 15) << 10) | ((mag - (1u << p)) << (10 - p));
}

#define EXEC(OP) \
  asm volatile( \
      "vsetvl zero, %[span], %[dst_type]\n" \
      "vle16.v v16, (%[initial])\n" \
      "vsetvl zero, %[count], %[type]\n" \
      "vle8.v v8, (%[src])\n" \
      "vlm.v v0, (%[mask])\n" \
      "vsetvl zero, %[vl], %[type]\n" \
      "csrwi frm, 0\n" \
      "csrwi fflags, 8\n" \
      "csrw vstart, %[start]\n" \
      OP "\n" \
      "csrr %[flags], fflags\n" \
      "csrr %[restart], vstart\n" \
      "vsetvl zero, %[span], %[dst_type]\n" \
      "vse16.v v16, (%[result])\n" \
      "fence\n" \
      "csrr zero, vl\n" \
      : [flags] "=&r"(flags), [restart] "=&r"(restart) \
      : [span] "r"(span), [dst_type] "r"(dst_type), [count] "r"(count), \
        [type] "r"(type), [vl] "r"(vl), [start] "r"(start), \
        [initial] "r"(initial), [src] "r"(src), [mask] "r"(mask), \
        [result] "r"(result) \
      : "memory", "v0", "v8", "v9", "v10", "v11", \
        "v16", "v17", "v18", "v19", "v20", "v21", "v22", "v23")

static void run(unsigned uns, unsigned long type, unsigned long bytes,
                unsigned policy) {
  unsigned long count = type > 3 ? bytes >> (8 - type) : bytes << type;
  unsigned long dst_lmul = (type + 1) & 7;
  unsigned long span = count < bytes / 2 ? bytes / 2 : count;
  unsigned long dst_type = 8 | (count < bytes / 2 ? 0 : dst_lmul);
  unsigned long vl = policy ? count - 3 : count;
  unsigned long start = policy == 2 ? count : (policy ? 5 : 0);
  unsigned long flags, restart;
  unsigned masked = policy == 1;
  for (unsigned i = 0; i < span; ++i) {
    src[i] = (uint8_t)(i * 73 + 91);
    initial[i] = 0x3555 ^ (i * 13);
    result[i] = ~initial[i];
  }
  for (unsigned i = 0; i < (span + 7) / 8; ++i) mask[i] = 0xa6;
  ++cases;
  if (uns) {
    if (masked) { EXEC("vfwcvt.f.xu.v v16, v8, v0.t"); }
    else { EXEC("vfwcvt.f.xu.v v16, v8"); }
  } else {
    if (masked) { EXEC("vfwcvt.f.x.v v16, v8, v0.t"); }
    else { EXEC("vfwcvt.f.x.v v16, v8"); }
  }
  for (unsigned i = 0; i < span; ++i) {
    uint16_t expected = initial[i];
    if (i >= start && i < vl && (!masked || (mask[i / 8] & (1 << (i % 8)))))
      expected = half_from_byte(src[i], uns);
    if (result[i] != expected) {
      printf("FAIL widening case=%u i=%u got=%x expected=%x\n", cases, i,
             (unsigned)result[i], (unsigned)expected);
      ++num_failed;
      break;
    }
  }
  if (flags != 8 || restart != 0) {
    printf("FAIL widening case=%u flags=%lx vstart=%lu\n", cases, flags, restart);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  unsigned long bytes, fcsr;
  asm volatile("csrr %0, vlenb; csrr %1, fcsr; csrwi vstart, 0"
               : "=r"(bytes), "=r"(fcsr) :: "memory");
  if (bytes < 128 || bytes * 4 > CAP) {
    printf("FAIL unsupported VLEN bytes=%lu\n", bytes);
    ++num_failed;
  } else {
    static const unsigned lmuls[] = {5, 0, 1, 2};
    for (unsigned l = 0; l < 4; ++l)
      for (unsigned uns = 0; uns < 2; ++uns)
        for (unsigned policy = 0; policy < 3; ++policy)
          run(uns, lmuls[l], bytes, policy);
  }
  asm volatile("csrw fcsr, %0" :: "r"(fcsr) : "memory");
  printf("vfwcvt_int8: %u cases\n", cases);
  EXIT_CHECK();
}
