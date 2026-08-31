#ifndef QBS_RUNTIME_H_
#define QBS_RUNTIME_H_

#include "qbs_abi.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  QBS_STATUS_OK = 0,
  QBS_STATUS_BAD_ARGUMENT,
  QBS_STATUS_SIZE_OVERFLOW,
  QBS_STATUS_BUFFER_TOO_SMALL,
  QBS_STATUS_BUFFER_ALIGNMENT,
  QBS_STATUS_RUNTIME_UNAVAILABLE,
  QBS_STATUS_ABI_MISMATCH,
  QBS_STATUS_NUMERICAL_CONTRACT,
  QBS_STATUS_CAPABILITY,
  QBS_STATUS_PROFILE,
  QBS_STATUS_PROFILE_PAIR,
  QBS_STATUS_LAYOUT,
  QBS_STATUS_SHAPE,
  QBS_STATUS_CONTEXT_UNSUPPORTED,
  QBS_STATUS_CONTEXT_TOKEN,
  QBS_STATUS_EXECUTION,
} qbs_status_t;

typedef enum {
  QBS_ACTIVATION_STORAGE_INVALID = 0,
  QBS_ACTIVATION_STORAGE_ROW_MAJOR = 1,
  /* Complete groups of four are M4-interleaved. A final 1--3-row tail is
     stored row-major at the same logical row offset. */
  QBS_ACTIVATION_STORAGE_M4_GROUPED = 2,
} qbs_activation_storage_t;

typedef struct {
  uint8_t id;
  uint16_t block_bytes;
  uint16_t block_elements;
  uint8_t subgroup_count;
  uint8_t subgroup_elements;
  uint8_t scale_format;
  uint8_t correction_mode;
  uint16_t compatible_activation_profiles;
} qbs_weight_profile_info_t;

typedef struct {
  uint8_t id;
  uint16_t block_bytes;
  uint16_t block_elements;
  uint8_t scale_format;
  uint8_t scale_bytes;
  uint16_t quant_bytes;
  uint8_t aux_count;
  uint8_t aux_element_bytes;
} qbs_activation_profile_info_t;

typedef struct {
  uint8_t valid;
  uint8_t architecture_version;
  uint8_t descriptor_version;
  uint8_t descriptor_bytes;
  uint8_t numerical_contract_version;
  uint8_t max_m;
  uint8_t max_n;
  uint16_t max_k_blocks;
  uint16_t weight_layouts;
  uint16_t activation_layouts;
  uint8_t descriptor_alignment_log2;
  uint8_t weight_alignment_log2;
  uint8_t activation_alignment_log2;
  uint8_t result_element_bits;
  uint8_t blocking_completion;
  uint8_t fault_atomic_destination;
  uint8_t requires_vstart_zero;
  uint8_t idempotent_memory_only;
  uint8_t requires_accelerator_consistency;
  uint8_t activation_context_count;
  uint8_t activation_context_max_m;
  uint8_t activation_context_max_k_blocks;
  uint8_t activation_context_generation_bits;
  uint8_t activation_context_access_modes;
  uint16_t activation_context_profiles;
  uint16_t activation_context_layouts;
} qbs_capabilities_t;

typedef struct {
  qbs_capabilities_t capabilities;
  uint16_t weight_profiles;
  uint16_t activation_profiles;
  uint16_t compatible_activation_profiles[16];
} qbs_device_t;

/* Frameworks identify an exact, versioned byte/numerical encoding. The common
   runtime resolves it to this device's compact hardware profile IDs. */
typedef struct {
  uint64_t weight_encoding_id;
  uint64_t activation_encoding_id;
  uint8_t weight_profile;
  uint8_t activation_profile;
} qbs_profile_binding_t;

typedef uint64_t (*qbs_info_reader_t)(void *context, unsigned index);

typedef struct {
  uint8_t weight_profile;
  uint8_t activation_profile;
  uint8_t weight_layout;
  uint8_t activation_storage;
  uint32_t m;
  uint32_t n;
  uint32_t k_elements;
} qbs_problem_t;

typedef struct {
  qbs_problem_t problem;
  uint16_t k_blocks;
  uint16_t command_k_blocks;
  uint8_t command_m;
  uint8_t command_n;
  uint8_t split_k;
  uint8_t needs_activation_gather;
  uint8_t activation_context_eligible;
  uint8_t activation_context_count;
  uint8_t activation_context_generation_bits;
  size_t workspace_bytes;
} qbs_plan_t;

typedef struct {
  uint8_t context_id;
  uint8_t generation;
} qbs_activation_context_token_t;

typedef enum {
  /* Preserve the original per-execution FILL ... RELEASE behavior. */
  QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION = 0,
  /* Fill a new logical activation and leave it resident after this call. */
  QBS_ACTIVATION_CONTEXT_SCOPE_FILL_KEEP = 1,
  /* Reuse an already resident activation and leave it resident. */
  QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_KEEP = 2,
  /* Reuse an already resident activation and release it on the final tile. */
  QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_RELEASE = 3,
} qbs_activation_context_scope_t;

typedef struct {
  uint8_t use_activation_context;
  qbs_activation_context_token_t activation_context;
  uint8_t activation_context_scope;
} qbs_execution_options_t;

typedef struct {
  uint32_t input_start;
  uint32_t output_start;
  uint16_t k_block_start;
  uint16_t k_blocks;
  uint8_t m;
  uint8_t n;
  uint8_t activation_layout;
  uint8_t accumulate;
  uint8_t gather_activation;
  size_t weight_offset_bytes;
  size_t activation_offset_bytes;
  size_t output_offset_elements;
} qbs_command_t;

typedef struct {
  uint32_t input_start;
  uint32_t output_start;
  uint16_t k_block_start;
  uint8_t done;
} qbs_plan_cursor_t;

typedef qbs_status_t (*qbs_command_executor_t)(
    void *context, const qbs_descriptor_t *descriptor, unsigned m,
    const void *activations, float *output, size_t output_stride_elements,
    unsigned n, int segmented);

const char *qbs_status_string(qbs_status_t status);

qbs_status_t qbs_weight_profile_info(unsigned profile,
                                     qbs_weight_profile_info_t *info);
qbs_status_t qbs_activation_profile_info(
    unsigned profile, qbs_activation_profile_info_t *info);

qbs_status_t qbs_capabilities_decode(uint64_t info0, uint64_t info1,
                                     qbs_capabilities_t *capabilities);
qbs_status_t qbs_device_query(qbs_info_reader_t reader, void *context,
                              qbs_device_t *device);
qbs_status_t qbs_device_init_reference(unsigned vlen_bits,
                                       qbs_device_t *device);
int qbs_device_supports_profile(const qbs_device_t *device,
                                unsigned weight_profile,
                                unsigned activation_profile);
/* This is exact matching, not geometry matching. Unknown encodings require an
   adapter-owned validated conversion or ordinary fallback. */
qbs_status_t qbs_device_bind_encodings(
    const qbs_device_t *device, uint64_t weight_encoding_id,
    uint64_t activation_encoding_id, qbs_profile_binding_t *binding);

size_t qbs_weight_storage_bytes(unsigned weight_profile,
                                unsigned weight_layout, size_t n,
                                size_t k_blocks);
size_t qbs_activation_storage_bytes(unsigned activation_profile,
                                    unsigned activation_storage, size_t m,
                                    size_t k_blocks);

/* Byte arguments are buffer capacities. Source and destination storage must
   not overlap; R4 padding is initialized but is never a logical output row. */
qbs_status_t qbs_repack_weight_r4(unsigned weight_profile,
                                  const void *row_major,
                                  size_t row_major_bytes, size_t n,
                                  size_t k_blocks, void *r4,
                                  size_t r4_bytes);
/* Packs exactly four complete row-major activation rows. A runtime appends a
   final 1--3-row tail unchanged, as specified by M4_GROUPED storage. */
qbs_status_t qbs_pack_activation_m4(unsigned activation_profile,
                                    const void *row_major,
                                    size_t row_major_bytes, size_t k_blocks,
                                    void *interleaved,
                                    size_t interleaved_bytes);

/* A successful plan is immutable and may be reused for the same device
   contract and logical problem. Only qbs_plan_create may initialize it. */
qbs_status_t qbs_plan_create(const qbs_device_t *device,
                             const qbs_problem_t *problem,
                             qbs_plan_t *plan);
void qbs_plan_cursor_reset(qbs_plan_cursor_t *cursor);
qbs_status_t qbs_plan_next(const qbs_plan_t *plan,
                           qbs_plan_cursor_t *cursor,
                           qbs_command_t *command, int *has_command);
int qbs_plan_supports_activation_context(const qbs_plan_t *plan);

/* workspace may be NULL only when plan->workspace_bytes is zero. All buffers
   and the plan must remain valid until the blocking executor returns. */
qbs_status_t qbs_execute(const qbs_plan_t *plan, const void *weights,
                         size_t weights_bytes, const void *activations,
                         size_t activations_bytes, float *output,
                         size_t output_capacity_elements,
                         size_t output_stride_elements, void *workspace,
                         size_t workspace_bytes,
                         qbs_command_executor_t executor,
                         void *executor_context);

/* Context reuse is explicit: the caller owns token generation and must not
   reuse a generation for a different logical activation. OPERATION preserves
   the original per-call FILL ... RELEASE scope. The KEEP scopes allow a
   serialized adapter to span one activation across multiple calls; that
   adapter must eventually use REUSE_RELEASE or supersede the generation with
   a new FILL. Unsupported plans return CONTEXT_UNSUPPORTED; qbs_execute()
   remains the always-DIRECT fallback. */
qbs_status_t qbs_execute_with_options(
    const qbs_plan_t *plan, const void *weights, size_t weights_bytes,
    const void *activations, size_t activations_bytes, float *output,
    size_t output_capacity_elements, size_t output_stride_elements,
    void *workspace, size_t workspace_bytes,
    const qbs_execution_options_t *options,
    qbs_command_executor_t executor, void *executor_context);

/* Native helpers do not probe extension presence. Callers must establish that
   Xaraqbs is available before executing qbs_native_info(). */
uint64_t qbs_native_info(void *context, unsigned index);
qbs_status_t qbs_native_execute_command(
    void *context, const qbs_descriptor_t *descriptor, unsigned m,
    const void *activations, float *output, size_t output_stride_elements,
    unsigned n, int segmented);

#ifdef __cplusplus
}
#endif

#endif  /* QBS_RUNTIME_H_ */
