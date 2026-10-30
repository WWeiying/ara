#include "qbs/qbs.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "RUNTIME_PACK_FAIL line=%d condition=%s\n", __LINE__, #x); \
  exit(1); } } while (0)

enum { GUARD = 32 };
static size_t checks;

static unsigned environment(void) {
#if defined(__riscv_vector)
  unsigned f, v;
  __asm__ volatile("frcsr %0; csrr %1, vcsr" : "=r"(f), "=r"(v) : : "memory");
  return f | (v << 8);
#else
  return 0;
#endif
}

static void set_environment(unsigned seed) {
#if defined(__riscv_vector)
  const unsigned f = seed ? 0x5f : 0, v = seed ? 7 : 0;
  __asm__ volatile("fscsr %0; csrw vcsr, %1" : : "r"(f), "r"(v) : "memory");
#else
  (void)seed;
#endif
}

/* Decode destination coordinates independently of the runtime pack loops. */
static uint8_t expected(const uint8_t *src, size_t m, size_t k,
                        size_t bytes, size_t offset) {
  const size_t row_bytes = k * bytes;
  const size_t tile_rows = m == 4 ? 4 : 8;
  const size_t group = offset / (tile_rows * row_bytes);
  const size_t first = group * tile_rows;
  const size_t active = m - first < tile_rows ? m - first : tile_rows;
  const size_t local = offset % (tile_rows * row_bytes);
  if (m != 4 && active <= 4) return src[first * row_bytes + local];
  const size_t block = local / (tile_rows * bytes);
  const size_t within = local % (tile_rows * bytes);
  const size_t scale = bytes == 34 ? 2 : 4;
  const size_t quant_end = bytes == 34 ? 34 : 260;
  size_t row, source_byte;
  if (within < tile_rows * scale) {
    row = within / scale;
    source_byte = within % scale;
  } else if (within < tile_rows * quant_end) {
    row = (within - tile_rows * scale) % tile_rows;
    source_byte = scale + (within - tile_rows * scale) / tile_rows;
  } else {
    const size_t aux = within - tile_rows * quant_end;
    row = (aux / 2) % tile_rows;
    source_byte = 260 + (aux / (2 * tile_rows)) * 2 + aux % 2;
  }
  return row < active ? src[(first + row) * row_bytes + block * bytes + source_byte] : 0;
}

static qbs_status_t pack(unsigned profile, size_t m, size_t k,
                          const uint8_t *src, size_t src_bytes,
                          uint8_t *dst, size_t dst_bytes) {
  if (m == 4)
    return qbs_pack_activation_m4(profile, src, src_bytes, k, dst, dst_bytes);
  return qbs_pack_activation_m8_grouped(profile, src, src_bytes, m, k, dst, dst_bytes);
}

static void run_case(unsigned profile, size_t m, size_t k,
                     size_t src_offset, size_t dst_offset) {
  const size_t bytes = profile == QBS_ACTIVATION_PROFILE_Q8_0 ? 34 : 292;
  const size_t src_bytes = m * k * bytes;
  const size_t tail = m == 4 ? 0 : m % 8;
  const size_t dst_bytes = (m + (tail >= 5 ? 8 - tail : 0)) * k * bytes;
  const size_t src_size = src_bytes + 2 * GUARD + src_offset;
  const size_t dst_size = dst_bytes + 2 * GUARD + dst_offset;
  uint8_t *source = malloc(src_size), *before = malloc(src_size);
  uint8_t *destination = malloc(dst_size), *oracle = malloc(dst_bytes);
  CHECK(source && before && destination && oracle);
  uint8_t *src = source + GUARD + src_offset;
  uint8_t *dst = destination + GUARD + dst_offset;
  for (unsigned seed = 0; seed < 2; ++seed) {
    memset(source, 0x69, src_size);
    for (size_t i = 0; i < src_bytes; ++i) {
      uint32_t x = (uint32_t)(i * 6361 + (i / bytes) * 1009 + seed * 104729);
      x ^= x >> 11;
      src[i] = (uint8_t)(x ^ (x >> 16));
    }
    memcpy(before, source, src_size);
    for (size_t i = 0; i < dst_bytes; ++i) oracle[i] = expected(src, m, k, bytes, i);
    memset(destination, 0xa5, dst_size);
    set_environment(seed);
    const unsigned initial = environment();
    CHECK(pack(profile, m, k, src, src_bytes, dst, dst_bytes) == QBS_STATUS_OK);
    CHECK(environment() == initial);
    CHECK(memcmp(dst, oracle, dst_bytes) == 0);
    CHECK(memcmp(source, before, src_size) == 0);
    CHECK(pack(profile, m, k, src, src_bytes - 1, dst, dst_bytes) == QBS_STATUS_BUFFER_TOO_SMALL);
    CHECK(pack(profile, m, k, src, src_bytes, dst, dst_bytes - 1) == QBS_STATUS_BUFFER_TOO_SMALL);
    CHECK(environment() == initial);
    CHECK(memcmp(dst, oracle, dst_bytes) == 0);
    CHECK(memcmp(source, before, src_size) == 0);
    for (size_t i = 0; i < GUARD + dst_offset; ++i) CHECK(destination[i] == 0xa5);
    for (size_t i = GUARD + dst_offset + dst_bytes; i < dst_size; ++i)
      CHECK(destination[i] == 0xa5);
    ++checks;
  }
  free(source); free(before); free(destination); free(oracle);
}

static void invalid_cases(void) {
  uint8_t src[136], dst[136];
  memset(src, 0x69, sizeof(src));
  memset(dst, 0xa5, sizeof(dst));
  const unsigned p = QBS_ACTIVATION_PROFILE_Q8_0;
  CHECK(qbs_pack_activation_m4(p, NULL, 136, 1, dst, 136) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_pack_activation_m4(p, src, 136, 1, NULL, 136) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_pack_activation_m4(p, src, 136, 0, dst, 136) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_pack_activation_m4(0, src, 136, 1, dst, 136) == QBS_STATUS_PROFILE);
  CHECK(qbs_pack_activation_m4(p, src, SIZE_MAX, SIZE_MAX / 4 + 1,
                                dst, SIZE_MAX) == QBS_STATUS_SIZE_OVERFLOW);
  CHECK(qbs_pack_activation_m8_grouped(p, src, 136, 4, 1, dst, 136) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_pack_activation_m8_grouped(p, src, SIZE_MAX, SIZE_MAX, 1,
                                        dst, SIZE_MAX) == QBS_STATUS_SIZE_OVERFLOW);
  CHECK(qbs_pack_activation_m8_grouped(p, src, SIZE_MAX, 8, SIZE_MAX,
                                        dst, SIZE_MAX) == QBS_STATUS_SIZE_OVERFLOW);
  for (size_t i = 0; i < sizeof(src); ++i) CHECK(src[i] == 0x69 && dst[i] == 0xa5);
}

int main(void) {
  const unsigned profiles[] = {QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_PROFILE_Q8_K};
  const size_t blocks[] = {1, 2, 7, 28, 32, 33, 65, 256};
  for (size_t p = 0; p < 2; ++p)
    for (size_t m = 4; m <= 24; ++m)
      for (size_t b = 0; b < sizeof(blocks) / sizeof(blocks[0]); ++b)
        for (size_t s = 0; s < 4; ++s)
          for (size_t d = 0; d < 4; ++d)
            run_case(profiles[p], m, blocks[b], s, d);
  invalid_cases();
  printf("RUNTIME_PACK_PASS cases=%zu invalid=8 bytes=exact guards=exact fcsr_vcsr=exact\n", checks);
  return 0;
}
