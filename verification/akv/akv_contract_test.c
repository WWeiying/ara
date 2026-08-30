#include "../../apps/common/akv_abi.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>


static int failures;

#define CHECK(condition)                                                       \
  do {                                                                         \
    if (!(condition)) {                                                        \
      fprintf(stderr, "AKV contract check failed at line %d: %s\n", __LINE__, \
              #condition);                                                     \
      ++failures;                                                              \
    }                                                                          \
  } while (0)


static akv_descriptor_t valid_descriptor(void) {
  const uint32_t row_bytes = AKV_HEAD_DIM_128 * 2u;
  const akv_descriptor_t descriptor = {
      .version = AKV_DESCRIPTOR_VERSION,
      .element_format = AKV_ELEMENT_FORMAT_F16,
      .q_rows = 6,
      .flags = 0,
      .head_dim = AKV_HEAD_DIM_128,
      .kv_length = 256,
      .q_row_stride_bytes = row_bytes,
      .k_token_stride_bytes = row_bytes,
      .v_token_stride_bytes = row_bytes,
      .reserved0 = 0,
      .q_base = UINT64_C(0x10000),
      .k_base = UINT64_C(0x20000),
      .v_base = UINT64_C(0x40000),
      .reserved1 = 0,
      .reserved2 = 0,
  };
  return descriptor;
}


int main(void) {
  CHECK(sizeof(akv_descriptor_t) == 64u);
  CHECK(_Alignof(akv_descriptor_t) == 64u);
  CHECK(offsetof(akv_descriptor_t, version) == 0u);
  CHECK(offsetof(akv_descriptor_t, head_dim) == 4u);
  CHECK(offsetof(akv_descriptor_t, q_row_stride_bytes) == 8u);
  CHECK(offsetof(akv_descriptor_t, q_base) == 24u);
  CHECK(offsetof(akv_descriptor_t, k_base) == 32u);
  CHECK(offsetof(akv_descriptor_t, v_base) == 40u);
  CHECK(offsetof(akv_descriptor_t, reserved2) == 56u);

  CHECK(akv_encode_fill(10, 11, AKV_FILL_FULL) == UINT32_C(0x00b5205b));
  CHECK(akv_encode_fill(10, 11, AKV_FILL_REFILL) == UINT32_C(0x02b5205b));
  CHECK(akv_encode_load(8, 10, AKV_HEAD_DIM_64) == UINT32_C(0x0005345b));
  CHECK(akv_encode_load(8, 10, AKV_HEAD_DIM_128) == UINT32_C(0x0205345b));
  CHECK(akv_encode_info(10, 10) == UINT32_C(0x0005455b));
  CHECK(akv_encode_release() == UINT32_C(0x0000505b));

  CHECK(akv_capability_word(0, 1) == UINT64_C(0x000f010808400101));
  CHECK(akv_capability_word(1, 1) == UINT64_C(0x00000000006b1a5b));
  CHECK(akv_capability_word(2, 1) == 0u);
  CHECK(akv_head_dim_code(64) == AKV_HEAD_DIM_CODE_64);
  CHECK(akv_head_dim_code(128) == AKV_HEAD_DIM_CODE_128);
  CHECK(akv_head_dim_code(96) == AKV_HEAD_DIM_CODE_INVALID);
  CHECK(akv_destination_registers(64) == 1u);
  CHECK(akv_destination_registers(128) == 2u);

  CHECK(akv_tile_length(256, 0) == 8u);
  CHECK(akv_tile_length(256, 248) == 8u);
  CHECK(akv_tile_length(253, 248) == 5u);
  CHECK(akv_tile_length(253, 253) == 0u);
  CHECK(akv_selector(AKV_STREAM_Q, 5) == 20u);
  CHECK(akv_selector(AKV_STREAM_K, 7) == 29u);
  CHECK(akv_selector(AKV_STREAM_V, 7) == 30u);
  CHECK(akv_selector(AKV_STREAM_V, 8) == UINT32_MAX);
  CHECK(akv_selector((akv_stream_t)3, 0) == UINT32_MAX);

  CHECK(akv_range_fits(UINT64_MAX - 255u, 256u, 1u, 256u));
  CHECK(!akv_range_fits(UINT64_MAX - 254u, 256u, 1u, 256u));

  akv_descriptor_t descriptor = valid_descriptor();
  CHECK(akv_descriptor_is_valid(&descriptor));
  _Alignas(AKV_DESCRIPTOR_BYTES)
      unsigned char misaligned_storage[2u * AKV_DESCRIPTOR_BYTES];
  CHECK(!akv_descriptor_is_valid(misaligned_storage + 1u));
  CHECK(akv_load_selector_is_valid(
      &descriptor, 8, akv_selector(AKV_STREAM_Q, 5)));
  CHECK(!akv_load_selector_is_valid(
      &descriptor, 8, akv_selector(AKV_STREAM_Q, 6)));
  CHECK(akv_load_selector_is_valid(
      &descriptor, 8, akv_selector(AKV_STREAM_K, 7)));
  CHECK(!akv_load_selector_is_valid(
      &descriptor, 5, akv_selector(AKV_STREAM_V, 5)));
  CHECK(!akv_load_selector_is_valid(&descriptor, 8, 32u));

  descriptor.flags = 1;
  CHECK(!akv_descriptor_is_valid(&descriptor));
  descriptor = valid_descriptor();
  descriptor.q_rows = 9;
  CHECK(!akv_descriptor_is_valid(&descriptor));
  descriptor = valid_descriptor();
  descriptor.head_dim = 96;
  CHECK(!akv_descriptor_is_valid(&descriptor));
  descriptor = valid_descriptor();
  descriptor.q_base |= 1u;
  CHECK(!akv_descriptor_is_valid(&descriptor));
  descriptor = valid_descriptor();
  descriptor.k_token_stride_bytes = 254;
  CHECK(!akv_descriptor_is_valid(&descriptor));
  descriptor = valid_descriptor();
  descriptor.reserved1 = 1;
  CHECK(!akv_descriptor_is_valid(&descriptor));
  descriptor = valid_descriptor();
  descriptor.v_base = UINT64_MAX - 128u;
  CHECK(!akv_descriptor_is_valid(&descriptor));

  if (failures != 0) return 1;
  puts("AKV ABI contract PASS");
  return 0;
}
