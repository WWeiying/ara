#include "../../../software/akv/experimental/paired_heads/admission.h"

#include <assert.h>
#include <stdio.h>

static akv_capabilities_t supported(void) {
  const akv_capabilities_t c = {
      .valid = 1, .enabled = 1, .f16_payload = 1,
      .max_q_rows = AKV_MAX_Q_ROWS, .context_count = 1,
      .head_dim_64 = 1, .head_dim_128 = 1,
      .token_axis_valid = 1, .token_axis_enabled = 1,
      .token_axis_tail = 1, .token_axis_row_view = 1,
      .token_axis_column_panel4 = 1, .token_axis_d_axis_tail = 1,
      .token_axis_tile_tokens = AKV_V2_TILE_TOKENS};
  return c;
}

int main(void) {
  unsigned checked = 0;
  for (unsigned dim = 0; dim <= 257; ++dim) {
    for (unsigned heads = 0; heads <= 9; ++heads) {
      akv_descriptor_t d = {.element_format = AKV_ELEMENT_FORMAT_F16,
                            .q_rows = heads, .head_dim = dim};
      const akv_capabilities_t good = supported();
      const int expected = heads >= 2 && heads <= 8 &&
          (dim == 64 || dim == 96 || dim == 128) &&
          !(heads == 6 && dim == 128);
      assert(akv_pair_f16_admitted(1, &d, &good) == expected);
      assert(!akv_pair_f16_admitted(0, &d, &good));
      assert(!akv_pair_f16_admitted(2, &d, &good));
      assert(!akv_pair_f16_admitted(1, NULL, &good));
      assert(!akv_pair_f16_admitted(1, &d, NULL));
      for (unsigned max_heads = 0; max_heads <= 9; ++max_heads) {
        akv_capabilities_t c = good;
        c.max_q_rows = max_heads;
        assert(akv_pair_f16_admitted(1, &d, &c) ==
               (expected && max_heads >= heads));
        ++checked;
      }
      for (unsigned format = 0; format <= 3; ++format) {
        d.element_format = format;
        assert(akv_pair_f16_admitted(1, &d, &good) ==
               (expected && format == AKV_ELEMENT_FORMAT_F16));
        ++checked;
      }
      d.element_format = AKV_ELEMENT_FORMAT_F16;
#define REJECT_WITHOUT(field) do { \
        akv_capabilities_t c = good; \
        c.field = 0; \
        assert(!akv_pair_f16_admitted(1, &d, &c)); \
        ++checked; \
      } while (0)
      REJECT_WITHOUT(valid);
      REJECT_WITHOUT(enabled);
      REJECT_WITHOUT(f16_payload);
      REJECT_WITHOUT(context_count);
      REJECT_WITHOUT(token_axis_valid);
      REJECT_WITHOUT(token_axis_enabled);
      REJECT_WITHOUT(token_axis_tail);
      REJECT_WITHOUT(token_axis_row_view);
      REJECT_WITHOUT(token_axis_column_panel4);
      REJECT_WITHOUT(token_axis_tile_tokens);
#undef REJECT_WITHOUT
      for (unsigned support = 0; support < 8; ++support) {
        akv_capabilities_t c = good;
        c.head_dim_64 = (support >> 0) & 1u;
        c.token_axis_d_axis_tail = (support >> 1) & 1u;
        c.head_dim_128 = (support >> 2) & 1u;
        const int has_dim = dim == 64 ? c.head_dim_64 :
            dim == 96 ? c.token_axis_d_axis_tail : c.head_dim_128;
        assert(akv_pair_f16_admitted(1, &d, &c) == (expected && has_dim));
        ++checked;
      }
      /* Calling another selection cannot alter this call's decision. */
      akv_descriptor_t other = d;
      other.q_rows = 1;
      assert(!akv_pair_f16_admitted(1, &other, &good));
      assert(akv_pair_f16_admitted(1, &d, &good) == expected);
      checked += 7;
    }
  }
  printf("PAIR_ADMISSION_PASS assertions=%u production_integrated=0\n", checked);
  return 0;
}
