#ifndef QBS_EXPERIMENTAL_VRF_PANEL_H
#define QBS_EXPERIMENTAL_VRF_PANEL_H

#include <stddef.h>
#include "qbs/qbs_abi.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  const qbs_descriptor_t *tile0;
  const qbs_descriptor_t *tile1;
  const void *activation;
} qbs_vrf_panel_record_t;

typedef enum {
  QBS_VRF_PANEL_OK = 0,
  QBS_VRF_PANEL_BAD_ARGUMENT = 1,
  QBS_VRF_PANEL_BAD_DESCRIPTOR = 2,
  QBS_VRF_PANEL_UNSUPPORTED = 3
} qbs_vrf_panel_status_t;

/* Experimental M4, two-tile panel. See README for memory/capability/trap
 * preconditions: this is not a fault-catching or context-sharing API. */
qbs_vrf_panel_status_t qbs_vrf_panel_run(
    const qbs_vrf_panel_record_t *records, size_t stripe_count,
    float *out0, float *out1, size_t stride_elements, size_t n0, size_t n1);

/* Full-K baseline: exactly one record, two DIRECT descriptors, K<=256.
 * Uses the same preflight, capability queries and assembly leaf as run(). */
qbs_vrf_panel_status_t qbs_vrf_panel_direct_run(
    const qbs_vrf_panel_record_t *record, float *out0, float *out1,
    size_t stride_elements, size_t n0, size_t n1);

#ifdef __cplusplus
}
#endif
#endif
