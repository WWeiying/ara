#ifndef QBS_PACK_RVV_INTERNAL_H
#define QBS_PACK_RVV_INTERNAL_H

/* Internal byte movers derived from activation_pack_rvv_candidate.h.
 * Callers own profile/capacity/overflow validation, scale copies, tail layout,
 * and zero padding. These helpers write only one active row's selected bytes.
 *
 * Preconditions for count > 0: valid nonoverlapping source/destination spans;
 * storage_rows is 4 or 8; all span/stride arithmetic has been checked by the
 * caller. No alignment is required. Zero count accesses neither pointer.
 * bytes: read count bytes; last write is dst[(count-1)*storage_rows].
 * aux16: read 2*count bytes; last write is dst[2*(count-1)*storage_rows+1].
 * Byte order is preserved; there is no FP conversion, saturation, or rounding.
 * RVV callers must enable vector state and enter with vstart=0. vl/vtype are
 * caller-clobbered; fcsr/vcsr are untouched. No Zfh/Zvfh instructions are used.
 * QBS_PACK_FORCE_SCALAR disables explicit RVV, not compiler autovectorization.
 */
#include <stddef.h>
#include <stdint.h>

#if defined(__riscv_vector) && !defined(QBS_PACK_FORCE_SCALAR)
#include <riscv_vector.h>
#define QBS_PACK_INTERNAL_RVV 1
typedef uint16_t qbs_pack_internal_alias_u16 __attribute__((__may_alias__));
#else
#define QBS_PACK_INTERNAL_RVV 0
#endif

/* Test-only AVL ceiling. Production leaves it at zero (no artificial cap). */
#ifndef QBS_PACK_AVL_LIMIT
#define QBS_PACK_AVL_LIMIT 0
#endif

static inline size_t qbs_pack_internal_avl(size_t remaining) {
#if QBS_PACK_AVL_LIMIT > 0
  return remaining < QBS_PACK_AVL_LIMIT
      ? remaining : QBS_PACK_AVL_LIMIT;
#else
  return remaining;
#endif
}

static inline void qbs_pack_interleave_bytes_internal(
    const uint8_t *src, uint8_t *dst, size_t count, size_t storage_rows) {
#if QBS_PACK_INTERNAL_RVV
  while (count) {
    const size_t vl = __riscv_vsetvl_e8m1(qbs_pack_internal_avl(count));
    const vuint8m1_t data = __riscv_vle8_v_u8m1(src, vl);
    __riscv_vsse8_v_u8m1(dst, (ptrdiff_t)storage_rows, data, vl);
    count -= vl;
    if (count) {
      src += vl;
      dst += vl * storage_rows;
    }
  }
#else
  for (size_t i = 0; i < count; ++i) dst[i * storage_rows] = src[i];
#endif
}

static inline void qbs_pack_interleave_aux16_internal(
    const uint8_t *src, uint8_t *dst, size_t count, size_t storage_rows) {
  if (!count) return;
#if QBS_PACK_INTERNAL_RVV
  if ((((uintptr_t)src | (uintptr_t)dst) & 1u) == 0) {
    size_t remaining = count;
    while (remaining) {
      const size_t vl = __riscv_vsetvl_e16m1(qbs_pack_internal_avl(remaining));
      const vuint16m1_t data = __riscv_vle16_v_u16m1(
          (const qbs_pack_internal_alias_u16 *)(const void *)src, vl);
      __riscv_vsse16_v_u16m1((qbs_pack_internal_alias_u16 *)(void *)dst,
                            (ptrdiff_t)(2 * storage_rows), data, vl);
      remaining -= vl;
      if (remaining) {
        src += 2 * vl;
        dst += 2 * storage_rows * vl;
      }
    }
    return;
  }
  /* Either pointer may be byte-unaligned: preserve each aux byte separately. */
  for (size_t byte = 0; byte < 2; ++byte) {
    size_t offset = 0;
    while (offset < count) {
      const size_t vl = __riscv_vsetvl_e8m1(qbs_pack_internal_avl(count - offset));
      const vuint8m1_t data = __riscv_vlse8_v_u8m1(src + 2 * offset + byte, 2, vl);
      __riscv_vsse8_v_u8m1(dst + 2 * storage_rows * offset + byte,
                          (ptrdiff_t)(2 * storage_rows), data, vl);
      offset += vl;
    }
  }
#else
  for (size_t i = 0; i < count; ++i) {
    dst[2 * storage_rows * i] = src[2 * i];
    dst[2 * storage_rows * i + 1] = src[2 * i + 1];
  }
#endif
}

#endif
