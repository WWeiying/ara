#ifndef AKV_RESIDENT_FEATURES_V2_EXECUTOR_H
#define AKV_RESIDENT_FEATURES_V2_EXECUTOR_H

#include "admission.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Build the native core with AKV_EXPERIMENTAL_RESIDENT_FEATURES_V2=1 and
 * AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1; link the unchanged QK/PV leaves.
 * Both macros default OFF. Stage3 and ordinary entries cannot choose this
 * policy, including in a build enabling both experiments. Capability stays 0.
 *
 * Execute one validated Decode group. Caller preflights all groups, workspace
 * capacities/nonaliasing and memory lifetime before the first FULL, slices
 * global feature arrays to local head 0, and owns the context through RELEASE
 * across the entire call. query_position/key_position_base stay absolute.
 * Features/options/device are value-snapshotted before native work. Features
 * embed their per-head arrays; no Q/K/V/mask tensor storage is copied. Caller
 * keeps the original group-local feature objects and tensor storage immutable
 * across the whole operation, including validation of subsequent groups.
 * No multi-query or per-row-query-position semantics are admitted here.
 *
 * automatic=0 retains the existing explicit/env policy; automatic=1 retains
 * native-auto. Optional eligibility failure keeps that exact policy. Invalid
 * version/policy/feature-row metadata returns BAD_ARGUMENT; non-Decode row
 * meaning returns RUNTIME_UNAVAILABLE before execution. Platform admission and
 * whole-call ownership are required even for native fallback. Actual CSR
 * guards run only after trap-safe admission; no CSR is written. RNE, vstart=0
 * and no effective refill overlap are required for resident selection.
 * Actual entry vstart!=0 is a hard RUNTIME_UNAVAILABLE rejection before any
 * snapshot or call, even when requested=0; it cannot enter native fallback.
 * vstart remains unchanged. The caller must restore C ABI state before further
 * C execution. Other optional misses retain native fallback under valid ABI
 * state; options.vstart alone is not a substitute for the actual CSR guard.
 *
 * Existing score transforms, masks, sink initialization, tile64 online softmax,
 * F16 PV preparation and final normalization are unchanged. Masked score
 * positions do not skip QK/PV work. A later group error is terminal; never retry
 * the operation or frontend fallback over partial execution. This entry alone
 * does not establish GGML/model equivalence or performance acceptance.
 */
akv_status_t akv_experimental_attention_execute_features_v2_native(
    const akv_device_t *device, const akv_attention_plan_t *plan,
    akv_attention_v2_workspace_t *workspace,
    const akv_attention_features_t *features,
    const akv_resident_features_v2_options_t *options, unsigned automatic);

#ifdef __cplusplus
}
#endif

#endif
