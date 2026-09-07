#ifndef QBS_FORMAT_H_
#define QBS_FORMAT_H_

#include "qbs.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  QBS_FORMAT_INVALID = 0,
  QBS_FORMAT_GROUPED_INTEGER,
  QBS_FORMAT_HIERARCHICAL_INTEGER,
  QBS_FORMAT_CODEBOOK,
} qbs_format_family_t;

qbs_format_family_t qbs_format_family(unsigned profile);

/* Little-endian consecutive packed integers, with independently strided rows.
 * scales/zero_points are [rows][K/group_elements]; scales are F32 containers.
 * Only scales exactly representable as finite F16 may use the current simple
 * profiles. A NULL zero_points array means zero, not an inferred midpoint.
 * This interface preserves decoded weights, not a foreign matmul's rounding
 * order or its activation precision. It does not perform quantization.
 */
typedef struct {
  const void *quants;
  size_t quant_bytes;
  size_t row_stride_bytes;
  const float *scales;
  size_t scale_count;
  const int16_t *zero_points;
  size_t zero_point_count;
  uint32_t rows;
  uint32_t k_elements;
  uint32_t group_elements;
  uint8_t bits;
  uint8_t signed_quants;
} qbs_grouped_integer_t;

/* Validate the entire source before publishing a plan or writing output.
 * target_profile is explicit: no silent promotion from INT4 to INT8 storage.
 * Output is canonical ROW_MAJOR, usable by qbs_repack_weight_r4().
 */
qbs_status_t qbs_grouped_integer_size(const qbs_grouped_integer_t *source,
                                     unsigned target_profile, size_t *bytes);
qbs_status_t qbs_import_grouped_integer(const qbs_grouped_integer_t *source,
                                       unsigned target_profile,
                                       void *destination, size_t bytes);

#ifdef __cplusplus
}
#endif
#endif
