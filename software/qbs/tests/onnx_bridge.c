/* Host-only bridge: exercise the public importer/planner against the same
 * instruction reference model used by RTL/QEMU verification. Not an ORT EP.
 */
#include "qbs/qbs_format.h"
#include "../../../verification/qbs/qbs_ref.h"

#include <stdlib.h>
#include <string.h>

static qbs_status_t reference_execute(
    void *opaque, const qbs_descriptor_t *descriptor, unsigned m,
    const void *activations, float *output, size_t stride,
    unsigned n, int segmented) {
  (void)segmented;
  uint64_t *commands = opaque;
  const qbs_descriptor_fields_t f = qbs_unpack_descriptor_header(descriptor->header);
  const void *weights = (const void *)(uintptr_t)descriptor->weight_base;
  const size_t wb = qbs_ref_weight_storage_bytes(f.weight_profile, f.weight_layout, n, f.k_blocks);
  const size_t ab = qbs_ref_activation_storage_bytes_for_profile(
      f.activation_profile, f.activation_layout, m, f.k_blocks);
  float destination[QBS_MAX_M * 32u] = {0};
  qbs_ref_result_t result;
  const qbs_ref_status_t status = qbs_ref_execute(
      descriptor, m, 8u, 1024u, (uintptr_t)activations, weights, wb,
      activations, ab, destination, QBS_MAX_M * 32u, NULL, NULL, &result);
  if (status != QBS_REF_OK) return QBS_STATUS_EXECUTION;
  for (unsigned row = 0; row < m; ++row)
    memcpy(output + row * stride, destination + row * 32u, n * sizeof(float));
  ++*commands;
  return QBS_STATUS_OK;
}

static void *aligned_buffer(size_t bytes) {
  return aligned_alloc(64u, (bytes + 63u) & ~(size_t)63u);
}

unsigned qbs_onnx_test_profile(unsigned bits) {
  switch (bits) {
  case 4: return QBS_WEIGHT_PROFILE_Q4_0;
  case 5: return QBS_WEIGHT_PROFILE_Q5_0;
  case 8: return QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
  default: return QBS_WEIGHT_PROFILE_INVALID;
  }
}

int qbs_onnx_test_matmul(const qbs_grouped_integer_t *weight_source,
                         const qbs_grouped_integer_t *activation_source,
                         unsigned profile, float *output, size_t elements,
                         uint64_t *commands) {
  if (!weight_source || !activation_source || !output || !commands ||
      weight_source->k_elements != activation_source->k_elements)
    return QBS_STATUS_BAD_ARGUMENT;
  *commands = 0;
  size_t wb = 0, ab = 0;
  qbs_status_t status = qbs_grouped_integer_size(weight_source, profile, &wb);
  if (status != QBS_STATUS_OK) return status;
  status = qbs_grouped_integer_size(activation_source, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT, &ab);
  if (status != QBS_STATUS_OK) return status;
  qbs_device_t device;
  status = qbs_device_init_reference(1024u, &device);
  if (status != QBS_STATUS_OK) return status;
  const qbs_problem_t problem = {
      .weight_profile = (uint8_t)profile,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = activation_source->rows, .n = weight_source->rows,
      .k_elements = weight_source->k_elements,
  };
  qbs_plan_t plan;
  status = qbs_plan_create(&device, &problem, &plan);
  if (status != QBS_STATUS_OK) return status;
  const size_t r4_bytes = qbs_weight_storage_bytes(profile, problem.weight_layout,
                                                   problem.n, plan.k_blocks);
  void *w = aligned_buffer(wb), *a = aligned_buffer(ab), *r4 = aligned_buffer(r4_bytes);
  void *workspace = aligned_buffer(plan.workspace_bytes ? plan.workspace_bytes : 64u);
  if (!w || !a || !r4 || !workspace) {
    status = QBS_STATUS_EXECUTION;
    goto done;
  }
  status = qbs_import_grouped_integer(weight_source, profile, w, wb);
  if (status != QBS_STATUS_OK) goto done;
  status = qbs_import_grouped_integer(activation_source, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT, a, ab);
  if (status != QBS_STATUS_OK) goto done;
  status = qbs_repack_weight_r4(profile, w, wb, problem.n, plan.k_blocks, r4, r4_bytes);
  if (status != QBS_STATUS_OK) goto done;
  status = qbs_execute(&plan, r4, r4_bytes, a, ab, output, elements, problem.n,
                       workspace, plan.workspace_bytes, reference_execute, commands);
done:
  free(w); free(a); free(r4); free(workspace);
  return status;
}
