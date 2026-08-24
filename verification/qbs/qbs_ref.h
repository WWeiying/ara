#ifndef ARA_VERIFICATION_QBS_REF_H_
#define ARA_VERIFICATION_QBS_REF_H_

#include <stddef.h>
#include <stdint.h>

#include "../../apps/common/qbs_abi.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef uint16_t qbs_fp16_t;

typedef struct {
  qbs_fp16_t d;
  qbs_fp16_t dmin;
  uint8_t scales[12];
  uint8_t qs[128];
} qbs_block_q4_k_t;

typedef struct {
  qbs_fp16_t d;
  qbs_fp16_t dmin;
  uint8_t scales[12];
  uint8_t qh[32];
  uint8_t qs[128];
} qbs_block_q5_k_t;

typedef struct __attribute__((packed)) {
  uint8_t ql[128];
  uint8_t qh[64];
  int8_t scales[16];
  qbs_fp16_t d;
} qbs_block_q6_k_t;

typedef struct {
  uint8_t hmask[32];
  uint8_t qs[64];
  uint8_t scales[12];
  qbs_fp16_t d;
} qbs_block_q3_k_t;

typedef struct {
  qbs_fp16_t d;
  uint8_t qs[16];
} qbs_block_q4_0_t;

typedef struct {
  float d;
  int8_t qs[256];
  int16_t bsums[16];
} qbs_block_q8_k_t;

typedef struct {
  qbs_fp16_t d;
  int8_t qs[32];
} qbs_block_q8_0_t;

typedef struct {
  float d[4];
  int8_t qs[1024];
  int16_t bsums[64];
} qbs_block_q8_kx4_t;

typedef struct {
  qbs_fp16_t d[4];
  int8_t qs[128];
} qbs_block_q8_0x4_t;

typedef enum {
  QBS_REF_OK = 0,
  QBS_REF_BAD_ARGUMENT,
  QBS_REF_DESCRIPTOR_ALIGNMENT,
  QBS_REF_DESCRIPTOR_VERSION,
  QBS_REF_DESCRIPTOR_RESERVED,
  QBS_REF_WEIGHT_PROFILE,
  QBS_REF_ACTIVATION_PROFILE,
  QBS_REF_WEIGHT_LAYOUT,
  QBS_REF_ACTIVATION_LAYOUT,
  QBS_REF_M_RANGE,
  QBS_REF_N_RANGE,
  QBS_REF_K_RANGE,
  QBS_REF_VLEN,
  QBS_REF_VD_ALIGNMENT,
  QBS_REF_BASE_ALIGNMENT,
  QBS_REF_ADDRESS_OVERFLOW,
  QBS_REF_BUFFER_SIZE,
  QBS_REF_OUTPUT_SIZE,
  QBS_REF_INTEGER_OVERFLOW,
  QBS_REF_ALLOCATION_FAILURE,
} qbs_ref_status_t;

typedef enum {
  QBS_TRACE_GROUP = 1,
  QBS_TRACE_BLOCK = 2,
} qbs_trace_kind_t;

typedef struct {
  qbs_trace_kind_t kind;
  uint8_t weight_profile;
  uint8_t context;
  uint8_t output;
  uint8_t group;
  uint16_t k_block;
  int32_t group_dot;
  int32_t group_aux;
  int32_t block_dot;
  int32_t block_aux;
  int16_t group_scale;
  int16_t group_min;
  float accumulator_before;
  float accumulator_after;
} qbs_trace_event_t;

typedef void (*qbs_trace_callback_t)(const qbs_trace_event_t *event,
                                     void *opaque);

typedef struct {
  unsigned destination_registers;
  unsigned destination_elements_per_register;
  unsigned active_outputs;
  uint32_t fflags;
} qbs_ref_result_t;

const char *qbs_ref_status_string(qbs_ref_status_t status);
float qbs_ref_fp16_to_fp32(qbs_fp16_t value);
uint64_t qbs_ref_capability_word(unsigned index, unsigned vlen_bits);

size_t qbs_ref_weight_storage_bytes(unsigned weight_profile,
                                    unsigned weight_layout, unsigned n,
                                    unsigned k_blocks);
size_t qbs_ref_activation_storage_bytes(unsigned activation_layout,
                                        unsigned m, unsigned k_blocks);
size_t qbs_ref_activation_storage_bytes_for_profile(
    unsigned activation_profile, unsigned activation_layout, unsigned m,
    unsigned k_blocks);

qbs_ref_status_t qbs_ref_validate_descriptor(
    const qbs_descriptor_v1_t *descriptor, unsigned m, unsigned vd,
    unsigned vlen_bits, uint64_t activation_base);

qbs_ref_status_t qbs_ref_repack_weight_r4(
    unsigned weight_profile, const void *row_major, size_t row_major_bytes,
    unsigned n, unsigned k_blocks, void *r4, size_t r4_bytes);

qbs_ref_status_t qbs_ref_pack_activation_m4(
    const qbs_block_q8_k_t *row_major, size_t row_major_blocks,
    unsigned k_blocks, qbs_block_q8_kx4_t *interleaved,
    size_t interleaved_blocks);
qbs_ref_status_t qbs_ref_pack_activation_m4_profile(
    unsigned activation_profile, const void *row_major,
    size_t row_major_bytes, unsigned k_blocks, void *interleaved,
    size_t interleaved_bytes);

qbs_ref_status_t qbs_ref_quantize_q8_k(const float *input,
                                       size_t input_elements,
                                       qbs_block_q8_k_t *output,
                                       size_t output_blocks);

void qbs_ref_decode_q4_k(const qbs_block_q4_k_t *block, int8_t values[256],
                         uint8_t scales[8], uint8_t mins[8]);
void qbs_ref_decode_q5_k(const qbs_block_q5_k_t *block, int8_t values[256],
                         uint8_t scales[8], uint8_t mins[8]);
void qbs_ref_decode_q6_k(const qbs_block_q6_k_t *block, int8_t values[256],
                         int8_t scales[16]);
void qbs_ref_decode_q3_k(const qbs_block_q3_k_t *block, int8_t values[256],
                         int8_t scales[16]);
void qbs_ref_decode_q8_0(const qbs_block_q8_0_t *block, int8_t values[32]);
void qbs_ref_decode_q4_0(const qbs_block_q4_0_t *block, int8_t values[32]);

qbs_ref_status_t qbs_ref_execute(
    const qbs_descriptor_v1_t *descriptor, unsigned m, unsigned vd,
    unsigned vlen_bits, uint64_t activation_base, const void *weight_data,
    size_t weight_bytes, const void *activation_data, size_t activation_bytes,
    float *destination, size_t destination_elements,
    qbs_trace_callback_t trace_callback, void *trace_opaque,
    qbs_ref_result_t *result);

#ifdef __cplusplus
}
#endif

#endif  /* ARA_VERIFICATION_QBS_REF_H_ */
