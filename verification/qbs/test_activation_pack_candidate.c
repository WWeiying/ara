#include "activation_pack_rvv_candidate.h"

#include <stdio.h>
#include <stdlib.h>

#define CHECK(condition) do { if (!(condition)) { \
  fprintf(stderr, "PACK_CANDIDATE_FAIL line=%d condition=%s\n", __LINE__, #condition); \
  exit(1); } } while (0)

enum { GUARD = 32 };
static size_t cases;

static uint8_t pattern(size_t row, size_t block, size_t byte, unsigned seed) {
  uint32_t x = (uint32_t)(row * 1009 + block * 9176 + byte * 6361 + seed * 104729);
  x ^= x >> 11;
  x *= UINT32_C(0x45d9f3b);
  return (uint8_t)(x ^ (x >> 16));
}

/* Destination-centric oracle: decode each output byte's semantic coordinate.
 * Constants are deliberately independent of the helper's metadata/loops.
 * No production packer or qbs_ref is linked into this executable.
 */
static uint8_t expected_byte(const uint8_t *source, size_t stride,
                             size_t m, size_t k, unsigned group,
                             unsigned profile, size_t offset) {
  const size_t block_bytes = profile == QBS_ACTIVATION_PROFILE_Q8_0 ? 34 : 292;
  const size_t scale = block_bytes == 34 ? 2 : 4;
  const size_t quant_end = block_bytes == 34 ? 34 : 260;
  size_t first, active, stored, local;
  if (group == 4) {
    first = 0; active = 4; stored = 4; local = offset;
  } else {
    const size_t full_bytes = (m / 8) * 8 * k * block_bytes;
    if (offset >= full_bytes && m % 8 <= 4) {
      local = offset - full_bytes;
      const size_t row = m / 8 * 8 + local / (k * block_bytes);
      return source[row * stride + local % (k * block_bytes)];
    }
    const size_t tile = offset / (8 * k * block_bytes);
    first = tile * 8;
    active = m - first < 8 ? m - first : 8;
    stored = 8;
    local = offset % (8 * k * block_bytes);
  }
  const size_t b = local / (stored * block_bytes);
  const size_t within = local % (stored * block_bytes);
  size_t row, source_byte;
  if (within < stored * scale) {
    row = within / scale;
    source_byte = within % scale;
  } else if (within < stored * quant_end) {
    row = (within - stored * scale) % stored;
    source_byte = scale + (within - stored * scale) / stored;
  } else {
    const size_t aux = within - stored * quant_end;
    row = (aux / 2) % stored;
    source_byte = 260 + (aux / (2 * stored)) * 2 + aux % 2;
  }
  return row < active ? source[(first + row) * stride + b * block_bytes + source_byte] : 0;
}

static void run_case(unsigned profile, unsigned group, size_t m, size_t k,
                     size_t gap, size_t source_offset, size_t dest_offset) {
  const size_t block = profile == QBS_ACTIVATION_PROFILE_Q8_0 ? 34 : 292;
  const size_t row_bytes = k * block, stride = row_bytes + gap;
  const size_t src_bytes = (m - 1) * stride + row_bytes;
  const size_t rows = group == 8 && m % 8 >= 5 ? (m + 7) / 8 * 8 : m;
  const size_t dst_bytes = rows * row_bytes;
  const size_t src_alloc = src_bytes + 2 * GUARD + source_offset;
  const size_t dst_alloc = dst_bytes + 2 * GUARD + dest_offset;
  uint8_t *src = malloc(src_alloc), *snapshot = malloc(src_alloc);
  uint8_t *dst = malloc(dst_alloc), *expected = malloc(dst_bytes);
  CHECK(src && snapshot && dst && expected);
  uint8_t *input = src + GUARD + source_offset;
  uint8_t *output = dst + GUARD + dest_offset;
  for (unsigned seed = 0; seed < 2; ++seed) {
    memset(src, seed ? 0x96 : 0x69, src_alloc);
    for (size_t row = 0; row < m; ++row)
      for (size_t b = 0; b < k; ++b)
        for (size_t byte = 0; byte < block; ++byte)
          input[row * stride + b * block + byte] = pattern(row, b, byte, seed);
    memcpy(snapshot, src, src_alloc);
    for (size_t i = 0; i < dst_bytes; ++i)
      expected[i] = expected_byte(input, stride, m, k, group, profile, i);
    memset(dst, seed ? 0xcd : 0xa5, dst_alloc);
    CHECK(qbs_pack_activation_candidate(profile, group, m, k, input, src_bytes,
        gap ? stride : 0, output, dst_bytes) == QBS_PACK_CANDIDATE_OK);
    if (memcmp(output, expected, dst_bytes)) {
      fprintf(stderr, "profile=%u group=%u m=%zu k=%zu gap=%zu src_off=%zu dst_off=%zu seed=%u\n",
              profile, group, m, k, gap, source_offset, dest_offset, seed);
      CHECK(0);
    }
    CHECK(memcmp(src, snapshot, src_alloc) == 0);
    for (size_t i = 0; i < GUARD + dest_offset; ++i) CHECK(dst[i] == (seed ? 0xcd : 0xa5));
    for (size_t i = GUARD + dest_offset + dst_bytes; i < dst_alloc; ++i)
      CHECK(dst[i] == (seed ? 0xcd : 0xa5));
    /* Short spans must be rejected before even padding bytes are touched. */
    CHECK(qbs_pack_activation_candidate(profile, group, m, k, input, src_bytes - 1,
        stride, output, dst_bytes) == QBS_PACK_CANDIDATE_BUFFER);
    CHECK(qbs_pack_activation_candidate(profile, group, m, k, input, src_bytes,
        stride, output, dst_bytes - 1) == QBS_PACK_CANDIDATE_BUFFER);
    CHECK(memcmp(output, expected, dst_bytes) == 0);
    CHECK(memcmp(src, snapshot, src_alloc) == 0);
    for (size_t i = 0; i < GUARD + dest_offset; ++i) CHECK(dst[i] == (seed ? 0xcd : 0xa5));
    for (size_t i = GUARD + dest_offset + dst_bytes; i < dst_alloc; ++i)
      CHECK(dst[i] == (seed ? 0xcd : 0xa5));
    ++cases;
  }
  free(src); free(snapshot); free(dst); free(expected);
}

static void invalid_cases(void) {
  uint8_t memory[512], before[512];
  memset(memory, 0x5c, sizeof(memory));
  memcpy(before, memory, sizeof(memory));
#define REJECT(profile, group, m, k, src, srcbytes, stride, dst, dstbytes, status) \
  do { CHECK(qbs_pack_activation_candidate(profile, group, m, k, src, srcbytes, stride, dst, dstbytes) == status); \
       CHECK(memcmp(memory, before, sizeof(memory)) == 0); } while (0)
  const unsigned p = QBS_ACTIVATION_PROFILE_Q8_0;
  REJECT(p, 4, 4, 1, NULL, 136, 0, memory, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 4, 4, 1, memory, 136, 0, NULL, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 4, 4, 0, memory, 136, 0, memory + 256, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 4, 3, 1, memory, 136, 0, memory + 256, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 8, 4, 1, memory, 136, 0, memory + 256, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 7, 8, 1, memory, 272, 0, memory + 256, 272, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(0, 4, 4, 1, memory, 136, 0, memory + 256, 136, QBS_PACK_CANDIDATE_PROFILE);
  REJECT(p, 4, 4, 1, memory, 136, 33, memory + 256, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 4, 4, SIZE_MAX, memory, SIZE_MAX, 0, memory + 256, SIZE_MAX, QBS_PACK_CANDIDATE_OVERFLOW);
  REJECT(p, 8, SIZE_MAX, 1, memory, SIZE_MAX, 0, memory + 256, SIZE_MAX, QBS_PACK_CANDIDATE_OVERFLOW);
  REJECT(p, 4, 4, 1, memory, SIZE_MAX, SIZE_MAX, memory + 256, SIZE_MAX, QBS_PACK_CANDIDATE_OVERFLOW);
  REJECT(p, 4, 4, 1, memory, 136, 0, memory, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 4, 4, 1, memory, 136, 0, memory + 1, 136, QBS_PACK_CANDIDATE_ARGUMENT);
  REJECT(p, 4, 4, 1, memory + 1, 136, 0, memory, 136, QBS_PACK_CANDIDATE_ARGUMENT);
#undef REJECT
}

int main(void) {
  const unsigned profiles[] = {QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_PROFILE_Q8_K};
  const size_t gaps[] = {0, 1, 7};
  const size_t boundaries[] = {17, 28, 32, 33, 65, 256};
  for (size_t p = 0; p < 2; ++p) {
    /* Exhaustive bounded small matrix: all tails, 0..3 byte alignments,
     * tight/odd-gap input strides, two unrelated byte patterns. */
    for (size_t m = 4; m <= 24; ++m)
      for (size_t k = 1; k <= 8; ++k)
        for (size_t gap = 0; gap < 3; ++gap)
          for (size_t src = 0; src < 4; ++src)
            for (size_t dst = 0; dst < 4; ++dst)
              run_case(profiles[p], m == 4 ? 4 : 8, m, k, gaps[gap], src, dst);
    for (size_t m = 4; m <= 24; ++m)
      for (size_t b = 0; b < sizeof(boundaries) / sizeof(boundaries[0]); ++b) {
        run_case(profiles[p], m == 4 ? 4 : 8, m, boundaries[b], 0, 0, 0);
        run_case(profiles[p], m == 4 ? 4 : 8, m, boundaries[b], 7, 1, 3);
      }
  }
  invalid_cases();
  printf("PACK_CANDIDATE_PASS cases=%zu rvv=%d avl_limit=%d invalid=14\n",
         cases, QBS_PACK_CANDIDATE_RVV, QBS_PACK_CANDIDATE_AVL_LIMIT);
  return 0;
}
