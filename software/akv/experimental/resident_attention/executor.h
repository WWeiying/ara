#ifndef AKV_EXPERIMENTAL_RESIDENT_ATTENTION_EXECUTOR_H
#define AKV_EXPERIMENTAL_RESIDENT_ATTENTION_EXECUTOR_H

#include "admission.h"
#include "../../include/akv/akv_features.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Build akv_v2_native_riscv.c with AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1 and
 * link qk.S and pv.S. The macro defaults to zero; this symbol is absent then.
 * Existing native entry points never select resident leaves, even in an
 * enabled build. No capability/discovery or deployment default is changed.
 *
 * Executes ONE immutable Decode group plan through the existing v2 core.
 * device/options are required; platform_admitted and whole_call_owned must
 * both be 1 even when selection retains native execution. automatic must be
 * 0 (original explicit/env policy) or 1 (original native-auto policy).
 * Other failed resident admission retains that exact native policy, including
 * features and refill overlap. Prefill, segmented D256 and non-F16 plans do
 * not select resident execution. A fitting descriptor alone is not Decode.
 *
 * Caller validates all groups, stable input spans and workspace capacity/
 * nonaliasing before the first operation, and owns the context across every
 * group through RELEASE. The typed workspace retains its existing padded
 * strides. Each group's plan owns the global pointer offsets; query-base in
 * the resident leaves is local to that FULL-loaded group (0,2,4,6).
 *
 * The core validates effective features/overlap, preflights full/tail maps,
 * then reads actual vlenb/frm/vstart only after trap-safe admission. No CSR is
 * written: prior flags survive and arithmetic accrues flags. RNE is required
 * for resident selection; it is never installed by this function. Options,
 * device capabilities and automatic policy are snapshotted for this group.
 * The route is fixed before workspace mutation/FULL and never retried after
 * execution starts. Any later group error is terminal for the whole caller;
 * do not replay through native or frontend fallback after partial execution.
 * Runtime retention remains experimental pending measured whole-call benefit.
 */
akv_status_t akv_experimental_attention_execute_v2_native(
    const akv_device_t *device, const akv_attention_plan_t *plan,
    akv_attention_v2_workspace_t *workspace,
    const akv_attention_features_t *features,
    const akv_resident_attention_options_t *options, unsigned automatic);

#ifdef __cplusplus
}
#endif

#endif
