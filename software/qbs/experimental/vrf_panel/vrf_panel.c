#include "vrf_panel.h"

#include <stdint.h>

_Static_assert(sizeof(void *) == 8 && sizeof(float) == 4, "RV64 record ABI");
_Static_assert(sizeof(qbs_vrf_panel_record_t) == 24, "record stride");
_Static_assert(offsetof(qbs_vrf_panel_record_t, tile0) == 0, "tile0 offset");
_Static_assert(offsetof(qbs_vrf_panel_record_t, tile1) == 8, "tile1 offset");
_Static_assert(offsetof(qbs_vrf_panel_record_t, activation) == 16, "activation offset");
_Static_assert(QBS_QBACC_FUNCT7_BIT == 3 && QBS_M_MINUS_ONE_BITS == 3 &&
               QBS_OPCODE_CUSTOM2 == 0x5b && QBS_QBEXEC_FUNCT3 == 0 &&
               QBS_QBINFO_FUNCT3 == 1, "assembly encoding contract");

extern void qbs_vrf_panel_asm(const qbs_vrf_panel_record_t *, size_t,
                            float *, float *, size_t, size_t, size_t);
extern uint64_t qbs_vrf_panel_info(unsigned index);
extern size_t qbs_vrf_panel_vlenb(void);

static int address_ok(const void *p, size_t alignment, size_t bytes) {
  uintptr_t base = (uintptr_t)p;
  return base != 0 && base % alignment == 0 && bytes <= UINTPTR_MAX - base;
}

static int overlap(uintptr_t a, size_t na, uintptr_t b, size_t nb) {
  return a <= b ? b - a < na : a - b < nb;
}

/* Keep both public APIs on one compiled core, without mode-specialized clones. */
static __attribute__((noinline, noclone)) qbs_vrf_panel_status_t panel_run(
    const qbs_vrf_panel_record_t *records, size_t count,
    float *out0, float *out1, size_t stride, size_t n0, size_t n1, int direct) {
  if (count < 1 || count > 256 || n0 < 1 || n0 > 32 || n1 < 1 || n1 > 32 ||
      stride < n0 || stride < n1 || stride > (SIZE_MAX / 4 - 32) / 3 ||
      !address_ok(records, _Alignof(qbs_vrf_panel_record_t), count * sizeof(*records)) ||
      !address_ok(out0, 4, (3 * stride + n0) * 4) ||
      !address_ok(out1, 4, (3 * stride + n1) * 4))
    return QBS_VRF_PANEL_BAD_ARGUMENT;
  // Row-wise checks permit two disjoint column tiles of one strided matrix.
  for (size_t r = 0; r < 4; ++r)
    for (size_t s = 0; s < 4; ++s)
      if (overlap((uintptr_t)out0 + r * stride * 4, n0 * 4,
                  (uintptr_t)out1 + s * stride * 4, n1 * 4))
        return QBS_VRF_PANEL_BAD_ARGUMENT;

  unsigned weight_profile = 0, activation_profile = 0, weight_layout = 0;
  for (size_t i = 0; i < count; ++i) {
    const qbs_vrf_panel_record_t *record = &records[i];
    if (!address_ok(record->tile0, 16, 16) || !address_ok(record->tile1, 16, 16) ||
        !address_ok(record->activation, 4, 1))
      return QBS_VRF_PANEL_BAD_ARGUMENT;
    qbs_descriptor_fields_t a = qbs_unpack_descriptor_header(record->tile0->header);
    qbs_descriptor_fields_t b = qbs_unpack_descriptor_header(record->tile1->header);
    unsigned block_bytes = qbs_activation_block_bytes(a.activation_profile);
    if (record->tile0->header >> 47 || record->tile1->header >> 47 ||
        a.descriptor_version != QBS_DESCRIPTOR_VERSION ||
        b.descriptor_version != QBS_DESCRIPTOR_VERSION ||
        !qbs_profiles_compatible(a.weight_profile, a.activation_profile) ||
        (a.weight_layout != QBS_WEIGHT_LAYOUT_ROW_MAJOR &&
         a.weight_layout != QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) ||
        a.activation_layout != QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED ||
        b.activation_layout != a.activation_layout ||
        b.weight_profile != a.weight_profile || b.activation_profile != a.activation_profile ||
        b.weight_layout != a.weight_layout || a.n != n0 || b.n != n1 ||
        a.k_blocks != b.k_blocks || a.k_blocks > QBS_MAX_K_BLOCKS || block_bytes == 0 ||
        a.context_id != 0 || b.context_id != 0 ||
        a.context_generation != b.context_generation ||
        record->tile0->weight_base == 0 || record->tile1->weight_base == 0 ||
        (record->tile0->weight_base & 1) || (record->tile1->weight_base & 1) ||
        record->tile0->weight_base == record->tile1->weight_base)
      return QBS_VRF_PANEL_BAD_DESCRIPTOR;
    if (direct) {
      if (a.activation_access != QBS_ACTIVATION_ACCESS_DIRECT ||
          b.activation_access != QBS_ACTIVATION_ACCESS_DIRECT ||
          a.context_generation != 0)
        return QBS_VRF_PANEL_BAD_DESCRIPTOR;
    } else {
      if (a.k_blocks > 32 ||
          (size_t)a.k_blocks * 4 * block_bytes > QBS_ACTIVATION_CONTEXT_CAPACITY_BYTES ||
          a.activation_access != QBS_ACTIVATION_ACCESS_FILL ||
          b.activation_access != (i + 1 == count ? QBS_ACTIVATION_ACCESS_RELEASE :
                                                  QBS_ACTIVATION_ACCESS_REUSE))
        return QBS_VRF_PANEL_BAD_DESCRIPTOR;
    }
    if (i != 0 && (weight_profile != a.weight_profile ||
                   activation_profile != a.activation_profile || weight_layout != a.weight_layout))
      return QBS_VRF_PANEL_BAD_DESCRIPTOR;
    weight_profile = a.weight_profile;
    activation_profile = a.activation_profile;
    weight_layout = a.weight_layout;
    if (!address_ok(record->activation, 4, (size_t)a.k_blocks * 4 * block_bytes))
      return QBS_VRF_PANEL_BAD_ARGUMENT;
  }

  // The platform must establish that QBINFO and RVV are legal before calling.
  // Keep this experimental baseline deliberately restricted to the current ABI.
  if (qbs_vrf_panel_vlenb() != 128)
    return QBS_VRF_PANEL_UNSUPPORTED;
  for (unsigned index = 0; index < 4; ++index)
    if (qbs_vrf_panel_info(index) != qbs_capability_word(index, 1024))
      return QBS_VRF_PANEL_UNSUPPORTED;
  if (qbs_vrf_panel_info(4) != UINT64_C(1))
    return QBS_VRF_PANEL_UNSUPPORTED;
  qbs_vrf_panel_asm(records, count, out0, out1, stride, n0, n1);
  return QBS_VRF_PANEL_OK;
}

qbs_vrf_panel_status_t qbs_vrf_panel_run(
    const qbs_vrf_panel_record_t *records, size_t count,
    float *out0, float *out1, size_t stride, size_t n0, size_t n1) {
  return panel_run(records, count, out0, out1, stride, n0, n1, 0);
}

qbs_vrf_panel_status_t qbs_vrf_panel_direct_run(
    const qbs_vrf_panel_record_t *record, float *out0, float *out1,
    size_t stride, size_t n0, size_t n1) {
  return panel_run(record, 1, out0, out1, stride, n0, n1, 1);
}
