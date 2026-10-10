// SPDX-License-Identifier: SHL-0.51
// Four Ara lanes map logical elements l and l+4 to the two FP32 slots.
// Exercise exception masks independently of destination write enables.
#include "vector_macros.h"

enum { N = 24, NX = 1, DZ = 8, NV = 16 };
enum { EXACT, DIV_ZERO, INVALID, SNAN };
enum { PATTERN, INACTIVE_INVALID, INACTIVE_SNAN };
static uint32_t numerator[N] __attribute__((aligned(128)));
static uint32_t denominator[N] __attribute__((aligned(128)));
static uint32_t initial[N] __attribute__((aligned(128)));
static uint32_t output[N] __attribute__((aligned(128)));
static uint32_t predicate __attribute__((aligned(128)));
static unsigned kinds[N];
static unsigned cases, checks, active_checks, prefix_checks, masked_checks, tail_checks;

static void check(unsigned id, const char *name, const char *field,
                  unsigned element, uint64_t got, uint64_t want) {
  ++checks;
  if (got != want) {
    if (num_failed < 16)
      printf("FAIL case=%u name=%s field=%s i=%u got=%lx expected=%lx\n",
             id, name, field, element, got, want);
    ++num_failed;
  }
}

// Keep the CSR read adjacent to DIV; vector barriers occur only afterwards.
#define EXECUTE(DIV)                                                           \
  asm volatile(                                                               \
      "fence\n"                                                              \
      "vsetvli zero, %[span], e32, m1, tu, mu\n"                               \
      "vle32.v v8, (%[num])\n"                                               \
      "vle32.v v10, (%[den])\n"                                              \
      "vle32.v v12, (%[init])\n"                                             \
      "vsetvli %[got_vl], %[vl], e32, m1, tu, mu\n"                           \
      "vlm.v v0, (%[mask])\n"                                                \
      "csrw fcsr, %[seed]\n"                                                 \
      "csrw vstart, %[start]\n"                                              \
      DIV                                                                     \
      "csrr %[flags], fflags\n"                                              \
      "csrr %[got_start], vstart\n"                                          \
      "vsetvli %[store_vl], %[span], e32, m1, tu, mu\n"                        \
      "vse32.v v12, (%[out])\n"                                              \
      "fence\n"                                                              \
      "csrr zero, vl\n"                                                      \
      "csrr %[late], fflags\n"                                               \
      "csrwi fflags, 0\n"                                                    \
      "csrr %[cleared], fflags\n"                                            \
      : [flags] "=&r"(flags), [got_start] "=&r"(got_start),                   \
        [got_vl] "=&r"(got_vl), [store_vl] "=&r"(store_vl),                  \
        [late] "=&r"(late), [cleared] "=&r"(cleared)                         \
      : [num] "r"(numerator), [den] "r"(denominator), [init] "r"(initial),   \
        [out] "r"(output), [mask] "r"(&predicate), [span] "r"((uint64_t)N), \
        [vl] "r"((uint64_t)vl), [start] "r"((uint64_t)start),                \
        [seed] "r"((uint64_t)seed)                                           \
      : "memory", "v0", "v8", "v10", "v12")

static __attribute__((noinline)) void run_case(
    const char *name, unsigned low, unsigned high, uint32_t mask,
    unsigned vl, unsigned start, unsigned mode, unsigned unmasked,
    unsigned seed, unsigned flags_contract) {
  const unsigned id = ++cases;
  uint64_t flags, got_start, got_vl, store_vl, late, cleared;
  unsigned expected_flags = seed;
  predicate = mask;
  for (unsigned i = 0; i < N; ++i) {
    unsigned kind = ((i / 4) & 1) ? high : low;
    if (mode != PATTERN && (i < start || i >= vl ||
                            (!unmasked && !(mask & (1u << i)))))
      kind = mode == INACTIVE_SNAN ? SNAN : INVALID;
    kinds[i] = kind;
    numerator[i] = kind == EXACT ? 0x40c00000u :
                   kind == INVALID ? 0 : kind == SNAN ? 0x7f800001u :
                   (i & 1) ? 0xbf800000u : 0x3f800000u;
    denominator[i] = (kind == EXACT || kind == SNAN) ? 0x40000000u : 0;
    initial[i] = 0x42c60000u + i;
    output[i] = ~initial[i];
  }
  if (unmasked) {
    EXECUTE("vfdiv.vv v12, v8, v10\n");
  } else {
    EXECUTE("vfdiv.vv v12, v8, v10, v0.t\n");
  }
  for (unsigned i = 0; i < N; ++i) {
    uint32_t want = initial[i];
    if (i >= vl) {
      ++tail_checks;
    } else if (i < start) {
      ++prefix_checks;
    } else if (!unmasked && !(mask & (1u << i))) {
      ++masked_checks;
    } else {
      ++active_checks;
      if (kinds[i] == EXACT) {
        want = 0x40400000u;
      } else if (kinds[i] == DIV_ZERO) {
        want = (numerator[i] & 0x80000000u) | 0x7f800000u;
        expected_flags |= DZ;
      } else {
        want = 0x7fc00000u;
        expected_flags |= NV;
      }
    }
    check(id, name, "vd", i, output[i], want);
  }
  check(id, name, "reference_flags", 0, expected_flags, flags_contract);
  check(id, name, "immediate_flags", 0, flags, flags_contract);
  check(id, name, "vstart_reset", 0, got_start, 0);
  check(id, name, "vl", 0, got_vl, vl);
  check(id, name, "store_vl", 0, store_vl, N);
  check(id, name, "late_flags", 0, late, flags_contract);
  check(id, name, "cleared_flags", 0, cleared, 0);
  printf("CASE id=%u name=%s vl=%u start=%u mask=%x unmasked=%u flags=%lx expected=%x\n",
         id, name, vl, start, mask, unmasked, flags, flags_contract);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  cases = checks = active_checks = prefix_checks = masked_checks = tail_checks = 0;
  const unsigned low[4] = {DIV_ZERO, INVALID, EXACT, INVALID};
  const unsigned high[4] = {INVALID, DIV_ZERO, INVALID, EXACT};
  const char *names[4][2] = {
      {"lower_DZ_upper_NV", "upper_NV_lower_DZ"},
      {"lower_NV_upper_DZ", "upper_DZ_lower_NV"},
      {"lower_exact_upper_NV", "upper_NV_lower_exact"},
      {"lower_NV_upper_exact", "upper_exact_lower_NV"}};
  for (unsigned lane = 0; lane < 4; ++lane) {
    for (unsigned pattern = 0; pattern < 4; ++pattern) {
      for (unsigned half = 0; half < 2; ++half) {
        unsigned kind = half ? high[pattern] : low[pattern];
        uint32_t mask = 0x010101u << (lane + 4 * half);
        run_case(names[pattern][half], low[pattern], high[pattern], mask,
                 N, 0, PATTERN, 0, 0, kind == DIV_ZERO ? DZ : kind == INVALID ? NV : 0);
      }
    }
  }
  run_case("all_exact_dummy_lane_guard", EXACT, EXACT, 0xffffff, N, 0, PATTERN, 1, 0, 0);
  run_case("all_DZ_no_dummy_NV", DIV_ZERO, DIV_ZERO, 0xffffff, N, 0, PATTERN, 1, 0, DZ);
  run_case("all_NV", INVALID, INVALID, 0xffffff, N, 0, PATTERN, 1, 0, NV);
  run_case("active_DZ_and_NV", DIV_ZERO, INVALID, 0xffffff, N, 0, PATTERN, 1, 0, DZ | NV);
  run_case("all_masked_NV", INVALID, INVALID, 0, N, 0, PATTERN, 0, 0, 0);
  run_case("vstart3_tail9", EXACT, EXACT, 0xffffff, 9, 3, INACTIVE_INVALID, 1, 0, 0);
  run_case("vstart5_tail14_snan", EXACT, EXACT, 0xffffff, 14, 5, INACTIVE_SNAN, 1, 0, 0);
  run_case("vstart7_tail13_upper", EXACT, EXACT, 0xf0f0f0, 13, 7, INACTIVE_INVALID, 0, 0, 0);
  run_case("tail3_inactive_NV", EXACT, EXACT, 0xffffff, 3, 0, INACTIVE_INVALID, 1, 0, 0);
  run_case("tail5_upper_DZ", INVALID, DIV_ZERO, 0xf0f0f0, 5, 0, PATTERN, 0, 0, DZ);
  run_case("tail7_lower_exact", EXACT, INVALID, 0x0f0f0f, 7, 0, PATTERN, 0, 0, 0);
  run_case("vstart_equals_vl", INVALID, INVALID, 0xffffff, 9, 9, PATTERN, 1, 0, 0);
  run_case("vstart_above_vl", INVALID, INVALID, 0xffffff, 7, 9, PATTERN, 1, 0, 0);
  run_case("zero_vl", INVALID, INVALID, 0xffffff, 0, 0, PATTERN, 1, 0, 0);
  run_case("vstart3_tail13_odd_DZ_sticky_NX", DIV_ZERO, DIV_ZERO, 0xaaaaaa, 13, 3,
           INACTIVE_INVALID, 0, NX, NX | DZ);
  run_case("vstart5_tail21_even_NV_sticky_DZ", INVALID, INVALID, 0x555555, 21, 5,
           PATTERN, 0, DZ, DZ | NV);
  run_case("upper_DZ_lower_prestart_NV", INVALID, DIV_ZERO, 0xffffff, 8, 4, PATTERN, 1, 0, DZ);
  run_case("lower_DZ_upper_tail_NV", DIV_ZERO, INVALID, 0xffffff, 4, 0, PATTERN, 1, 0, DZ);
  run_case("upper_NV_lower_prestart_DZ", DIV_ZERO, INVALID, 0xffffff, 8, 4, PATTERN, 1, 0, NV);
  run_case("lower_NV_upper_tail_DZ", INVALID, DIV_ZERO, 0xffffff, 4, 0, PATTERN, 1, 0, NV);
  printf("vfdiv_mask_flags: %u cases, %u checks, active=%u prefix=%u masked=%u tail=%u\n",
         cases, checks, active_checks, prefix_checks, masked_checks, tail_checks);
  EXIT_CHECK();
}
