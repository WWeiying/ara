#ifndef QBS_ACTIVATION_PACK_RVV_CANDIDATE_H
#define QBS_ACTIVATION_PACK_RVV_CANDIDATE_H

/* Standalone successor experiment; not selected by the production runtime.
 * Requires readable/writable, nonoverlapping spans. No quantization or FP ops.
 * row_stride=0 means tightly packed input. group=4 requires m=4; group=8
 * reproduces qbs_pack_activation_m8_grouped, including ROW_MAJOR short tails.
 * RVV requires vector state enabled by the caller/platform, as in GGML RVV.
 * This targets standalone row-quantize + pack and the shared M8 runtime path;
 * GGML M4 uses a fused scalar quantize/interleave and is not accelerated here.
 * Strided stores can still generate many small VLSU requests. Before selecting
 * a threshold, measure against vsseg4/8e8 or byte assembly into u32/u64 with
 * contiguous stores. Those alternatives and fused quantization are out of scope.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "qbs/qbs.h"

#if defined(__riscv_vector) && !defined(QBS_PACK_CANDIDATE_FORCE_SCALAR)
#include <riscv_vector.h>
#define QBS_PACK_CANDIDATE_RVV 1
typedef uint16_t qbs_pack_alias_u16 __attribute__((__may_alias__));
#else
#define QBS_PACK_CANDIDATE_RVV 0
#endif

/* Test-only AVL ceiling to exercise strip-mining even on large-VLEN hosts. */
#ifndef QBS_PACK_CANDIDATE_AVL_LIMIT
#define QBS_PACK_CANDIDATE_AVL_LIMIT 0
#endif

typedef enum {
  QBS_PACK_CANDIDATE_OK = 0,
  QBS_PACK_CANDIDATE_ARGUMENT,
  QBS_PACK_CANDIDATE_PROFILE,
  QBS_PACK_CANDIDATE_OVERFLOW,
  QBS_PACK_CANDIDATE_BUFFER
} qbs_pack_candidate_status;

static inline size_t qbs_pack_candidate_avl(size_t remaining) {
#if QBS_PACK_CANDIDATE_AVL_LIMIT > 0
  return remaining < QBS_PACK_CANDIDATE_AVL_LIMIT
      ? remaining : QBS_PACK_CANDIDATE_AVL_LIMIT;
#else
  return remaining;
#endif
}

static inline void qbs_pack_candidate_bytes(const uint8_t *src, uint8_t *dst,
                                           size_t count, size_t stride) {
#if QBS_PACK_CANDIDATE_RVV
  while (count) {
    const size_t vl = __riscv_vsetvl_e8m1(qbs_pack_candidate_avl(count));
    const vuint8m1_t data = __riscv_vle8_v_u8m1(src, vl);
    __riscv_vsse8_v_u8m1(dst, (ptrdiff_t)stride, data, vl);
    count -= vl;
    if (count) {
      src += vl;
      dst += vl * stride;
    }
  }
#else
  for (size_t i = 0; i < count; ++i) dst[i * stride] = src[i];
#endif
}

static inline void qbs_pack_candidate_aux(const uint8_t *src, uint8_t *dst,
                                         size_t stored_rows) {
#if QBS_PACK_CANDIDATE_RVV
  if ((((uintptr_t)src | (uintptr_t)dst) & 1u) == 0) {
    size_t remaining = 16;
    while (remaining) {
      const size_t vl = __riscv_vsetvl_e16m1(qbs_pack_candidate_avl(remaining));
      const vuint16m1_t data = __riscv_vle16_v_u16m1(
          (const qbs_pack_alias_u16 *)(const void *)src, vl);
      __riscv_vsse16_v_u16m1((qbs_pack_alias_u16 *)(void *)dst,
                             (ptrdiff_t)(2 * stored_rows), data, vl);
      remaining -= vl;
      if (remaining) {
        src += 2 * vl;
        dst += 2 * stored_rows * vl;
      }
    }
    return;
  }
  /* Unaligned sources need a strided byte load as well as a strided store. */
  for (size_t byte = 0; byte < 2; ++byte) {
    size_t offset = 0;
    while (offset < 16) {
      const size_t vl = __riscv_vsetvl_e8m1(qbs_pack_candidate_avl(16 - offset));
      const vuint8m1_t data = __riscv_vlse8_v_u8m1(src + 2 * offset + byte, 2, vl);
      __riscv_vsse8_v_u8m1(dst + 2 * stored_rows * offset + byte,
                           (ptrdiff_t)(2 * stored_rows), data, vl);
      offset += vl;
    }
  }
#else
  for (size_t i = 0; i < 16; ++i) {
    dst[2 * stored_rows * i] = src[2 * i];
    dst[2 * stored_rows * i + 1] = src[2 * i + 1];
  }
#endif
}

static inline qbs_pack_candidate_status qbs_pack_activation_candidate(
    unsigned profile, unsigned group, size_t m, size_t k,
    const void *source, size_t source_bytes, size_t row_stride,
    void *destination, size_t destination_bytes) {
  if (!source || !destination || !k ||
      (group != 4 && group != 8) || (group == 4 ? m != 4 : m < 5))
    return QBS_PACK_CANDIDATE_ARGUMENT;
  const size_t block = profile == QBS_ACTIVATION_PROFILE_Q8_0 ? 34 :
      profile == QBS_ACTIVATION_PROFILE_Q8_K ? 292 : 0;
  if (!block) return QBS_PACK_CANDIDATE_PROFILE;
  if (k > SIZE_MAX / block) return QBS_PACK_CANDIDATE_OVERFLOW;
  const size_t row_bytes = k * block;
  if (!row_stride) row_stride = row_bytes;
  if (row_stride < row_bytes) return QBS_PACK_CANDIDATE_ARGUMENT;
  if (m - 1 > (SIZE_MAX - row_bytes) / row_stride)
    return QBS_PACK_CANDIDATE_OVERFLOW;
  const size_t required_source = (m - 1) * row_stride + row_bytes;
  const size_t tail = group == 8 ? m % 8 : 0;
  const size_t padding = tail >= 5 ? 8 - tail : 0;
  if (m > SIZE_MAX - padding || m + padding > SIZE_MAX / row_bytes)
    return QBS_PACK_CANDIDATE_OVERFLOW;
  const size_t required_destination = (m + padding) * row_bytes;
  if (source_bytes < required_source || destination_bytes < required_destination)
    return QBS_PACK_CANDIDATE_BUFFER;
  const uintptr_t s = (uintptr_t)source, d = (uintptr_t)destination;
  if (required_source > UINTPTR_MAX - s || required_destination > UINTPTR_MAX - d)
    return QBS_PACK_CANDIDATE_OVERFLOW;
  if (s <= d ? d - s < required_source : s - d < required_destination)
    return QBS_PACK_CANDIDATE_ARGUMENT;

  const size_t scale = block == 34 ? 2 : 4;
  const size_t quants = block == 34 ? 32 : 256;
  size_t written = 0;
  for (size_t first = 0; first < m;) {
    const size_t active = m - first < group ? m - first : group;
    const size_t stored = group == 8 && active >= 5 ? 8 : active;
    uint8_t *out = (uint8_t *)destination + written;
    if (group == 8 && active <= 4) {
      for (size_t row = 0; row < active; ++row)
        memcpy(out + row * row_bytes,
               (const uint8_t *)source + (first + row) * row_stride, row_bytes);
    } else {
      /* Full groups overwrite every byte. Only padded groups need zeroing. */
      if (active != stored) memset(out, 0, stored * row_bytes);
      for (size_t b = 0; b < k; ++b) {
        uint8_t *slab = out + b * stored * block;
        for (size_t row = 0; row < active; ++row) {
          const uint8_t *in = (const uint8_t *)source +
              (first + row) * row_stride + b * block;
          memcpy(slab + row * scale, in, scale);
          qbs_pack_candidate_bytes(in + scale, slab + stored * scale + row,
                                    quants, stored);
          if (block == 292)
            qbs_pack_candidate_aux(in + 260, slab + stored * 260 + 2 * row, stored);
        }
      }
    }
    written += stored * row_bytes;
    first += active;
  }
  return QBS_PACK_CANDIDATE_OK;
}

#endif
