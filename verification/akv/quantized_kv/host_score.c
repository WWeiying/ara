#include "verification/qbs/qbs_ref.h"
#include <stdint.h>
#include <string.h>

/* Independent host FP execution, with real target-produced activation bytes. */
int quant_kv_host_score(unsigned kind, const unsigned char *weights,
                        const unsigned char *query, uint32_t *bits,
                        uint32_t *flags) {
  if (kind > 1 || !weights || !query || !bits || !flags) return -1;
  unsigned char w[136] __attribute__((aligned(64)));
  unsigned char a[136] __attribute__((aligned(64)));
  float destination[32] = {0};
  const size_t bytes = kind ? 72 : 136;
  memcpy(w, weights, bytes);
  memcpy(a, query, sizeof(a));
  qbs_descriptor_fields_t fields = {0};
  fields.descriptor_version = QBS_DESCRIPTOR_VERSION;
  fields.weight_profile = kind ? QBS_WEIGHT_PROFILE_Q4_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
  fields.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
  fields.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
  fields.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  fields.n = 1;
  fields.k_blocks = 4;
  fields.activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
  qbs_descriptor_t descriptor = {qbs_pack_descriptor_header(&fields), (uintptr_t)w};
  qbs_ref_result_t result = {0};
  const qbs_ref_status_t status = qbs_ref_execute(&descriptor, 1, 8, 1024,
      (uintptr_t)a, w, bytes, a, sizeof(a), destination, 32, NULL, NULL, &result);
  if (status != QBS_REF_OK) return (int)status;
  memcpy(bits, destination, sizeof(*bits));
  *flags = result.fflags;
  return 0;
}
