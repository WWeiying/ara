// Adjacent independent slide/reduction must not consume each other's operands.
#include "vector_macros.h"

static unsigned cases;
static unsigned checks;
static uint8_t mask_bits __attribute__((aligned(128)));

// Keep both instructions in one asm block with no intervening synchronization.
#define PAIR(SMASK, RMASK)                                                   \
  asm volatile("vslide1up.vx v8, v4, %[scalar]" SMASK "\n"                  \
               "vredand.vs v12, v16, v20" RMASK "\n"                     \
               :: [scalar] "r"(scalar) : "v8", "v12", "memory")

#define DEFINE_TEST(SEW, T)                                                  \
static void run_e##SEW(unsigned vl, unsigned ones, unsigned masked) {         \
  static T source[2] __attribute__((aligned(128)));                          \
  static T old_slide[2] __attribute__((aligned(128)));                       \
  static T red_source[2] __attribute__((aligned(128)));                      \
  static T seed[2] __attribute__((aligned(128)));                            \
  static T old_red[2] __attribute__((aligned(128)));                         \
  static T slide_result[2] __attribute__((aligned(128)));                    \
  static T red_result[2] __attribute__((aligned(128)));                      \
  const unsigned long scalar = UINT64_C(0x91a2b3c4d5e6f789);                \
  source[0] = (T)UINT64_C(0x123456789abcdef0);                              \
  source[1] = (T)UINT64_C(0xfedcba9876543210);                              \
  old_slide[0] = (T)UINT64_C(0x5a6b7c8d9eafb0c1);                           \
  old_slide[1] = (T)UINT64_C(0xc1b0af9e8d7c6b5a);                           \
  red_source[0] = (T)UINT64_C(0xf3c7ab6d95e1b7d3);                          \
  red_source[1] = (T)UINT64_C(0x6db3e7c95fa3cd6e);                          \
  seed[0] = (T)UINT64_C(0xdef7bd6fdb7eedb7);                                \
  seed[1] = 0;                                                             \
  old_red[0] = (T)UINT64_C(0x13579bdf2468ace0);                             \
  old_red[1] = (T)UINT64_C(0x02468ace13579bdf);                             \
  mask_bits = ones ? 3 : 0;                                                \
  asm volatile("fence rw, rw\n"                                           \
               "vsetivli zero, 2, e" #SEW ", m1, tu, mu\n"               \
               "vle" #SEW ".v v4, (%[source])\n"                         \
               "vle" #SEW ".v v8, (%[old_slide])\n"                      \
               "vle" #SEW ".v v12, (%[old_red])\n"                       \
               "vle" #SEW ".v v16, (%[red_source])\n"                    \
               "vle" #SEW ".v v20, (%[seed])\n"                          \
               "vlm.v v0, (%[mask])\n"                                   \
               "vsetvli zero, %[vl], e" #SEW ", m1, tu, mu\n"            \
               :: [source] "r"(source), [old_slide] "r"(old_slide),        \
                  [old_red] "r"(old_red), [red_source] "r"(red_source),    \
                  [seed] "r"(seed), [mask] "r"(&mask_bits),                \
                  [vl] "r"((unsigned long)vl)                             \
               : "v0", "v4", "v8", "v12", "v16", "v20", "memory");       \
  switch (masked) {                                                        \
    case 0: PAIR("", ""); break;                                          \
    case 1: PAIR(", v0.t", ""); break;                                    \
    case 2: PAIR("", ", v0.t"); break;                                    \
    default: PAIR(", v0.t", ", v0.t"); break;                             \
  }                                                                        \
  asm volatile("vsetivli zero, 2, e" #SEW ", m1, tu, mu\n"                \
               "vse" #SEW ".v v8, (%[slide_result])\n"                   \
               "vse" #SEW ".v v12, (%[red_result])\n"                    \
               :: [slide_result] "r"(slide_result),                       \
                  [red_result] "r"(red_result) : "memory");              \
  MEMORY_BARRIER;                                                          \
  ++cases;                                                                 \
  T expected_red = seed[0];                                                \
  if (!(masked & 2) || ones)                                               \
    for (unsigned i = 0; i < vl; ++i) expected_red &= red_source[i];        \
  for (unsigned i = 0; i < 2; ++i) {                                      \
    T expected_slide = old_slide[i];                                      \
    if (i < vl && (!(masked & 1) || ones))                                \
      expected_slide = i ? source[0] : (T)scalar;                          \
    T expected = i ? old_red[i] : expected_red;                           \
    checks += 2;                                                          \
    if (slide_result[i] != expected_slide || red_result[i] != expected) {  \
      printf("FAIL case=%u sew=%u vl=%u ones=%u masked=%u index=%u "        \
             "slide=%lx/%lx red=%lx/%lx\n", cases, SEW, vl, ones, masked, \
             i, (unsigned long)slide_result[i],                           \
             (unsigned long)expected_slide,                               \
             (unsigned long)red_result[i], (unsigned long)expected);      \
      ++num_failed;                                                       \
    }                                                                      \
  }                                                                        \
}

DEFINE_TEST(8, uint8_t)
DEFINE_TEST(16, uint16_t)
DEFINE_TEST(32, uint32_t)
DEFINE_TEST(64, uint64_t)

int main(void) {
  INIT_CHECK();
  enable_vec();
  cases = checks = 0;
  for (unsigned vl = 1; vl <= 2; ++vl)
    for (unsigned ones = 0; ones <= 1; ++ones)
      for (unsigned masked = 0; masked < 4; ++masked) {
        run_e8(vl, ones, masked);
        run_e16(vl, ones, masked);
        run_e32(vl, ones, masked);
        run_e64(vl, ones, masked);
      }
  printf("vslide1up_vredand: %u cases, %u checks, %d failures\n",
         cases, checks, num_failed);
  EXIT_CHECK();
}
