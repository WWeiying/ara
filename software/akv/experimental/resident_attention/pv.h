#ifndef AKV_EXPERIMENTAL_RESIDENT_PV_H
#define AKV_EXPERIMENTAL_RESIDENT_PV_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Experimental execution leaf, not runtime selection or capability discovery.
 * a0-a5: probability, accumulator, old_scale, tokens, dimensions, heads.
 * Caller admits RV64 V/Zfh/Zvfh, VLEN1024/four lanes, enabled FS/VS, vstart=0,
 * legal frm (0..4), T1..64, D64/96/128 and H1/2, and exclusively owns a valid
 * resident context with matching D and enough active V rows. Runtime admission
 * may be stricter (currently RNE only). No argument, capacity or trap probing.
 *
 * Head strides are probability=256B, accumulator=512B, old_scale=4B. Only T
 * probabilities, D accumulators and one scale per active head are accessed.
 * Caller supplies aligned, accessible, nonoverlapping input/output spans;
 * probability/old_scale remain read-only. H1 never accesses head1 memory.
 *
 * Preparation rounds scales/weights to F16, rescales F16 accumulators, then
 * PV performs token-ordered F16 FMAs. Active results replace the accumulator.
 * Existing fflags and frm are preserved; active operations may accrue flags.
 * No CSR reset, context FULL/REFILL/RELEASE, retry or final normalization.
 * Completion follows the existing dependent vector-store convention; this
 * leaf does not add a scalar memory fence or promise stores drained at return.
 *
 * Standard scalar calling convention, not the vector calling convention:
 * clobbers a0/a1/a4/a5, t0/t1, ft0/ft1, v0-v3, v8-v21, VL/VTYPE, and accrued
 * fflags. Callee-saved scalar registers and SP are preserved. Compile pv.S
 * only: it includes the byte-identical preparation successor internally.
 * Static host/object checks are not numerical or hardware acceptance.
 */
void akv_experimental_resident_pv(const float *probability,
    uint16_t *accumulator, const float *old_scale, uint32_t tokens,
    uint32_t dimensions, uint32_t heads);

/* Same contract and arithmetic, with inlined preparation and no stack frame.
 * Also clobbers t6. The original leaf remains available for paired checks. */
void akv_experimental_resident_pv_fast(const float *probability,
    uint16_t *accumulator, const float *old_scale, uint32_t tokens,
    uint32_t dimensions, uint32_t heads);

/* Same arithmetic/ABI clobbers as fast; control must match the validated tile.
 * The caller must not construct an unchecked control from user input. */
void akv_experimental_resident_pv_prepared(const float *probability,
    uint16_t *accumulator, const float *old_scale, uint32_t tokens,
    uint32_t dimensions, uint32_t heads, uint64_t control);

#ifdef __cplusplus
}
#endif

#endif
