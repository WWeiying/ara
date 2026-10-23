/* Build with -std=c11 -O2 -Wall -Wextra -Werror -fno-tree-vectorize and
 * -Isoftware/qbs/include. Link no runtime: this isolates the new helpers from
 * the parent-owned runtime integration. Native builds use rv64gcv/lp64d;
 * repeat at VLEN128/1024 and QBS_PACK_AVL_LIMIT=7 after review.
 * The 33264 layout cases mirror the sealed candidate's 99792 native checks
 * across three configurations, not a claim that this new header ran there.
 */
#include "qbs/qbs_pack_rvv_internal.h"
#include "activation_pack_rvv_candidate.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { \
  fprintf(stderr, "PACK_INTERNAL_FAIL line=%d condition=%s\n", __LINE__, #c); \
  exit(1); } } while (0)

enum { GUARD = 32 };
static size_t layout_cases, mover_cases;

static void csr_begin(void) {
#if defined(__riscv_vector)
  __asm__ volatile("csrwi vcsr, 7\n\tli t0, 159\n\tcsrw fcsr, t0"
               : : : "t0", "memory");
#endif
}

static void csr_end(void) {
#if defined(__riscv_vector)
  unsigned fcsr, vcsr;
  __asm__ volatile("csrr %0, fcsr\n\tcsrr %1, vcsr"
               : "=r"(fcsr), "=r"(vcsr) : : "memory");
  CHECK(fcsr == 159 && vcsr == 7);
#endif
}

/* Test fixture only: emulate the parent's group/tail/zeroing responsibilities.
 * No validation API is introduced by the shared low-level helpers.
 */
static void pack_fixture(unsigned profile, unsigned group, size_t m, size_t k,
                         const uint8_t *src, size_t stride, uint8_t *dst) {
  const size_t block = profile == QBS_ACTIVATION_PROFILE_Q8_0 ? 34 : 292;
  const size_t scale = block == 34 ? 2 : 4, quant = block == 34 ? 32 : 256;
  for (size_t first = 0; first < m;) {
    const size_t active = m - first < group ? m - first : group;
    const size_t stored = group == 8 && active >= 5 ? 8 : active;
    if (group == 8 && active <= 4) {
      for (size_t row = 0; row < active; ++row)
        memcpy(dst + row * k * block, src + (first + row) * stride, k * block);
    } else {
      if (active != stored) memset(dst, 0, stored * k * block);
      for (size_t b = 0; b < k; ++b) {
        uint8_t *slab = dst + b * stored * block;
        for (size_t row = 0; row < active; ++row) {
          const uint8_t *in = src + (first + row) * stride + b * block;
          memcpy(slab + row * scale, in, scale);
          qbs_pack_interleave_bytes_internal(in + scale, slab + stored * scale + row,
                                              quant, stored);
          if (block == 292)
            qbs_pack_interleave_aux16_internal(in + 260, slab + stored * 260 + 2 * row,
                                               16, stored);
        }
      }
    }
    dst += stored * k * block;
    first += active;
  }
}

/* Destination-centric oracle from the sealed candidate test: independent of
 * the new helper's row loops and independent of its RVV/scalar implementation.
 */
static uint8_t expected_byte(const uint8_t *source, size_t stride, size_t m,
                             size_t k, unsigned group, size_t block, size_t offset) {
  const size_t scale = block == 34 ? 2 : 4, quant_end = block == 34 ? 34 : 260;
  size_t first = 0, active = 4, stored = 4, local = offset;
  if (group == 8) {
    const size_t full_bytes = (m / 8) * 8 * k * block;
    if (offset >= full_bytes && m % 8 <= 4) {
      local = offset - full_bytes;
      const size_t row = m / 8 * 8 + local / (k * block);
      return source[row * stride + local % (k * block)];
    }
    first = offset / (8 * k * block) * 8;
    active = m - first < 8 ? m - first : 8;
    stored = 8;
    local = offset % (8 * k * block);
  }
  const size_t b = local / (stored * block), within = local % (stored * block);
  size_t row, byte;
  if (within < stored * scale) {
    row = within / scale;
    byte = within % scale;
  } else if (within < stored * quant_end) {
    row = (within - stored * scale) % stored;
    byte = scale + (within - stored * scale) / stored;
  } else {
    const size_t aux = within - stored * quant_end;
    row = (aux / 2) % stored;
    byte = 260 + (aux / (2 * stored)) * 2 + aux % 2;
  }
  return row < active ? source[(first + row) * stride + b * block + byte] : 0;
}

static void shape(unsigned profile, size_t m, size_t k, size_t gap, size_t so, size_t d_o) {
  const size_t group = m == 4 ? 4 : 8;
  const size_t block = profile == QBS_ACTIVATION_PROFILE_Q8_0 ? 34 : 292;
  const size_t stride = k * block + gap, input_bytes = (m - 1) * stride + k * block;
  const size_t rows = group == 8 && m % 8 >= 5 ? (m + 7) / 8 * 8 : m;
  const size_t output_bytes = rows * k * block;
  const size_t in_size = input_bytes + 2 * GUARD + so;
  const size_t out_size = output_bytes + 2 * GUARD + d_o;
  uint8_t *input = malloc(in_size), *before = malloc(in_size);
  uint8_t *output = malloc(out_size), *reference = malloc(out_size);
  CHECK(input && before && output && reference);
  for (unsigned seed = 0; seed < 2; ++seed) {
    for (size_t i = 0; i < in_size; ++i) {
      uint32_t value = (uint32_t)i * 104729u + seed * 9176u;
      value ^= value >> 11;
      value *= UINT32_C(0x45d9f3b);
      input[i] = (uint8_t)(value ^ (value >> 16));
    }
    memcpy(before, input, in_size);
    memset(output, seed ? 0x96 : 0x69, out_size);
    memset(reference, seed ? 0x96 : 0x69, out_size);
    csr_begin();
    pack_fixture(profile, (unsigned)group, m, k, input + GUARD + so, stride, output + GUARD + d_o);
    csr_end();
    CHECK(qbs_pack_activation_candidate(profile, (unsigned)group, m, k,
          input + GUARD + so, input_bytes, gap ? stride : 0,
          reference + GUARD + d_o, output_bytes) == QBS_PACK_CANDIDATE_OK);
    CHECK(memcmp(output, reference, out_size) == 0);
    CHECK(memcmp(input, before, in_size) == 0);
    for (size_t i = 0; i < out_size; ++i) {
      const uint8_t wanted = i < GUARD + d_o || i >= GUARD + d_o + output_bytes
          ? (seed ? 0x96 : 0x69)
          : expected_byte(input + GUARD + so, stride, m, k, (unsigned)group, block, i - GUARD - d_o);
      CHECK(output[i] == wanted);
    }
    ++layout_cases;
  }
  free(input); free(before); free(output); free(reference);
}

/* Holes and bytes belonging to inactive rows must remain untouched. Exercise
 * exact source/destination adjacency too: disjoint spans may share allocation.
 */
static void movers(void) {
  const size_t counts[] = {0, 1, 7, 16, 17, 31, 32, 33, 255, 256};
  uint8_t src[1024], before[1024], dst[8192], expected[8192];
  for (size_t i = 0; i < sizeof(src); ++i) src[i] = (uint8_t)(i * 37 + i / 256);
  memcpy(before, src, sizeof(src));
  for (size_t rows = 4; rows <= 8; rows += 4)
    for (size_t c = 0; c < sizeof(counts) / sizeof(counts[0]); ++c)
      for (size_t so = 0; so < 4; ++so)
        for (size_t d_o = 0; d_o < 4; ++d_o)
          for (size_t width = 1; width <= 2; ++width) {
            memset(dst, 0xa5, sizeof(dst));
            memcpy(expected, dst, sizeof(dst));
            for (size_t i = 0; i < counts[c]; ++i)
              for (size_t j = 0; j < width; ++j)
                expected[GUARD + d_o + width * rows * i + j] = src[so + width * i + j];
            csr_begin();
            if (width == 1)
              qbs_pack_interleave_bytes_internal(src + so, dst + GUARD + d_o, counts[c], rows);
            else
              qbs_pack_interleave_aux16_internal(src + so, dst + GUARD + d_o, counts[c], rows);
            csr_end();
            CHECK(memcmp(src, before, sizeof(src)) == 0);
            CHECK(memcmp(dst, expected, sizeof(dst)) == 0);
            ++mover_cases;
          }
  csr_begin();
  qbs_pack_interleave_bytes_internal(NULL, NULL, 0, 4);
  qbs_pack_interleave_aux16_internal(NULL, NULL, 0, 8);
  csr_end();
  for (size_t width = 1; width <= 2; ++width) {
    uint8_t joint[512], saved[512];
    memset(joint, 0xa5, sizeof(joint));
    for (size_t i = 0; i < 16 * width; ++i) joint[i] = (uint8_t)i;
    memcpy(saved, joint, sizeof(joint));
    for (size_t i = 0; i < 16; ++i)
      for (size_t j = 0; j < width; ++j) saved[16 * width + 4 * width * i + j] = joint[width * i + j];
    if (width == 1) qbs_pack_interleave_bytes_internal(joint, joint + 16, 16, 4);
    else qbs_pack_interleave_aux16_internal(joint, joint + 32, 16, 4);
    CHECK(memcmp(joint, saved, sizeof(joint)) == 0);
  }
}

int main(void) {
#if defined(__riscv_vector)
  unsigned saved_fcsr, saved_vcsr;
  __asm__ volatile("csrr %0, fcsr\n\tcsrr %1, vcsr"
               : "=r"(saved_fcsr), "=r"(saved_vcsr) : : "memory");
#endif
  movers();
  const unsigned profiles[] = {QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_PROFILE_Q8_K};
  const size_t gaps[] = {0, 1, 7}, boundaries[] = {17, 28, 32, 33, 65, 256};
  for (size_t p = 0; p < 2; ++p) {
    for (size_t m = 4; m <= 24; ++m)
      for (size_t k = 1; k <= 8; ++k)
        for (size_t gap = 0; gap < 3; ++gap)
          for (size_t src = 0; src < 4; ++src)
            for (size_t dst = 0; dst < 4; ++dst)
              shape(profiles[p], m, k, gaps[gap], src, dst);
    for (size_t m = 4; m <= 24; ++m)
      for (size_t b = 0; b < sizeof(boundaries) / sizeof(boundaries[0]); ++b) {
        shape(profiles[p], m, boundaries[b], 0, 0, 0);
        shape(profiles[p], m, boundaries[b], 7, 1, 3);
      }
  }
  CHECK(layout_cases == 33264 && mover_cases == 640);
#if defined(__riscv_vector)
  __asm__ volatile("csrw fcsr, %0\n\tcsrw vcsr, %1" : : "r"(saved_fcsr), "r"(saved_vcsr) : "memory");
#endif
  printf("PACK_INTERNAL_PASS layouts=%zu movers=%zu rvv=%d avl_limit=%d\n",
         layout_cases, mover_cases, QBS_PACK_INTERNAL_RVV, QBS_PACK_AVL_LIMIT);
  return 0;
}
