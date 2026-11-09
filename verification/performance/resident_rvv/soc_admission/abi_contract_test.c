#include "akv_abi.h"

#include <assert.h>
#include <stdio.h>

static int registers_valid(uint32_t vd, uint32_t vs2) {
  if (vd >= 32u || vs2 >= 32u || vd % 4u || vs2 % 8u ||
      vd + 4u > 32u || vs2 + 8u > 32u)
    return 0;
  for (uint32_t d = vd; d < vd + 4u; ++d)
    for (uint32_t s = vs2; s < vs2 + 8u; ++s)
      if (d == s) return 0;
  return 1;
}

int main(void) {
  unsigned shapes = 0, controls = 0, encodings = 0;
  assert(AKV_RESIDENT_PV_SUPPORTED == 0u);
  assert(!akv_resident_pv_is_supported());
  assert(AKV_RESIDENT_PV_SOURCE_REGISTERS == 6u);
  assert(AKV_RESIDENT_PV_SOURCE_RESERVED_REGISTERS == 8u);
  assert(AKV_RESIDENT_PV_DESTINATION_REGISTERS == 4u);
  assert(AKV_RESIDENT_PV_SOURCE_ELEMENTS == 384u);
  assert(AKV_RESIDENT_PV_SOURCE_LANE_ELEMENTS == 96u);
  assert(AKV_RESIDENT_PV_SOURCE_LANE_WORDS == 24u);
  assert(AKV_RESIDENT_PV_DESTINATION_ELEMENTS == 256u);
  assert(AKV_RESIDENT_PV_HEAD_STRIDE_ELEMENTS == 128u);

  const unsigned dimensions[] = {64, 128, 96};
  for (unsigned d = 0; d < 3; ++d)
    for (unsigned h = 1; h <= 2; ++h)
      for (unsigned t = 1; t <= 64; ++t) {
        const uint64_t control = akv_resident_pv_control(t, h, dimensions[d]);
        assert(control == (t - 1u) + (h - 1u)*64u + d*128u);
        assert(akv_resident_pv_tokens(control) == t);
        assert(akv_resident_pv_heads(control) == h);
        assert(akv_resident_pv_head_dim(control) == dimensions[d]);
        assert(akv_resident_pv_command_is_valid(control, 0, 8));
        for (unsigned bit = 9; bit < 64; ++bit)
          assert(!akv_resident_pv_command_is_valid(control | (UINT64_C(1) << bit), 0, 8));
        ++shapes;
      }
  assert(shapes == 384u);

  for (uint64_t control = 0; control < 512; ++control)
    for (uint32_t vd = 0; vd < 32; ++vd)
      for (uint32_t vs2 = 0; vs2 < 32; ++vs2) {
        const int expected = ((control >> 7) != 3u) && registers_valid(vd, vs2);
        assert(akv_resident_pv_command_is_valid(control, vd, vs2) == expected);
        ++controls;
      }
  assert(controls == 524288u);

  for (uint32_t vd = 0; vd <= 32; ++vd)
    for (uint32_t vs2 = 0; vs2 <= 32; ++vs2)
      for (uint32_t rs1 = 0; rs1 <= 32; ++rs1) {
        const uint32_t actual = akv_encode_resident_pv(vd, rs1, vs2);
        if (rs1 < 32u && registers_valid(vd, vs2)) {
          const uint32_t expected = (2u << 25) | (vs2 << 20) |
              (rs1 << 15) | (7u << 12) | (vd << 7) | 0x5bu;
          assert(actual == expected);
          ++encodings;
        } else assert(actual == UINT32_MAX);
      }
  assert(encodings == 768u);
  assert(akv_encode_resident_pv(0, 10, 8) == UINT32_C(0x0485705b));
  assert(akv_resident_pv_command_is_valid(0, 28, 0));
  assert(akv_resident_pv_command_is_valid(0, 0, 24));
  assert(!akv_resident_pv_command_is_valid(0, 28, 24));
  assert(!akv_resident_pv_command_is_valid(0, UINT32_MAX, 8));
  assert(!akv_resident_pv_command_is_valid(0, 0, UINT32_MAX));
  assert(akv_encode_resident_pv(0, UINT32_MAX, 8) == UINT32_MAX);
  assert(!akv_resident_pv_command_is_valid(UINT64_MAX, 0, 8));

  const unsigned invalid_t[] = {0, 65, UINT32_MAX};
  const unsigned invalid_h[] = {0, 3, UINT32_MAX};
  const unsigned invalid_d[] = {0, 63, 65, 95, 97, 127, 129, 256, UINT32_MAX};
  for (unsigned i = 0; i < sizeof invalid_t / sizeof *invalid_t; ++i)
    assert(akv_resident_pv_control(invalid_t[i], 1, 64) == UINT64_MAX);
  for (unsigned i = 0; i < sizeof invalid_h / sizeof *invalid_h; ++i)
    assert(akv_resident_pv_control(1, invalid_h[i], 64) == UINT64_MAX);
  for (unsigned i = 0; i < sizeof invalid_d / sizeof *invalid_d; ++i)
    assert(akv_resident_pv_control(1, 1, invalid_d[i]) == UINT64_MAX);

  for (unsigned index = 0; index < 8; ++index)
    for (unsigned enabled = 0; enabled < 2; ++enabled)
      assert(akv_resident_pv_capability_word(index, enabled) == 0u);
  assert(akv_v2_capability_word(4, 1) == 0u);
  assert(akv_capability_word(0, 1) == UINT64_C(0x000f010808400101));
  assert(akv_capability_word(1, 1) == UINT64_C(0x00000000006b1a5b));
  assert(akv_v2_capability_word(2, 1) == UINT64_C(0x000001ff06084002));
  assert(akv_v2_capability_word(3, 1) == UINT64_C(0x0000000001803e5b));
  assert(akv_encode_v2_column_load(8, 10) == UINT32_C(0x0005745b));
  assert(akv_encode_v2_column_panel_load(8, 10) == UINT32_C(0x0205745b));
  assert(akv_encode_load(8, 10, 96) == UINT32_C(0x0405345b));
  assert(akv_destination_registers(64) == 1u);
  assert(akv_destination_registers(96) == 2u);
  assert(akv_destination_registers(128) == 2u);
  puts("ABI_PV_HOST_PASS shapes=384 controls=524288 encodings=768 capability=0");
  return 0;
}
