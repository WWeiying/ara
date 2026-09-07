#include "qbs/qbs_format.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void put_quant(uint8_t *p, unsigned i, unsigned bits, unsigned q) {
  for (unsigned b = 0; b < bits; ++b) {
    unsigned bit = i * bits + b;
    p[bit / 8u] |= (uint8_t)(((q >> b) & 1u) << (bit % 8u));
  }
}

static int unpack(const uint8_t *p, unsigned profile, unsigned i) {
  if (profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT)
    return p[2u + i] < 128u ? p[2u + i] : (int)p[2u + i] - 256;
  const unsigned offset = profile == QBS_WEIGHT_PROFILE_Q4_0 ? 2u : 6u;
  int q = (p[offset + i % 16u] >> (i < 16u ? 0u : 4u)) & 15u;
  if (profile == QBS_WEIGHT_PROFILE_Q5_0)
    q |= ((p[2u + i / 8u] >> (i % 8u)) & 1u) << 4;
  return q - (profile == QBS_WEIGHT_PROFILE_Q4_0 ? 8 : 16);
}

int main(void) {
  uint8_t packed[3][264], output[3 * 8 * 34], r4[4 * 8 * 34];
  float scales[24];
  int16_t zp[24];
  size_t cases = 0;
  for (unsigned bits = 2; bits <= 8; ++bits) {
    for (unsigned sign = 0; sign <= 1; ++sign) {
      for (unsigned group = 32; group <= 256; group *= 2) {
        const unsigned profile = bits <= 4 ? QBS_WEIGHT_PROFILE_Q4_0 :
            bits == 5 ? QBS_WEIGHT_PROFILE_Q5_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
        memset(packed, 0, sizeof(packed));
        for (unsigned i = 0; i < 24; ++i) {
          scales[i] = i % 2 ? -0.125f : 0.25f;
          zp[i] = sign ? 0 : (int16_t)(1u << (bits - 1u));
        }
        for (unsigned row = 0; row < 3; ++row)
          for (unsigned k = 0; k < 256; ++k)
            put_quant(packed[row], k, bits, (k + row) & ((1u << bits) - 1u));
        qbs_grouped_integer_t source = {
            .quants = packed, .quant_bytes = sizeof(packed),
            .row_stride_bytes = sizeof(packed[0]), .scales = scales,
            .scale_count = 24, .zero_points = zp, .zero_point_count = 24,
            .rows = 3, .k_elements = 256, .group_elements = group,
            .bits = bits, .signed_quants = sign};
        size_t bytes = 0;
        assert(qbs_grouped_integer_size(&source, profile, &bytes) == QBS_STATUS_OK);
        assert(bytes == 3u * 8u * qbs_weight_block_bytes(profile));
        assert(qbs_import_grouped_integer(&source, profile, output, sizeof(output)) == QBS_STATUS_OK);
        for (unsigned row = 0; row < 3; ++row) {
          for (unsigned k = 0; k < 256; ++k) {
            int q = (k + row) & ((1u << bits) - 1u);
            if (sign && (unsigned)q >= (1u << (bits - 1u))) q -= (1u << bits);
            if (!sign) q -= (1u << (bits - 1u));
            const uint8_t *block = output +
                (row * 8u + k / 32u) * qbs_weight_block_bytes(profile);
            assert(unpack(block, profile, k % 32u) == q);
            assert(block[0] == 0);
            assert(block[1] == ((row * (256u / group) + k / group) % 2u ? 0xb0 : 0x34));
          }
        }
        assert(qbs_repack_weight_r4(profile, output, bytes, 3, 8, r4, sizeof(r4)) == QBS_STATUS_OK);
        memset(output, 0xa5, sizeof(output));
        scales[0] = 0.1f;
        assert(qbs_import_grouped_integer(&source, profile, output, sizeof(output)) == QBS_STATUS_NUMERICAL_CONTRACT);
        for (size_t i = 0; i < sizeof(output); ++i) assert(output[i] == 0xa5);
        scales[0] = 0x1p-24f;
        assert(qbs_import_grouped_integer(&source, profile, output, sizeof(output)) == QBS_STATUS_OK);
        assert(output[0] == 1 && output[1] == 0);
        source.quant_bytes = 1;
        assert(qbs_import_grouped_integer(&source, profile, output, sizeof(output)) == QBS_STATUS_BUFFER_TOO_SMALL);
        source.quant_bytes = sizeof(packed);
        source.group_elements = 16;
        assert(qbs_grouped_integer_size(&source, profile, &bytes) == QBS_STATUS_SHAPE);
        ++cases;
      }
    }
  }
  assert(qbs_format_family(QBS_WEIGHT_PROFILE_Q4_K) == QBS_FORMAT_HIERARCHICAL_INTEGER);
  assert(qbs_format_family(QBS_WEIGHT_PROFILE_IQ4_NL) == QBS_FORMAT_CODEBOOK);
  assert(qbs_format_family(0) == QBS_FORMAT_INVALID);
  memset(packed, 100, sizeof(packed));
  scales[0] = 1.0f;
  qbs_grouped_integer_t edge = {
      .quants = packed, .quant_bytes = 32, .row_stride_bytes = 32,
      .scales = scales, .scale_count = 1, .rows = 1,
      .k_elements = 32, .group_elements = 32, .bits = 8, .signed_quants = 1};
  memset(output, 0xa5, sizeof(output));
  assert(qbs_import_grouped_integer(&edge, QBS_WEIGHT_PROFILE_Q4_0,
                                    output, sizeof(output)) == QBS_STATUS_NUMERICAL_CONTRACT);
  assert(qbs_import_grouped_integer(&edge, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                                    output, 33) == QBS_STATUS_BUFFER_TOO_SMALL);
  for (size_t i = 0; i < sizeof(output); ++i) assert(output[i] == 0xa5);
  assert(qbs_import_grouped_integer(&edge, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                                    packed, sizeof(packed)) == QBS_STATUS_BAD_ARGUMENT);
  assert(packed[0][0] == 100);
  assert(qbs_import_grouped_integer(&edge, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                                    scales, sizeof(scales)) == QBS_STATUS_BAD_ARGUMENT);
  assert(scales[0] == 1.0f);
  assert(qbs_import_grouped_integer(&edge, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                                    output, sizeof(output)) == QBS_STATUS_OK);
  assert(output[2] == 100);
  printf("QBS exact grouped-integer conversion: %zu combinations PASS\n", cases);
  return 0;
}
