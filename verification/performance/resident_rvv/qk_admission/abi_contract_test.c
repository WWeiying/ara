/* Host ABI checks only: experimental macros never advertise runtime support. */
#include "akv_abi.h"

#include <assert.h>
#include <stdio.h>

static int valid_destination(uint32_t vd) {
  return vd < 32u && vd % 4u == 0u;
}

int main(void) {
  unsigned shapes = 0, controls = 0, encodings = 0;
  const unsigned dimensions[] = {64, 128, 96};
  assert(AKV_RESIDENT_QK_FUNCT3 == 7u && AKV_RESIDENT_QK_FUNCT7 == 3u);
  assert(AKV_RESIDENT_QK_CONTROL_BITS == 12u);
  assert(AKV_RESIDENT_QK_QUERY_BASE_SHIFT == 9u);
  assert(AKV_RESIDENT_QK_QUERY_BASE_BITS == 3u);
  assert(AKV_RESIDENT_QK_NR_LANES == 4u && AKV_RESIDENT_QK_VLEN_BITS == 1024u);
  assert(AKV_RESIDENT_QK_ELEMENT_BITS == 32u);
  assert(AKV_RESIDENT_QK_HEAD_STRIDE_ELEMENTS == 64u);
  assert(AKV_RESIDENT_QK_DESTINATION_ELEMENTS == 128u);
  assert(AKV_RESIDENT_QK_DESTINATION_REGISTERS == 4u);
  assert(AKV_RESIDENT_QK_SOURCE_REGISTERS == 0u);
  assert(AKV_RESIDENT_QK_SUPPORTED == 0u && !akv_resident_qk_is_supported());

  for (unsigned d = 0; d < 3; ++d)
    for (unsigned h = 1; h <= 2; ++h)
      for (unsigned t = 1; t <= 64; ++t)
        for (unsigned q = 0; q < 8; ++q) {
          const uint64_t actual = akv_resident_qk_control(t, h, dimensions[d], q);
          if (q + h > 8) {
            assert(actual == UINT64_MAX);
            continue;
          }
          const uint64_t expected = (t - 1u) + 64u*(h - 1u) + 128u*d + 512u*q;
          assert(actual == expected);
          assert(akv_resident_pv_tokens(actual) == t);
          assert(akv_resident_pv_heads(actual) == h);
          assert(akv_resident_pv_head_dim(actual) == dimensions[d]);
          assert(akv_resident_qk_query_base(actual) == q);
          assert((actual & 511u) == akv_resident_pv_control(t, h, dimensions[d]));
          assert(akv_resident_qk_command_is_valid(actual, 0, 0));
          assert(akv_resident_qk_command_is_valid(actual, 28, 0));
          for (unsigned bit = 12; bit < 64; ++bit)
            assert(!akv_resident_qk_command_is_valid(actual | (UINT64_C(1) << bit), 0, 0));
          ++shapes;
        }
  assert(shapes == 2880u);

  for (uint64_t c = 0; c < 4096; ++c)
    for (uint32_t vd = 0; vd < 32; ++vd)
      for (uint32_t rs2 = 0; rs2 < 32; ++rs2) {
        const unsigned d = (unsigned)(c / 128u) % 4u;
        const unsigned h = 1u + (unsigned)(c / 64u) % 2u;
        const unsigned q = (unsigned)(c / 512u);
        const int expected = d != 3u && q + h <= 8u && rs2 == 0 && valid_destination(vd);
        assert(akv_resident_qk_command_is_valid(c, vd, rs2) == expected);
        ++controls;
      }
  assert(controls == 4194304u);

  for (uint32_t vd = 0; vd <= 32; ++vd)
    for (uint32_t rs1 = 0; rs1 <= 32; ++rs1) {
      const uint32_t actual = akv_encode_resident_qk(vd, rs1);
      if (valid_destination(vd) && rs1 < 32u) {
        assert(actual == (UINT32_C(0x0600705b) | (rs1 << 15) | (vd << 7)));
        assert(((actual >> 20) & 31u) == 0u);
        ++encodings;
      } else assert(actual == UINT32_MAX);
    }
  assert(encodings == 256u);
  assert(akv_encode_resident_qk(0, 10) == UINT32_C(0x0605705b));
  assert(akv_encode_resident_qk(UINT32_MAX, 0) == UINT32_MAX);
  assert(akv_encode_resident_qk(0, UINT32_MAX) == UINT32_MAX);
  assert(!akv_resident_qk_command_is_valid(UINT64_MAX, 0, 0));
  assert(!akv_resident_qk_command_is_valid(0, UINT32_MAX, 0));
  assert(!akv_resident_qk_command_is_valid(0, 0, UINT32_MAX));
  assert(akv_resident_qk_control(64, 1, 96, 7) != UINT64_MAX);
  assert(akv_resident_qk_control(64, 2, 96, 7) == UINT64_MAX);
  const unsigned bad_tokens[] = {0, 65, UINT32_MAX};
  const unsigned bad_heads[] = {0, 3, UINT32_MAX};
  const unsigned bad_dims[] = {0, 63, 65, 95, 97, 127, 129, 256, UINT32_MAX};
  const unsigned bad_bases[] = {8, 9, 255, UINT32_MAX};
  for (unsigned i = 0; i < sizeof bad_tokens / sizeof *bad_tokens; ++i)
    assert(akv_resident_qk_control(bad_tokens[i], 1, 64, 0) == UINT64_MAX);
  for (unsigned i = 0; i < sizeof bad_heads / sizeof *bad_heads; ++i)
    assert(akv_resident_qk_control(1, bad_heads[i], 64, 0) == UINT64_MAX);
  for (unsigned i = 0; i < sizeof bad_dims / sizeof *bad_dims; ++i)
    assert(akv_resident_qk_control(1, 1, bad_dims[i], 0) == UINT64_MAX);
  for (unsigned i = 0; i < sizeof bad_bases / sizeof *bad_bases; ++i)
    assert(akv_resident_qk_control(1, 1, 64, bad_bases[i]) == UINT64_MAX);

  for (unsigned index = 0; index < 256; ++index)
    for (unsigned enabled = 0; enabled < 2; ++enabled) {
      assert(akv_resident_qk_capability_word(index, enabled) == 0);
      assert(akv_resident_pv_capability_word(index, enabled) == 0);
    }
  assert(akv_resident_qk_capability_word(UINT64_MAX, 1) == 0);
  assert((akv_capability_word(4, 1) | akv_v2_capability_word(4, 1) |
          akv_resident_pv_capability_word(4, 1) | akv_resident_qk_capability_word(4, 1)) == 0);
  puts("QK_ABI_HOST_PASS shapes=2880 controls=4194304 encodings=256 capability=0");
  return 0;
}
